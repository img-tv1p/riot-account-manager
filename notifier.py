"""Notification helper using winotify and winsound."""
import logging
import winsound
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from winotify import Notification, audio
    HAS_WINOTIFY = True
except ImportError:
    HAS_WINOTIFY = False


def send_notification(
    title: str,
    message: str,
    app_id: str = "Riot Account Manager - RAM",
    play_audio: bool = True,
    icon_path: Optional[str] = None
):
    """Sends native Windows 10/11 toast notification and plays sound."""
    if play_audio:
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception as e:
            logger.debug("Failed to play sound: %s", e)

    if HAS_WINOTIFY:
        try:
            toast = Notification(
                app_id=app_id,
                title=title,
                msg=message,
                duration="short",
                icon=icon_path or ""
            )
            if play_audio:
                toast.set_audio(audio.Default, loop=False)
            toast.show()
            return True
        except Exception as e:
            logger.warning("winotify failed to show notification: %s", e)

    return False
