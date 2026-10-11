r"""
App Installer and Auto-start Manager for Riot Account Manager - RAM.
Handles self-relocation to C:\Program Files (x86)\RAM,
Desktop shortcut creation, and Windows autostart registry management.
"""
import os
import sys
import shutil
import logging
import winreg
import subprocess

logger = logging.getLogger(__name__)

APP_NAME = "RAM"
APP_FULL_NAME = "Riot Account Manager - RAM"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_install_dir() -> str:
    r"""Returns C:\Program Files (x86)\RAM when compiled, or local directory in dev mode."""

    if not getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(__file__))

    pfx = os.environ.get("ProgramFiles(x86)")
    if not pfx or not os.path.exists(pfx):
        pfx = r"C:\Program Files (x86)"
    target = os.path.join(pfx, APP_NAME)
    try:
        os.makedirs(target, exist_ok=True)
        return target
    except Exception as e:
        logger.warning("Could not create %s (%s), falling back to LocalAppData", target, e)
        fallback = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP_NAME)
        os.makedirs(fallback, exist_ok=True)
        return fallback


def get_desktop_dir() -> str:
    """Returns the user's Desktop directory path."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        )
        val, _ = winreg.QueryValueEx(key, "Desktop")
        winreg.CloseKey(key)
        return os.path.expandvars(val)
    except Exception:
        return os.path.join(os.path.expanduser("~"), "Desktop")


def create_desktop_shortcut(target_exe: str, shortcut_name: str = f"{APP_FULL_NAME}.lnk") -> bool:
    """Creates a Windows shortcut (.lnk) on the user's Desktop."""
    desktop = get_desktop_dir()
    lnk_path = os.path.join(desktop, shortcut_name)
    target_dir = os.path.dirname(os.path.abspath(target_exe))

    icon_path = os.path.join(target_dir, "icon.ico")
    if not os.path.exists(icon_path):
        icon_path = target_exe

    vbs_content = f"""Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{lnk_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{target_exe}"
oLink.WorkingDirectory = "{target_dir}"
oLink.Description = "{APP_FULL_NAME}"
oLink.IconLocation = "{icon_path}, 0"
oLink.Save
"""
    vbs_path = os.path.join(target_dir, "_make_shortcut.vbs")
    try:
        with open(vbs_path, "w", encoding="cp1251") as f:
            f.write(vbs_content)
        subprocess.run(
            ["cscript", "//nologo", vbs_path],
            capture_output=True,
            creationflags=0x08000000,
        )
        try:
            os.remove(vbs_path)
        except Exception:
            pass
        created = os.path.exists(lnk_path)
        if created:
            logger.info("Desktop shortcut verified: %s", lnk_path)

            old_lnk = os.path.join(desktop, "RiotAutomatic.lnk")
            if os.path.exists(old_lnk):
                try:
                    os.remove(old_lnk)
                    logger.info("Removed old shortcut: %s", old_lnk)
                except Exception:
                    pass
        return created
    except Exception as e:
        logger.error("Failed to create desktop shortcut: %s", e)
        return False


def is_autostart_enabled() -> bool:
    """Checks if the app is registered in HKCU Run key."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ)
        try:
            val, _ = winreg.QueryValueEx(key, APP_NAME)
        except FileNotFoundError:
            val, _ = winreg.QueryValueEx(key, "RiotAutomatic")
        winreg.CloseKey(key)
        return bool(val)
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.debug("Error checking autostart: %s", e)
        return False


def set_autostart(enable: bool, exe_path: str = None) -> bool:
    """Enables or disables autostart in HKCU Run key."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE)

        try:
            winreg.DeleteValue(key, "RiotAutomatic")
        except FileNotFoundError:
            pass

        if enable:
            if not exe_path:
                exe_path = os.path.join(get_install_dir(), f"{APP_NAME}.exe")
            quoted = f'"{exe_path}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, quoted)
            logger.info("Autostart enabled: %s", quoted)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
            logger.info("Autostart disabled.")
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logger.error("Failed to set autostart to %s: %s", enable, e)
        return False


def ensure_installed_and_relocate() -> bool:
    r"""
    Ensures that the app and its files are installed in C:\Program Files (x86)\RAM.
    If running outside the install dir as a frozen .exe, copies itself and files,
    creates the Desktop shortcut, launches the installed .exe, and returns True
    (indicating the current process must terminate).
    """
    install_dir = get_install_dir()
    target_exe = os.path.join(install_dir, f"{APP_NAME}.exe")
    is_frozen = getattr(sys, "frozen", False)

    current_exe = os.path.abspath(sys.executable if is_frozen else __file__)
    current_dir = os.path.dirname(current_exe)
    bundle_dir = getattr(sys, "_MEIPASS", current_dir)

    old_pfx = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    old_dir = os.path.join(old_pfx, "RiotAutomatic")
    if os.path.exists(old_dir):
        for fname in ["config.json", "accounts.json"]:
            old_f = os.path.join(old_dir, fname)
            dst_f = os.path.join(install_dir, fname)
            if os.path.exists(old_f) and (not os.path.exists(dst_f) or os.path.getsize(dst_f) == 0):
                try:
                    shutil.copy2(old_f, dst_f)
                    logger.info("Migrated %s from previous installation", fname)
                except Exception as e:
                    logger.warning("Could not migrate %s: %s", fname, e)

    for fname in ["config.json", "accounts.json", "icon.ico", "icon.png", "icon_tray.png"]:
        src_file = os.path.join(current_dir, fname)
        if not os.path.exists(src_file) and bundle_dir != current_dir:
            src_file = os.path.join(bundle_dir, fname)

        dst_file = os.path.join(install_dir, fname)
        if os.path.exists(src_file):
            same_file = False
            try:
                same_file = os.path.samefile(src_file, dst_file)
            except Exception:
                same_file = (os.path.abspath(src_file).lower() == os.path.abspath(dst_file).lower())

            if not same_file:
                need_copy = not os.path.exists(dst_file) or os.path.getsize(dst_file) == 0
                if need_copy:
                    try:
                        shutil.copy2(src_file, dst_file)
                        logger.info("Installed file %s -> %s", fname, dst_file)
                    except Exception as e:
                        logger.warning("Could not copy %s: %s", fname, e)

    in_install_dir = (os.path.abspath(current_dir).lower() == os.path.abspath(install_dir).lower())

    if is_frozen and not in_install_dir:
        logger.info("Running outside install dir (%s). Installing to %s...", current_exe, target_exe)

        copied = False
        try:
            shutil.copy2(current_exe, target_exe)
            copied = True
            logger.info("Successfully copied executable to %s", target_exe)
        except PermissionError:
            logger.info("Target executable locked. Terminating old instances...")
            current_pid = os.getpid()
            import time
            ps_cmd = f"Get-Process -Name '{APP_NAME}', 'RiotAutomatic', 'RiotGrabber' -ErrorAction SilentlyContinue | Where-Object {{ $_.Id -ne {current_pid} }} | Stop-Process -Force"
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, creationflags=0x08000000)
            time.sleep(0.8)
            try:
                shutil.copy2(current_exe, target_exe)
                copied = True
                logger.info("Successfully copied executable after terminating old instances.")
            except Exception as e:
                logger.error("Failed to copy executable after retry: %s", e)
        except Exception as e:
            logger.error("Failed to copy executable: %s", e)

        create_desktop_shortcut(target_exe)

        if is_autostart_enabled():
            set_autostart(True, target_exe)

        try:
            subprocess.Popen(
                [target_exe],
                cwd=install_dir,
                creationflags=0x08000000 | 0x00000200,
            )
            logger.info("Launched installed executable: %s", target_exe)

            try:
                del_cmd = (
                    f"Start-Sleep -Milliseconds 600; "
                    f"for ($i=0; $i -lt 10; $i++) {{ "
                    f"try {{ if (Test-Path -LiteralPath '{current_exe}') {{ Remove-Item -LiteralPath '{current_exe}' -Force -ErrorAction Stop; break }} }} "
                    f"catch {{ Start-Sleep -Milliseconds 500 }} }}"
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", del_cmd],
                    creationflags=0x08000000 | 0x00000200,
                )
                logger.info("Scheduled self-deletion for original executable: %s", current_exe)
            except Exception as e:
                logger.warning("Could not schedule self-deletion of %s: %s", current_exe, e)

            return True
        except Exception as e:
            logger.error("Failed to launch %s: %s", target_exe, e)
            return False

    desktop_lnk = os.path.join(get_desktop_dir(), f"{APP_FULL_NAME}.lnk")
    if not os.path.exists(desktop_lnk):
        create_desktop_shortcut(target_exe if os.path.exists(target_exe) else current_exe)

    return False
