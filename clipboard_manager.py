"""Lightweight clipboard manager using Windows ctypes (zero dependencies)."""
import ctypes
from ctypes import wintypes
import logging

logger = logging.getLogger(__name__)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040
GHND = GMEM_MOVEABLE | GMEM_ZEROINIT

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL

user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL

user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL

user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL

kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID

kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL


def copy_to_clipboard(text: str) -> bool:
    """Copies given unicode text to Windows clipboard."""
    if not isinstance(text, str):
        text = str(text)

    encoded = (text + "\0").encode("utf-16le")
    size = len(encoded)

    h_global = kernel32.GlobalAlloc(GHND, size)
    if not h_global:
        logger.error("Failed to allocate global memory for clipboard.")
        return False

    p_data = kernel32.GlobalLock(h_global)
    if not p_data:
        logger.error("Failed to lock global memory for clipboard.")
        return False

    ctypes.memmove(p_data, encoded, size)
    kernel32.GlobalUnlock(h_global)

    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                res = user32.SetClipboardData(CF_UNICODETEXT, h_global)
                if res:
                    logger.info("Copied '%s' to clipboard.", text)
                    return True
                else:
                    logger.error("SetClipboardData failed.")
                    return False
            finally:
                user32.CloseClipboard()

        kernel32.Sleep(20)

    logger.warning("Could not open clipboard after retries.")
    return False
