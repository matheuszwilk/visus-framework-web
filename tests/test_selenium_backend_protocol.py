import os
import tempfile

from visus.web.backends.base import Backend
from visus.web.backends.selenium_backend import SeleniumBackend, SeleniumBrowserDelegate


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


def test_dispose_removes_both_temp_dirs_and_is_idempotent():
    profile_dir = tempfile.mkdtemp(prefix="visus-web-test-")
    download_dir = tempfile.mkdtemp(prefix="visus-dl-test-")
    driver = _FakeDriver()
    delegate = SeleniumBrowserDelegate(driver, profile_dir, download_dir)

    assert os.path.isdir(profile_dir)
    assert os.path.isdir(download_dir)

    delegate.dispose()

    assert not os.path.exists(profile_dir)
    assert not os.path.exists(download_dir)  # guards against the download-dir leak
    assert driver.quit_calls == 1

    # idempotent: a second dispose must be a no-op
    delegate.dispose()
    assert driver.quit_calls == 1
