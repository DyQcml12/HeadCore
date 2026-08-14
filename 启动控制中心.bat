@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe"
set "HOST=127.0.0.1"
set "PORT=8000"
set "CONTROL_URL=http://%HOST%:%PORT%/control"

title HutaoChatCore Control Center

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found:
    echo %PYTHON_EXE%
    echo.
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%" || (
    echo [ERROR] Cannot enter project directory:
    echo %PROJECT_DIR%
    echo.
    pause
    exit /b 1
)

echo HutaoChatCore control center
echo Project: %PROJECT_DIR%
echo URL:     %CONTROL_URL%
echo.

if /i "%~1"=="--check-only" (
    echo [OK] Startup script check passed.
    exit /b 0
)

echo Browser will open automatically in a few seconds.
echo Keep this window open while using the control center.
echo Press Ctrl+C to stop the server.
echo.

start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process '%CONTROL_URL%'"

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://%HOST%:%PORT%/health' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if !ERRORLEVEL! EQU 0 (
    echo Core API is already running on %HOST%:%PORT%.
    echo Control center: %CONTROL_URL%
    echo.
    pause
    exit /b 0
)

"%PYTHON_EXE%" -m uvicorn app.main:app --host %HOST% --port %PORT%

echo.
echo HutaoChatCore control center stopped.
pause
