from visus.web.backends.browsers import edge
from visus.web.engine import Engine
from visus.web.registry import get_browser_config


def test_options_headless_adds_flag(tmp_path):
    opts = edge.build_options(
        headless=True, download_dir=str(tmp_path), user_data_dir=str(tmp_path / "p")
    )
    args = opts.arguments
    assert "--headless=new" in args
    assert any(a.startswith("--user-data-dir=") for a in args)


def test_options_headed_omits_headless(tmp_path):
    opts = edge.build_options(
        headless=False, download_dir=str(tmp_path), user_data_dir=str(tmp_path / "p")
    )
    assert "--headless=new" not in opts.arguments


def test_service_factory_returns_service():
    svc = edge.build_service()
    assert hasattr(svc, "path")


def test_registry_edge_config_present():
    cfg = get_browser_config(Engine.EDGE)
    assert cfg.engine is Engine.EDGE
    assert callable(cfg.options_factory)
    assert callable(cfg.driver_factory)
