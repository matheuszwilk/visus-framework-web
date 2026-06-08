"""IE-mode preflight: align the Windows registry so IEDriverServer can drive Edge in
IE mode instead of hanging at session creation.

Edge IE mode (driven by IEDriverServer with ``attach_to_edge_chrome``) blocks in
``webdriver.Ie(...)`` — the Edge window opens but the page never loads — when either:

1. Edge's ``InternetExplorerIntegrationLevel`` policy does not enable IE mode, so the page
   renders in Chromium and the Trident document the driver waits for never appears; or
2. IE Protected Mode (zone value ``2500``) differs across security zones 0..4.

This module fixes what a non-admin process can fix (the IE zones, under HKCU) and makes a
best-effort attempt to enable the Edge policy (succeeds only when the process can write the
policy hive, e.g. running elevated). It deliberately does NOT decide on its own that IE mode
is impossible — the caller launches and lets a watchdog surface a clear error if it hangs,
so a machine where IE mode is enabled by some other means is never wrongly blocked.
"""

from __future__ import annotations

import sys
from types import ModuleType

_ZONES = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings\Zones"
_EDGE_POLICY = r"SOFTWARE\Policies\Microsoft\Edge"
_LEVEL = "InternetExplorerIntegrationLevel"
_RELOAD = "InternetExplorerIntegrationReloadInIEModeAllowed"
# 2500 = "Turn on Protected Mode": 0 = on, 3 = off. The value is irrelevant to IEDriver as
# long as it is IDENTICAL across zones 0..4; we equalize to 3 (off), matching automation.
_PROTECTED_MODE = 3


def ensure() -> None:
    """Best-effort registry alignment for Edge IE mode (no-op off Windows).

    Equalizes the IE security zones (no admin) and tries to enable the Edge IE-mode policy
    (succeeds only if this process can write the policy hive). Never raises: if IE mode still
    cannot start, the caller's launch watchdog surfaces a clear, actionable error.
    """
    if sys.platform != "win32":
        return
    import winreg

    _equalize_protected_mode(winreg)
    _try_enable_ie_mode(winreg)


def ie_mode_enabled() -> bool:
    """True if Edge's IE-mode integration policy is enabled (HKLM or HKCU)."""
    if sys.platform != "win32":
        return False
    import winreg

    return any(
        _read_dword(winreg, hive, _EDGE_POLICY, _LEVEL) in (1, 2)
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
    )


def admin_hint() -> str:
    """The exact elevated commands that enable Edge IE mode, for an actionable error."""
    return (
        "IE mode is not enabled in Edge. Open an Administrator terminal, run these two "
        "commands once, then restart Edge:\n"
        f'  reg add "HKLM\\{_EDGE_POLICY}" /v {_LEVEL} /t REG_DWORD /d 1 /f\n'
        f'  reg add "HKLM\\{_EDGE_POLICY}" /v {_RELOAD} /t REG_DWORD /d 1 /f\n'
        "(Or run the app as Administrator once to configure this automatically.)"
    )


def _equalize_protected_mode(reg: ModuleType) -> None:
    """Set zone value ``2500`` to the same value across security zones 0..4 (HKCU; no admin)."""
    for zone in range(5):
        try:
            key = reg.CreateKeyEx(
                reg.HKEY_CURRENT_USER, rf"{_ZONES}\{zone}", 0, reg.KEY_READ | reg.KEY_SET_VALUE
            )
        except OSError:
            continue  # zone not writable: leave it; the equality check may still pass
        try:
            try:
                current, _ = reg.QueryValueEx(key, "2500")
            except FileNotFoundError:
                current = None
            if current != _PROTECTED_MODE:
                reg.SetValueEx(key, "2500", 0, reg.REG_DWORD, _PROTECTED_MODE)
        finally:
            reg.CloseKey(key)


def _read_dword(reg: ModuleType, hive: int, path: str, name: str) -> int | None:
    try:
        key = reg.OpenKey(hive, path)
    except OSError:
        return None
    try:
        value, _ = reg.QueryValueEx(key, name)
        return int(value)
    except (FileNotFoundError, ValueError, TypeError):
        return None
    finally:
        reg.CloseKey(key)


def _try_enable_ie_mode(reg: ModuleType) -> None:
    """Enable the Edge IE-mode policy if possible. Best-effort: stays silent when the policy
    hive is not writable (the launch watchdog will report the admin step if needed)."""
    # 1 = IE mode, 2 = IE11 — either value already enables IE-mode integration.
    for hive in (reg.HKEY_LOCAL_MACHINE, reg.HKEY_CURRENT_USER):
        if _read_dword(reg, hive, _EDGE_POLICY, _LEVEL) in (1, 2):
            return

    # Not enabled: try to set it. Succeeds only if this process can write the policy hive
    # (e.g. running as Administrator). HKLM first (machine-wide), then HKCU.
    for hive in (reg.HKEY_LOCAL_MACHINE, reg.HKEY_CURRENT_USER):
        try:
            key = reg.CreateKeyEx(hive, _EDGE_POLICY, 0, reg.KEY_SET_VALUE)
        except OSError:
            continue
        try:
            reg.SetValueEx(key, _LEVEL, 0, reg.REG_DWORD, 1)
            # Reload unconfigured sites (no Enterprise Site List) in IE mode.
            reg.SetValueEx(key, _RELOAD, 0, reg.REG_DWORD, 1)
            return
        except OSError:
            continue
        finally:
            reg.CloseKey(key)
