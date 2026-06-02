"""Public exception hierarchy. No selenium.* type ever escapes through these."""

from __future__ import annotations


class VisusWebError(Exception):
    """Base class for all visus.web errors."""


class UnsupportedEngineError(VisusWebError):
    """Raised when an engine is requested that the backend cannot drive."""


class VisusTimeoutError(VisusWebError):
    """Raised when an operation exceeds its deadline."""


class NavigationError(VisusWebError):
    """Raised when a navigation fails."""


class TargetClosedError(VisusWebError):
    """Raised when operating on a page/context/browser that is already closed."""
