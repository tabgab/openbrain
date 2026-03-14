#!/bin/bash

# Open Brain — Start All Services
# Stops any existing instances first, then starts everything fresh.

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🧠 Open Brain — Starting up..."

# Stop existing services first
echo "── Cleaning up old processes..."
pkill -f "uvicorn src.api:app" 2>/dev/null
pkill -f "python src/telegram_bot.py" 2>/dev/null
pkill -f "python src/server.py" 2>/dev/null
pkill -f "vite" 2>/dev/null
sleep 1

# Activate venv
source "$DIR/venv/bin/activate"

# Install/update deps quietly
echo "── Checking dependencies..."
pip install -q fastapi uvicorn python-multipart requests openai psycopg2-binary \
    python-dotenv pgvector numpy PyPDF2 python-docx openpyxl Pillow 2>/dev/null

# 1. API Server
echo "── Starting FastAPI backend on :8000..."
uvicorn src.api:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# 2. Telegram Bot
echo "── Starting Telegram bot..."
python src/telegram_bot.py &
BOT_PID=$!

# 3. MCP Server (SSE transport on port 3100)
echo "── Starting MCP server on :3100..."
MCP_TRANSPORT=sse python src/server.py &
MCP_PID=$!

# 4. Vite Frontend
echo "── Starting Web UI on :5173..."
cd "$DIR/ui"
npm run dev &
UI_PID=$!

echo ""
echo "🟢 Open Brain is running!"
echo "   Dashboard: http://localhost:5173"
echo "   API:       http://localhost:8000"
echo "   MCP (SSE): http://localhost:3100/sse"
echo ""
echo "   Press Ctrl+C to stop all services."
echo ""

# Trap Ctrl+C to kill all child processes
trap "echo ''; echo '🔴 Shutting down...'; kill $API_PID $BOT_PID $MCP_PID $UI_PID 2>/dev/null; exit 0" INT TERM

# Wait for all processes
wait $API_PID $BOT_PID $MCP_PID $UI_PID
