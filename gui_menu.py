"""Modern and lightweight Tkinter GUI window for Riot Accounts & 2FA Codes.
Optimized for 0 RAM overhead when closed (completely unloads from memory).
Supports multi-account management with individual email bindings, DPAPI encryption,
dynamic mailbox switching, and visual active account selection.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os
import threading
import gc
import logging
import webbrowser
from typing import Optional, Callable

from gui_clipboard_helper import enable_universal_clipboard

from account_manager import (
    load_accounts,
    add_account,
    update_account,
    delete_account,
    get_account_password,
    get_saved_mailboxes,
    get_selected_account,
    set_selected_account,
)
from email_setup_dialog import (
    MAIL_PROVIDERS,
    test_imap_credentials,
    COLOR_LINK,
    COLOR_LINK_HOVER,
    open_email_setup_dialog,
)
from crypto_manager import encrypt_string, decrypt_string
from clipboard_manager import copy_to_clipboard
from riot_automator import execute_auto_login
from app_installer import is_autostart_enabled, set_autostart, get_install_dir

logger = logging.getLogger(__name__)

COLOR_BG = "#18181b"
COLOR_CARD = "#222226"
COLOR_CARD_BORDER = "#2e2e34"
COLOR_ACCENT = "#d13639"
COLOR_ACCENT_HOVER = "#e5484c"
COLOR_SUCCESS = "#22c55e"
COLOR_WARNING = "#f59e0b"
COLOR_ERROR = "#ef4444"
COLOR_TEXT_PRIMARY = "#f4f4f5"
COLOR_TEXT_SECONDARY = "#a1a1aa"
COLOR_TEXT_MUTED = "#71717a"
COLOR_INPUT_BG = "#2a2a30"
COLOR_INPUT_BORDER = "#3f3f46"
COLOR_BTN_SECONDARY = "#27272a"
COLOR_BTN_SECONDARY_HOVER = "#3f3f46"


class AccountDialog(tk.Toplevel):
    """Modal dialog to add or edit a Riot account with email binding."""

    def __init__(self, parent, account_data: Optional[dict] = None, on_saved: Optional[Callable] = None):
        super().__init__(parent)
        self.account_data = account_data
        self.on_saved = on_saved
        self.is_edit = account_data is not None

        self.title("Редактировать аккаунт" if self.is_edit else "Добавить аккаунт Riot Games")
        self.geometry("500x740")
        self.resizable(False, False)
        self.configure(bg=COLOR_BG)
        self.transient(parent)
        self.grab_set()

        self.saved_mailboxes = get_saved_mailboxes()
        self.current_provider_id = "yandex"
        self.provider_buttons = {}

        self._build_ui()
        self._center_window()
        self._load_existing_data()

    def _center_window(self):
        self.update_idletasks()
        w = 540
        h = 800
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        px = max(10, (sw - w) // 2)
        py = max(10, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{px}+{py}")

    def _build_ui(self):
        main_frame = tk.Frame(self, bg=COLOR_BG, padx=20, pady=16)
        main_frame.pack(fill="both", expand=True)

        header_lbl = tk.Label(
            main_frame,
            text="Данные аккаунта Riot Games & Почты",
            font=("Segoe UI", 12, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_BG,
        )
        header_lbl.pack(anchor="w", pady=(0, 10))

        acc_box = tk.Frame(main_frame, bg=COLOR_CARD, highlightbackground=COLOR_CARD_BORDER, highlightthickness=1, padx=14, pady=10)
        acc_box.pack(fill="x", pady=(0, 10))

        tk.Label(acc_box, text="Имя / Заметка (например, Основной):", font=("Segoe UI", 8), fg=COLOR_TEXT_SECONDARY, bg=COLOR_CARD).pack(anchor="w")
        self.name_entry = tk.Entry(
            acc_box,
            font=("Segoe UI", 9),
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.name_entry.pack(fill="x", pady=(2, 6), ipady=3)

        tk.Label(acc_box, text="Логин Riot Games:", font=("Segoe UI", 8, "bold"), fg=COLOR_TEXT_PRIMARY, bg=COLOR_CARD).pack(anchor="w")
        self.login_entry = tk.Entry(
            acc_box,
            font=("Segoe UI", 9),
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.login_entry.pack(fill="x", pady=(2, 6), ipady=3)

        pwd_title = "Пароль Riot (шифруется DPAPI):" if not self.is_edit else "Новый пароль Riot (пусто = без изменений):"
        tk.Label(acc_box, text=pwd_title, font=("Segoe UI", 8, "bold"), fg=COLOR_TEXT_PRIMARY, bg=COLOR_CARD).pack(anchor="w")

        pwd_row = tk.Frame(acc_box, bg=COLOR_CARD)
        pwd_row.pack(fill="x", pady=(2, 2))

        self.pwd_shown = False
        self.password_entry = tk.Entry(
            pwd_row,
            font=("Segoe UI", 9),
            show="•",
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.password_entry.pack(side="left", fill="x", expand=True, ipady=3)

        self.eye_pwd_btn = tk.Button(
            pwd_row,
            text="👁️",
            font=("Segoe UI", 9),
            bg=COLOR_BTN_SECONDARY,
            fg=COLOR_TEXT_SECONDARY,
            relief="flat",
            cursor="hand2",
            command=self._toggle_pwd_eye,
            width=3,
        )
        self.eye_pwd_btn.pack(side="right", padx=(4, 0))

        mail_box = tk.Frame(main_frame, bg=COLOR_CARD, highlightbackground=COLOR_CARD_BORDER, highlightthickness=1, padx=14, pady=10)
        mail_box.pack(fill="both", expand=True, pady=(0, 10))

        tk.Label(
            mail_box,
            text="📧 Привязка почты для 2FA кодов",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        ).pack(anchor="w", pady=(0, 6))

        self.mail_mode = tk.StringVar(value="existing" if self.saved_mailboxes else "new")

        if self.saved_mailboxes:
            mode_row = tk.Frame(mail_box, bg=COLOR_CARD)
            mode_row.pack(fill="x", pady=(0, 6))

            tk.Radiobutton(
                mode_row,
                text="Выбрать уже привязанную почту",
                variable=self.mail_mode,
                value="existing",
                font=("Segoe UI", 8, "bold"),
                fg=COLOR_TEXT_PRIMARY,
                bg=COLOR_CARD,
                selectcolor=COLOR_INPUT_BG,
                activebackground=COLOR_CARD,
                activeforeground=COLOR_TEXT_PRIMARY,
                command=self._update_mail_mode_view,
            ).pack(side="left", padx=(0, 10))

            tk.Radiobutton(
                mode_row,
                text="Привязать новую почту",
                variable=self.mail_mode,
                value="new",
                font=("Segoe UI", 8, "bold"),
                fg=COLOR_TEXT_PRIMARY,
                bg=COLOR_CARD,
                selectcolor=COLOR_INPUT_BG,
                activebackground=COLOR_CARD,
                activeforeground=COLOR_TEXT_PRIMARY,
                command=self._update_mail_mode_view,
            ).pack(side="left")

            self.existing_mail_frame = tk.Frame(mail_box, bg=COLOR_CARD)
            self.existing_mail_frame.pack(fill="x", pady=(2, 6))

            tk.Label(self.existing_mail_frame, text="Выберите почтовый ящик:", font=("Segoe UI", 8), fg=COLOR_TEXT_SECONDARY, bg=COLOR_CARD).pack(anchor="w")

            combobox_values = [f"{m['email']} ({m.get('mail_provider', 'почта')})" for m in self.saved_mailboxes]
            self.mail_combo = ttk.Combobox(self.existing_mail_frame, values=combobox_values, font=("Segoe UI", 9), state="readonly")
            self.mail_combo.pack(fill="x", pady=(2, 2))
            if combobox_values:
                self.mail_combo.current(0)
        else:
            self.existing_mail_frame = None

        self.new_mail_frame = tk.Frame(mail_box, bg=COLOR_CARD)

        prov_row = tk.Frame(self.new_mail_frame, bg=COLOR_CARD)
        prov_row.pack(fill="x", pady=(2, 6))

        for pid, pdata in MAIL_PROVIDERS.items():
            btn = tk.Button(
                prov_row,
                text=pdata["btn_title"],
                font=("Segoe UI", 8, "bold"),
                relief="flat",
                cursor="hand2",
                command=lambda p=pid: self._select_provider(p),
                padx=6,
                pady=3,
            )
            btn.pack(side="left", padx=(0, 4), expand=True, fill="x")
            self.provider_buttons[pid] = btn

        self.new_email_lbl = tk.Label(self.new_mail_frame, text="Email адрес:", font=("Segoe UI", 8, "bold"), fg=COLOR_TEXT_PRIMARY, bg=COLOR_CARD)
        self.new_email_lbl.pack(anchor="w")

        self.new_email_entry = tk.Entry(
            self.new_mail_frame,
            font=("Segoe UI", 9),
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.new_email_entry.pack(fill="x", pady=(2, 6), ipady=3)

        tk.Label(self.new_mail_frame, text="Пароль приложения для почты (шифруется DPAPI):", font=("Segoe UI", 8, "bold"), fg=COLOR_TEXT_PRIMARY, bg=COLOR_CARD).pack(anchor="w")

        new_pwd_row = tk.Frame(self.new_mail_frame, bg=COLOR_CARD)
        new_pwd_row.pack(fill="x", pady=(2, 4))

        self.new_app_pwd_shown = False
        self.new_app_pwd_entry = tk.Entry(
            new_pwd_row,
            font=("Segoe UI", 9),
            show="•",
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            insertbackground=COLOR_TEXT_PRIMARY,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_INPUT_BORDER,
            highlightcolor=COLOR_ACCENT,
        )
        self.new_app_pwd_entry.pack(side="left", fill="x", expand=True, ipady=3)

        self.eye_new_pwd_btn = tk.Button(
            new_pwd_row,
            text="👁️",
            font=("Segoe UI", 9),
            bg=COLOR_BTN_SECONDARY,
            fg=COLOR_TEXT_SECONDARY,
            relief="flat",
            cursor="hand2",
            command=self._toggle_new_mail_pwd_eye,
            width=3,
        )
        self.eye_new_pwd_btn.pack(side="right", padx=(4, 0))

        self.custom_server_frame = tk.Frame(self.new_mail_frame, bg=COLOR_CARD)
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
        self.new_server_entry = tk.Entry(
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
        self.new_server_entry.pack(fill="x", ipady=3, pady=(2, 0))

        port_col = tk.Frame(custom_row, bg=COLOR_CARD)
        port_col.pack(side="right", padx=(6, 0))
        tk.Label(
            port_col,
            text="Порт (SSL):",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        ).pack(anchor="w")
        self.new_port_entry = tk.Entry(
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
        self.new_port_entry.pack(fill="x", ipady=3, pady=(2, 0))
        self.new_port_entry.insert(0, "993")

        self.guide_box = tk.Frame(self.new_mail_frame, bg=COLOR_CARD)
        self.guide_box.pack(fill="x", pady=(2, 2))

        self.guide_title_lbl = tk.Label(self.guide_box, text="Инструкция:", font=("Segoe UI", 8, "bold"), fg=COLOR_TEXT_PRIMARY, bg=COLOR_CARD, anchor="w")
        self.guide_title_lbl.pack(anchor="w")

        self.guide_items_frame = tk.Frame(self.guide_box, bg=COLOR_CARD)
        self.guide_items_frame.pack(fill="x", pady=(2, 0))

        self._select_provider("yandex")
        self._update_mail_mode_view()

        btn_frame = tk.Frame(main_frame, bg=COLOR_BG)
        btn_frame.pack(fill="x", pady=(6, 0))

        cancel_btn = tk.Button(
            btn_frame,
            text="Отмена",
            font=("Segoe UI", 9),
            fg=COLOR_TEXT_SECONDARY,
            bg=COLOR_CARD,
            activebackground=COLOR_CARD_BORDER,
            activeforeground=COLOR_TEXT_PRIMARY,
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=self.destroy,
        )
        cancel_btn.pack(side="left")

        save_btn = tk.Button(
            btn_frame,
            text="Сохранить аккаунт",
            font=("Segoe UI", 9, "bold"),
            fg="#FFFFFF",
            bg=COLOR_ACCENT,
            activebackground=COLOR_ACCENT_HOVER,
            activeforeground="#FFFFFF",
            relief="flat",
            padx=16,
            pady=6,
            cursor="hand2",
            command=self._on_save,
        )
        save_btn.pack(side="right")

    def _toggle_pwd_eye(self):
        self.pwd_shown = not self.pwd_shown
        self.password_entry.config(show="" if self.pwd_shown else "•")
        self.eye_pwd_btn.config(text="🙈" if self.pwd_shown else "👁️")

    def _toggle_new_mail_pwd_eye(self):
        self.new_app_pwd_shown = not self.new_app_pwd_shown
        self.new_app_pwd_entry.config(show="" if self.new_app_pwd_shown else "•")
        self.eye_new_pwd_btn.config(text="🙈" if self.new_app_pwd_shown else "👁️")

    def _update_mail_mode_view(self):
        mode = self.mail_mode.get()
        if mode == "existing" and self.existing_mail_frame:
            self.existing_mail_frame.pack(fill="x", pady=(2, 6))
            self.new_mail_frame.pack_forget()
        else:
            if self.existing_mail_frame:
                self.existing_mail_frame.pack_forget()
            self.new_mail_frame.pack(fill="both", expand=True, pady=(2, 0))

    def _select_provider(self, provider_id: str):
        self.current_provider_id = provider_id
        pdata = MAIL_PROVIDERS[provider_id]

        for pid, b in self.provider_buttons.items():
            if pid == provider_id:
                b.config(bg=COLOR_ACCENT, fg="#ffffff", activebackground=COLOR_ACCENT_HOVER)
            else:
                b.config(bg=COLOR_BTN_SECONDARY, fg=COLOR_TEXT_SECONDARY, activebackground=COLOR_BTN_SECONDARY_HOVER)

        self.new_email_lbl.config(text=f"Email адрес ({pdata['name']}):")

        if provider_id == "custom":
            self.custom_server_frame.pack(fill="x", before=self.guide_box, pady=(2, 4))
        else:
            self.custom_server_frame.pack_forget()

        for w in self.guide_items_frame.winfo_children():
            w.destroy()

        self.guide_title_lbl.config(text=f"📋 {pdata['guide_title']}")

        for bold_t, desc in pdata["steps"]:
            step_box = tk.Frame(self.guide_items_frame, bg=COLOR_CARD)
            step_box.pack(fill="x", anchor="w", pady=(1, 2))
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
                wraplength=460,
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

    def _load_existing_data(self):
        if not self.is_edit or not self.account_data:
            return
        self.name_entry.insert(0, self.account_data.get("name", ""))
        self.login_entry.insert(0, self.account_data.get("login", ""))

        cur_mail = self.account_data.get("email", "")
        if cur_mail and self.saved_mailboxes and self.existing_mail_frame:
            for idx, m in enumerate(self.saved_mailboxes):
                if m["email"].lower() == cur_mail.lower():
                    self.mail_combo.current(idx)
                    self.mail_mode.set("existing")
                    self._update_mail_mode_view()
                    break

    def _on_save(self):
        name = self.name_entry.get().strip()
        login = self.login_entry.get().strip()
        password = self.password_entry.get()

        if not login:
            messagebox.showwarning("Внимание", "Логин Riot не может быть пустым!", parent=self)
            return

        if not self.is_edit and not password:
            messagebox.showwarning("Внимание", "Введите пароль от аккаунта Riot!", parent=self)
            return

        mode = self.mail_mode.get()
        email = ""
        mail_provider = "yandex"
        enc_app_pwd = ""
        app_pwd = ""
        server = "imap.yandex.ru"
        port = 993

        if mode == "existing" and self.saved_mailboxes:
            sel_idx = self.mail_combo.current()
            if 0 <= sel_idx < len(self.saved_mailboxes):
                target_m = self.saved_mailboxes[sel_idx]
                email = target_m["email"]
                mail_provider = target_m.get("mail_provider", "yandex")
                enc_app_pwd = target_m.get("encrypted_app_password", "")
                server = target_m.get("imap_server", "imap.yandex.ru")
                port = target_m.get("imap_port", 993)
        else:
            email = self.new_email_entry.get().strip()
            app_pwd = self.new_app_pwd_entry.get().strip().replace(" ", "")
            pdata = MAIL_PROVIDERS[self.current_provider_id]
            mail_provider = self.current_provider_id

            if self.current_provider_id == "custom":
                server = self.new_server_entry.get().strip()
                try:
                    port = int(self.new_port_entry.get().strip())
                except ValueError:
                    port = 993
                if not server:
                    messagebox.showwarning("Внимание", "Укажите адрес IMAP сервера (например: imap.rambler.ru)!", parent=self)
                    self.new_server_entry.focus_set()
                    return
            else:
                server = pdata["server"]
                port = pdata["port"]

            if not email:
                messagebox.showwarning("Внимание", "Укажите адрес электронной почты!", parent=self)
                self.new_email_entry.focus_set()
                return
            if not self.is_edit and not app_pwd:
                messagebox.showwarning("Внимание", "Укажите пароль приложения для почты!", parent=self)
                self.new_app_pwd_entry.focus_set()
                return

        try:
            if self.is_edit:
                update_account(
                    acc_id=self.account_data["id"],
                    name=name or login,
                    login=login,
                    password=password if password else None,
                    email=email,
                    mail_provider=mail_provider,
                    app_password=app_pwd if app_pwd else None,
                    encrypted_app_password=enc_app_pwd if enc_app_pwd else None,
                    imap_server=server,
                    imap_port=port,
                )
            else:
                add_account(
                    name=name or login,
                    login=login,
                    password=password,
                    email=email,
                    mail_provider=mail_provider,
                    app_password=app_pwd,
                    encrypted_app_password=enc_app_pwd,
                    imap_server=server,
                    imap_port=port,
                    is_selected=False,
                )

            if self.on_saved:
                self.on_saved()

            self.destroy()
        except Exception as e:
            messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить аккаунт:\n{e}", parent=self)


class RiotGrabberGUI:
    """Main lightweight GUI window."""

    def __init__(self, app_context):
        self.app = app_context
        self.root: Optional[tk.Tk] = None
        self.timer_job = None
        self.is_closed = False
        self.accounts = []

    def show(self):
        """Creates and renders the main GUI window centered on screen."""
        self.is_closed = False
        self.root = tk.Tk()
        enable_universal_clipboard(self.root)
        self.root.title("Riot Account Manager - RAM")
        self.root.configure(bg=COLOR_BG)

        window_w = 610
        window_h = 740
        self.root.resizable(False, False)

        icon_path = os.path.join(get_install_dir(), "icon.ico")
        if not os.path.exists(icon_path):
            bundle_dir = getattr(sys, "_MEIPASS", get_install_dir())
            icon_path = os.path.join(bundle_dir, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        self._build_ui()
        self._center_window(window_w, window_h)
        self._refresh_accounts_list()
        self._update_code_display()
        self._schedule_auto_refresh()

        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.root.mainloop()

    def _center_window(self, w: int, h: int):
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        pos_x = max(10, (screen_w - w) // 2)
        pos_y = max(10, (screen_h - h) // 2)
        self.root.geometry(f"{w}x{h}+{pos_x}+{pos_y}")

    def hide(self):
        """Hides the window to tray instead of destroying Tcl interpreter."""
        self.is_closed = True
        if self.timer_job and self.root:
            try:
                self.root.after_cancel(self.timer_job)
            except Exception:
                pass
            self.timer_job = None

        if self.root:
            try:
                self.root.withdraw()
            except Exception:
                pass

    def close(self):
        self.hide()

    def restore_and_show(self):
        """Restores window from hidden state, refreshes data and brings to front."""
        if not self.root:
            return

        def _do():
            try:
                self.is_closed = False
                self.root.deiconify()
                self._center_window(610, 740)
                self._refresh_accounts_list()
                self._update_code_display()
                self._schedule_auto_refresh()
                self.root.attributes("-topmost", True)
                self.root.lift()
                self.root.attributes("-topmost", False)
                self.root.focus_force()
            except Exception as e:
                logger.error("Failed to restore GUI window: %s", e)

        try:
            self.root.after(0, _do)
        except Exception:
            pass

    def destroy_app(self):
        """Terminates Tkinter root on application exit."""
        self.is_closed = True
        if self.timer_job and self.root:
            try:
                self.root.after_cancel(self.timer_job)
            except Exception:
                pass
            self.timer_job = None

        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass
            self.root = None

    def _build_ui(self):
        main_container = tk.Frame(self.root, bg=COLOR_BG, padx=20, pady=16)
        main_container.pack(fill="both", expand=True)

        top_bar = tk.Frame(main_container, bg=COLOR_BG)
        top_bar.pack(fill="x", pady=(0, 10))

        title_lbl = tk.Label(
            top_bar,
            text="Riot Account Manager - RAM",
            font=("Segoe UI", 13, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_BG,
        )
        title_lbl.pack(side="left")

        self.autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        autostart_cb = tk.Checkbutton(
            top_bar,
            text="🚀 Автозагрузка",
            variable=self.autostart_var,
            font=("Segoe UI", 8),
            fg=COLOR_TEXT_SECONDARY,
            bg=COLOR_BG,
            selectcolor=COLOR_INPUT_BG,
            activebackground=COLOR_BG,
            activeforeground=COLOR_TEXT_PRIMARY,
            command=self._on_autostart_toggle,
        )
        autostart_cb.pack(side="right")

        acc_card = tk.Frame(main_container, bg=COLOR_CARD, padx=16, pady=12, relief="flat")
        acc_card.pack(fill="both", expand=True, pady=(0, 10))

        acc_header = tk.Frame(acc_card, bg=COLOR_CARD)
        acc_header.pack(fill="x", pady=(0, 6))

        tk.Label(
            acc_header,
            text="👤 Сохраненные аккаунты Riot",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        ).pack(side="left")

        add_btn = tk.Button(
            acc_header,
            text="➕ Добавить аккаунт",
            font=("Segoe UI", 8, "bold"),
            fg="#FFFFFF",
            bg=COLOR_ACCENT,
            activebackground=COLOR_ACCENT_HOVER,
            activeforeground="#FFFFFF",
            relief="flat",
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._on_add_account_click,
        )
        add_btn.pack(side="right")

        list_container = tk.Frame(acc_card, bg=COLOR_INPUT_BG)
        list_container.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_container, orient="vertical")
        self.acc_listbox = tk.Listbox(
            list_container,
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT_PRIMARY,
            selectbackground="#2e2e34",
            selectforeground="#FFFFFF",
            font=("Segoe UI", 10),
            relief="flat",
            highlightthickness=0,
            yscrollcommand=scrollbar.set,
            activestyle="none",
        )
        scrollbar.config(command=self.acc_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.acc_listbox.pack(side="left", fill="both", expand=True, padx=4, pady=4)

        self.acc_listbox.bind("<ButtonRelease-1>", self._on_account_click)
        self.acc_listbox.bind("<<ListboxSelect>>", self._on_account_click)

        acc_actions_row1 = tk.Frame(acc_card, bg=COLOR_CARD)
        acc_actions_row1.pack(fill="x", pady=(8, 0))

        self.login_btn = tk.Button(
            acc_actions_row1,
            text="🚀 Войти в Riot Client",
            font=("Segoe UI", 9, "bold"),
            fg="#FFFFFF",
            bg=COLOR_ACCENT,
            activebackground=COLOR_ACCENT_HOVER,
            activeforeground="#FFFFFF",
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._on_login_click,
        )
        self.login_btn.pack(side="left")

        self.delete_btn = tk.Button(
            acc_actions_row1,
            text="🗑️ Удалить",
            font=("Segoe UI", 9),
            fg="#f87171",
            bg=COLOR_CARD_BORDER,
            activebackground=COLOR_INPUT_BORDER,
            activeforeground="#ef4444",
            relief="flat",
            padx=8,
            pady=5,
            cursor="hand2",
            command=self._on_delete_click,
        )
        self.delete_btn.pack(side="right")

        self.edit_btn = tk.Button(
            acc_actions_row1,
            text="✏️ Редактировать",
            font=("Segoe UI", 9),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD_BORDER,
            activebackground=COLOR_INPUT_BORDER,
            activeforeground=COLOR_TEXT_PRIMARY,
            relief="flat",
            padx=8,
            pady=5,
            cursor="hand2",
            command=self._on_edit_click,
        )
        self.edit_btn.pack(side="right", padx=(0, 6))

        acc_actions_row2 = tk.Frame(acc_card, bg=COLOR_CARD)
        acc_actions_row2.pack(fill="x", pady=(6, 0))

        self.logout_btn = tk.Button(
            acc_actions_row2,
            text="🚪 Выйти из аккаунта",
            font=("Segoe UI", 9, "bold"),
            fg="#fb7185",
            bg="#27272a",
            activebackground="#3f3f46",
            activeforeground="#f43f5e",
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
            command=self._on_logout_click,
        )
        self.logout_btn.pack(side="left")

        self.fix_val43_btn = tk.Button(
            acc_actions_row2,
            text="🛠️ FIX VAL43",
            font=("Segoe UI", 9, "bold"),
            fg="#fbbf24",
            bg="#27272a",
            activebackground="#3f3f46",
            activeforeground="#f59e0b",
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
            command=self._on_fix_val43_click,
        )
        self.fix_val43_btn.pack(side="right")

        self.mail_settings_btn = tk.Button(
            acc_actions_row2,
            text="📧 Почта (IMAP)",
            font=("Segoe UI", 9, "bold"),
            fg="#60a5fa",
            bg="#27272a",
            activebackground="#3f3f46",
            activeforeground="#93c5fd",
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
            command=self._on_mail_settings_click,
        )
        self.mail_settings_btn.pack(side="right", padx=(0, 6))

        code_card = tk.Frame(main_container, bg=COLOR_CARD, padx=16, pady=12, relief="flat")
        code_card.pack(fill="x")

        code_card_header = tk.Frame(code_card, bg=COLOR_CARD)
        code_card_header.pack(fill="x", pady=(0, 4))

        tk.Label(
            code_card_header,
            text="🔑 2FA Код авторизации для выбранного аккаунта",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD,
        ).pack(side="left")

        self.sync_lbl = tk.Label(
            code_card_header,
            text="автообновление раз в 10 сек",
            font=("Segoe UI", 8),
            fg=COLOR_TEXT_SECONDARY,
            bg=COLOR_CARD,
        )
        self.sync_lbl.pack(side="right")

        self.selected_account_lbl = tk.Label(
            code_card,
            text="Выбранный аккаунт: — | Почта: —",
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_SUCCESS,
            bg=COLOR_CARD,
            anchor="w",
        )
        self.selected_account_lbl.pack(fill="x", pady=(0, 4))

        code_box = tk.Frame(code_card, bg=COLOR_INPUT_BG, padx=12, pady=8)
        code_box.pack(fill="x", pady=4)

        self.code_val_lbl = tk.Label(
            code_box,
            text="—",
            font=("Segoe UI", 26, "bold"),
            fg=COLOR_ACCENT,
            bg=COLOR_INPUT_BG,
        )
        self.code_val_lbl.pack()

        self.time_lbl = tk.Label(
            code_box,
            text="Дата и время: ожидание новых писем...",
            font=("Segoe UI", 9),
            fg=COLOR_TEXT_SECONDARY,
            bg=COLOR_INPUT_BG,
        )
        self.time_lbl.pack(pady=(2, 0))

        code_btn_bar = tk.Frame(code_card, bg=COLOR_CARD)
        code_btn_bar.pack(fill="x", pady=(8, 0))

        self.copy_btn = tk.Button(
            code_btn_bar,
            text="📋 Скопировать код",
            font=("Segoe UI", 9, "bold"),
            fg="#FFFFFF",
            bg="#2563eb",
            activebackground="#1d4ed8",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._on_copy_code_click,
        )
        self.copy_btn.pack(side="left")

        self.refresh_btn = tk.Button(
            code_btn_bar,
            text="🔄 Обновить",
            font=("Segoe UI", 9),
            fg=COLOR_TEXT_PRIMARY,
            bg=COLOR_CARD_BORDER,
            activebackground=COLOR_INPUT_BORDER,
            activeforeground=COLOR_TEXT_PRIMARY,
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._on_manual_refresh_click,
        )
        self.refresh_btn.pack(side="left", padx=8)

        self.status_msg_lbl = tk.Label(
            code_btn_bar,
            text="",
            font=("Segoe UI", 9),
            fg=COLOR_SUCCESS,
            bg=COLOR_CARD,
        )
        self.status_msg_lbl.pack(side="right", padx=6)

    def _schedule_auto_refresh(self):
        if self.is_closed or not self.root:
            return
        self._update_code_display()
        self.timer_job = self.root.after(10000, self._schedule_auto_refresh)

    def _update_code_display(self):
        if not self.root or self.is_closed:
            return

        code = getattr(self.app, "last_code", "нет")
        code_time = getattr(self.app, "last_code_time", "")

        if code and code != "нет":
            self.code_val_lbl.config(text=f"{code}")
            if code_time:
                self.time_lbl.config(text=f"Получено: {code_time}")
            else:
                self.time_lbl.config(text="Получено из последнего письма")
            self.copy_btn.config(state="normal")
        else:
            self.code_val_lbl.config(text="—")
            self.time_lbl.config(text="Дата и время: новых кодов не поступало")

    def _refresh_accounts_list(self):
        """Reloads accounts from accounts.json into Listbox with (Выбран) marker."""
        if not self.root or self.is_closed:
            return

        self.accounts = load_accounts()
        self.acc_listbox.delete(0, tk.END)

        selected_idx = 0
        for idx, acc in enumerate(self.accounts):
            name = acc.get("name", "Без имени")
            login = acc.get("login", "")
            email = acc.get("email", "")
            is_sel = acc.get("is_selected", False)

            status_str = " (Выбран)" if is_sel else ""
            mail_str = f" • [{email}]" if email else ""

            display_str = f"  👤  {name} — {login}{status_str}{mail_str}"
            self.acc_listbox.insert(tk.END, display_str)

            if is_sel:
                selected_idx = idx

        if self.accounts:
            self.acc_listbox.select_set(selected_idx)
            sel_acc = self.accounts[selected_idx]
            self._update_selected_account_banner(sel_acc)

    def _update_selected_account_banner(self, acc: dict):
        login = acc.get("login", "—")
        email = acc.get("email", "почта не привязана")
        self.selected_account_lbl.config(
            text=f"Аккаунт: {login} (Выбран) | Привязанная почта: {email}"
        )

    def _on_account_click(self, event=None):
        """LMB click on an account in listbox: marks account as (Выбран) and switches mail monitor."""
        selection = self.acc_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if 0 <= idx < len(self.accounts):
            acc = self.accounts[idx]
            set_selected_account(acc["id"])

            self._refresh_accounts_list()
            self.acc_listbox.select_set(idx)

            self._update_selected_account_banner(acc)
            if self.app and hasattr(self.app, "switch_monitored_account"):
                self.app.switch_monitored_account(acc)

            self.status_msg_lbl.config(text=f"Выбран аккаунт: {acc.get('login')}", fg=COLOR_SUCCESS)

    def _get_selected_account(self) -> Optional[dict]:
        selection = self.acc_listbox.curselection()
        if not selection:
            return None
        idx = selection[0]
        if 0 <= idx < len(self.accounts):
            return self.accounts[idx]
        return None

    def _on_add_account_click(self):
        AccountDialog(self.root, on_saved=self._refresh_accounts_list)

    def _on_edit_click(self):
        acc = self._get_selected_account()
        if not acc:
            messagebox.showinfo("Инфо", "Выберите аккаунт для редактирования из списка.", parent=self.root)
            return
        AccountDialog(self.root, account_data=acc, on_saved=self._refresh_accounts_list)

    def _on_delete_click(self):
        acc = self._get_selected_account()
        if not acc:
            messagebox.showinfo("Инфо", "Выберите аккаунт для удаления из списка.", parent=self.root)
            return

        confirm = messagebox.askyesno(
            "Удаление аккаунта",
            f"Вы уверены, что хотите удалить аккаунт '{acc.get('name')}'?",
            parent=self.root,
        )
        if confirm:
            delete_account(acc["id"])
            self._refresh_accounts_list()

    def _on_login_click(self):
        acc = self._get_selected_account()
        if not acc:
            messagebox.showinfo("Инфо", "Выберите аккаунт для входа.", parent=self.root)
            return

        login = acc.get("login", "")
        password = get_account_password(acc["id"])

        if not password:
            messagebox.showerror(
                "Ошибка",
                "Не удалось расшифровать пароль аккаунта. Возможно, он был сохранен на другом ПК или профиле Windows.",
                parent=self.root,
            )
            return

        self.status_msg_lbl.config(text="Запуск автовхода в Riot Client...", fg=COLOR_ACCENT)
        self.login_btn.config(state="disabled")

        def run_login():
            success, message = execute_auto_login(login, password)
            color = COLOR_SUCCESS if success else "#ef4444"

            def finish():
                self.status_msg_lbl.config(text=message, fg=color)
                self.login_btn.config(state="normal")

            self.root.after(0, finish)

        threading.Thread(target=run_login, daemon=True).start()

    def _on_fix_val43_click(self):
        confirm = messagebox.askyesno(
            "FIX VAL43",
            "Выполнить исправление ошибки VAL 43?\n\nБудут закрыты все процессы Riot Client и VALORANT, удалены поврежденные кэш-файлы (RiotGamesPrivateSettings.yaml, ShutdownData.yaml) и перезапущен Riot Client.",
            parent=self.root,
        )
        if not confirm:
            return

        self.status_msg_lbl.config(text="Выполняется FIX VAL43...", fg="#eab308")
        self.fix_val43_btn.config(state="disabled")

        def run_fix():
            from val43_fixer import run_val43_fix
            success, message = run_val43_fix(
                status_cb=lambda s: self.root.after(0, lambda: self.status_msg_lbl.config(text=s, fg="#eab308"))
            )
            color = COLOR_SUCCESS if success else "#ef4444"

            def finish():
                self.status_msg_lbl.config(text=message, fg=color)
                self.fix_val43_btn.config(state="normal")

            self.root.after(0, finish)

        threading.Thread(target=run_fix, daemon=True).start()

    def _on_logout_click(self):
        self.status_msg_lbl.config(text="Выполняется выход из аккаунта...", fg="#eab308")
        self.logout_btn.config(state="disabled")

        def run_logout():
            from val43_fixer import run_logout_account
            success, message = run_logout_account(
                status_cb=lambda s: self.root.after(0, lambda: self.status_msg_lbl.config(text=s, fg="#eab308"))
            )
            color = COLOR_SUCCESS if success else "#ef4444"

            def finish():
                self.status_msg_lbl.config(text=message, fg=color)
                self.logout_btn.config(state="normal")

            self.root.after(0, finish)

        threading.Thread(target=run_logout, daemon=True).start()

    def _on_mail_settings_click(self):
        try:
            cfg_path = os.path.join(get_install_dir(), "config.json")

            def on_saved(new_cfg):
                email = new_cfg.get("email", "")
                self.status_msg_lbl.config(text=f"Почта ({email}) сохранена!", fg=COLOR_SUCCESS)
                if self.app and hasattr(self.app, "restart_listener"):
                    self.app.config = new_cfg
                    self.app.restart_listener()

            open_email_setup_dialog(
                parent=self.root,
                config_path=cfg_path,
                initial_config=getattr(self.app, "config", None),
                on_saved=on_saved,
                is_first_launch=False,
            )
        except Exception as e:
            logger.error("Failed to open email settings: %s", e)

    def _on_autostart_toggle(self):
        enabled = self.autostart_var.get()
        success = set_autostart(enabled)
        if success:
            msg = "Автозагрузка включена" if enabled else "Автозагрузка отключена"
            self.status_msg_lbl.config(text=msg, fg=COLOR_SUCCESS)
            self.root.after(3000, lambda: self.status_msg_lbl.config(text=""))
        else:
            self.status_msg_lbl.config(text="Ошибка изменения автозагрузки", fg="#ef4444")

    def _on_copy_code_click(self):
        code = getattr(self.app, "last_code", "")
        if code and code != "нет":
            copy_to_clipboard(code)
            self.status_msg_lbl.config(text=f"Код {code} скопирован в буфер!", fg=COLOR_SUCCESS)
            self.root.after(3000, lambda: self.status_msg_lbl.config(text=""))

    def _on_manual_refresh_click(self):
        self.status_msg_lbl.config(text="Проверка почты...", fg="#60a5fa")
        self.refresh_btn.config(state="disabled")

        def run_manual():
            found_code = None
            if self.app and hasattr(self.app, "listener") and self.app.listener:
                found_code = self.app.listener.check_messages(manual=True)

            def finish():
                self.refresh_btn.config(state="normal")
                if found_code:
                    self._update_code_display()
                    self.status_msg_lbl.config(text=f"Найден код: {found_code}", fg=COLOR_SUCCESS)
                else:
                    self.status_msg_lbl.config(text="Новых кодов не обнаружено", fg=COLOR_TEXT_SECONDARY)
                self.root.after(3000, lambda: self.status_msg_lbl.config(text=""))

            self.root.after(0, finish)

        threading.Thread(target=run_manual, daemon=True).start()


def open_accounts_menu(app_context=None):
    """Standalone runner for menu testing."""
    gui = RiotGrabberGUI(app_context)
    gui.show()


if __name__ == "__main__":
    open_accounts_menu()
