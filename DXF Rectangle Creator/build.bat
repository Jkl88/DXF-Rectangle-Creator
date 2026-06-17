@echo off
chcp 65001 >nul
title DXF Creator Build

echo =======================================
echo   СБОРКА DXF Rectangle Creator (EXE)
echo =======================================
echo.

echo Удаляем старые сборки...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del DXF_Rectangle_Creator.spec 2>nul

echo.
echo Запуск PyInstaller...
echo.

pyinstaller ^
 --noconfirm ^
 --onefile ^
 --windowed ^
 --clean ^
 --name DXF_Rectangle_Creator ^
 --exclude PySide6 ^
 --exclude shiboken6 ^
 --exclude PyQt5 ^
 --collect-all PyQt6 ^
 --collect-all ezdxf ^
 --collect-all numpy ^
 --paths . ^
 main.py

echo.
echo =======================================
echo   СБОРКА ЗАВЕРШЕНА!
echo =======================================
echo.

if exist dist\DXF_Rectangle_Creator.exe (
    echo Готовый файл:
    echo   dist\DXF_Rectangle_Creator.exe
) else (
    echo ОШИБКА: EXE не был создан.
)

echo.
pause
