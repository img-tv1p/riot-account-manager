"""
First Run Wizard for Riot Automatic v2.
Combines IMAP Email configuration with Riot Games account binding.
All passwords (Riot account password & Mail app password) are encrypted via Windows DPAPI.
Upon completion, marks program as configured and automatically launches the main GUI menu.
"""
import os
import sys
import json
import webbrowser
import threading
import logging
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable
from gui_clipboard_helper import enable_universal_clipboard

from email_setup_dialog import (
    MAIL_PROVIDERS,
    test_imap_credentials,
    COLOR_BG,
    COLOR_CARD,
    COLOR_CARD_BORDER,
    COLOR_ACCENT,
    COLOR_ACCENT_HOVER,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_TEXT_MUTED,
    COLOR_INPUT_BG,
    COLOR_INPUT_BORDER,
    COLOR_LINK,
    COLOR_LINK_HOVER,
    COLOR_BTN_SECONDARY,
    COLOR_BTN_SECONDARY_HOVER,
)
from account_manager import add_account, load_accounts
from crypto_manager import encrypt_password, encrypt_string
from app_installer import get_install_dir

logger = logging.getLogger(__name__)

BASE_DIR = get_install_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
ACCOUNTS_FILE = os.path.join(BASE_DIR, "accounts.json")


class FirstRunWizardDialog(tk.Tk):
    """Initial setup wizard shown only on first launch."""

    def __init__(self, on_completed: Optional[Callable] = None):
        super().__init__()
        self.on_completed = on_completed
        self.is_testing = False

        self.title("Riot Account Manager - RAM — Первоначальная настройка")
        enable_universal_clipboard(self)
        self.geometry("560x780")
        self.resizable(False, False)
        self.configure(bg=COLOR_BG)

        icon_path = os.path.join(BASE_DIR, "icon.ico")
        if not os.path.exists(icon_path):
            bundle_dir = getattr(sys, "_MEIPASS", BASE_DIR)
            icon_path = os.path.join(bundle_dir, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.current_provider_id = "yandex"
        self.provider_buttons = {}

        self._build_ui()
        self._center_window()

    def _center_window(self):
        self.update_idletasks()
        w = 580
        h = 820
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(20, (sw - w) // 2)
        y = max(20, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        container = tk.Frame(self, bg=COLOR_BG, padx=22, pady=16)
        container.pack(fill="both", expand=True)

        header = tk.Frame(container, bg=COLOR_BG)
        header.pack(fill="x", pady=(0, 10))

        tk.Label(
            header,
            text="🚀 Добро пожаловать в Riot Account Manager - RAM!",
            font=("Segoe UI", 13, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_BG,
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Настройте почту для кодов 2FA и привяжите ваш аккаунт Riot / Valorant.",
            font=("Segoe UI", 9),
            fg=COLOR_TEXT_SECONDARY,
            bg=COLOR_BG,
        ).pack(anchor="w", pady=(2, 0))

        mail_card = tk.Frame(
            container,
            bg=COLOR_CARD,
            highlightbackground=COLOR_CARD_BORDER,
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        mail_card.pack(fill="x", pady=(0, 10))

        tk.Label(
            mail_card,
            text="📧 Шаг 1: Почта для получения 2FA кодов",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        ).pack(anchor="w", pady=(0, 8))

        tabs_box = tk.Frame(mail_card, bg=COLOR_CARD)
        tabs_box.pack(fill="x", pady=(0, 8))

        for pid, pdata in MAIL_PROVIDERS.items():
            btn = tk.Button(
                tabs_box,
                text=pdata["btn_title"],
                font=("Segoe UI", 8, "bold"),
                relief="flat",
                cursor="hand2",
                command=lambda p=pid: self._select_provider(p),
                padx=8,
                pady=4,
            )
            btn.pack(side="left", padx=(0, 4), expand=True, fill="x")
            self.provider_buttons[pid] = btn

        self.mail_lbl = tk.Label(
            mail_card,
            text="Email адрес (Яндекс):",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        )
        self.mail_lbl.pack(anchor="w")

        self.email_entry = tk.Entry(
            mail_card,
            font=("Segoe UI", 9),
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.email_entry.pack(fill="x", ipady=3, pady=(2, 6))

        pass_top = tk.Frame(mail_card, bg=COLOR_CARD)
        pass_top.pack(fill="x")
        self.pass_lbl = tk.Label(
            pass_top,
            text="Пароль приложения (зашифрован в Windows):",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        )
        self.pass_lbl.pack(side="left")

        pass_row = tk.Frame(mail_card, bg=COLOR_CARD)
        pass_row.pack(fill="x", pady=(2, 4))

        self.app_pwd_shown = False
        self.app_pwd_entry = tk.Entry(
            pass_row,
            font=("Segoe UI", 9),
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            show="•",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.app_pwd_entry.pack(side="left", fill="x", expand=True, ipady=3)

        self.eye_mail_btn = tk.Button(
            pass_row,
            text="👁️",
            font=("Segoe UI", 9),
            bg=COLOR_BTN_SECONDARY,
            fg=COLOR_TEXT_SECONDARY,
            relief="flat",
            cursor="hand2",
            command=self._toggle_mail_pwd_eye,
            width=3,
        )
        self.eye_mail_btn.pack(side="right", padx=(4, 0))

        self.custom_server_frame = tk.Frame(mail_card, bg=COLOR_CARD)
        custom_row = tk.Frame(self.custom_server_frame, bg=COLOR_CARD)
        custom_row.pack(fill="x", pady=(2, 4))

        srv_col = tk.Frame(custom_row, bg=COLOR_CARD)
        srv_col.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(
            srv_col,
            text="IMAP Сервер:",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        ).pack(anchor="w")
        self.server_entry = tk.Entry(
            srv_col,
            font=("Segoe UI", 9),
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.server_entry.pack(fill="x", ipady=3, pady=(2, 0))

        port_col = tk.Frame(custom_row, bg=COLOR_CARD)
        port_col.pack(side="right", padx=(6, 0))
        tk.Label(
            port_col,
            text="Порт (SSL):",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        ).pack(anchor="w")
        self.port_entry = tk.Entry(
            port_col,
            font=("Segoe UI", 9),
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            width=8,
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.port_entry.pack(fill="x", ipady=3, pady=(2, 0))
        self.port_entry.insert(0, "993")

        self.guide_box = tk.Frame(mail_card, bg=COLOR_CARD)
        self.guide_box.pack(fill="x", pady=(4, 4))

        self.guide_title_lbl = tk.Label(
            self.guide_box,
            text="Инструкция:",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
            anchor="w",
        )
        self.guide_title_lbl.pack(anchor="w")

        self.guide_items_frame = tk.Frame(self.guide_box, bg=COLOR_CARD)
        self.guide_items_frame.pack(fill="x", pady=(2, 0))

        self.test_conn_btn = tk.Button(
            mail_card,
            text="⚡ Проверить подключение к почте",
            font=("Segoe UI", 8, "bold"),
            bg=COLOR_BTN_SECONDARY,
            fg=COLOR_LINK,
            activebackground=COLOR_BTN_SECONDARY_HOVER,
            activeforeground=COLOR_LINK_HOVER,
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=4,
            command=self._test_email_connection,
        )
        self.test_conn_btn.pack(anchor="e", pady=(2, 0))

        acc_card = tk.Frame(
            container,
            bg=COLOR_CARD,
            highlightbackground=COLOR_CARD_BORDER,
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        acc_card.pack(fill="x", pady=(0, 10))

        tk.Label(
            acc_card,
            text="🎮 Шаг 2: Привязка первого аккаунта Riot Games / Valorant",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(
            acc_card,
            text="Имя / Заметка (например: Основной):",
            font=("Segoe UI", 8),
            fg=COLOR_TEXT_SECONDARY,
            bg=COLOR_CARD,
        ).pack(anchor="w")
        self.acc_name_entry = tk.Entry(
            acc_card,
            font=("Segoe UI", 9),
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.acc_name_entry.pack(fill="x", ipady=3, pady=(2, 6))
        self.acc_name_entry.insert(0, "Основной")

        creds_row = tk.Frame(acc_card, bg=COLOR_CARD)
        creds_row.pack(fill="x")

        log_col = tk.Frame(creds_row, bg=COLOR_CARD)
        log_col.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Label(
            log_col,
            text="Логин Riot Games:",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        ).pack(anchor="w")
        self.acc_login_entry = tk.Entry(
            log_col,
            font=("Segoe UI", 9),
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.acc_login_entry.pack(fill="x", ipady=3, pady=(2, 0))

        pwd_col = tk.Frame(creds_row, bg=COLOR_CARD)
        pwd_col.pack(side="right", fill="x", expand=True, padx=(6, 0))
        tk.Label(
            pwd_col,
            text="Пароль Riot (шифруется DPAPI):",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        ).pack(anchor="w")

        acc_pwd_row = tk.Frame(pwd_col, bg=COLOR_CARD)
        acc_pwd_row.pack(fill="x", pady=(2, 0))

        self.acc_pwd_shown = False
        self.acc_pwd_entry = tk.Entry(
            acc_pwd_row,
            font=("Segoe UI", 9),
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            show="•",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.acc_pwd_entry.pack(side="left", fill="x", expand=True, ipady=3)

        self.eye_acc_btn = tk.Button(
            acc_pwd_row,
            text="👁️",
            font=("Segoe UI", 9),
            bg=COLOR_BTN_SECONDARY,
            fg=COLOR_TEXT_SECONDARY,
            relief="flat",
            cursor="hand2",
            command=self._toggle_acc_pwd_eye,
            width=3,
        )
        self.eye_acc_btn.pack(side="right", padx=(4, 0))

        self.status_lbl = tk.Label(
            container,
            text="",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_TEXT_SECONDARY,
            bg=COLOR_BG,
            wraplength=510,
            justify="center",
        )
        self.status_lbl.pack(fill="x", pady=(0, 6))

        self.finish_btn = tk.Button(
            container,
            text="🚀 Сохранить и открыть Riot Automatic",
            font=("Segoe UI", 10, "bold"),
            bg=COLOR_ACCENT,
            fg="#ffffff",
            activebackground=COLOR_ACCENT_HOVER,
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            pady=9,
            command=self._on_finish_click,
        )
        self.finish_btn.pack(fill="x")

        self._select_provider("yandex")

    def _toggle_mail_pwd_eye(self):
        self.app_pwd_shown = not self.app_pwd_shown
        self.app_pwd_entry.config(show="" if self.app_pwd_shown else "•")
        self.eye_mail_btn.config(text="🙈" if self.app_pwd_shown else "👁️")

    def _toggle_acc_pwd_eye(self):
        self.acc_pwd_shown = not self.acc_pwd_shown
        self.acc_pwd_entry.config(show="" if self.acc_pwd_shown else "•")
        self.eye_acc_btn.config(text="🙈" if self.acc_pwd_shown else "👁️")

    def _select_provider(self, provider_id: str):
        self.current_provider_id = provider_id
        pdata = MAIL_PROVIDERS[provider_id]

        for pid, b in self.provider_buttons.items():
            if pid == provider_id:
                b.config(bg=COLOR_ACCENT, fg="#ffffff", activebackground=COLOR_ACCENT_HOVER)
            else:
                b.config(bg=COLOR_BTN_SECONDARY, fg=COLOR_TEXT_SECONDARY, activebackground=COLOR_BTN_SECONDARY_HOVER)

        self.mail_lbl.config(text=f"Email адрес ({pdata['name']}):")

        if provider_id == "custom":
            self.custom_server_frame.pack(fill="x", before=self.guide_box, pady=(2, 4))
        else:
            self.custom_server_frame.pack_forget()

        for w in self.guide_items_frame.winfo_children():
            w.destroy()

        self.guide_title_lbl.config(text=f"📋 {pdata['guide_title']}")

        for bold_t, desc in pdata["steps"]:
            step_box = tk.Frame(self.guide_items_frame, bg=COLOR_CARD)
            step_box.pack(fill="x", anchor="w", pady=(2, 2))
            tk.Label(
                step_box,
                text=f"• {bold_t}:",
                font=("Segoe UI", 8, "bold"),
                fg=COLOR_TEXT_PRIMARY,
                bg=COLOR_CARD,
                anchor="w",
            ).pack(fill="x", anchor="w")
            tk.Label(
                step_box,
                text=desc,
                font=("Segoe UI", 8),
                fg=COLOR_TEXT_SECONDARY,
                bg=COLOR_CARD,
                wraplength=480,
                justify="left",
                anchor="w",
            ).pack(fill="x", anchor="w", padx=(10, 0))

        if pdata["links"]:
            for text, url in pdata["links"]:
                btn = tk.Button(
                    self.guide_items_frame,
                    text=f"{text} ↗",
                    font=("Segoe UI", 8, "underline"),
                    fg=COLOR_LINK,
                    activeforeground=COLOR_LINK_HOVER,
                    bg=COLOR_CARD,
                    activebackground=COLOR_CARD,
                    bd=0,
                    anchor="w",
                    cursor="hand2",
                    command=lambda u=url: webbrowser.open_new_tab(u),
                )
                btn.pack(anchor="w", pady=(1, 1))

    def _test_email_connection(self):
        if self.is_testing:
            return
        if self.current_provider_id == "custom":
            server = self.server_entry.get().strip()
            port_str = self.port_entry.get().strip()
            try:
                port = int(port_str)
            except ValueError:
                port = 993
            if not server:
                self.status_lbl.config(text="⚠️ Укажите IMAP сервер (например: imap.rambler.ru).", fg=COLOR_WARNING)
                self.server_entry.focus_set()
                return
        else:
            server = pdata["server"]
            port = pdata["port"]

        if not email or not pwd:
            self.status_lbl.config(text="⚠️ Введите email и пароль приложения для проверки.", fg=COLOR_WARNING)
            return

        self.is_testing = True
        self.status_lbl.config(text=f"🔄 Проверка подключения к {server}...", fg=COLOR_LINK)
        self.test_conn_btn.config(state="disabled")

        def run_test():
            success, msg = test_imap_credentials(server, port, email, pwd)
            self.is_testing = False
            self.after(0, lambda: self.test_conn_btn.config(state="normal"))
            if success:
                self.after(0, lambda: self.status_lbl.config(text="✅ Подключение к почте успешно!", fg=COLOR_SUCCESS))
            else:
                self.after(0, lambda: self.status_lbl.config(text=f"❌ {msg}", fg=COLOR_ERROR))

        threading.Thread(target=run_test, daemon=True).start()

    def _on_finish_click(self):
        email = self.email_entry.get().strip()
        app_pwd = self.app_pwd_entry.get().strip().replace(" ", "")
        acc_name = self.acc_name_entry.get().strip()
        acc_login = self.acc_login_entry.get().strip()
        acc_pwd = self.acc_pwd_entry.get().strip()

        if not email:
            self.status_lbl.config(text="⚠️ Укажите адрес электронной почты.", fg=COLOR_WARNING)
            self.email_entry.focus_set()
            return

        if not app_pwd:
            self.status_lbl.config(text="⚠️ Введите пароль приложения для почты.", fg=COLOR_WARNING)
            self.app_pwd_entry.focus_set()
            return

        if not acc_login:
            self.status_lbl.config(text="⚠️ Введите логин от аккаунта Riot Games.", fg=COLOR_WARNING)
            self.acc_login_entry.focus_set()
            return

        if not acc_pwd:
            self.status_lbl.config(text="⚠️ Введите пароль от аккаунта Riot Games.", fg=COLOR_WARNING)
            self.acc_pwd_entry.focus_set()
            return

        pdata = MAIL_PROVIDERS[self.current_provider_id]
        if self.current_provider_id == "custom":
            server = self.server_entry.get().strip()
            port_str = self.port_entry.get().strip()
            try:
                port = int(port_str)
            except ValueError:
                port = 993
            if not server:
                self.status_lbl.config(text="⚠️ Укажите адрес IMAP сервера.", fg=COLOR_WARNING)
                self.server_entry.focus_set()
                return
        else:
            server = pdata["server"]
            port = pdata["port"]

        try:

            enc_mail_pwd = encrypt_string(app_pwd)

            cfg = {
                "mail_provider": self.current_provider_id,
                "email": email,
                "encrypted_app_password": enc_mail_pwd,
                "imap_server": server,
                "imap_port": port,
                "check_interval_seconds": 5,
                "auto_copy_to_clipboard": True,
                "show_notifications": True,
                "play_sound": True,
                "is_configured": True,
            }
            os.makedirs(BASE_DIR, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)

            add_account(
                name=acc_name or acc_login,
                login=acc_login,
                password=acc_pwd,
                email=email,
                mail_provider=self.current_provider_id,
                encrypted_app_password=enc_mail_pwd,
                imap_server=server,
                imap_port=port,
                is_selected=True,
            )

            self.status_lbl.config(text="✅ Настройки и аккаунт успешно сохранены!", fg=COLOR_SUCCESS)

            def finish():
                self.destroy()
                if self.on_completed:
                    self.on_completed(cfg)

            self.after(600, finish)
        except Exception as e:
            logger.error("Error saving first run wizard: %s", e)
            self.status_lbl.config(text=f"❌ Ошибка сохранения: {e}", fg=COLOR_ERROR)


def show_first_run_wizard_if_needed(on_completed: Optional[Callable] = None) -> bool:
    """
    Checks if first run wizard is needed. If so, opens it synchronously.
    Returns True if wizard was shown and completed, False if already configured.
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if cfg.get("is_configured", False) and cfg.get("email"):
                    accounts = load_accounts()
                    if accounts:
                        return False
        except Exception:
            pass

    wizard = FirstRunWizardDialog(on_completed=on_completed)
    wizard.mainloop()
    return True


if __name__ == "__main__":
    show_first_run_wizard_if_needed()
