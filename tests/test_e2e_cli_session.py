"""End-to-end cross-process test of the persistent CLI session.

Proves the daemon truly runs in a SEPARATE process: ``start_daemon`` spawns a
detached ``python -m visus.web.cli.session_server``, the test sends JSON ops over
the socket (list_fields → fill → click → get_text), then ``stop`` shuts it down
and we assert the process exited and the session file was cleaned up.

Everything is isolated under ``tmp_path`` so no ``.visus`` leaks into the repo.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from visus.web.cli import session_client

# A self-contained page (no fixture server needed) with a top input + a button.
_PAGE = (
    "data:text/html,"
    "<input id='name' placeholder='name'>"
    "<button id='go' onclick=\"document.getElementById('name').value='clicked'\">Go</button>"
)


def _pid_alive(pid: int) -> bool:
    return session_client._pid_alive(pid)


@pytest.mark.browser
def test_cross_process_daemon_full_cycle(tmp_path: Path) -> None:
    transcript: list[str] = []

    # No session yet under this isolated cwd.
    assert session_client.find_session(tmp_path) is None
    transcript.append("pre: no session")

    # 1) Spawn the DETACHED daemon in a separate process.
    info = session_client.start_daemon("chrome", headless=True, url=_PAGE, cwd=tmp_path)
    pid = int(info["pid"])
    port = int(info["port"])
    transcript.append(f"started daemon pid={pid} port={port} (this process pid={os.getpid()})")
    assert pid != os.getpid()  # genuinely a different process
    assert _pid_alive(pid)
    sf = tmp_path / ".visus" / "session.json"
    assert sf.is_file()

    try:
        # 2) Cross-process op: list_fields over the socket.
        result = session_client.send("list_fields", {"highlight": False}, start_dir=tmp_path)
        fields = result["fields"]
        locs = [f["locator"] for f in fields]
        transcript.append(f"list_fields -> {locs}")
        assert any(loc == "#name" for loc in locs)
        assert any(loc == "#go" for loc in locs)

        name_idx = next(f["index"] for f in fields if f["locator"] == "#name")
        go_idx = next(f["index"] for f in fields if f["locator"] == "#go")

        # 3) fill by index (re-resolved from the daemon's cached field).
        r = session_client.send("fill", {"index": name_idx, "text": "Ada"}, start_dir=tmp_path)
        transcript.append(f"fill[{name_idx}]='Ada' -> {r}")
        assert r == "filled with 'Ada'"
        assert session_client.send(
            "get_text", {"selector": "#name"}, start_dir=tmp_path
        ) is not None  # input has no text content but call succeeds

        # 4) click the button by index → its onclick sets #name to 'clicked'.
        r = session_client.send("click", {"index": go_idx}, start_dir=tmp_path)
        transcript.append(f"click[{go_idx}] -> {r}")
        assert r == "clicked"

        # 5) status reflects the live page from the OTHER process.
        st = session_client.status(start_dir=tmp_path)
        transcript.append(f"status -> running={st.get('running')} url={st.get('url', '')[:24]!r}")
        assert st is not None and st.get("running") is True
    finally:
        # 6) Stop the daemon and prove the process and file are gone.
        msg = session_client.stop(start_dir=tmp_path)
        transcript.append(f"stop -> {msg}")

    # Wait for the OS to reap the detached process.
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.2)
    transcript.append(f"post-stop: pid_alive={_pid_alive(pid)} session_file_exists={sf.is_file()}")

    print("\n--- CROSS-PROCESS TRANSCRIPT ---\n" + "\n".join(transcript))

    assert not _pid_alive(pid), "daemon process did not exit after stop"
    assert not sf.is_file(), "session.json was not cleaned up after stop"


@pytest.mark.browser
def test_cross_process_start_refuses_duplicate(tmp_path: Path) -> None:
    info = session_client.start_daemon("chrome", headless=True, url=_PAGE, cwd=tmp_path)
    try:
        with pytest.raises(session_client.SessionError, match="already running"):
            session_client.start_daemon("chrome", headless=True, url=_PAGE, cwd=tmp_path)
    finally:
        session_client.stop(start_dir=tmp_path)
    pid = int(info["pid"])
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.2)
    assert not _pid_alive(pid)
