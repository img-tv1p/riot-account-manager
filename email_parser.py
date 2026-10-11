"""Parser for Riot Games verification emails."""
import email
import email.message
from email.header import decode_header
import re
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

RIOT_SENDERS = [
    "riotgames.com",
    "mail.accounts.riotgames.com",
    "accounts.riotgames.com",
    "riot games",
]

CODE_KEYWORDS = [
    r"код\s+для\s+входа",
    r"код\s+подтверждения",
    r"одноразовый\s+код",
    r"ваш\s+код",
    r"login\s+code",
    r"verification\s+code",
    r"single-use\s+code",
    r"security\s+code",
    r"riot\s+code",
    r"auth\s+code",
]


def decode_str(header_value: Optional[str]) -> str:
    """Decodes MIME encoded header strings to normal unicode."""
    if not header_value:
        return ""
    decoded_fragments = []
    for part, encoding in decode_header(header_value):
        if isinstance(part, bytes):
            try:
                decoded_fragments.append(part.decode(encoding or "utf-8", errors="replace"))
            except Exception:
                decoded_fragments.append(part.decode("latin1", errors="replace"))
        else:
            decoded_fragments.append(str(part))
    return "".join(decoded_fragments).strip()


def extract_body(msg: email.message.Message) -> Tuple[str, str]:
    """Extracts (plain_text, html_text) from an email message."""
    plain_text = ""
    html_text = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in content_disposition:
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue

            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                decoded = payload.decode("latin1", errors="replace")

            if content_type == "text/plain":
                plain_text += "\n" + decoded
            elif content_type == "text/html":
                html_text += "\n" + decoded
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                decoded = payload.decode("latin1", errors="replace")
            if msg.get_content_type() == "text/html":
                html_text = decoded
            else:
                plain_text = decoded

    return plain_text.strip(), html_text.strip()


def is_riot_email(sender: str, subject: str) -> bool:
    """Checks if message is likely a Riot verification/login code email."""
    sender_lower = sender.lower()
    subject_lower = subject.lower()

    matches_sender = any(domain in sender_lower for domain in RIOT_SENDERS)
    matches_subject_riot = "riot" in subject_lower
    matches_subject_code = (
        "login code:" in subject_lower
        or "код для входа:" in subject_lower
        or "login code" in subject_lower
        or "код для входа" in subject_lower
        or "код подтверждения" in subject_lower
        or bool(re.search(r":\s*\d{6}(?!\d)", subject))
    )

    if matches_sender or matches_subject_riot or matches_subject_code:
        return True

    return False


def extract_riot_code(subject: str, plain_body: str, html_body: str) -> Optional[str]:
    """
    Extracts the verification code from Riot Games email.
    Prioritizes:
    1. Direct subject match for 'Login Code: 123456', 'Код для входа: 123456', or ': 123456'
    2. Any 6 digits directly in subject
    3. Body text matching ': 123456' or near keywords
    4. HTML styled container
    5. Standalone 6 digits
    """

    subj_colon = re.search(r":\s*(\d{6})(?!\d)", subject)
    if subj_colon:
        code = subj_colon.group(1)
        logger.info("Found code directly after ':' in subject: %s", code)
        return code

    subject_digits = re.findall(r"(?<!\d)(\d{6})(?!\d)", subject)
    if subject_digits:
        for num in subject_digits:
            if not (2020 <= int(num) <= 2035):
                logger.info("Found 6-digit code in subject: %s", num)
                return num

    clean_html_text = ""
    if html_body:
        clean = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", html_body, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<(?:p|div|tr|h\d|br|hr)[^>]*>", "\n", clean, flags=re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean_html_text = re.sub(r"\s+", " ", clean).strip()

    combined_text = f"{subject}\n{plain_body}\n{clean_html_text}"

    colon_body = re.search(r"(?:login\s*code|код\s*для\s*входа|код\s*подтверждения|code|код)?\s*:\s*(\d{6})(?!\d)", combined_text, flags=re.IGNORECASE)
    if colon_body and colon_body.group(1):
        code = colon_body.group(1)
        if not (2020 <= int(code) <= 2035):
            return code

    keyword_pattern = (
        r"(?:login\s*code|код\s*для\s*входа|код\s*подтверждения|"
        r"одноразовый\s*код|verification\s*code|single-use\s*code|"
        r"security\s*code|your\s*code)[\s\S]{0,80}?(?<!\d)(\d{6})(?!\d)"
    )
    match = re.search(keyword_pattern, combined_text, flags=re.IGNORECASE)
    if match:
        code = match.group(1)
        if not (2020 <= int(code) <= 2035):
            return code

    if html_body:
        styled_match = re.search(
            r"(?:letter-spacing|font-size\s*:\s*[2-4]\dpx|font-weight\s*:\s*(?:bold|700))[^>]*>\s*(?<!\d)(\d{6})(?!\d)",
            html_body,
            flags=re.IGNORECASE,
        )
        if styled_match:
            code = styled_match.group(1)
            if not (2020 <= int(code) <= 2035):
                return code

    candidates = re.findall(r"(?<!\d)(\d{6})(?!\d)", combined_text)
    for cand in candidates:
        if not (2020 <= int(cand) <= 2035):
            return cand

    return None


def parse_email_message(raw_bytes: bytes) -> dict:
    """Parses raw email bytes into a structured dict with code if present."""
    msg = email.message_from_bytes(raw_bytes)

    subject = decode_str(msg.get("Subject", ""))
    sender = decode_str(msg.get("From", ""))
    date_str = decode_str(msg.get("Date", ""))
    msg_id = decode_str(msg.get("Message-ID", ""))

    plain_body, html_body = extract_body(msg)

    is_riot = is_riot_email(sender, subject)
    code = None
    if is_riot:
        code = extract_riot_code(subject, plain_body, html_body)

    return {
        "message_id": msg_id,
        "sender": sender,
        "subject": subject,
        "date": date_str,
        "is_riot": is_riot,
        "code": code,
        "preview": (plain_body[:200] if plain_body else clean_html_snippet(html_body))
    }


def clean_html_snippet(html: str) -> str:
    """Extracts a short plain text snippet from html for logging."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    return " ".join(text.split())[:200]
