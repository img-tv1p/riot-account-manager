"""
VAL43 Fixer Module for Riot Client / VALORANT.
Terminates Riot processes, cleans corrupted cache/yaml files, and restarts Riot Client.
"""
import os
import time
import subprocess
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

RIOT_PROCESSES = [
    "Riot Client.exe",
    "RiotClient.exe",
    "RiotClientServices.exe",
    "RiotClientCrashHandler.exe",
    "RiotClientUx.exe",
    "RiotClientUxRender.exe",
    "VALORANT.exe",
    "VALORANT-Win64-Shipping.exe",
]

TARGET_FILES = [
    "RiotGamesPrivateSettings.yaml",
    "ShutdownData.yaml",
]

DEFAULT_LNK = r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Riot Games\Riot Client.lnk"
FALLBACK_EXE = r"C:\Riot Games\Riot Client\RiotClientServices.exe"


def kill_riot_processes():
    """Force terminates all running Riot and Valorant processes."""
    for proc_name in RIOT_PROCESSES:
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", proc_name, "/T"],
                capture_output=True,
                creationflags=0x08000000,
            )
        except Exception as e:
            logger.debug("Failed to kill %s: %s", proc_name, e)


def delete_val43_files() -> int:
    """Deletes RiotGamesPrivateSettings.yaml and ShutdownData.yaml in both Riot Client and VALORANT Data dirs."""
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        local_appdata = os.path.expanduser(r"~\AppData\Local")

    data_dirs = [
        os.path.join(local_appdata, "Riot Games", "Riot Client", "Data"),
        os.path.join(local_appdata, "Riot Games", "VALORANT", "Data"),
    ]

    deleted_count = 0
    target_lower = [t.lower() for t in TARGET_FILES]

    for d in data_dirs:
        if not os.path.exists(d):
            logger.info("Папка не существует (пропуск): %s", d)
            continue
        try:
            entries = os.listdir(d)
        except Exception as e:
            logger.warning("Не удалось прочитать содержимое папки %s: %s", d, e)
            entries = []

        for item in entries:
            if item.lower() in target_lower:
                filepath = os.path.join(d, item)
                try:
                    os.chmod(filepath, 0o777)
                    os.remove(filepath)
                    deleted_count += 1
                    logger.info("Deleted VAL43 file: %s", filepath)
                except Exception as e:
                    logger.warning("Could not delete %s: %s", filepath, e)

    return deleted_count


def launch_riot_client() -> bool:
    """Launches Riot Client via start menu shortcut or direct fallback executable."""

    if os.path.exists(DEFAULT_LNK):
        try:
            os.startfile(DEFAULT_LNK)
            logger.info("Launched Riot Client via: %s", DEFAULT_LNK)
            return True
        except Exception as e:
            logger.warning("Failed to start %s: %s", DEFAULT_LNK, e)

    if os.path.exists(FALLBACK_EXE):
        try:
            os.startfile(FALLBACK_EXE)
            logger.info("Launched Riot Client via fallback: %s", FALLBACK_EXE)
            return True
        except Exception as e:
            logger.warning("Failed to start %s: %s", FALLBACK_EXE, e)

    return False


def run_val43_fix(status_cb=None) -> Tuple[bool, str]:
    """
    Executes full FIX VAL43 routine:
    1. Terminate all RiotClient processes
    2. Wait 3 seconds
    3. Delete RiotGamesPrivateSettings.yaml & ShutdownData.yaml
    4. Launch Riot Client
    """
    try:
        from desktop_helper import attach_to_default_desktop
        attach_to_default_desktop()
    except Exception:
        pass

    if status_cb:
        status_cb("Закрытие Riot Client...")
    logger.info("Terminating all Riot Client processes for FIX VAL43...")
    kill_riot_processes()

    for sec_left in (3, 2, 1):
        if status_cb:
            status_cb(f"Ожидание перед удалением файлов ({sec_left} сек)...")
        time.sleep(1.0)

    if status_cb:
        status_cb("Удаление файлов настроек...")
    deleted = delete_val43_files()

    if status_cb:
        status_cb("Запуск Riot Client...")
    launched = launch_riot_client()

    if launched:
        if deleted > 0:
            msg = f"VAL43 исправлен! Удалено файлов: {deleted}. Riot Client перезапущен."
        else:
            msg = "VAL43: Riot Client перезапущен (файлы настроек уже отсутствовали)."
        logger.info(msg)
        return True, msg
    else:
        msg = f"Файлы обработаны (удалено: {deleted}), но не удалось запустить Riot Client."
        logger.warning(msg)
        return False, msg


def run_logout_account(status_cb=None) -> Tuple[bool, str]:
    """
    Executes Riot Client account logout routine (identical mechanics to FIX VAL43):
    1. Terminate all RiotClient processes
    2. Wait 3 seconds
    3. Delete session files (RiotGamesPrivateSettings.yaml & ShutdownData.yaml)
    4. Launch Riot Client to open fresh login screen
    """
    try:
        from desktop_helper import attach_to_default_desktop
        attach_to_default_desktop()
    except Exception:
        pass

    if status_cb:
        status_cb("Закрытие Riot Client...")
    logger.info("Terminating all Riot Client processes for Account Logout...")
    kill_riot_processes()

    for sec_left in (3, 2, 1):
        if status_cb:
            status_cb(f"Ожидание перед сбросом сессии ({sec_left} сек)...")
        time.sleep(1.0)

    if status_cb:
        status_cb("Сброс активной сессии Riot...")
    deleted = delete_val43_files()

    if status_cb:
        status_cb("Запуск Riot Client...")
    launched = launch_riot_client()

    if launched:
        msg = "Выход из аккаунта выполнен! Riot Client перезапущен на экране логина."
        logger.info(msg)
        return True, msg
    else:
        msg = f"Сессия сброшена (удалено файлов: {deleted}), но не удалось запустить Riot Client."
        logger.warning(msg)
        return False, msg

