@echo off
setlocal
cd /d "%~dp0"

echo =======================================
echo   DXF Rectangle Creator build v2.0.0
echo =======================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    pause
    exit /b 1
)

echo Installing dependencies...
python -m pip install -r requirements.txt pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

echo.
echo Cleaning old build...
if exist build rmdir /s /q build
if exist dist\DXF_Rectangle_Creator.exe del /f /q dist\DXF_Rectangle_Creator.exe 2>nul

echo.
echo Running PyInstaller...
python -m PyInstaller --noconfirm --clean DXF_Rectangle_Creator.spec
if errorlevel 1 (
    if not exist dist\DXF_Rectangle_Creator.exe (
        echo ERROR: PyInstaller failed and EXE was not created.
        pause
        exit /b 1
    )
    echo WARNING: PyInstaller reported an error, but EXE exists.
)

if not exist dist\DXF_Rectangle_Creator.exe (
    echo ERROR: EXE was not created.
    pause
    exit /b 1
)

echo.
echo =======================================
echo   BUILD COMPLETE
echo =======================================
echo   dist\DXF_Rectangle_Creator.exe
echo.
pause
endlocal
