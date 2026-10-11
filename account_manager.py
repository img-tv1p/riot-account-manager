"""
Account management and secure DPAPI storage.
Handles Riot Games accounts linked to specific email accounts,
with encrypted account passwords and encrypted mail app passwords.
"""
import json
import os
import sys
import uuid
import logging
from typing import List, Dict, Optional
from crypto_manager import encrypt_password, decrypt_password, encrypt_string, decrypt_string
from app_installer import get_install_dir

logger = logging.getLogger(__name__)

BASE_DIR = get_install_dir()
ACCOUNTS_FILE = os.path.join(BASE_DIR, "accounts.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


def _get_fallback_mailbox() -> Dict:
    """Reads fallback mailbox settings from config.json if available."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            email = cfg.get("email", "").strip()
            enc_pwd = cfg.get("encrypted_app_password", "")
            raw_pwd = cfg.get("app_password", "")
            if not enc_pwd and raw_pwd:
                enc_pwd = encrypt_string(raw_pwd)

            return {
                "email": email,
                "mail_provider": cfg.get("mail_provider", "yandex"),
                "encrypted_app_password": enc_pwd,
                "imap_server": cfg.get("imap_server", "imap.yandex.ru"),
                "imap_port": cfg.get("imap_port", 993),
            }
    except Exception:
        return {}


def load_accounts() -> List[Dict]:
    """Loads accounts from accounts.json, performs auto-migration and ensures one is selected."""
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                return []

            fb_mail = _get_fallback_mailbox()
            modified = False

            has_selected = any(acc.get("is_selected", False) for acc in data)
            if data and not has_selected:
                data[0]["is_selected"] = True
                modified = True

            for acc in data:
                if not acc.get("email") and fb_mail.get("email"):
                    acc["email"] = fb_mail["email"]
                    acc["mail_provider"] = fb_mail.get("mail_provider", "yandex")
                    acc["encrypted_app_password"] = fb_mail.get("encrypted_app_password", "")
                    acc["imap_server"] = fb_mail.get("imap_server", "imap.yandex.ru")
                    acc["imap_port"] = fb_mail.get("imap_port", 993)
                    modified = True

            if modified:
                save_accounts(data)

            return data
    except Exception as e:
        logger.error("Failed to load accounts.json: %s", e)
        return []


def save_accounts(accounts: List[Dict]) -> bool:
    """Saves accounts list safely to accounts.json."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(ACCOUNTS_FILE)), exist_ok=True)
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error("Failed to save accounts.json: %s", e)
        return False


def get_saved_mailboxes() -> List[Dict]:
    """
    Returns unique list of all configured mailboxes across all accounts and config.json.
    Useful for selecting an already configured mailbox when adding a new account.
    """
    mailboxes = {}
    
    fb = _get_fallback_mailbox()
    if fb.get("email"):
        mailboxes[fb["email"].lower()] = fb

    for acc in load_accounts():
        em = (acc.get("email") or "").strip()
        if em and em.lower() not in mailboxes:
            mailboxes[em.lower()] = {
                "email": em,
                "mail_provider": acc.get("mail_provider", "yandex"),
                "encrypted_app_password": acc.get("encrypted_app_password", ""),
                "imap_server": acc.get("imap_server", "imap.yandex.ru"),
                "imap_port": acc.get("imap_port", 993),
            }

    return list(mailboxes.values())


def get_selected_account() -> Optional[Dict]:
    """Returns the currently selected Riot account, or the first account."""
    accounts = load_accounts()
    if not accounts:
        return None
    for acc in accounts:
        if acc.get("is_selected", False):
            return acc

    accounts[0]["is_selected"] = True
    save_accounts(accounts)
    return accounts[0]


def set_selected_account(acc_id: str) -> Optional[Dict]:
    """Sets account with acc_id as the selected one. Returns the selected account dict."""
    accounts = load_accounts()
    selected_acc = None
    for acc in accounts:
        if acc.get("id") == acc_id:
            acc["is_selected"] = True
            selected_acc = acc
        else:
            acc["is_selected"] = False

    if selected_acc:
        save_accounts(accounts)
        logger.info("Selected account changed to: %s (%s)", selected_acc.get("login"), selected_acc.get("name"))
    return selected_acc


def add_account(
    name: str,
    login: str,
    password: str,
    email: str = "",
    mail_provider: str = "yandex",
    app_password: str = "",
    encrypted_app_password: str = "",
    imap_server: str = "imap.yandex.ru",
    imap_port: int = 993,
    is_selected: bool = False,
) -> Dict:
    """Adds a new account with encrypted Riot password and encrypted mail app password."""
    accounts = load_accounts()
    acc_id = str(uuid.uuid4())[:8]

    enc_pass = encrypt_password(password)

    enc_mail_pwd = encrypted_app_password
    if not enc_mail_pwd and app_password:
        enc_mail_pwd = encrypt_string(app_password)

    if not accounts or is_selected:
        for acc in accounts:
            acc["is_selected"] = False
        is_selected = True

    new_acc = {
        "id": acc_id,
        "name": name.strip() or login.strip(),
        "login": login.strip(),
        "encrypted_password": enc_pass,
        "email": email.strip(),
        "mail_provider": mail_provider,
        "encrypted_app_password": enc_mail_pwd,
        "imap_server": imap_server.strip() or "imap.yandex.ru",
        "imap_port": int(imap_port or 993),
        "is_selected": is_selected,
    }
    accounts.append(new_acc)
    save_accounts(accounts)
    logger.info("Added account '%s' (login: %s, email: %s)", new_acc["name"], new_acc["login"], new_acc["email"])
    return new_acc


def update_account(
    acc_id: str,
    name: str,
    login: str,
    password: Optional[str] = None,
    email: Optional[str] = None,
    mail_provider: Optional[str] = None,
    app_password: Optional[str] = None,
    encrypted_app_password: Optional[str] = None,
    imap_server: Optional[str] = None,
    imap_port: Optional[int] = None,
) -> bool:
    """Updates existing account details and re-encrypts passwords if changed."""
    accounts = load_accounts()
    found = False
    for acc in accounts:
        if acc.get("id") == acc_id:
            acc["name"] = name.strip() or login.strip()
            acc["login"] = login.strip()

            if password is not None and password != "":
                acc["encrypted_password"] = encrypt_password(password)

            if email is not None:
                acc["email"] = email.strip()

            if mail_provider is not None:
                acc["mail_provider"] = mail_provider

            if app_password is not None and app_password != "":
                acc["encrypted_app_password"] = encrypt_string(app_password)
            elif encrypted_app_password is not None:
                acc["encrypted_app_password"] = encrypted_app_password

            if imap_server is not None:
                acc["imap_server"] = imap_server.strip()

            if imap_port is not None:
                acc["imap_port"] = int(imap_port)

            found = True
            break

    if found:
        save_accounts(accounts)
        logger.info("Updated account id: %s", acc_id)
    return found


def delete_account(acc_id: str) -> bool:
    """Deletes an account by id. If it was selected, selects another account."""
    accounts = load_accounts()
    initial_len = len(accounts)
    was_selected = any(acc.get("id") == acc_id and acc.get("is_selected", False) for acc in accounts)

    accounts = [acc for acc in accounts if acc.get("id") != acc_id]
    if len(accounts) < initial_len:
        if was_selected and accounts:
            accounts[0]["is_selected"] = True
        save_accounts(accounts)
        logger.info("Deleted account id: %s", acc_id)
        return True
    return False


def get_account_password(acc_id: str) -> Optional[str]:
    """Decrypts and returns the plaintext Riot password for an account."""
    accounts = load_accounts()
    for acc in accounts:
        if acc.get("id") == acc_id:
            enc = acc.get("encrypted_password", "")
            if not enc:
                return ""
            try:
                return decrypt_password(enc)
            except Exception as e:
                logger.error("Failed to decrypt password for account %s: %s", acc_id, e)
                return None
    return None


def get_account_app_password(acc_id: str) -> Optional[str]:
    """Decrypts and returns the plaintext mail app password for an account."""
    accounts = load_accounts()
    for acc in accounts:
        if acc.get("id") == acc_id:
            enc = acc.get("encrypted_app_password", "")
            if not enc:
                return ""
            try:
                return decrypt_string(enc)
            except Exception as e:
                logger.error("Failed to decrypt app password for account %s: %s", acc_id, e)
                return None
    return None
