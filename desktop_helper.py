"""
Helper to ensure Windows GUI elements and system tray icons attach
to the user's interactive 'Default' desktop station.

When processes are spawned by background IDE runners or subshells,
Windows may place them on an isolated virtual desktop (e.g. agy-...).
This module ensures the thread connects to the interactive desktop
so the system tray icon, notifications, and Tkinter GUI are visible.
"""
import sys
import ctypes
import logging

logger = logging.getLogger("desktop_helper")


def attach_to_default_desktop() -> bool:
    """Attaches the current thread to the 'Default' desktop in WinSta0."""
    if sys.platform != "win32":
        return True

    try:
        u32 = ctypes.windll.user32

        h_def = u32.OpenDesktopW("Default", 0, False, 0x01FF)
        if h_def:
            res = u32.SetThreadDesktop(h_def)
            if res:
                logger.info("Successfully attached thread to interactive 'Default' desktop.")
                return True
            else:
                err = ctypes.windll.kernel32.GetLastError()
                logger.debug("SetThreadDesktop returned 0, error code: %s", err)
        else:
            logger.debug("OpenDesktopW('Default') returned NULL.")
    except Exception as e:
        logger.debug("attach_to_default_desktop failed: %s", e)

    return False
