# 🧠 Open Brain

**Your personal AI-powered knowledge base and second brain.**

Open Brain is a self-hosted system that stores, categorizes, and retrieves your personal information — notes, invoices, ideas, documents, and more — using semantic search and multi-model AI. It works as an **MCP server** so any AI assistant (Windsurf, Claude Desktop, Cursor, etc.) can read and write to your brain, and includes a **Telegram bot** for on-the-go capture and querying.

---

## ✨ Features

- **Semantic Memory Search** — Store anything, find it later by meaning (not just keywords) using pgvector embeddings
- **Multi-Model AI** — Configurable LLM roles (text, reasoning, coding, vision, embedding) via OpenRouter, supporting 200+ models
- **Document Ingestion** — Upload PDFs (including scanned), images, Word docs, Excel files — auto-OCR, categorize, and embed
- **Telegram Bot** — Send text, photos, or documents via Telegram to capture memories; ask questions naturally
- **Auto Question Detection** — The bot intelligently distinguishes questions from memories without needing prefixes
- **MCP Server** — Full Model Context Protocol support (stdio + SSE) so other AI systems can use your brain as a tool
- **PII Scrubbing** — Automatic detection and redaction of secrets, API keys, credit cards, SSNs
- **Secure Vault** — Sensitive information stored separately, never exposed in search results
- **Google Drive Sync** — OAuth 2.0 connection to Google Drive; search, filter, preview, and selectively ingest documents (Docs, Sheets, PDFs, etc.)
- **Gmail Integration** — Search, preview, and ingest emails with optional image OCR; filter by label (including custom labels)
- **Google Calendar** — Scan calendars with week/month/list views, per-calendar color-coded toggles, recurring event deduplication, and selective ingestion
- **WhatsApp Import** — Import WhatsApp chat exports (.txt files); messages are grouped, categorized, and stored
- **Smart Search** — Questions automatically search stored memories, Google Calendar, and Gmail with LLM-powered common-sense query expansion (e.g., "dentist" also searches "Nánási Dent", "Dentideal")
- **Search Mode Toggle** — Choose between "Memory Only" (fast, stored data) and "Advanced Search" (memories + Calendar + Gmail) in both the dashboard and Telegram
- **Live Thinking Process** — Real-time streaming of search steps as they happen (SSE), with collapsible thinking panel on answers
- **Dashboard Chat** — Chat with your brain directly from the web dashboard with streaming answers, same auto-detect logic as Telegram
- **Web Dashboard** — Beautiful React UI for browsing memories, uploading documents, chatting, configuring models, and viewing logs
- **Encrypted Backup & Restore** — One-click AES-256-GCM encrypted backup of your entire brain (database, vault, config) with password-protected restore
- **Setup Wizard** — Guided first-run configuration for API keys, database, and Telegram bot

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Open Brain                         │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Telegram  │  │  Web Dashboard│  │   MCP Server      │  │
│  │ Bot       │  │  (React/Vite) │  │   (stdio + SSE)   │  │
│  │ :telegram │  │  :5173        │  │   :3100            │  │
│  └─────┬─────┘  └──────┬───────┘  └────────┬──────────┘  │
│        │               │                    │             │
│        └───────────────┼────────────────────┘             │
│                        │                                  │
│                 ┌──────┴───────┐                          │
│                 │  FastAPI     │                          │
│                 │  Backend     │                          │
│                 │  :8000       │                          │
│                 └──────┬───────┘                          │
│                        │                                  │
│           ┌────────────┼────────────┐                     │
│           │            │            │                     │
│      ┌────┴────┐ ┌─────┴─────┐ ┌───┴────┐               │
│      │ LLM     │ │ Ingestion │ │Scrubber│               │
│      │ (multi- │ │ Pipeline  │ │ (PII)  │               │
│      │  model) │ │           │ │        │               │
│      └────┬────┘ └───────────┘ └────────┘               │
│           │                                              │
│    ┌──────┴──────┐                                       │
│    │  OpenRouter  │  (or OpenAI, Ollama, etc.)           │
│    └─────────────┘                                       │
│                                                          │
│    ┌──────────────────────────────┐                      │
│    │  PostgreSQL + pgvector       │                      │
│    │  (memories + vault tables)   │                      │
│    └──────────────────────────────┘                      │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Node.js 18+** and npm
- **Docker** (for PostgreSQL + pgvector)
- An **OpenRouter API key** (or OpenAI/Ollama)
- A **Telegram Bot Token** (from [@BotFather](https://t.me/BotFather))

### 1. Clone & Configure

```bash
git clone https://github.com/tabgab/openbrain.git
cd openbrain

# Copy the example env and fill in your credentials
cp .env.example .env
# Edit .env with your API keys, database password, and Telegram token
```

### 2. Start the Database

```bash
docker compose up -d
```

This starts PostgreSQL with pgvector. The schema is auto-initialized from `init-scripts/schema.sql`.

### 3. Set Up Python Environment

```bash
python3 -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate.bat       # Windows
pip install fastapi uvicorn python-multipart requests openai psycopg2-binary \
    python-dotenv pgvector numpy PyPDF2 python-docx openpyxl Pillow pymupdf mcp
```

### 4. Set Up Frontend

```bash
cd ui
npm install
cd ..
```

### 5. Start Everything

```bash
# macOS / Linux
./start-openbrain.sh

# Windows
start-openbrain.bat
```

This starts all four services:

| Service         | Port  | Description                        |
|-----------------|-------|------------------------------------|
| FastAPI Backend | 8000  | REST API for dashboard & ingestion |
| Telegram Bot    | —     | Long-poll listener                 |
| MCP Server      | 3100  | SSE transport for AI agents        |
| Web Dashboard   | 5173  | React UI (Vite dev server)         |

To stop everything: `./stop-openbrain.sh` (or `stop-openbrain.bat` on Windows)

---

## 📱 Telegram Bot

Send messages to your bot on Telegram:

| Input | Action |
|-------|--------|
| Any text | Auto-detected: stored as memory OR answered as question |
| `q: <question>` | Explicit question (searches brain + answers via reasoning model) |
| `/ask <question>` | Same as above |
| `m: <text>` | Force-store as memory (even if it looks like a question) |
| Send a photo | Vision model describes it, stored as memory |
| Send a document | PDF/Word/Excel parsed, categorized, and stored |

The bot auto-detects questions using heuristics + LLM classification — no prefix needed in most cases.

When a question is detected, the bot presents **inline keyboard buttons** to choose:
- **🧠 Memory Only** — Fast search of stored memories only
- **🔎 Advanced Search** — Searches memories + Google Calendar + Gmail with smart query expansion

---

## ☁️ Google Drive, Gmail & Calendar

Sync files from Google Drive, emails from Gmail, and events from Google Calendar directly into your Open Brain.

### Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one)
3. Enable the **Google Drive API**, **Gmail API**, and **Google Calendar API**
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
   - Application type: **Web application**
   - Authorized redirect URI: `http://localhost:8000/api/google/callback`
5. Download the JSON file and save it as `google_credentials.json` in the project root
6. In the dashboard, go to **Settings → Google Drive, Gmail & Calendar** and click **Add Account**
7. Authorize in the browser — you'll be redirected back automatically
8. Add your Google email(s) as **test users** in the OAuth consent screen (required for external apps)

### Google Drive

Search and filter files by name, type, and date. Preview files before ingesting. Select individual files or bulk-select and ingest into your brain.

### Gmail

Search emails with filters (sender, subject, label, date range). All labels are shown including custom ones. Preview email content inline. Ingest with optional image attachment OCR via vision model.

### Google Calendar

Scan all connected calendars with three view modes:
- **Week view** — 7-day grid with color-coded event chips
- **Month view** — Full month grid with overflow indicators
- **List view** — Flat searchable list with inline preview

Features:
- **Per-calendar toggle chips** — Click to show/hide calendars, colored to match Google Calendar colors
- **Recurring event deduplication** — Recurring events collapsed into one entry with pattern info (Weekly, Biweekly, Monthly, etc.)
- **"In Brain" indicators** — Already-ingested events clearly marked in all views
- **Startup scan prompt** — First scan covers 12 months; subsequent scans cover the current month
- **Selective ingestion** — Pick individual events or select all new

---

## 💬 WhatsApp Import

Import WhatsApp chat history into your Open Brain:

1. In WhatsApp, open a chat → tap **⋮** → **Export chat** → **Without media**
2. Save the `.txt` file
3. In the dashboard, go to **Settings → WhatsApp Import**
4. Select the file, optionally name the chat, and click **Import Chat**

Messages are grouped by sender (consecutive messages merged), PII-scrubbed, categorized, and stored with metadata (sender, timestamp, chat name).

---

## 🔌 MCP Server

Other AI systems can connect to Open Brain as an MCP server with **17 tools**:

### Memory Tools
- `save_memory` — Store a fact/note (auto-categorized, embedded, PII-scrubbed)
- `search_brain` — Semantic similarity search
- `ask_brain` — Q&A with smart search (memories + Calendar + Gmail, with query expansion)
- `list_memories` — Browse recent memories
- `edit_memory` — Update content (auto re-embeds)
- `remove_memory` — Delete a memory

### Document Tools
- `ingest_document` — Parse and store a document (base64-encoded)

### Vault Tools
- `save_vault_secret` / `get_vault_secret` — Secure secret storage

### Gmail Tools
- `search_gmail` — Search emails by query, label, date range
- `read_gmail` — Read full content of a specific email
- `ingest_gmail` — Ingest emails into the brain (with optional image OCR)

### Calendar Tools
- `search_calendar` — Search calendar events by query, date range
- `read_calendar_event` — Read full details of a specific event
- `ingest_calendar_events` — Ingest events into the brain

### Account Tools
- `list_google_accounts` — List connected Google accounts

### Connecting via stdio (Windsurf, Claude Desktop, Cursor)

Add to your MCP config (e.g., `~/.codeium/windsurf/mcp_config.json`):

```json
{
  "mcpServers": {
    "openbrain": {
      "command": "python",
      "args": ["src/server.py"],
      "cwd": "/path/to/openbrain",
      "env": {
        "PYTHONPATH": "src"
      }
    }
  }
}
```

### Connecting via SSE (network access)

The SSE server runs on `http://localhost:3100/sse` when started with `./start-openbrain.sh`.

---

## 🎨 Web Dashboard

Access at **http://localhost:5173** after starting services.

- **Dashboard** — Browse memories, edit/delete, upload documents
- **Chat** — Conversational interface with streaming answers, live thinking process, and search mode toggle (Memory Only / Advanced Search)
- **Settings** — Configure model roles, API keys, database, Telegram token, backup & restore, Google Drive/Gmail/Calendar, WhatsApp import
- **Logs** — Real-time system event log from all services

---

## 🤖 Multi-Model Configuration

Open Brain uses role-based model assignment. Each task type can use a different model:

| Role | Default Model | Purpose |
|------|--------------|---------|
| **Text** | `moonshotai/kimi-k2.5` | Categorization, extraction, question detection |
| **Reasoning** | `anthropic/claude-sonnet-4.6` | Complex Q&A, analysis, research |
| **Coding** | `minimax/minimax-m2.5` | Code generation, debugging |
| **Vision** | `moonshotai/kimi-k2.5` | OCR, image description, scanned PDFs |
| **Embedding** | `openai/text-embedding-3-small` | Vector embeddings for semantic search |

All models are accessed through **OpenRouter** by default (one API key, 200+ models). You can also point to local models via Ollama or direct OpenAI.

Configure in `.env` or via the Settings tab in the dashboard.

---

## 📁 Project Structure

```
openbrain/
├── src/
│   ├── api.py              # FastAPI REST endpoints
│   ├── db.py               # PostgreSQL/pgvector database layer
│   ├── llm.py              # Multi-model LLM client (roles, embeddings, vision)
│   ├── ingest.py           # Document ingestion (PDF, images, Word, Excel)
│   ├── backup.py           # Encrypted backup & restore (AES-256-GCM)
│   ├── google_integration.py # Google Drive, Gmail & Calendar OAuth + sync
│   ├── whatsapp_import.py  # WhatsApp chat export parser & ingester
│   ├── smart_search.py     # Augmented search (Calendar + Gmail + query expansion)
│   ├── scrubber.py         # PII detection and redaction
│   ├── server.py           # MCP server (stdio + SSE)
│   └── telegram_bot.py     # Telegram bot with auto question detection + search mode
├── ui/
│   └── src/App.tsx         # React dashboard (settings, memories, logs)
├── init-scripts/
│   └── schema.sql          # PostgreSQL schema (memories + vault tables)
├── docker-compose.yml      # PostgreSQL + pgvector container
├── .env.example            # Template for configuration
├── start-openbrain.sh      # Start all services (macOS/Linux)
├── stop-openbrain.sh       # Stop all services (macOS/Linux)
├── start-openbrain.bat     # Start all services (Windows)
├── stop-openbrain.bat      # Stop all services (Windows)
└── project_thesis.md       # Original project vision
```

---

## 🔒 Security

- **PII Scrubbing** — API keys, credit cards, SSNs, and passwords are automatically detected and redacted before storage
- **Secure Vault** — Extracted secrets are stored in a separate encrypted-at-rest table, never in the searchable memory index
- **Masked Display** — Secrets are masked in the dashboard and API responses
- **Authorization** — Optional `TELEGRAM_AUTHORIZED_CHAT_ID` restricts bot access to a single user
- **No secret leakage** — `.gitignore` excludes `.env`, and the settings UI never sends masked values back to the server
- **Encrypted Backups** — Backups use AES-256-GCM with PBKDF2 key derivation (600k iterations); the `.obk` file is a single opaque blob

---

## 💾 Backup & Restore

Open Brain includes a full encrypted backup and restore system. A backup packages **everything** into a single password-protected file:

- All memories (with embeddings)
- All vault secrets
- `.env` configuration (API keys, database credentials, model settings)
- Database schema

### Creating a Backup

1. Go to **Settings → Backup & Restore** in the dashboard
2. Enter an encryption password (minimum 4 characters — use a strong passphrase)
3. Click **Download Backup** — saves an `.obk` file

Or via API:
```bash
curl -X POST http://localhost:8000/api/backup \
  -H 'Content-Type: application/json' \
  -d '{"password": "your-strong-password"}' \
  -o openbrain_backup.obk
```

### Restoring from Backup

1. Set up a fresh Open Brain instance (clone repo, start database, create venv)
2. Go to **Settings → Backup & Restore**
3. Select the `.obk` file and enter the original password
4. Click **Restore System** — all data and config are restored
5. Restart the backend to apply the restored `.env`

Or via API:
```bash
curl -X POST http://localhost:8000/api/restore \
  -F 'file=@openbrain_backup.obk' \
  -F 'password=your-strong-password'
```

### Encryption Details

| Property | Value |
|----------|-------|
| Cipher | AES-256-GCM |
| Key derivation | PBKDF2-HMAC-SHA256, 600,000 iterations |
| Salt | 16 bytes random per backup |
| Nonce | 12 bytes random per backup |
| File format | `[salt][nonce][ciphertext+GCM-tag]` |

The backup file (`.obk`) is opaque — without the password, it is computationally infeasible to recover any data.

---

## 🛠️ Development

```bash
# Start only the database
docker compose up -d

# Run backend manually (with hot reload)
source venv/bin/activate
uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

# Run frontend with hot reload
cd ui && npm run dev

# Run Telegram bot
python src/telegram_bot.py

# Run MCP server (stdio mode for testing)
python src/server.py
```

---

## 📄 License

MIT — use it, fork it, make it yours.

---

## 🙏 Credits

- Inspired by ideas from [Nate Jones](https://gemini.google.com/share/b07f16ab6580)
- Built with [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), [pgvector](https://github.com/pgvector/pgvector), [OpenRouter](https://openrouter.ai/), and [MCP](https://modelcontextprotocol.io/)
