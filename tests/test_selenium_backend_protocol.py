from visus.web.backends.base import Backend
from visus.web.backends.selenium_backend import SeleniumBackend


def test_backend_conforms_to_protocol():
    assert isinstance(SeleniumBackend(), Backend)
