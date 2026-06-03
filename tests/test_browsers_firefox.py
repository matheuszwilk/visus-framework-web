"""Unit tests for the Firefox browser plug-in.

These tests only exercise option/service construction — no Firefox launch occurs
because Firefox is not installed in this environment.
"""

from visus.web.backends.browsers import firefox
from visus.web.engine import Engine
from visus.web.registry import get_browser_config


def test_options_headless_adds_flag(tmp_path):
    opts = firefox.build_options(
        headless=True, download_dir=str(tmp_path), user_data_dir=str(tmp_path / "p")
    )
    assert "-headless" in opts.arguments


def test_options_headed_omits_headless(tmp_path):
    opts = firefox.build_options(
        headless=False, download_dir=str(tmp_path), user_data_dir=str(tmp_path / "p")
    )
    assert "-headless" not in opts.arguments


def test_options_download_dir_preference(tmp_path):
    dl_dir = str(tmp_path / "downloads")
    opts = firefox.build_options(
        headless=True, download_dir=dl_dir, user_data_dir=str(tmp_path / "p")
    )
    # Firefox Options stores prefs in opts.preferences dict
    prefs = opts.preferences
    assert prefs.get("browser.download.dir") == dl_dir


def test_options_pdfjs_disabled(tmp_path):
    opts = firefox.build_options(
        headless=False, download_dir=str(tmp_path), user_data_dir=str(tmp_path / "p")
    )
    assert opts.preferences.get("pdfjs.disabled") is True


def test_options_download_prefs_set(tmp_path):
    opts = firefox.build_options(
        headless=False, download_dir=str(tmp_path), user_data_dir=str(tmp_path / "p")
    )
    prefs = opts.preferences
    assert prefs.get("browser.download.folderList") == 2
    assert prefs.get("browser.download.useDownloadDir") is True
    assert "application/pdf" in prefs.get("browser.helperApps.neverAskSaveToDisk", "")


def test_service_factory_returns_service():
    svc = firefox.build_service()
    assert hasattr(svc, "path")


def test_registry_firefox_config_present():
    cfg = get_browser_config(Engine.FIREFOX)
    assert cfg.engine is Engine.FIREFOX
    assert callable(cfg.options_factory)
    assert callable(cfg.driver_factory)
