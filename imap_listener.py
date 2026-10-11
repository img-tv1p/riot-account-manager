"""
IMAP Listener for real-time Riot Games email monitoring across ALL mail folders.
Supports automatic folder discovery (INBOX, Riot Code, Spam, Archive, etc.)
with zero CPU usage and thread-safe operations.
"""
import imaplib
import socket
import ssl
import time
import re
import threading
import logging
from typing import Callable, Optional, Set, List
from email_parser import parse_email_message

logger = logging.getLogger(__name__)

IGNORED_FOLDER_PATTERNS = [
    "draft", "черновик", "sent", "отправлен", "outbox", "исходящ"
]


def _format_folder_arg(folder: str) -> str:
    """Properly quotes IMAP folder names containing special characters or spaces."""
    if folder.startswith('"') and folder.endswith('"'):
        return folder
    if any(c in folder for c in [' ', '|', '/', '\\', '[', ']', '&']):
        return f'"{folder}"'
    return folder


class RiotImapListener:
    def __init__(
        self,
        email_address: str,
        app_password: str,
        imap_server: str = "imap.yandex.ru",
        imap_port: int = 993,
        poll_interval: int = 4,
        on_code: Optional[Callable[[str, str, str, str], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ):
        self.email_address = email_address.strip()
        self.app_password = app_password.strip()
        self.imap_server = imap_server.strip()
        self.imap_port = imap_port
        self.poll_interval = max(2, poll_interval)
        self.on_code = on_code
        self.on_status = on_status

        self.running = False
        self.client: Optional[imaplib.IMAP4_SSL] = None
        self.lock = threading.RLock()
        self.processed_uids: Set[str] = set()
        self.last_code: Optional[str] = None
        self.last_code_date: str = ""
        self.monitored_folders: List[str] = ["INBOX"]

    def set_status(self, text: str):
        logger.info("Status: %s", text)
        if self.on_status:
            try:
                self.on_status(text)
            except Exception as e:
                logger.error("Error in on_status callback: %s", e)

    def _discover_folders(self) -> List[str]:
        """Discovers all readable mail folders from the IMAP server."""
        if not self.client:
            return ["INBOX"]

        try:
            typ, data = self.client.list()
            if typ != "OK" or not data:
                return ["INBOX"]

            folders = []
            for entry in data:
                line = entry.decode("utf-8", errors="ignore")

                m = re.search(r'\((?P<flags>.*?)\)\s+"(?P<delim>.*?)"\s+(?P<name>.*)', line)
                if m:
                    f_name = m.group("name").strip()
                    if f_name.startswith('"') and f_name.endswith('"'):
                        f_name = f_name[1:-1]
                else:
                    f_name = line.split()[-1]

                f_lower = f_name.lower()

                if any(pat in f_lower for pat in IGNORED_FOLDER_PATTERNS):
                    continue

                folders.append(f_name)

            def folder_priority(f):
                fl = f.lower()
                if "riot" in fl or "code" in fl:
                    return 0
                if fl == "inbox":
                    return 1
                if "spam" in fl or "junk" in fl or "спам" in fl:
                    return 2
                return 3

            folders.sort(key=folder_priority)
            result = folders if folders else ["INBOX"]
            logger.info("Monitored mail folders: %s", result)
            return result
        except Exception as e:
            err_str = str(e).lower()
            if any(w in err_str for w in ["socket", "eof", "connection", "abort", "closed", "violation of protocol"]):
                raise
            logger.warning("Could not list IMAP folders: %s", e)
            return ["INBOX"]

    def connect(self) -> bool:
        """Establishes IMAP SSL connection, authenticates, and discovers folders."""
        with self.lock:
            try:
                self.set_status("Подключение к IMAP...")
                self.client = imaplib.IMAP4_SSL(self.imap_server, self.imap_port, timeout=20)
                self.client.login(self.email_address, self.app_password)
                self.set_status("Подключено к почте")
                logger.info("Successfully connected and authenticated as %s", self.email_address)

                self.monitored_folders = self._discover_folders()

                self._seed_existing_uids()
                return True
            except imaplib.IMAP4.error as e:
                err_msg = str(e)
                logger.error("IMAP Authentication/Protocol error: %s", err_msg)
                if any(k in err_msg.lower() for k in ["authenticationfailed", "invalid credentials", "disabled", "bad"]):
                    self.set_status("Ошибка входа: проверьте пароль приложения и включение IMAP")
                else:
                    self.set_status(f"Ошибка авторизации: {err_msg[:40]}")
                return False
            except (socket.error, OSError) as e:
                logger.error("Network error while connecting to IMAP: %s", e)
                self.set_status("Ошибка сети")
                return False
            except Exception as e:
                logger.error("Unexpected error in connect: %s", e)
                self.set_status(f"Ошибка: {e}")
                return False

    def _seed_existing_uids(self):
        """Remembers existing message UIDs in all folders so we only alert on newly incoming emails."""
        with self.lock:
            if not self.client:
                return

            total_seeded = 0
            for folder in self.monitored_folders:
                folder_arg = _format_folder_arg(folder)
                try:
                    typ, _ = self.client.select(folder_arg, readonly=True)
                    if typ != "OK":
                        continue
                    typ_s, data = self.client.uid("SEARCH", None, "ALL")
                    if typ_s == "OK" and data and data[0]:
                        uids = data[0].split()

                        for u in uids[-50:]:
                            uid_str = u.decode("utf-8", errors="ignore")
                            key = f"{folder}:{uid_str}"
                            self.processed_uids.add(key)
                            total_seeded += 1
                except Exception as e:
                    logger.debug("Could not seed UIDs in folder %s: %s", folder, e)

            logger.info("Initial seed loaded %d existing UIDs across %d folders.", total_seeded, len(self.monitored_folders))

    def check_messages(self, manual: bool = False) -> Optional[str]:
        """
        Scans all monitored mail folders for Riot 2FA codes.
        If manual=True, checks recent messages in every folder.
        If manual=False, checks UNSEEN and new messages.
        Thread-safe.
        """
        with self.lock:
            if not self.client:
                return None

            found_code = None
            for folder in self.monitored_folders:
                folder_arg = _format_folder_arg(folder)
                try:
                    typ_sel, _ = self.client.select(folder_arg, readonly=True)
                    if typ_sel != "OK":
                        continue

                    typ_search, search_data = self.client.uid("SEARCH", None, "UNSEEN")
                    if typ_search != "OK" or not search_data or not search_data[0]:
                        if manual:
                            typ_search, search_data = self.client.uid("SEARCH", None, "ALL")
                        else:
                            continue

                    if typ_search != "OK" or not search_data or not search_data[0]:
                        continue

                    uids = search_data[0].split()

                    check_uids = uids[-5:] if manual else uids

                    for uid_bytes in reversed(check_uids):
                        uid_str = uid_bytes.decode("utf-8", errors="ignore")
                        key = f"{folder}:{uid_str}"

                        if not manual and key in self.processed_uids:
                            continue

                        typ_fetch, msg_data = self.client.uid("FETCH", uid_bytes, "(RFC822)")
                        if typ_fetch != "OK" or not msg_data:
                            continue

                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                raw_email = response_part[1]
                                parsed = parse_email_message(raw_email)
                                logger.info(
                                    "Inspecting [%s] [UID: %s] From: %s | Subject: %s | Is Riot: %s",
                                    folder, uid_str, parsed["sender"], parsed["subject"], parsed["is_riot"]
                                )

                                if parsed["is_riot"] and parsed["code"]:
                                    found_code = parsed["code"]
                                    self.last_code = found_code
                                    self.last_code_date = parsed.get("date", "")
                                    self.processed_uids.add(key)
                                    logger.info(
                                        "Extracted Riot code: %s in '%s' (Date: %s)",
                                        found_code, folder, self.last_code_date
                                    )

                                    if self.on_code:
                                        self.on_code(found_code, parsed["sender"], parsed["subject"], self.last_code_date)
                                    return found_code
                                elif not manual:
                                    self.processed_uids.add(key)

                except (socket.error, OSError, imaplib.IMAP4.abort, ssl.SSLError) as e:
                    logger.warning("Connection lost while checking folder '%s': %s", folder, e)
                    raise
                except Exception as e:
                    err_str = str(e).lower()
                    if any(w in err_str for w in ["socket", "eof", "connection", "abort", "closed", "violation of protocol", "broken pipe", "reset"]):
                        logger.warning("Connection error in folder '%s': %s", folder, e)
                        raise
                    logger.error("Error checking folder '%s': %s", folder, e)

            return found_code

    def run(self):
        """Main listening loop that monitors all mailbox folders with zero CPU overhead."""
        self.running = True

        while self.running:
            connected = self.connect()
            if not connected:
                self.set_status("Переподключение через 10 сек...")
                for _ in range(10):
                    if not self.running:
                        return
                    time.sleep(1)
                continue

            self.set_status(f"Мониторинг всех папок ({len(self.monitored_folders)} шт.)...")

            cycle_count = 0
            while self.running:
                try:
                    self.check_messages(manual=False)
                except Exception as e:
                    logger.warning("Connection lost (%s). Reconnecting to IMAP...", e)
                    break

                cycle_count += 1

                if cycle_count % 6 == 0:
                    try:
                        with self.lock:
                            if self.client:
                                typ, _ = self.client.noop()
                                if typ != "OK":
                                    logger.warning("IMAP NOOP returned non-OK (%s), reconnecting...", typ)
                                    break
                    except Exception as e:
                        logger.warning("IMAP connection died during keep-alive NOOP: %s", e)
                        break

                if cycle_count >= 30:
                    cycle_count = 0
                    try:
                        with self.lock:
                            if self.client:
                                self.monitored_folders = self._discover_folders()
                    except Exception as e:
                        logger.warning("Folder discovery failed (%s), reconnecting...", e)
                        break

                for _ in range(self.poll_interval):
                    if not self.running:
                        self._close_connection()
                        return
                    time.sleep(1)

            self._close_connection()

            if self.running:
                self.set_status("Связь прервана, переподключение...")
                time.sleep(3)

        self.set_status("Остановлен")

    def stop(self):
        """Stops the listener immediately without blocking or hanging."""
        self.running = False
        self._close_connection()

    def _close_connection(self):
        """Safely and immediately closes IMAP connection."""
        with self.lock:
            client = self.client
            self.client = None
            if not client:
                return
            try:

                if hasattr(client, "sock") and client.sock:
                    try:
                        client.sock.shutdown(2)
                    except Exception:
                        pass
                    try:
                        client.sock.close()
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                client.close()
            except Exception:
                pass
            try:
                client.logout()
            except Exception:
                pass
