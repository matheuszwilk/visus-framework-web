from selenium.common.exceptions import (
    NoSuchWindowException,
    TimeoutException,
    WebDriverException,
)
from visus.web import errors
from visus.web.backends.selenium.driver_delegate import translate_exc


def test_timeout_maps_to_visus_timeout():
    assert isinstance(translate_exc(TimeoutException("t")), errors.VisusTimeoutError)


def test_closed_window_maps_to_target_closed():
    assert isinstance(translate_exc(NoSuchWindowException("w")), errors.TargetClosedError)


def test_generic_webdriver_maps_to_base():
    out = translate_exc(WebDriverException("x"))
    assert isinstance(out, errors.VisusWebError)
    assert not isinstance(out, (errors.VisusTimeoutError, errors.TargetClosedError))
