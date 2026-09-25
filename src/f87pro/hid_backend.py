"""
Cross-platform HID backend resolution.

The upstream project targeted Linux only and imported the `hidraw` module
directly. macOS has no hidraw subsystem, so we resolve whichever binding is
present at import time and expose it under a single name.

Both bindings expose the same surface we rely on: `enumerate()`, `device()`
and `HIDException`.
"""
import sys
from types import ModuleType

# Ordered by preference. `hid` (cython-hidapi) is the portable binding and is
# the only one available on macOS; `hidraw` is the Linux-specific one the
# upstream project used.
_BACKEND_CANDIDATES = ("hid", "hidraw")


def _load_backend() -> ModuleType:
    """
    Import the first available HID binding.

    @returns The imported module.
    @raises ImportError If no supported binding is installed.
    """
    errors = []
    for module_name in _BACKEND_CANDIDATES:
        try:
            return __import__(module_name)
        except ImportError as exc:
            errors.append(f"{module_name}: {exc}")

    raise ImportError(
        "No HID backend available. Install one of: "
        + ", ".join(_BACKEND_CANDIDATES)
        + f" (pip install hidapi). Tried -> {'; '.join(errors)}"
    )


hid = _load_backend()

IS_MACOS = sys.platform == "darwin"


def _enable_shared_access() -> bool:
    """
    Ask hidapi to open devices non-exclusively on macOS.

    hidapi's macOS backend defaults to opening with `kIOHIDOptionsTypeSeizeDevice`,
    which takes the device away from the OS. That is invisible for the main
    typing interface, which the F87 Pro exposes separately, but the interface
    carrying the RGB control also carries the consumer-control collection --
    the volume and media keys. Seizing it silently stops those keys working for
    as long as the lighting process runs.

    Opening shared keeps the keys working, and the vendor feature reports the
    lighting needs still go through.

    @returns True if sharing is active (or not needed on this platform).
    """
    if not IS_MACOS:
        return True

    try:
        import ctypes

        library = ctypes.CDLL(hid.__file__)
        library.hid_darwin_set_open_exclusive(0)
        return library.hid_darwin_get_open_exclusive() == 0
    except (OSError, AttributeError, TypeError):
        # Older hidapi builds lack the symbol; the lighting still works, the
        # media keys just stay seized while it runs.
        return False


#: Whether the keyboard is shared with the OS rather than seized. Applied at
#: import so every code path that opens the device inherits it.
SHARED_ACCESS = _enable_shared_access()

# macOS gates any HID device that advertises a keyboard usage page behind the
# Input Monitoring TCC permission, so `open_path` fails with a bare
# "open failed" until the controlling terminal is granted access.
MACOS_PERMISSION_HELP = """
macOS could not open the keyboard's HID interface.

The Aula F87 Pro exposes a keyboard usage page, so macOS requires the
'Input Monitoring' permission before any process may open it.

Fix it once:
  1. System Settings -> Privacy & Security -> Input Monitoring
  2. Enable your terminal app (Terminal, iTerm2, Ghostty, WezTerm, VS Code...)
  3. Fully quit and reopen that terminal, then retry.

If the app is not listed, click '+' and add it from /Applications.
Running the command under `sudo` is an alternative but is not recommended.
""".strip()


def sharing_warning() -> str:
    """
    Warning to show when the device had to be seized rather than shared.

    @returns A message, or an empty string when sharing is active.
    """
    if SHARED_ACCESS:
        return ""
    return (
        "Warning: this hidapi build cannot share the keyboard with macOS, so "
        "the volume and media keys will not work while the lighting runs. "
        "Upgrade hidapi (pip install -U hidapi) to fix it."
    )


def permission_hint() -> str:
    """
    Platform-appropriate guidance for a failed device open.

    @returns A human-readable remediation message.
    """
    if IS_MACOS:
        return MACOS_PERMISSION_HELP
    return (
        "Could not open the HID interface. Set up the udev rule described in "
        "the README, or re-run with sudo."
    )
