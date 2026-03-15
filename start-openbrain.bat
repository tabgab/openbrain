@echo off
REM Open Brain — Start All Services (Windows)
REM Stops any existing instances first, then starts everything fresh.

echo Open Brain — Starting up...

REM Stop existing services first
echo -- Cleaning up old processes...
taskkill /F /FI "WINDOWTITLE eq uvicorn*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq telegram_bot*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq server.py*" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3100 " ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173 " ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
timeout /t 1 >nul

REM Activate venv
call venv\Scripts\activate.bat

REM Install/update deps quietly
echo -- Checking dependencies...
pip install -q fastapi uvicorn python-multipart requests openai psycopg2-binary python-dotenv pgvector numpy PyPDF2 python-docx openpyxl Pillow pymupdf mcp cryptography 2>nul

REM Start API Server
echo -- Starting FastAPI backend on :8000...
start "uvicorn" /B cmd /c "uvicorn src.api:app --host 0.0.0.0 --port 8000"

REM Start Telegram Bot
echo -- Starting Telegram bot...
start "telegram_bot" /B cmd /c "python src/telegram_bot.py"

REM Start MCP Server (SSE)
echo -- Starting MCP server on :3100...
set MCP_TRANSPORT=sse
start "server.py" /B cmd /c "python src/server.py"

REM Start Vite Frontend
echo -- Starting Web UI on :5173...
cd ui
start "vite" /B cmd /c "npm run dev"
cd ..

echo.
echo Open Brain is running!
echo    Dashboard: http://localhost:5173
echo    API:       http://localhost:8000
echo    MCP (SSE): http://localhost:3100/sse
echo.
echo    Press Ctrl+C or close this window to stop.
echo.

REM Keep window open
pause
