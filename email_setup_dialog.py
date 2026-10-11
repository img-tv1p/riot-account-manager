"""
Email Setup Dialog for Riot Automatic v2.
Interactive GUI to configure IMAP credentials for Yandex, Mail.ru, Gmail, or Custom IMAP.
Features dynamic step-by-step guides with clickable links, live IMAP connection testing,
and automatic config.json updates.
"""
import os
import sys
import json
import socket
import imaplib
import webbrowser
import threading
import logging
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, Dict, Any
from gui_clipboard_helper import enable_universal_clipboard

logger = logging.getLogger(__name__)

COLOR_BG = "#18181b"
COLOR_CARD = "#222226"
COLOR_CARD_BORDER = "#2e2e34"
COLOR_ACCENT = "#d13639"
COLOR_ACCENT_HOVER = "#e5484c"
COLOR_ACCENT_BG = "#38191b"
COLOR_SUCCESS = "#22c55e"
COLOR_WARNING = "#f59e0b"
COLOR_ERROR = "#ef4444"
COLOR_TEXT_PRIMARY = "#f4f4f5"
COLOR_TEXT_SECONDARY = "#a1a1aa"
COLOR_TEXT_MUTED = "#71717a"
COLOR_INPUT_BG = "#2a2a30"
COLOR_INPUT_BORDER = "#3f3f46"
COLOR_LINK = "#60a5fa"
COLOR_LINK_HOVER = "#93c5fd"
COLOR_BTN_SECONDARY = "#27272a"
COLOR_BTN_SECONDARY_HOVER = "#3f3f46"

MAIL_PROVIDERS = {
    "yandex": {
        "id": "yandex",
        "name": "Яндекс Почта",
        "btn_title": "🔴 Яндекс",
        "domains": ["@yandex.ru", "@ya.ru", "@yandex.com", "@yandex.by", "@yandex.kz"],
        "server": "imap.yandex.ru",
        "port": 993,
        "ssl": True,
        "email_placeholder": "username@yandex.ru",
        "password_hint": "Пароль приложения (16 символов латиницей)",
        "guide_title": "Инструкция для Яндекс Почты:",
        "steps": [
            ("1. Включите доступ по IMAP", "В настройках Яндекс Почты откройте раздел «Почтовые программы» и отметьте галочку «С сервера по протоколу IMAP»."),
            ("2. Создайте пароль приложения", "Перейдите в Яндекс ID в раздел «Безопасность» -> «Пароли приложений»."),
            ("3. Выберите тип «Почта»", "Нажмите «Создать пароль», тип выберите «Почта», задайте имя (например: Riot Grabber)."),
            ("4. Скопируйте пароль", "Скопируйте полученный 16-значный пароль и вставьте в поле выше."),
        ],
        "links": [
            ("🔑 Создать пароль приложения в Яндекс ID", "https://id.yandex.ru/security/app-passwords"),
            ("⚙️ Включить IMAP в настройках Яндекс Почты", "https://mail.yandex.ru/#setup/client"),
        ],
    },
    "mailru": {
        "id": "mailru",
        "name": "Mail.ru",
        "btn_title": "🔵 Mail.ru",
        "domains": ["@mail.ru", "@inbox.ru", "@list.ru", "@bk.ru"],
        "server": "imap.mail.ru",
        "port": 993,
        "ssl": True,
        "email_placeholder": "username@mail.ru",
        "password_hint": "Пароль для внешних приложений Mail.ru",
        "guide_title": "Инструкция для Mail.ru:",
        "steps": [
            ("1. Создайте пароль приложения", "Перейдите по кнопке ниже в раздел «Пароли для внешних приложений» (IMAP в Mail.ru включён по умолчанию)."),
            ("2. Добавьте пароль", "Нажмите «Добавить», введите имя программы (например: Riot Grabber) и нажмите «Создать»."),
            ("3. Скопируйте пароль", "Скопируйте сгенерированный пароль приложения и вставьте в поле выше."),
        ],
        "links": [
            ("🔑 Создать пароль для приложений в Mail.ru", "https://account.mail.ru/user/2-step-auth/passwords"),
        ],
    },
    "gmail": {
        "id": "gmail",
        "name": "Gmail (Google)",
        "btn_title": "🟢 Gmail",
        "domains": ["@gmail.com", "@googlemail.com"],
        "server": "imap.gmail.com",
        "port": 993,
        "ssl": True,
        "email_placeholder": "username@gmail.com",
        "password_hint": "Пароль приложений Google (16 символов)",
        "guide_title": "Инструкция для Google Gmail:",
        "steps": [
            ("1. Двухэтапная аутентификация", "В Google Аккаунте обязательно должна быть включена «2-этапная аутентификация»."),
            ("2. Создайте пароль приложения", "Перейдите на страницу «Пароли приложений» по кнопке ниже (IMAP в Google включён по умолчанию)."),
            ("3. Задайте имя", "Укажите название приложения (например: Riot Grabber) и нажмите «Создать»."),
            ("4. Вставьте пароль", "Скопируйте 16-значный пароль (пробелы удалятся автоматически) и вставьте в поле выше."),
        ],
        "links": [
            ("🔑 Создать пароль приложения Google", "https://myaccount.google.com/apppasswords"),
            ("🛡️ 2-этапная аутентификация Google", "https://myaccount.google.com/signinoptions/two-step-verification"),
        ],
    },
    "custom": {
        "id": "custom",
        "name": "Другая почта",
        "btn_title": "⚙️ Другая",
        "domains": [],
        "server": "",
        "port": 993,
        "ssl": True,
        "email_placeholder": "username@yourdomain.com",
        "password_hint": "Пароль приложения или пароль ящика",
        "guide_title": "Инструкция для своего IMAP сервера:",
        "steps": [
            ("1. Адрес почты", "Укажите ваш полный адрес email."),
            ("2. Сервер и порт IMAP", "Укажите IMAP-сервер вашего провайдера (например: imap.rambler.ru, порт 993)."),
            ("3. Разрешите IMAP в настройках", "В веб-интерфейсе почтового сервиса включите протокол IMAP."),
            ("4. Пароль приложения", "Если включена 2FA, сгенерируйте пароль приложения в безопасности аккаунта."),
        ],
        "links": [],
    },
}


def test_imap_credentials(server: str, port: int, email: str, password: str, timeout: int = 12) -> tuple:
    """Tests IMAP authentication synchronously. Returns (bool, str)."""
    server = server.strip()
    email = email.strip()
    password = password.strip().replace(" ", "")

    if not server:
        return False, "Не указан IMAP сервер"
    if not email:
        return False, "Не указан адрес почты"
    if not password:
        return False, "Не указан пароль приложения"

    try:
        client = imaplib.IMAP4_SSL(server, int(port), timeout=timeout)
        client.login(email, password)
        try:
            client.logout()
        except Exception:
            pass
        return True, "Успешное подключение к IMAP серверу!"
    except imaplib.IMAP4.error as e:
        err = ""
        if e.args:
            val = e.args[0]
            err = val.decode("utf-8", errors="ignore") if isinstance(val, bytes) else str(val)
        else:
            err = str(e)
        logger.warning("IMAP Auth failed for %s: %s", email, err)
        if any(w in err.lower() for w in ["auth", "credential", "invalid", "password", "failure", "disabled", "bad"]):
            return False, "Неверный пароль приложения или логин. Проверьте правильность и включен ли IMAP в настройках почты."
        return False, f"Ошибка авторизации IMAP: {err}"
    except (socket.timeout, TimeoutError):
        return False, f"Таймаут подключения к {server}:{port}. Проверьте сервер и интернет."
    except (socket.gaierror, socket.error, OSError) as e:
        return False, f"Ошибка сети при подключении к {server}:{port}: {e}"
    except Exception as e:
        return False, f"Ошибка: {e}"


class EmailSetupDialog(tk.Toplevel):
    """Modern setup window for email credentials and provider selection."""

    def __init__(
        self,
        parent: Optional[tk.Tk] = None,
        config_path: Optional[str] = None,
        initial_config: Optional[Dict[str, Any]] = None,
        on_saved: Optional[Callable[[Dict[str, Any]], None]] = None,
        is_first_launch: bool = False,
    ):
        if parent is None:
            self._standalone = True
            self.root = tk.Tk()
            super().__init__(self.root)
        else:
            self._standalone = False
            self.root = parent
            super().__init__(parent)

        self.config_path = config_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config.json"
        )
        self.initial_config = initial_config or {}
        self.on_saved = on_saved
        self.is_first_launch = is_first_launch
        self.is_testing = False

        self.title("Riot Account Manager - RAM — Настройка почты" if not is_first_launch else "Первоначальная настройка Riot Account Manager - RAM")
        enable_universal_clipboard(self)
        self.geometry("560x730")
        self.resizable(False, False)
        self.configure(bg=COLOR_BG)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_dir, "icon.ico")
        if not os.path.exists(icon_path):
            bundle_dir = getattr(sys, "_MEIPASS", base_dir)
            icon_path = os.path.join(bundle_dir, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        if not self._standalone and parent:
            self.transient(parent)
            self.grab_set()

        self.current_provider_id = self._detect_initial_provider()
        self.provider_buttons = {}

        self._build_ui()
        self._center_window()

        self._load_values()

    def _detect_initial_provider(self) -> str:
        saved_provider = self.initial_config.get("mail_provider")
        if saved_provider in MAIL_PROVIDERS:
            return saved_provider

        email = (self.initial_config.get("email") or "").lower().strip()
        server = (self.initial_config.get("imap_server") or "").lower().strip()

        if "gmail" in email or "gmail" in server:
            return "gmail"
        if any(d in email for d in ["mail.ru", "inbox.ru", "list.ru", "bk.ru"]) or "mail.ru" in server:
            return "mailru"
        if any(d in email for d in ["yandex", "ya.ru"]) or "yandex" in server:
            return "yandex"
        if server and server != "imap.yandex.ru":
            return "custom"
        return "yandex"

    def _center_window(self):
        self.update_idletasks()
        w = 560
        h = 730
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(20, (sw - w) // 2)
        y = max(20, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        main_container = tk.Frame(self, bg=COLOR_BG, padx=22, pady=18)
        main_container.pack(fill="both", expand=True)

        header_frame = tk.Frame(main_container, bg=COLOR_BG)
        header_frame.pack(fill="x", pady=(0, 14))

        title_text = "🚀 Добро пожаловать в Riot Account Manager - RAM!" if self.is_first_launch else "📧 Настройка почты для кодов 2FA"
        title_lbl = tk.Label(
            header_frame,
            text=title_text,
            font=("Segoe UI", 13, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_BG,
        )
        title_lbl.pack(anchor="w")

        sub_text = (
            "Для автоматического перехвата кодов Riot Games укажите ваш почтовый ящик.\n"
            "Выберите почтовый сервис ниже и следуйте шагам инструкции:"
        )
        sub_lbl = tk.Label(
            header_frame,
            text=sub_text,
            font=("Segoe UI", 9),
            fg=COLOR_TEXT_SECONDARY,
            bg=COLOR_BG,
            justify="left",
        )
        sub_lbl.pack(anchor="w", pady=(4, 0))

        btn_container = tk.Frame(main_container, bg=COLOR_BG)
        btn_container.pack(fill="x", pady=(0, 14))

        for pid, pdata in MAIL_PROVIDERS.items():
            b = tk.Button(
                btn_container,
                text=pdata["btn_title"],
                font=("Segoe UI", 9, "bold"),
                relief="flat",
                cursor="hand2",
                command=lambda p=pid: self._select_provider(p),
                padx=12,
                pady=6,
            )
            b.pack(side="left", padx=(0, 6), expand=True, fill="x")
            self.provider_buttons[pid] = b

        self.input_card = tk.Frame(
            main_container,
            bg=COLOR_CARD,
            highlightbackground=COLOR_CARD_BORDER,
            highlightthickness=1,
            padx=16,
            pady=12,
        )
        self.input_card.pack(fill="x", pady=(0, 12))

        self.email_label = tk.Label(
            self.input_card,
            text="Адрес электронной почты:",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        )
        self.email_label.pack(anchor="w", pady=(0, 2))

        self.email_entry = tk.Entry(
            self.input_card,
            font=("Segoe UI", 10),
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.email_entry.pack(fill="x", ipady=4, pady=(0, 8))

        self.pass_label = tk.Label(
            self.input_card,
            text="Пароль приложения:",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        )
        self.pass_label.pack(anchor="w", pady=(0, 2))

        pass_row = tk.Frame(self.input_card, bg=COLOR_CARD)
        pass_row.pack(fill="x", pady=(0, 4))

        self.password_show = False
        self.pass_entry = tk.Entry(
            pass_row,
            font=("Segoe UI", 10),
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            show="•",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.pass_entry.pack(side="left", fill="x", expand=True, ipady=4)

        self.eye_btn = tk.Button(
            pass_row,
            text="👁️",
            font=("Segoe UI", 10),
            bg=COLOR_BTN_SECONDARY,
            fg=COLOR_TEXT_SECONDARY,
            activebackground=COLOR_BTN_SECONDARY_HOVER,
            activeforeground=COLOR_TEXT_PRIMARY,
            relief="flat",
            cursor="hand2",
            command=self._toggle_password_visibility,
            width=3,
        )
        self.eye_btn.pack(side="right", padx=(6, 0))

        self.pass_hint_lbl = tk.Label(
            self.input_card,
            text="⚠️ Не обычный пароль от почты, а специальный Пароль Приложения (см. инструкцию ниже).",
            font=("Segoe UI", 8),
            fg=COLOR_WARNING,
            bg=COLOR_CARD,
            anchor="w",
        )
        self.pass_hint_lbl.pack(anchor="w", pady=(0, 4))

        self.custom_frame = tk.Frame(self.input_card, bg=COLOR_CARD)
        
        custom_row = tk.Frame(self.custom_frame, bg=COLOR_CARD)
        custom_row.pack(fill="x", pady=(4, 0))

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

        self.guide_card = tk.Frame(
            main_container,
            bg=COLOR_CARD,
            highlightbackground=COLOR_CARD_BORDER,
            highlightthickness=1,
            padx=16,
            pady=12,
        )
        self.guide_card.pack(fill="both", expand=True, pady=(0, 12))

        self.guide_title_lbl = tk.Label(
            self.guide_card,
            text="📋 Инструкция по настройке:",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
            anchor="w",
        )
        self.guide_title_lbl.pack(anchor="w", pady=(0, 6))

        self.guide_content_frame = tk.Frame(self.guide_card, bg=COLOR_CARD)
        self.guide_content_frame.pack(fill="both", expand=True)

        self.status_lbl = tk.Label(
            main_container,
            text="",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_TEXT_SECONDARY,
            bg=COLOR_BG,
            wraplength=510,
            justify="center",
        )
        self.status_lbl.pack(fill="x", pady=(0, 8))

        actions_frame = tk.Frame(main_container, bg=COLOR_BG)
        actions_frame.pack(fill="x")

        self.test_save_btn = tk.Button(
            actions_frame,
            text="⚡ Проверить подключение и сохранить",
            font=("Segoe UI", 10, "bold"),
            bg=COLOR_ACCENT,
            fg="#ffffff",
            activebackground=COLOR_ACCENT_HOVER,
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=8,
            command=self._on_test_and_save_click,
        )
        self.test_save_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.skip_btn = tk.Button(
            actions_frame,
            text="Сохранить без теста",
            font=("Segoe UI", 9),
            bg=COLOR_BTN_SECONDARY,
            fg=COLOR_TEXT_SECONDARY,
            activebackground=COLOR_BTN_SECONDARY_HOVER,
            activeforeground=COLOR_TEXT_PRIMARY,
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=8,
            command=self._on_save_without_test_click,
        )
        self.skip_btn.pack(side="right", padx=(6, 0))

        self._select_provider(self.current_provider_id)

    def _toggle_password_visibility(self):
        self.password_show = not self.password_show
        if self.password_show:
            self.pass_entry.config(show="")
            self.eye_btn.config(text="🙈")
        else:
            self.pass_entry.config(show="•")
            self.eye_btn.config(text="👁️")

    def _select_provider(self, provider_id: str):
        """Updates UI state when switching mail provider."""
        self.current_provider_id = provider_id
        pdata = MAIL_PROVIDERS[provider_id]

        for pid, b in self.provider_buttons.items():
            if pid == provider_id:
                b.config(
                    bg=COLOR_ACCENT,
                    fg="#ffffff",
                    activebackground=COLOR_ACCENT_HOVER,
                    activeforeground="#ffffff",
                )
            else:
                b.config(
                    bg=COLOR_BTN_SECONDARY,
                    fg=COLOR_TEXT_SECONDARY,
                    activebackground=COLOR_BTN_SECONDARY_HOVER,
                    activeforeground=COLOR_TEXT_PRIMARY,
                )

        self.email_label.config(text=f"Адрес электронной почты ({pdata['name']}):")
        self.pass_label.config(text=pdata["password_hint"] + ":")

        if provider_id == "custom":
            self.custom_frame.pack(fill="x", pady=(4, 0))
        else:
            self.custom_frame.pack_forget()

        self._render_guide(pdata)

    def _render_guide(self, pdata: dict):
        """Renders step-by-step instructions and clickable links for the selected service."""

        for w in self.guide_content_frame.winfo_children():
            w.destroy()

        self.guide_title_lbl.config(text=f"📋 {pdata['guide_title']}")

        steps_box = tk.Frame(self.guide_content_frame, bg=COLOR_CARD)
        steps_box.pack(fill="x", pady=(0, 8))

        for bold_title, desc in pdata["steps"]:
            step_row = tk.Frame(steps_box, bg=COLOR_CARD)
            step_row.pack(fill="x", anchor="w", pady=(2, 2))

            bullet_lbl = tk.Label(
                step_row,
                text="•",
                font=("Segoe UI", 10, "bold"),
                fg=COLOR_ACCENT,
                bg=COLOR_CARD,
            )
            bullet_lbl.pack(side="left", anchor="n", padx=(0, 6))

            text_frame = tk.Frame(step_row, bg=COLOR_CARD)
            text_frame.pack(side="left", fill="x", expand=True)

            title_lbl = tk.Label(
                text_frame,
                text=bold_title + ":",
                font=("Segoe UI", 9, "bold"),
                fg=COLOR_TEXT_PRIMARY,
                bg=COLOR_CARD,
                anchor="w",
            )
            title_lbl.pack(anchor="w", fill="x")

            desc_lbl = tk.Label(
                text_frame,
                text=desc,
                font=("Segoe UI", 8),
                fg=COLOR_TEXT_SECONDARY,
                bg=COLOR_CARD,
                anchor="w",
                wraplength=480,
                justify="left",
            )
            desc_lbl.pack(anchor="w", fill="x", padx=(2, 0))

        if pdata["links"]:
            links_hdr = tk.Label(
                self.guide_content_frame,
                text="Прямые ссылки для перехода в настройки:",
                font=("Segoe UI", 8, "bold"),
                fg=COLOR_TEXT_MUTED,
                bg=COLOR_CARD,
                anchor="w",
            )
            links_hdr.pack(anchor="w", pady=(4, 4))

            links_box = tk.Frame(self.guide_content_frame, bg=COLOR_CARD)
            links_box.pack(fill="x", anchor="w")

            for text, url in pdata["links"]:
                link_btn = tk.Button(
                    links_box,
                    text=f"{text} ↗",
                    font=("Segoe UI", 9, "underline"),
                    fg=COLOR_LINK,
                    activeforeground=COLOR_LINK_HOVER,
                    bg=COLOR_CARD,
                    activebackground=COLOR_CARD,
                    bd=0,
                    cursor="hand2",
                    anchor="w",
                    command=lambda u=url: webbrowser.open_new_tab(u),
                )
                link_btn.pack(anchor="w", pady=(1, 1))

    def _load_values(self):
        """Populates fields from existing configuration if present."""
        email = self.initial_config.get("email", "")

        if "your_email" in email:
            email = ""
        self.email_entry.delete(0, "end")
        self.email_entry.insert(0, email)

        pwd = self.initial_config.get("app_password", "")
        if "your_yandex" in pwd:
            pwd = ""
        self.pass_entry.delete(0, "end")
        self.pass_entry.insert(0, pwd)

        srv = self.initial_config.get("imap_server", "")
        self.server_entry.delete(0, "end")
        self.server_entry.insert(0, srv if srv else "")

        port = str(self.initial_config.get("imap_port", 993))
        self.port_entry.delete(0, "end")
        self.port_entry.insert(0, port)

    def _get_current_inputs(self) -> dict:
        pdata = MAIL_PROVIDERS[self.current_provider_id]
        email = self.email_entry.get().strip()
        pwd = self.pass_entry.get().strip().replace(" ", "")

        if self.current_provider_id == "custom":
            server = self.server_entry.get().strip()
            try:
                port = int(self.port_entry.get().strip())
            except ValueError:
                port = 993
        else:
            server = pdata["server"]
            port = pdata["port"]

        return {
            "mail_provider": self.current_provider_id,
            "email": email,
            "app_password": pwd,
            "imap_server": server,
            "imap_port": port,
            "is_configured": True,
        }

    def _save_to_disk(self, new_data: dict) -> bool:
        """Saves configuration safely to config.json (and synchronizes across install dir)."""
        try:
            cfg = dict(self.initial_config)
            cfg.update(new_data)

            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)

            logger.info("Saved config to %s", self.config_path)

            try:
                from app_installer import get_install_dir
                inst_dir = get_install_dir()
                inst_cfg = os.path.join(inst_dir, "config.json")
                if inst_cfg != self.config_path and os.path.exists(inst_dir):
                    with open(inst_cfg, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=2, ensure_ascii=False)
                    logger.info("Synced config to install dir: %s", inst_cfg)
            except Exception as e:
                logger.debug("Could not sync to install dir: %s", e)

            if self.on_saved:
                try:
                    self.on_saved(cfg)
                except Exception as e:
                    logger.error("Error in on_saved callback: %s", e)

            return True
        except Exception as e:
            logger.error("Failed to save config: %s", e)
            self.status_lbl.config(text=f"❌ Ошибка сохранения: {e}", fg=COLOR_ERROR)
            return False

    def _on_test_and_save_click(self):
        """Runs live IMAP test in background thread and saves on success."""
        if self.is_testing:
            return

        data = self._get_current_inputs()
        email = data["email"]
        pwd = data["app_password"]
        server = data["imap_server"]
        port = data["imap_port"]

        if not email:
            self.status_lbl.config(text="⚠️ Пожалуйста, введите адрес электронной почты.", fg=COLOR_WARNING)
            self.email_entry.focus_set()
            return

        if not pwd:
            self.status_lbl.config(text="⚠️ Пожалуйста, введите пароль приложения.", fg=COLOR_WARNING)
            self.pass_entry.focus_set()
            return

        if not server:
            self.status_lbl.config(text="⚠️ Пожалуйста, укажите IMAP сервер.", fg=COLOR_WARNING)
            return

        self.is_testing = True
        self.status_lbl.config(
            text=f"🔄 Проверка подключения к {server}:{port}...",
            fg=COLOR_LINK,
        )
        self.test_save_btn.config(state="disabled")
        self.skip_btn.config(state="disabled")

        def run_test():
            success, msg = test_imap_credentials(server, port, email, pwd)

            def handle_result():
                self.is_testing = False
                self.test_save_btn.config(state="normal")
                self.skip_btn.config(state="normal")

                if success:
                    self.status_lbl.config(
                        text="✅ Подключение успешно! Настройки сохранены.",
                        fg=COLOR_SUCCESS,
                    )
                    self._save_to_disk(data)

                    self.after(1100, self._close_dialog)
                else:
                    self.status_lbl.config(
                        text=f"❌ {msg}",
                        fg=COLOR_ERROR,
                    )

            self.after(0, handle_result)

        threading.Thread(target=run_test, daemon=True).start()

    def _on_save_without_test_click(self):
        """Saves current values immediately without performing live connection test."""
        data = self._get_current_inputs()
        if not data["email"]:
            self.status_lbl.config(text="⚠️ Введите адрес электронной почты.", fg=COLOR_WARNING)
            return
        if not data["app_password"]:
            self.status_lbl.config(text="⚠️ Введите пароль приложения.", fg=COLOR_WARNING)
            return

        if self._save_to_disk(data):
            self.status_lbl.config(text="✅ Настройки сохранены.", fg=COLOR_SUCCESS)
            self.after(600, self._close_dialog)

    def _close_dialog(self):
        if self._standalone:
            self.root.destroy()
        else:
            self.destroy()

    def show(self):
        if self._standalone:
            self.root.mainloop()


def open_email_setup_dialog(
    parent=None,
    config_path=None,
    initial_config=None,
    on_saved=None,
    is_first_launch=False,
):
    """Convenience helper to show EmailSetupDialog."""
    dlg = EmailSetupDialog(
        parent=parent,
        config_path=config_path,
        initial_config=initial_config,
        on_saved=on_saved,
        is_first_launch=is_first_launch,
    )
    if parent is None:
        dlg.show()
    return dlg


if __name__ == "__main__":

    open_email_setup_dialog(is_first_launch=True)
