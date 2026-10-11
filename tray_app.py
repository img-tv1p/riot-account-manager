"""System tray application for Riot Games 2FA Code Grabber."""
import json
import os
import sys
import threading
import logging
from logging.handlers import RotatingFileHandler
import subprocess

import pystray
from PIL import Image

from clipboard_manager import copy_to_clipboard
from notifier import send_notification
from email_parser import parse_email_message
from imap_listener import RiotImapListener
from icon_generator import create_tray_icon_image, save_icon_files

from app_installer import (
    get_install_dir,
    is_autostart_enabled,
    set_autostart,
    ensure_installed_and_relocate,
    APP_NAME,
)

BASE_DIR = get_install_dir()
LOG_FILE = os.path.join(BASE_DIR, "riot_grabber.log")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
ICON_ICO = os.path.join(BASE_DIR, "icon.ico")
ICON_PNG = os.path.join(BASE_DIR, "icon.png")
ICON_TRAY_PNG = os.path.join(BASE_DIR, "icon_tray.png")

if getattr(sys, "frozen", False):
    bundle_dir = getattr(sys, "_MEIPASS", BASE_DIR)
    if not os.path.exists(ICON_ICO) and os.path.exists(os.path.join(bundle_dir, "icon.ico")):
        ICON_ICO = os.path.join(bundle_dir, "icon.ico")
    if not os.path.exists(ICON_PNG) and os.path.exists(os.path.join(bundle_dir, "icon.png")):
        ICON_PNG = os.path.join(bundle_dir, "icon.png")
    if not os.path.exists(ICON_TRAY_PNG) and os.path.exists(os.path.join(bundle_dir, "icon_tray.png")):
        ICON_TRAY_PNG = os.path.join(bundle_dir, "icon_tray.png")

logger = logging.getLogger("RiotGrabber")
logger.setLevel(logging.INFO)

formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

try:
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
except Exception:
    pass

file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

logging.root.setLevel(logging.INFO)
logging.root.addHandler(file_handler)
logging.root.addHandler(console_handler)


class RiotGrabberApp:
    def __init__(self):
        self.config = self.load_config()
        self.last_code: str = "нет"
        self.last_code_time: str = ""
        self.gui_window = None
        self.status_text: str = "Инициализация..."
        self.listener: RiotImapListener = None
        self.listener_thread: threading.Thread = None
        self.icon: pystray.Icon = None

        if not os.path.exists(ICON_ICO):
            try:
                save_icon_files(BASE_DIR)
            except Exception as e:
                logger.warning("Could not pre-save icon files: %s", e)

    def load_config(self) -> dict:
        """Loads configuration from config.json or creates default template."""
        default_config = {
            "email": "your_email@yandex.ru",
            "app_password": "your_yandex_app_password",
            "imap_server": "imap.yandex.ru",
            "imap_port": 993,
            "check_interval_seconds": 5,
            "auto_copy_to_clipboard": True,
            "show_notifications": True,
            "play_sound": True
        }

        if not os.path.exists(CONFIG_FILE):

            local_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
            local_cfg = os.path.join(local_dir, "config.json")
            if os.path.exists(local_cfg):
                try:
                    import shutil
                    shutil.copy2(local_cfg, CONFIG_FILE)
                    logger.info("Migrated config.json from %s to %s", local_cfg, CONFIG_FILE)
                except Exception as e:
                    logger.warning("Could not migrate config.json: %s", e)

        if not os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error("Failed to write default config.json: %s", e)
            return default_config

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**default_config, **data}
        except Exception as e:
            logger.error("Failed to read config.json: %s", e)
            return default_config

    def on_code_received(self, code: str, sender: str, subject: str, date: str = ""):
        """Callback when a new Riot Games code is detected."""
        from datetime import datetime
        self.last_code = code
        self.last_code_time = date if date else datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        logger.info(">>> CODE DETECTED: %s (Time: %s | From: %s) <<<", code, self.last_code_time, sender)

        copied = False
        if self.config.get("auto_copy_to_clipboard", True):
            copied = copy_to_clipboard(code)

        if self.icon:
            self.icon.title = f"Riot Code: {code}"
            self.update_menu()

        if self.gui_window and not getattr(self.gui_window, "is_closed", True):
            try:
                self.gui_window.root.after(0, self.gui_window._update_code_display)
            except Exception as e:
                logger.debug("Failed to update GUI code display: %s", e)

        if self.config.get("show_notifications", True):
            title = "Riot Games — Код получен!"
            msg = f"Код: {code} " + ("скопирован в буфер обмена!\nВставьте в Riot Client (Ctrl+V)." if copied else "получен!")
            send_notification(
                title=title,
                message=msg,
                play_audio=self.config.get("play_sound", True),
                icon_path=ICON_PNG if os.path.exists(ICON_PNG) else None
            )

    def on_status_updated(self, status: str):
        """Callback when IMAP connection status changes."""
        try:
            self.status_text = status
            if self.icon:
                self.update_menu()
        except Exception as e:
            logger.debug("Error in on_status_updated: %s", e)

    def update_menu(self):
        """Updates tray icon context menu."""
        if not self.icon or not getattr(self.icon, "visible", False):
            return
        try:
            self.icon.menu = self.create_menu()
        except Exception as e:
            logger.debug("Failed to update menu: %s", e)

    def action_open_menu(self, icon=None, item=None):
        """Opens or brings to front the lightweight Tkinter GUI."""
        if self.gui_window and getattr(self.gui_window, "root", None):
            try:
                if self.gui_window.root.winfo_exists():
                    self.gui_window.restore_and_show()
                    return
            except Exception:
                self.gui_window = None

        from gui_menu import RiotGrabberGUI
        self.gui_window = RiotGrabberGUI(self)

        def _run_gui():
            from desktop_helper import attach_to_default_desktop
            attach_to_default_desktop()
            self.gui_window.show()

        gui_thread = threading.Thread(target=_run_gui, daemon=True, name="GuiThread")
        gui_thread.start()

    def action_copy_last_code(self, icon, item):
        """Manually copies the last known code again."""
        if self.last_code and self.last_code != "нет":
            copy_to_clipboard(self.last_code)
            send_notification(
                title="Буфер обмена",
                message=f"Код {self.last_code} скопирован повторно!",
                play_audio=False
            )

    def action_check_now(self, icon, item):
        """Triggers immediate mailbox check in a thread."""
        def run_check():
            self.on_status_updated("Ручная проверка...")
            if self.listener:
                code = self.listener.check_messages(manual=True)
                if code:
                    self.on_status_updated(f"Найден код: {code}")
                else:
                    self.on_status_updated("Новых кодов не найдено")
                    send_notification(
                        title="Riot Account Manager - RAM",
                        message="Новых кодов от Riot Games в последних письмах не найдено.",
                        play_audio=False
                    )

        threading.Thread(target=run_check, daemon=True).start()

    def action_open_config(self, icon=None, item=None):
        """Opens config.json in default editor."""
        try:
            os.startfile(CONFIG_FILE)
        except Exception as e:
            logger.error("Could not open config.json: %s", e)

    def is_configured(self) -> bool:
        """Checks if valid email and app password are configured."""
        email = self.config.get("email", "").strip()
        pwd = self.config.get("app_password", "").strip()
        if not email or not pwd:
            return False
        if "your_email" in email or "your_yandex" in pwd:
            return False
        return bool(self.config.get("is_configured", True))

    def restart_listener(self):
        """Restarts the IMAP listener thread with current configuration."""
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
        self.start_listener()

    def action_open_email_setup(self, icon=None, item=None):
        """Opens interactive email configuration window on interactive desktop."""
        def run_dialog():
            try:
                from desktop_helper import attach_to_default_desktop
                attach_to_default_desktop()
            except Exception:
                pass

            try:
                from email_setup_dialog import open_email_setup_dialog
                def on_saved(new_cfg):
                    logger.info("Email configuration updated: %s", new_cfg.get("email"))
                    self.config = new_cfg
                    self.restart_listener()

                open_email_setup_dialog(
                    parent=None,
                    config_path=CONFIG_FILE,
                    initial_config=self.config,
                    on_saved=on_saved,
                    is_first_launch=False,
                )
            except Exception as e:
                logger.error("Error opening email setup dialog: %s", e)

        threading.Thread(target=run_dialog, daemon=True, name="EmailSetupDialogThread").start()

    def action_quit(self, icon, item):
        """Exits the application completely and terminates all RiotGrabber processes."""
        logger.info("Stopping application and exiting immediately...")

        try:
            if self.icon:
                self.icon.visible = False
        except Exception:
            pass

        try:
            if self.listener:
                self.listener.stop()
        except Exception:
            pass

        try:
            if self.gui_window:
                self.gui_window.destroy_app()
        except Exception:
            pass

        try:
            import subprocess
            subprocess.Popen(
                ["cmd.exe", "/c", f"timeout /t 1 /nobreak >nul & taskkill /F /IM {APP_NAME}.exe /T & taskkill /F /IM RiotGrabber.exe /T"],
                creationflags=0x08000000,
            )
        except Exception:
            pass

        os._exit(0)

    def action_toggle_autostart(self, icon=None, item=None):
        """Toggles Windows autostart state."""
        current = is_autostart_enabled()
        new_state = not current
        set_autostart(new_state)
        msg = "Автозагрузка включена" if new_state else "Автозагрузка отключена"
        self.on_status_updated(msg)
        send_notification(
            title="Автозагрузка",
            message=msg,
            play_audio=False,
        )

    def action_logout_riot(self, icon=None, item=None):
        """Runs the Riot Client account logout routine in a background thread."""
        def run_logout():
            from val43_fixer import run_logout_account
            from notifier import send_notification
            success, msg = run_logout_account()
            send_notification(
                title="Выход из аккаунта Riot",
                message=msg,
                play_audio=True,
                icon_path=ICON_PNG if os.path.exists(ICON_PNG) else None,
            )
        threading.Thread(target=run_logout, daemon=True).start()

    def action_fix_val43(self, icon=None, item=None):
        """Runs the FIX VAL43 routine in a background thread."""
        def run_fix():
            from val43_fixer import run_val43_fix
            from notifier import send_notification
            success, msg = run_val43_fix()
            send_notification(
                title="FIX VAL43",
                message=msg,
                play_audio=True,
                icon_path=ICON_PNG if os.path.exists(ICON_PNG) else None,
            )
        threading.Thread(target=run_fix, daemon=True).start()

    def create_menu(self):
        """Builds pystray context menu."""
        code_label = f"🔑 Код: {self.last_code}"
        if self.last_code != "нет":
            code_label += " (кликните, чтобы скопировать)"

        return pystray.Menu(
            pystray.MenuItem("🖥️ Открыть меню", self.action_open_menu, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"⚡ Статус: {self.status_text}", None, enabled=False),
            pystray.MenuItem(code_label, self.action_copy_last_code, enabled=(self.last_code != "нет")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🔄 Проверить почту сейчас", self.action_check_now),
            pystray.MenuItem("🚀 Автозагрузка с Windows", self.action_toggle_autostart, checked=lambda item: is_autostart_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Выход", self.action_quit)
        )

    def start_listener(self):
        """Initializes and runs the IMAP listener in background thread for current selected account."""
        from account_manager import get_selected_account
        from crypto_manager import decrypt_string

        acc = get_selected_account()
        email_addr = ""
        password = ""
        server = "imap.yandex.ru"
        port = 993

        if acc and acc.get("email"):
            email_addr = acc["email"].strip()
            enc_pwd = acc.get("encrypted_app_password", "")
            if enc_pwd:
                try:
                    password = decrypt_string(enc_pwd) or ""
                except Exception as e:
                    logger.warning("Could not decrypt account app password: %s", e)
            server = acc.get("imap_server") or self.config.get("imap_server", "imap.yandex.ru")
            port = int(acc.get("imap_port") or self.config.get("imap_port", 993))

        if not email_addr or not password:
            email_addr = self.config.get("email", "").strip()
            enc_cfg_pwd = self.config.get("encrypted_app_password", "")
            if enc_cfg_pwd:
                try:
                    password = decrypt_string(enc_cfg_pwd) or ""
                except Exception:
                    password = ""
            if not password:
                password = self.config.get("app_password", "").strip()
            server = self.config.get("imap_server", "imap.yandex.ru")
            port = int(self.config.get("imap_port", 993))

        if not email_addr or not password:
            self.status_text = "Требуется настройка почты"
            logger.warning("No email credentials found for IMAP listener.")
            return

        self.current_monitored_email = email_addr
        logger.info("Starting IMAP listener for email: %s on %s:%d", email_addr, server, port)

        self.listener = RiotImapListener(
            email_address=email_addr,
            app_password=password,
            imap_server=server,
            imap_port=port,
            poll_interval=self.config.get("check_interval_seconds", 5),
            on_code=self.on_code_received,
            on_status=self.on_status_updated,
        )

        self.listener_thread = threading.Thread(target=self.listener.run, daemon=True)
        self.listener_thread.start()

    def switch_monitored_account(self, account_dict: dict):
        """Switches IMAP listener to the selected account's mailbox if different."""
        new_email = (account_dict.get("email") or "").strip()
        if not new_email:
            return

        current_email = getattr(self, "current_monitored_email", "")
        if new_email.lower() == current_email.lower() and self.listener and self.listener.running:
            logger.info("Selected account shares current monitored mailbox (%s). No reconnect needed.", new_email)
            return

        logger.info(
            "Switching monitored mailbox from '%s' to '%s' for account '%s'...",
            current_email, new_email, account_dict.get("login")
        )
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
        self.start_listener()

    def _setup_tray(self, icon):
        """Pystray setup callback — runs in a separate thread. Keep minimal."""
        icon.visible = True
        logger.info("Tray icon is now visible in system tray.")

    def run(self):
        """Starts tray application."""
        logger.info("Starting Riot Account Manager - RAM tray app...")

        _original_excepthook = threading.excepthook

        def _thread_excepthook(args):
            logger.error(
                "Uncaught exception in thread '%s': %s",
                args.thread.name if args.thread else "?",
                args.exc_value,
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
            if _original_excepthook:
                try:
                    _original_excepthook(args)
                except Exception:
                    pass

        threading.excepthook = _thread_excepthook

        icon_img = None
        if os.path.exists(ICON_TRAY_PNG):
            try:
                icon_img = Image.open(ICON_TRAY_PNG)
                icon_img = icon_img.resize((64, 64), Image.Resampling.LANCZOS)
            except Exception as e:
                logger.warning("Could not load icon_tray.png: %s", e)
        if icon_img is None and os.path.exists(ICON_PNG):
            try:
                icon_img = Image.open(ICON_PNG)
                icon_img = icon_img.resize((64, 64), Image.Resampling.LANCZOS)
            except Exception as e:
                logger.warning("Could not load icon.png: %s", e)
        if icon_img is None:
            icon_img = create_tray_icon_image(64)

        self.icon = pystray.Icon(
            name="RAM",
            icon=icon_img,
            title="Riot Account Manager - RAM",
            menu=self.create_menu()
        )

        orig_on_notify = getattr(self.icon, "_on_notify", None)
        if orig_on_notify:
            def _patched_on_notify(wparam, lparam):

                if lparam in (0x0202, 0x0203):
                    self.action_open_menu()
                    return
                return orig_on_notify(wparam, lparam)
            self.icon._on_notify = _patched_on_notify

        def _delayed_start():
            """Give the icon a moment to render, then start listener."""
            import time
            time.sleep(1.0)
            self.start_listener()

        threading.Thread(target=_delayed_start, daemon=True, name="DelayedStart").start()

        self.icon.run(setup=self._setup_tray)


def main():

    def _global_excepthook(exc_type, exc_value, exc_tb):
        logger.critical(
            "FATAL uncaught exception", exc_info=(exc_type, exc_value, exc_tb)
        )
    sys.excepthook = _global_excepthook

    try:
        if ensure_installed_and_relocate():
            sys.exit(0)
    except Exception as e:
        logger.error("Error during installation check: %s", e)

    try:
        from desktop_helper import attach_to_default_desktop
        attach_to_default_desktop()

        from first_run_wizard import show_first_run_wizard_if_needed
        first_run_completed = False

        def on_wizard_done(cfg):
            nonlocal first_run_completed
            first_run_completed = True

        was_first_run = show_first_run_wizard_if_needed(on_completed=on_wizard_done)

        app = RiotGrabberApp()

        if was_first_run or first_run_completed:
            def _open_initial_gui():
                import time
                time.sleep(1.2)
                app.action_open_menu()
            threading.Thread(target=_open_initial_gui, daemon=True).start()

        app.run()
    except Exception:
        logger.critical("App crashed", exc_info=True)


if __name__ == "__main__":
    main()
