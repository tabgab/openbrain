#!/bin/bash

# Open Brain — Stop All Services
echo "🧠 Stopping Open Brain services..."

# Kill API server
pkill -f "uvicorn src.api:app" 2>/dev/null && echo "  ✓ API server stopped" || echo "  - API server not running"

# Kill Telegram bot
pkill -f "python src/telegram_bot.py" 2>/dev/null && echo "  ✓ Telegram bot stopped" || echo "  - Telegram bot not running"

# Kill MCP server
pkill -f "python src/server.py" 2>/dev/null && echo "  ✓ MCP server stopped" || echo "  - MCP server not running"

# Kill Vite dev server
pkill -f "vite" 2>/dev/null && echo "  ✓ Vite UI stopped" || echo "  - Vite UI not running"

echo "Done."
