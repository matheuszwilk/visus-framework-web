from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Defaults:
    """Default timeouts in milliseconds (matches BotCity/Playwright conventions)."""

    action_timeout_ms: int = 30_000
    navigation_timeout_ms: int = 30_000
    expect_timeout_ms: int = 5_000
    slow_mo_ms: int = 0  # delay before each action/navigation (debug/demo aid)
