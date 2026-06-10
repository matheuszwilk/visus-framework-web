import os
import tempfile

from visus.web.backends.base import Backend, BrowserConfig
from visus.web.backends.selenium_backend import SeleniumBackend, SeleniumBrowserDelegate
from visus.web.engine import Engine


def test_backend_conforms_to_protocol():
    assert isinstance(SeleniumBackend(), Backend)


class _FakeDriver:
    """Minimal stand-in for a WebDriver — no real browser, just lifecycle hooks."""

    def __init__(self) -> None:
        self.quit_calls = 0

    @property
    def current_window_handle(self) -> str:
        return "win-1"

    def quit(self) -> None:
        self.quit_calls += 1


def _fake_config() -> BrowserConfig:
    return BrowserConfig(
        engine=Engine.CHROME,
        options_factory=lambda **k: None,
        service_factory=lambda: None,
        driver_factory=lambda **k: _FakeDriver(),
    )


def test_dispose_removes_both_temp_dirs_and_is_idempotent():
    profile_dir = tempfile.mkdtemp(prefix="visus-web-test-")
    download_dir = tempfile.mkdtemp(prefix="visus-dl-test-")
    driver = _FakeDriver()
    delegate = SeleniumBrowserDelegate(
        driver, profile_dir, download_dir, config=_fake_config(), headless=True
    )

    assert os.path.isdir(profile_dir)
    assert os.path.isdir(download_dir)

    delegate.dispose()

    assert not os.path.exists(profile_dir)
    assert not os.path.exists(download_dir)  # guards against the download-dir leak
    assert driver.quit_calls == 1

    # idempotent: a second dispose must be a no-op
    delegate.dispose()
    assert driver.quit_calls == 1


class _SpawnableFakeDriver(_FakeDriver):
    @property
    def window_handles(self):
        return ["win-1"]

    def execute_cdp_cmd(self, cmd, params):
        raise AttributeError("no CDP on fake driver")


def test_launch_with_user_data_dir_uses_and_preserves_it(tmp_path):
    captured = {}

    def opts(*, headless, download_dir, user_data_dir):
        captured["user_data_dir"] = user_data_dir
        return None

    cfg = BrowserConfig(
        engine=Engine.CHROME,
        options_factory=opts,
        service_factory=lambda: None,
        driver_factory=lambda **k: _SpawnableFakeDriver(),
    )
    profile = tmp_path / "my-profile"
    delegate = SeleniumBackend().launch(cfg, headless=True, user_data_dir=str(profile))
    assert captured["user_data_dir"] == str(profile)
    assert profile.is_dir()  # created on demand
    delegate.dispose()
    assert profile.is_dir()  # NEVER deleted: it is the user's persistent profile


def test_launch_with_remote_url_uses_remote_webdriver(monkeypatch):
    created = {}

    class FakeRemote(_SpawnableFakeDriver):
        def __init__(self, *, command_executor, options):
            super().__init__()
            created["url"] = command_executor

    import visus.web.backends.selenium_backend as sb

    monkeypatch.setattr(sb.webdriver, "Remote", FakeRemote)

    def fail_factory(**k):
        raise AssertionError("local driver_factory must not be used for remote")

    cfg = BrowserConfig(
        engine=Engine.CHROME,
        options_factory=lambda **k: None,
        service_factory=lambda: None,
        driver_factory=fail_factory,
    )
    delegate = SeleniumBackend().launch(cfg, headless=True, remote_url="http://grid:4444/wd/hub")
    assert created["url"] == "http://grid:4444/wd/hub"
    delegate.dispose()


def test_cleanup_respects_owns_profile(tmp_path):
    import weakref

    from visus.web.backends.selenium_backend import _cleanup

    class _D:
        def __init__(self):
            self.quit_calls = 0

        def quit(self):
            self.quit_calls += 1

    d = _D()
    profile = tmp_path / "profile"
    profile.mkdir()
    dl = tmp_path / "dl"
    dl.mkdir()
    _cleanup(weakref.ref(d), str(profile), str(dl), False)
    assert d.quit_calls == 1
    assert profile.is_dir()  # user-owned profile preserved
    assert not dl.exists()  # temp download dir removed

    dl.mkdir()
    _cleanup(weakref.ref(d), str(profile), str(dl), True)
    assert not profile.exists()
    assert not dl.exists()
