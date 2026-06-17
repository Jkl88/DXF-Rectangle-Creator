from __future__ import annotations

import os
import sys
import tempfile

import requests
from PyQt6.QtWidgets import QMessageBox

from app.version import CURRENT_VERSION


def check_update(parent) -> None:
    try:
        url = "https://api.github.com/repos/Jkl88/DXF-Rectangle-Creator/releases/latest"
        response = requests.get(url, timeout=5)
        data = response.json()
        latest = data["tag_name"].lstrip("v")
        exe_url = None
        for a in data.get("assets", []):
            if a["name"].lower().endswith(".exe"):
                exe_url = a["browser_download_url"]
                break
        if exe_url is None or latest == CURRENT_VERSION:
            return
        reply = QMessageBox.question(
            parent, "Доступно обновление",
            f"Доступна новая версия: {latest}\nТекущая: {CURRENT_VERSION}\n\nОбновить?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            _perform_update(parent, exe_url)
    except Exception as e:
        QMessageBox.warning(parent, "Ошибка", f"Не удалось проверить обновление:\n{e}")


def _perform_update(parent, download_url: str) -> None:
    try:
        current_path = sys.executable
        exe_name = os.path.basename(current_path)
        tmp_dir = tempfile.gettempdir()
        new_exe = os.path.join(tmp_dir, "update_new.exe")
        r = requests.get(download_url, stream=True)
        with open(new_exe, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        updater_path = os.path.join(tmp_dir, "update.bat")
        with open(updater_path, "w", encoding="cp866") as bat:
            bat.write(f"""@echo off
title Updating...
:waitloop
tasklist | find /i "{exe_name}" >nul
if not errorlevel 1 (
    timeout /t 1 >nul
    goto waitloop
)
copy /y "{new_exe}" "{current_path}" >nul
del "{new_exe}"
del "%~f0"
""")
        os.startfile(updater_path)
        os.system(f"taskkill /F /PID {os.getpid()}")
    except Exception as e:
        QMessageBox.critical(parent, "Ошибка", f"Не удалось обновить:\n{e}")
