# Интеграция: как другой программе узнать, что DXF Rectangle Creator установлен, и открыть в нём DXF

## Общая схема

```
Ваша программа
    │
    ├─ 1. Прочитать реестр → программа установлена?
    │
    └─ 2. Отправить DXF
           ├─ редактор уже запущен → IPC (локальный сокет)
           └─ не запущен → запуск exe с --import
```

Редактор при **каждом запуске** записывает сведения о себе в реестр Windows. Пока пользователь хотя бы раз не запустил программу после установки, запись в реестре может отсутствовать.

---

## 1. Как проверить, что программа есть

### Реестр Windows

| Параметр | Значение |
|----------|----------|
| Раздел | `HKEY_CURRENT_USER\Software\Jkl88\DXF Rectangle Creator` |
| `AppId` | `dxf-rectangle-creator` |
| `InstallPath` | полный путь к `DXF_Rectangle_Creator.exe` |
| `Version` | версия, например `2.0.3` |
| `ImportFormats` | `dxf` |
| `IpcSocket` | `Jkl88.DXF_Rectangle_Creator` |

**Программа считается установленной**, если:

1. ключ реестра существует;
2. `InstallPath` указывает на **существующий** `.exe`.

### Python

```python
import os
import winreg

REG_KEY = r"Software\Jkl88\DXF Rectangle Creator"

def is_dxf_rectangle_creator_available() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
            install_path, _ = winreg.QueryValueEx(key, "InstallPath")
            import_formats, _ = winreg.QueryValueEx(key, "ImportFormats")
    except OSError:
        return False
    return (
        os.path.isfile(install_path)
        and "dxf" in import_formats.lower()
    )
```

### C#

```csharp
using Microsoft.Win32;

bool IsDxfRectangleCreatorAvailable()
{
    using var key = Registry.CurrentUser.OpenSubKey(@"Software\Jkl88\DXF Rectangle Creator");
    if (key == null) return false;

    var installPath = key.GetValue("InstallPath") as string;
    var formats = key.GetValue("ImportFormats") as string ?? "";

    return File.Exists(installPath) && formats.Contains("dxf", StringComparison.OrdinalIgnoreCase);
}
```

### Если у вас тоже Python-проект

Можно использовать готовый модуль из этого репозитория:

```python
from app.integration import get_installation_info, import_dxf

info = get_installation_info()
if info:
    print("Установлена:", info["install_path"], "v", info["version"])

# Открыть DXF (сам выберет: в запущенный экземпляр или новый запуск)
ok = import_dxf(r"C:\path\to\file.dxf")
```

---

## 2. Как открыть DXF в этой программе

Рекомендуемый порядок:

1. Проверить реестр.
2. Попробовать отправить файл **в уже запущенный** экземпляр (IPC).
3. Если не получилось — **запустить exe** с аргументом `--import`.

### Способ A — запуск exe (самый простой)

```text
"C:\Path\To\DXF_Rectangle_Creator.exe" --import "C:\path\to\file.dxf"
```

Допустимые варианты аргументов:

```text
--import "C:\file.dxf"
--import=C:\file.dxf
"C:\file.dxf"          (если путь существует и заканчивается на .dxf)
```

**Python:**

```python
import subprocess
import winreg
import os

def open_dxf_in_rectangle_creator(dxf_path: str) -> bool:
    dxf_path = os.path.abspath(dxf_path)
    if not os.path.isfile(dxf_path):
        return False

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Jkl88\DXF Rectangle Creator") as key:
        exe, _ = winreg.QueryValueEx(key, "InstallPath")

    subprocess.Popen([exe, "--import", dxf_path])
    return True
```

**C#:**

```csharp
Process.Start(installPath, $"--import \"{dxfPath}\"");
```

Если редактор **уже открыт**, второй запуск с `--import` не создаст новое окно — файл уйдёт в уже работающий экземпляр и процесс завершится.

---

### Способ B — IPC (если редактор уже запущен)

Имя локального сокета: `Jkl88.DXF_Rectangle_Creator`

Сообщение — одна строка JSON + перевод строки `\n`:

```json
{"action": "import_dxf", "path": "C:\\path\\to\\file.dxf"}
```

**Python (PyQt6, как в редакторе):**

```python
import json
import os
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtNetwork import QLocalSocket

SOCKET = "Jkl88.DXF_Rectangle_Creator"

def send_dxf_to_running_instance(dxf_path: str) -> bool:
    app = QCoreApplication.instance() or QCoreApplication([])
    sock = QLocalSocket(app)
    sock.connectToServer(SOCKET)
    if not sock.waitForConnected(400):
        return False

    msg = json.dumps({
        "action": "import_dxf",
        "path": os.path.abspath(dxf_path),
    }, ensure_ascii=False) + "\n"
    sock.write(msg.encode("utf-8"))
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True
```

**C# (Qt-совместимый named pipe на Windows):**

На Windows `QLocalServer` использует именованный канал. Имя обычно: `\\.\pipe\Jkl88.DXF_Rectangle_Creator` (если прямое подключение не сработает — используйте способ A, он надёжнее).

---

### Способ C — готовая функция «всё сразу»

```python
from app.integration import import_dxf

success = import_dxf(r"C:\path\to\file.dxf")
```

Логика внутри:

1. попытка IPC → запущенный экземпляр;
2. если не вышло → `subprocess` с `--import`.

---

## 3. Что увидит пользователь после импорта

После открытия DXF (любым способом) редактор:

1. загружает контур из файла;
2. показывает диалог **«Установите базовую точку»**;
3. ждёт клик по контуру для задания начала координат.

Это штатное поведение, его стоит учитывать в UX вашей программы.

---

## 4. Чеклист для вашей программы

| Шаг | Действие |
|-----|----------|
| 1 | Прочитать `HKCU\Software\Jkl88\DXF Rectangle Creator` |
| 2 | Проверить, что `InstallPath` существует |
| 3 | Проверить `ImportFormats` содержит `dxf` |
| 4 | Вызвать `import_dxf(path)` или запустить `exe --import path` |
| 5 | При отсутствии в реестре — показать «установите и запустите DXF Rectangle Creator» |

---

## 5. Важные замечания

- Интеграция рассчитана на **Windows**.
- Запись в реестр появляется **после первого запуска** программы.
- Путь к DXF должен быть **абсолютным** и файл должен **существовать**.
- Ручной способ для пользователя: перетащить `.dxf` в окно редактора (drag-and-drop).

---

## См. также

- Реализация на стороне редактора: `app/integration.py`
