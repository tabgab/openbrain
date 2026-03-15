@echo off
REM Open Brain — Stop All Services (Windows)
echo Stopping Open Brain services...

REM Kill by port (most reliable on Windows)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1 && echo   OK API server stopped
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3100 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1 && echo   OK MCP server stopped
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1 && echo   OK Vite UI stopped
)

REM Also try by image name patterns
taskkill /F /FI "WINDOWTITLE eq telegram_bot*" >nul 2>&1 && echo   OK Telegram bot stopped

echo Done.
