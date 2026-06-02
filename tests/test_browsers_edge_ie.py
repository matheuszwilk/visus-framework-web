from visus.web.backends.browsers import edge_ie
from visus.web.engine import Engine
from visus.web.registry import get_browser_config


def test_options_returns_ie_options(tmp_path):
    """build_options always returns an IE Options instance (IE-mode is always headed)."""
    from selenium.webdriver.ie.options import Options

    opts = edge_ie.build_options(
        headless=True, download_dir=str(tmp_path), user_data_dir=str(tmp_path / "p")
    )
    assert isinstance(opts, Options)


def test_options_headless_ignored(tmp_path):
    """IE-mode ignores headless; both headed and headless calls succeed identically."""
    opts_headed = edge_ie.build_options(
        headless=False, download_dir=str(tmp_path), user_data_dir=str(tmp_path / "p")
    )
    opts_headless = edge_ie.build_options(
        headless=True, download_dir=str(tmp_path), user_data_dir=str(tmp_path / "p")
    )
    # Both must have attach_to_edge_chrome set to True
    assert opts_headed.attach_to_edge_chrome is True  # type: ignore[attr-defined]
    assert opts_headless.attach_to_edge_chrome is True  # type: ignore[attr-defined]


def test_options_sets_edge_chrome_mode(tmp_path):
    """build_options sets the IE-mode flags needed to run under Edge."""
    opts = edge_ie.build_options(
        headless=False, download_dir=str(tmp_path), user_data_dir=str(tmp_path / "p")
    )
    assert opts.attach_to_edge_chrome is True  # type: ignore[attr-defined]
    assert opts.ignore_zoom_level is True  # type: ignore[attr-defined]
    assert opts.ignore_protected_mode_settings is True  # type: ignore[attr-defined]


def test_service_factory_returns_service():
    from selenium.webdriver.ie.service import Service

    svc = edge_ie.build_service()
    assert isinstance(svc, Service)
    assert hasattr(svc, "path")


def test_registry_edge_ie_config_present():
    cfg = get_browser_config(Engine.EDGE_IE)
    assert cfg.engine is Engine.EDGE_IE
    assert callable(cfg.options_factory)
    assert callable(cfg.driver_factory)
