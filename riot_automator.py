"""
Riot Client UI automation for auto-login and input simulation.
Uses Win32 SendInput with correct 64-bit structure alignment.
"""
import ctypes
from ctypes import wintypes
import time
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_SPACE = 0x20
VK_V = 0x56
VK_A = 0x41

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

SW_RESTORE = 9
SW_SHOW = 5

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("_u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_u", _INPUTunion),
    ]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL


def press_vk(vk: int, delay_after: float = 0.1):
    """Presses and releases a virtual key."""
    d = INPUT(type=INPUT_KEYBOARD)
    d.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)

    u = INPUT(type=INPUT_KEYBOARD)
    u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)

    ev = (INPUT * 2)(d, u)
    user32.SendInput(2, ev, ctypes.sizeof(INPUT))
    if delay_after > 0:
        time.sleep(delay_after)


def press_combo(vk_mod: int, vk_key: int, delay_after: float = 0.1):
    """Sends modifier + key combination (e.g. Ctrl+A)."""
    mod_down = INPUT(type=INPUT_KEYBOARD)
    mod_down.ki = KEYBDINPUT(wVk=vk_mod, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)

    key_down = INPUT(type=INPUT_KEYBOARD)
    key_down.ki = KEYBDINPUT(wVk=vk_key, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)

    key_up = INPUT(type=INPUT_KEYBOARD)
    key_up.ki = KEYBDINPUT(wVk=vk_key, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)

    mod_up = INPUT(type=INPUT_KEYBOARD)
    mod_up.ki = KEYBDINPUT(wVk=vk_mod, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)

    ev = (INPUT * 4)(mod_down, key_down, key_up, mod_up)
    user32.SendInput(4, ev, ctypes.sizeof(INPUT))
    if delay_after > 0:
        time.sleep(delay_after)


def type_char_unicode(c: str):
    """Sends a single unicode character (layout-independent)."""
    code = ord(c)
    d = INPUT(type=INPUT_KEYBOARD)
    d.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)

    u = INPUT(type=INPUT_KEYBOARD)
    u.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)

    ev = (INPUT * 2)(d, u)
    user32.SendInput(2, ev, ctypes.sizeof(INPUT))


def type_text(text: str, char_delay: float = 0.03):
    """Types text using SendInput unicode events with natural delay."""
    for c in text:
        type_char_unicode(c)
        if char_delay > 0:
            time.sleep(char_delay)


def click_at(x: int, y: int, delay_after: float = 0.15):
    """Moves mouse to (x, y) and performs a left mouse button click."""
    user32.SetCursorPos(x, y)
    time.sleep(0.05)

    d = INPUT(type=INPUT_MOUSE)
    d.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTDOWN, time=0, dwExtraInfo=0)

    u = INPUT(type=INPUT_MOUSE)
    u.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTUP, time=0, dwExtraInfo=0)

    ev = (INPUT * 2)(d, u)
    user32.SendInput(2, ev, ctypes.sizeof(INPUT))
    if delay_after > 0:
        time.sleep(delay_after)


def find_riot_client_window() -> Optional[wintypes.HWND]:
    """Finds Riot Client window handle."""
    try:
        from desktop_helper import attach_to_default_desktop
        attach_to_default_desktop()
    except Exception:
        pass

    hwnd = user32.FindWindowW(None, "Riot Client")
    if hwnd and user32.IsWindowVisible(hwnd):
        return hwnd

    found_hwnd = None
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def enum_proc(h, _):
        nonlocal found_hwnd
        if user32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(h, buf, 512)
            title = buf.value
            if "Riot Client" in title:
                found_hwnd = h
                return False
        return True

    user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
    return found_hwnd


def focus_riot_client() -> Tuple[bool, Optional[wintypes.HWND]]:
    """Finds, restores, and brings Riot Client window to foreground."""
    hwnd = find_riot_client_window()
    if not hwnd:
        logger.warning("Riot Client window not found.")
        return False, None

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.35)
    else:
        user32.ShowWindow(hwnd, SW_SHOW)

    user32.SetForegroundWindow(hwnd)
    time.sleep(0.35)
    return True, hwnd


def execute_auto_login(login: str, password: str, status_cb=None) -> Tuple[bool, str]:
    """
    Executes the user-specified login sequence without mouse clicking:
    1. Bring Riot window to foreground (cursor is already in Username field)
    2. Clear field & paste login (Ctrl+A -> Backspace -> Ctrl+V)
    3. Tab to Password
    4. Clear field & paste password (Ctrl+A -> Backspace -> Ctrl+V)
    5. 6 Tabs (skip intermediate social login buttons)
    6. Space (toggle 'Remember me' checkbox)
    7. Tab (focus 'Sign in' button)
    8. Space / Return (submit sign in)
    """
    try:
        from desktop_helper import attach_to_default_desktop
        attach_to_default_desktop()
    except Exception:
        pass

    if not login or not password:
        return False, "Логин или пароль пустые"

    if status_cb:
        status_cb("Поиск окна Riot Client...")

    ok, hwnd = focus_riot_client()
    if not ok or not hwnd:
        return False, "Окно Riot Client не найдено! Запустите Riot Client."

    time.sleep(0.2)

    if status_cb:
        status_cb("Ввод логина...")

    press_combo(VK_CONTROL, VK_A, delay_after=0.08)
    press_vk(VK_BACK, delay_after=0.08)

    from clipboard_manager import copy_to_clipboard
    copy_to_clipboard(login)
    time.sleep(0.05)
    press_combo(VK_CONTROL, VK_V, delay_after=0.15)

    if status_cb:
        status_cb("Переход к паролю (Tab)...")
    press_vk(VK_TAB, delay_after=0.2)

    if status_cb:
        status_cb("Ввод пароля...")

    press_combo(VK_CONTROL, VK_A, delay_after=0.08)
    press_vk(VK_BACK, delay_after=0.08)

    copy_to_clipboard(password)
    time.sleep(0.05)
    press_combo(VK_CONTROL, VK_V, delay_after=0.2)

    if status_cb:
        status_cb("Переход к 'Запомнить меня' (6x Tab)...")
    for _ in range(6):
        press_vk(VK_TAB, delay_after=0.12)

    if status_cb:
        status_cb("Включение 'Запомнить меня' (Space)...")
    press_vk(VK_SPACE, delay_after=0.2)

    if status_cb:
        status_cb("Переход к кнопке входа (Tab)...")
    press_vk(VK_TAB, delay_after=0.2)

    if status_cb:
        status_cb("Нажатие кнопки входа...")
    press_vk(VK_SPACE, delay_after=0.1)
    press_vk(VK_RETURN, delay_after=0.1)

    if status_cb:
        status_cb("Вход выполнен! Ожидание кода подтверждения...")

    return True, "Данные успешно введены в Riot Client!"
