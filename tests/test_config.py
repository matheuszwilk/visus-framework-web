from dataclasses import FrozenInstanceError

import pytest
from visus.web.config import Defaults


def test_default_values():
    d = Defaults()
    assert d.action_timeout_ms == 30_000
    assert d.navigation_timeout_ms == 30_000
    assert d.expect_timeout_ms == 5_000


def test_is_frozen():
    d = Defaults()
    with pytest.raises(FrozenInstanceError):
        d.action_timeout_ms = 1  # type: ignore[misc]
