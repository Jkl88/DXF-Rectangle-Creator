"""Интеграция с другими программами (Windows).

Другая программа может:

1. Проверить, установлен ли редактор::
       from app.integration import get_installation_info
       info = get_installation_info()
       if info and "dxf" in info.get("import_formats", []):
           ...

2. Импортировать DXF в уже запущенный экземпляр или запустить редактор::
       from app.integration import import_dxf
       ok = import_dxf(r"C:\\path\\file.dxf")

3. Запустить редактор с файлом напрямую::
       DXF_Rectangle_Creator.exe --import "C:\\path\\file.dxf"

При старте редактор записывает сведения в реестр:
``HKCU\\Software\\Jkl88\\DXF Rectangle Creator``
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

APP_ID = "dxf-rectangle-creator"
REGISTRY_KEY = r"Software\Jkl88\DXF Rectangle Creator"
IPC_SOCKET_NAME = "Jkl88.DXF_Rectangle_Creator"
IMPORT_ACTION = "import_dxf"


def get_executable_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(sys.argv[0])


def register_installation(version: str) -> None:
    if sys.platform != "win32":
        return
    import winreg

    exe_path = get_executable_path()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
        winreg.SetValueEx(key, "AppId", 0, winreg.REG_SZ, APP_ID)
        winreg.SetValueEx(key, "InstallPath", 0, winreg.REG_SZ, exe_path)
        winreg.SetValueEx(key, "Version", 0, winreg.REG_SZ, version)
        winreg.SetValueEx(key, "ImportFormats", 0, winreg.REG_SZ, "dxf")
        winreg.SetValueEx(key, "IpcSocket", 0, winreg.REG_SZ, IPC_SOCKET_NAME)
        winreg.SetValueEx(key, "CommandImport", 0, winreg.REG_SZ, f'"{exe_path}" --import')


def get_installation_info() -> dict[str, Any] | None:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
            install_path, _ = winreg.QueryValueEx(key, "InstallPath")
            version, _ = winreg.QueryValueEx(key, "Version")
            import_formats, _ = winreg.QueryValueEx(key, "ImportFormats")
            ipc_socket, _ = winreg.QueryValueEx(key, "IpcSocket")
    except OSError:
        return None

    if not install_path or not os.path.isfile(install_path):
        return None
    return {
        "app_id": APP_ID,
        "install_path": install_path,
        "version": version,
        "import_formats": [f.strip().lower() for f in import_formats.split(",") if f.strip()],
        "ipc_socket": ipc_socket,
    }


def parse_import_paths(argv: list[str]) -> list[str]:
    paths: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--import", "/import"):
            i += 1
            if i < len(argv):
                paths.append(os.path.abspath(argv[i]))
        elif arg.startswith("--import="):
            paths.append(os.path.abspath(arg.split("=", 1)[1]))
        elif arg.lower().endswith(".dxf") and os.path.isfile(arg):
            paths.append(os.path.abspath(arg))
        i += 1
    return paths


def _encode_ipc_message(path: str) -> bytes:
    payload = json.dumps({"action": IMPORT_ACTION, "path": os.path.abspath(path)}, ensure_ascii=False)
    return (payload + "\n").encode("utf-8")


def _decode_ipc_messages(data: bytes) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return messages


def try_forward_import_to_running_instance(paths: list[str], socket_name: str = IPC_SOCKET_NAME) -> bool:
    if not paths:
        return False
    from PyQt6.QtCore import QCoreApplication
    from PyQt6.QtNetwork import QLocalSocket

    core = QCoreApplication.instance() or QCoreApplication([])
    sock = QLocalSocket(core)
    sock.connectToServer(socket_name)
    if not sock.waitForConnected(400):
        return False
    for path in paths:
        sock.write(_encode_ipc_message(path))
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def launch_with_import(path: str) -> bool:
    info = get_installation_info()
    if not info:
        return False
    import subprocess

    exe = info["install_path"]
    if not os.path.isfile(exe):
        return False
    subprocess.Popen([exe, "--import", os.path.abspath(path)], close_fds=True)
    return True


def import_dxf(path: str) -> bool:
    """Импорт DXF: в запущенный экземпляр или через запуск exe."""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return False
    if try_forward_import_to_running_instance([path]):
        return True
    return launch_with_import(path)


def decode_ipc_messages(data: bytes) -> list[str]:
    paths: list[str] = []
    for message in _decode_ipc_messages(data):
        if message.get("action") != IMPORT_ACTION:
            continue
        file_path = message.get("path")
        if isinstance(file_path, str) and os.path.isfile(file_path):
            paths.append(os.path.abspath(file_path))
    return paths
