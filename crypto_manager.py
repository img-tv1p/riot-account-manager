"""Windows DPAPI encryption helper for securing stored passwords."""
import ctypes
from ctypes import wintypes
import base64
import logging

logger = logging.getLogger(__name__)


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32

crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    wintypes.LPCWSTR,
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
crypt32.CryptProtectData.restype = wintypes.BOOL

crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    wintypes.LPCWSTR,
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
crypt32.CryptUnprotectData.restype = wintypes.BOOL


def encrypt_password(plain_text: str) -> str:
    """Encrypts a plaintext string using Windows DPAPI and returns Base64 string."""
    if not plain_text:
        return ""

    raw_bytes = plain_text.encode("utf-8")
    ubytes = (ctypes.c_ubyte * len(raw_bytes))(*raw_bytes)
    in_blob = DATA_BLOB(len(raw_bytes), ctypes.cast(ubytes, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = DATA_BLOB()

    success = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "RiotAccountCredentials",
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not success:
        error_code = kernel32.GetLastError()
        raise RuntimeError(f"CryptProtectData failed with error code: {error_code}")

    try:
        cipher_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return base64.b64encode(cipher_bytes).decode("ascii")
    finally:
        kernel32.LocalFree(out_blob.pbData)


def decrypt_password(cipher_b64: str) -> str:
    """Decrypts a DPAPI Base64 string back into plain text string."""
    if not cipher_b64:
        return ""

    raw_bytes = base64.b64decode(cipher_b64.encode("ascii"))
    ubytes = (ctypes.c_ubyte * len(raw_bytes))(*raw_bytes)
    in_blob = DATA_BLOB(len(raw_bytes), ctypes.cast(ubytes, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = DATA_BLOB()

    success = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not success:
        error_code = kernel32.GetLastError()
        raise RuntimeError(f"CryptUnprotectData failed with error code: {error_code}")

    try:
        plain_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return plain_bytes.decode("utf-8")
    finally:
        kernel32.LocalFree(out_blob.pbData)


encrypt_string = encrypt_password
decrypt_string = decrypt_password
