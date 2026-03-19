# 🧠 Open Brain

**Your personal AI-powered knowledge base and second brain.**

Open Brain is a self-hosted system that stores, categorizes, and retrieves your personal information — notes, invoices, ideas, documents, and more — using semantic search and multi-model AI. It works as an **MCP server** so any AI assistant (Windsurf, Claude Desktop, Cursor, etc.) can read and write to your brain, and includes a **Telegram bot** for on-the-go capture and querying.

---

## ✨ Features

- **Semantic Memory Search** — Store anything, find it later by meaning (not just keywords) using pgvector embeddings
- **Multi-Model AI** — Configurable LLM roles (text, reasoning, coding, vision, embedding) via OpenRouter, supporting 200+ models
- **Document Ingestion** — Upload PDFs (including scanned), images, Word docs, Excel files — auto-OCR, categorize, and embed
- **Telegram Bot** — Send text, photos, documents, or voice notes via Telegram to capture memories; ask questions naturally
- **Voice Note Transcription** — Send a voice message via Telegram; it's auto-transcribed (language detected), then routed as a question or stored as a memory. Configurable STT provider: OpenAI Whisper API, local Whisper (with automatic GPU detection for CUDA/MPS), or Groq. Pre-download models from Settings to avoid first-use delay
- **Auto Question Detection** — The bot intelligently distinguishes questions from memories without needing prefixes
- **MCP Server** — Full Model Context Protocol support (stdio + SSE) so other AI systems can use your brain as a tool
- **PII Scrubbing** — Automatic detection and redaction of secrets, API keys, credit cards, SSNs
- **Secure Vault** — Sensitive information stored separately, never exposed in search results
- **Google Drive Sync** — OAuth 2.0 connection to Google Drive; search, filter, preview, and selectively ingest documents (Docs, Sheets, PDFs, etc.)
- **Gmail Integration** — Search, preview, and ingest emails with optional image OCR; filter by label (including custom labels)
- **Google Calendar** — Scan calendars with week/month/list views, per-calendar color-coded toggles, recurring event deduplication, and selective ingestion
- **Google Photos** — Ingest photos via the Picker API; user selects images in Google's native picker, photos are described by the vision model and stored as searchable memories with metadata (camera, resolution, date)
- **Microsoft 365** — OAuth 2.0 connection to OneDrive, Outlook, and Calendar via Microsoft Graph API; search, filter, and selectively ingest files, emails, and events (supports personal and organizational accounts)
- **Dropbox** — OAuth 2.0 integration; search files by name/type/path and ingest into your brain
- **pCloud** — OAuth 2.0 integration; browse and filter files, ingest into your brain
- **MEGA** — End-to-end encrypted cloud storage; sign in with email/password, browse and ingest files
- **Manual Import** — Import data from end-to-end encrypted or API-less services: Proton Mail/Drive, iCloud Mail/Drive, Tuta Mail, and WhatsApp — export your data, then upload the files
- **Paginated List Views** — All file and result lists (Google, Microsoft, Dropbox, pCloud, MEGA) use paginated Prev/Next navigation, matching the Gmail pagination pattern
- **URL Content Extraction** — Send a URL (X/Twitter post, YouTube video, article, etc.) via Telegram or Dashboard Chat and the actual content is automatically fetched, extracted, and stored as a searchable memory
- **YouTube Video Summarization** — YouTube links are enriched with the actual video transcript (via captions), summarized by an LLM, and stored with title, channel, summary, and source URL for full searchability
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

- **Python 3.10+**
- **Node.js 18+** and npm
- **Docker** (for PostgreSQL + pgvector)
- An **OpenRouter API key** (or OpenAI/Ollama)
- A **Telegram Bot Token** (optional, from [@BotFather](https://t.me/BotFather))

### Option A: Interactive Installer (Recommended)

The easiest way to get started. The installer checks prerequisites, installs dependencies, starts the database, and walks you through configuration — all interactively.

```bash
git clone https://github.com/tabgab/openbrain.git
cd openbrain

# macOS / Linux
./install.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File install.ps1
```

The installer will:
1. **Check & install prerequisites** — Python, Node.js, Docker (via Homebrew, apt/dnf/pacman, or winget)
2. **Create a Python virtual environment** and install all packages from `requirements.txt`
3. **Install frontend dependencies** (`npm install` in the `ui/` directory)
4. **Start PostgreSQL + pgvector** via Docker Compose
5. **Walk you through `.env` configuration** — API keys, model selection, Telegram token, database credentials, STT settings (all with sensible defaults)
6. **Verify everything works** — checks imports, database connection, and UI dependencies

After installation, just run:
```bash
./start-openbrain.sh          # macOS / Linux
start-openbrain.bat            # Windows
```

### Option B: Manual Setup

<details>
<summary>Click to expand manual setup instructions</summary>

#### 1. Clone & Configure

```bash
git clone https://github.com/tabgab/openbrain.git
cd openbrain
cp .env.example .env
# Edit .env with your API keys, database password, and Telegram token
```

#### 2. Start the Database

```bash
docker compose up -d
```

This starts PostgreSQL with pgvector. The schema is auto-initialized from `init-scripts/schema.sql`.

#### 3. Set Up Python Environment

```bash
python3 -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate.bat       # Windows
pip install -r requirements.txt
```

#### 4. Set Up Frontend

```bash
cd ui && npm install && cd ..
```

#### 5. Start Everything

```bash
./start-openbrain.sh              # macOS / Linux
start-openbrain.bat                # Windows
```

</details>

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
| Send a voice note | Transcribed (language auto-detected), then routed as question or stored as memory |
| Send a YouTube link | Video transcript fetched, LLM-summarized, stored with URL |

The bot auto-detects questions using heuristics + LLM classification — no prefix needed in most cases.

When a question is detected, the bot presents **inline keyboard buttons** to choose:
- **🧠 Memory Only** — Fast search of stored memories only
- **🔎 Advanced Search** — Searches memories + Google Calendar + Gmail with smart query expansion

---

## ☁️ Google Drive, Gmail, Calendar & Photos

Sync files from Google Drive, emails from Gmail, events from Google Calendar, and photos from Google Photos directly into your Open Brain.

### Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one)
3. Enable the **Google Drive API**, **Gmail API**, **Google Calendar API**, and **Photos Picker API**
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
   - Application type: **Web application**
   - Authorized redirect URI: `http://localhost:8000/api/google/callback`
5. Download the JSON file and save it as `google_credentials.json` in the project root
6. In the dashboard, go to **Settings → Google Drive, Gmail, Calendar & Photos** and click **Add Account**
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

### Google Photos

Ingest photos from Google Photos using the **Picker API** (the new post-March 2025 approach — `photoslibrary.readonly` scope is deprecated).

**How it works:**
1. Click **Pick Photos** in the Photos tab — this opens Google's native photo picker in a new browser tab
2. Use Google's built-in search (e.g., "Paris 2024", "Dogs") and select the photos you want
3. Close the picker when done — Open Brain automatically detects completion via polling
4. Review the selected photos (with metadata and sync status)
5. Select which photos to ingest — each photo is downloaded, described by the **vision model**, and stored as a searchable memory

**Features:**
- **Vision model descriptions** — Each photo is analyzed by the configured vision model to generate a rich text description
- **Metadata preserved** — Camera make/model, resolution, creation date stored alongside the description
- **Already-synced indicators** — Photos previously ingested are clearly marked (but can be force re-added)
- **Live ingestion progress** — Per-photo progress bar with success/failure status during ingestion

**Note:** The `baseUrl` provided by Google Photos is temporary (~60 minutes). Photos are downloaded immediately during ingestion. Google Photos IDs are stored in the account data as read-only references — all custom metadata and tags live in Open Brain's own database.

---

## 📎 Microsoft 365 (OneDrive, Outlook, Calendar)

Connect your Microsoft account to search and ingest files from OneDrive, emails from Outlook, and events from Calendar — all via the Microsoft Graph API.

### Setup

1. Go to [Azure Portal → App registrations](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade) and sign in
2. Click **+ New registration**
3. Enter a name (e.g. "Open Brain")
4. Under **Supported account types**, select:  
   **"Accounts in any organizational directory (Any Microsoft Entra ID tenant — Multitenant) and personal Microsoft accounts (e.g. Skype, Xbox)"**
   > ⚠️ If you plan to sign in with a personal Microsoft account (@outlook.com, @hotmail.com, @live.com), you **must** pick this option. Other options will reject personal accounts with a "Tenant mismatch" error.
5. Under **Redirect URI**, select **Web** and enter: `http://localhost:8000/api/microsoft/callback`
6. Click **Register**

#### Enable v2.0 tokens (required for personal accounts)

1. In your app's left sidebar, click **Manifest**
2. Find `requestedAccessTokenVersion` (likely `null` or `1`)
3. Change it to `2` — so it reads: `"requestedAccessTokenVersion": 2`
4. Click **Save**

> Microsoft has two identity platform versions. v1.0 only supports work/school accounts; v2.0 supports both personal and organizational accounts.

#### Get credentials

1. Go to **Overview** → copy the **Application (client) ID**
2. Go to **Certificates & secrets** → **+ New client secret** → copy the **Value** (not the Secret ID)
3. Go to **API permissions** → **+ Add a permission** → **Microsoft Graph** → **Delegated permissions** → add: `User.Read`, `Files.Read`, `Mail.Read`, `Calendars.Read`
4. In the dashboard, paste the Application ID and Client Secret Value

### OneDrive

Search files by name and type. Select individual files or bulk-select and ingest into your brain. Paginated results for large file collections.

### Outlook

Search emails with filters (sender, subject, date range). Preview email content inline. Paginated results with Prev/Next navigation.

### Calendar

Scan calendar events within a configurable date range. View events with time, location, and recurrence info. Selectively ingest events.

#### Troubleshooting

- **"Tenant mismatch"** → Verify the account type allows personal accounts (see setup step 4)
- **"Access token version" error** → Set `requestedAccessTokenVersion` to `2` in the Manifest
- **Changes not taking effect** → Wait 60 seconds for Azure to propagate changes

---

## 📦 Dropbox

Connect your Dropbox account to search and ingest files directly into your brain.

### Setup

1. Go to [Dropbox App Console](https://www.dropbox.com/developers/apps)
2. Click **Create app** → **Scoped access** → **Full Dropbox**
3. Under **Permissions**, enable: `files.metadata.read`, `files.content.read`
4. Under **Settings** → **OAuth 2** → Add redirect URI: `http://localhost:8000/api/dropbox/callback`
5. Create a JSON file with: `{"app_key": "YOUR_KEY", "app_secret": "YOUR_SECRET"}`
6. Upload it in the dashboard, then click **Add Account**

### Features

- Search files by name, path, and type (documents, spreadsheets, PDFs, images)
- Server-side pagination via Dropbox cursor tokens
- Selective or bulk ingestion

---

## ☁️ pCloud

Connect your pCloud account to browse and ingest files.

### Setup

1. Go to [pCloud Developer](https://docs.pcloud.com/) and create an app
2. Under **Settings**, set the redirect URI: `http://localhost:8000/api/pcloud/callback`
3. Create a JSON file with: `{"client_id": "YOUR_ID", "client_secret": "YOUR_SECRET"}`
4. Upload it in the dashboard, then click **Add Account**

### Features

- Browse and filter files by name and type
- Client-side pagination (30 items per page) with "Select page" / "Select all" controls
- Selective or bulk ingestion

---

## 📁 MEGA

Connect your MEGA account to browse and ingest files. MEGA is end-to-end encrypted, so there is no OAuth — you sign in with your email and password directly.

### Setup

1. In the dashboard, go to **Ingest → Cloud Storage → MEGA**
2. Enter your MEGA email and password
3. Click **Sign In** — your files will be available to browse immediately

### Features

- Browse all files in your MEGA cloud
- Filter by name and type (documents, spreadsheets, PDFs, images)
- Client-side pagination (30 items per page)
- Selective or bulk ingestion

**Note:** Your MEGA credentials are stored locally (server-side only) and used solely to authenticate with MEGA’s servers. If you have two-factor authentication enabled, you may need to use an app-specific password.

---

## 📧 Manual Import (Proton, iCloud, Tuta, WhatsApp)

Some services are end-to-end encrypted or don't provide third-party API access. For these, export your data manually and upload the files in the **Files** tab.

### Proton Mail & Drive

1. Install [Proton Mail Bridge](https://proton.me/mail/bridge) on your computer
2. Connect a mail client (Thunderbird recommended) via Bridge
3. Export emails as `.mbox` or `.eml` files
4. Upload in the dashboard under **Files → Manual Import → Proton**
5. For Proton Drive, download files from [drive.proton.me](https://drive.proton.me) and upload them

### iCloud Mail & Drive

1. Export emails from Apple Mail as `.mbox` (Mailbox → Export Mailbox) or forward as `.eml`
2. Download files from [icloud.com/iclouddrive](https://www.icloud.com/iclouddrive)
3. Upload in the dashboard under **Files → Manual Import → iCloud**

### Tuta Mail

1. Use Tuta's export feature (desktop app → Settings → Export)
2. Export emails as `.eml` or `.mbox`
3. Upload in the dashboard under **Files → Manual Import → Tuta**

### WhatsApp

1. In WhatsApp, open a chat → tap **⋮** → **Export chat** → **Without media**
2. Save the `.txt` file
3. Upload in the dashboard under **Files → Manual Import → WhatsApp**
4. Messages are grouped by sender, PII-scrubbed, categorized, and stored with metadata

---

## 🎤 Voice Transcription (STT)

Open Brain transcribes voice notes sent via Telegram (and can be extended to other inputs). Language is auto-detected.

### Providers

| Provider | Config Value | Requirements | Notes |
|----------|-------------|--------------|-------|
| **OpenAI Whisper API** | `openai` (default) | `OPENAI_API_KEY` (direct OpenAI, not OpenRouter) | Fast, accurate, cloud-based |
| **Local Whisper** | `local` | `pip install openai-whisper` + `ffmpeg` | Fully private, runs on-device |
| **Groq Whisper** | `groq` | `GROQ_API_KEY` | Very fast, free tier available |

Configure via `.env` or the **Settings → Voice Transcription** panel in the dashboard.

### Local Whisper Details

- **GPU Detection** — Automatically detects and uses CUDA (NVIDIA) or MPS (Apple Silicon), falls back to CPU
- **FP16 Handling** — Uses FP16 on CUDA for speed, FP32 on CPU/MPS to avoid warnings
- **Model Caching** — The loaded model is kept in memory across transcriptions
- **Model Pre-Download** — Download the selected model from Settings before first use (avoids delay on first voice message)
- **Model Sizes** — `tiny`, `base`, `small`, `medium`, `large` (configurable via `WHISPER_MODEL_SIZE`)

### Environment Variables

```env
STT_PROVIDER=local          # openai | local | groq
WHISPER_MODEL_SIZE=base     # tiny | base | small | medium | large
OPENAI_API_KEY=sk-...       # Required for STT_PROVIDER=openai
GROQ_API_KEY=gsk_...        # Required for STT_PROVIDER=groq
```

---

##  MCP Server

Other AI systems can connect to Open Brain as an MCP server with **18 tools**:

### Memory Tools
- `save_memory` — Store a fact/note (auto-categorized, embedded, PII-scrubbed)
- `search_brain` — Semantic similarity search
- `ask_brain` — Q&A with smart search (memories + Calendar + Gmail, with query expansion)
- `list_memories` — Browse recent memories
- `edit_memory` — Update content (auto re-embeds)
- `remove_memory` — Delete a memory

### Document Tools
- `ingest_document` — Parse and store a document (base64-encoded)

### URL Tools
- `ingest_url` — Fetch content from a URL (web page, X post, YouTube video, etc.) and store as a memory

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

- **Dashboard** — Browse memories with click-to-expand full content, edit/delete, semantic search, upload documents. Click the Database indicator to see live metrics (total memories, DB size, storage breakdown, source/category stats, timeline)
- **Ingest** — Two tabs: **Files** (upload documents + manual import from Proton, iCloud, Tuta, WhatsApp) and **Cloud Storage** (Google, Microsoft 365, Dropbox, pCloud, MEGA). Already-synced items can be force re-added with a confirmation prompt
- **Chat** — Conversational interface with streaming answers, live thinking process, and search mode toggle (Memory Only / Advanced Search)
- **Settings** — Configure model roles, API keys, database, Telegram token, voice transcription (STT provider, local Whisper model download, GPU detection), backup & restore
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
│   ├── api.py              # FastAPI app setup, CORS, and router registration
│   ├── event_log.py        # Shared in-memory event log (used by api + routes)
│   ├── routes/             # API route modules (one per domain)
│   │   ├── health.py       #   Health check & database stats
│   │   ├── memories.py     #   Memory CRUD & document ingestion
│   │   ├── chat.py         #   Chat (sync + streaming SSE) with intent detection
│   │   ├── config.py       #   Configuration, logs, backend restart
│   │   ├── stt.py          #   Speech-to-text utilities
│   │   ├── backup.py       #   Encrypted backup & restore
│   │   ├── google.py       #   Google Drive, Gmail, Calendar, Photos endpoints
│   │   ├── microsoft.py    #   Microsoft 365 (OneDrive, Outlook, Calendar)
│   │   ├── dropbox.py      #   Dropbox file search & ingestion
│   │   ├── pcloud.py       #   pCloud file browsing & ingestion
│   │   ├── email_import.py #   MBOX/EML email import (shared by Proton/iCloud/Tuta)
│   │   ├── mega.py         #   MEGA file browsing & ingestion
│   │   └── whatsapp.py     #   WhatsApp chat import
│   ├── google_svc/         # Google integration service layer
│   │   ├── auth.py         #   OAuth 2.0, multi-account management
│   │   ├── drive.py        #   Drive search & ingestion
│   │   ├── gmail.py        #   Gmail labels, search, preview, ingestion
│   │   ├── calendar.py     #   Calendar scanning, dedup, ingestion
│   │   └── photos.py       #   Photos Picker API, download, ingestion
│   ├── cloud_svc/          # Cloud storage integration service layer
│   │   ├── common.py       #   Shared credential & account helpers
│   │   ├── microsoft_svc.py#   Microsoft Graph: OneDrive, Outlook, Calendar
│   │   ├── dropbox_svc.py  #   Dropbox OAuth, search, download, ingestion
│   │   ├── pcloud_svc.py   #   pCloud OAuth, list, download, ingestion
│   │   └── mega_svc.py     #   MEGA email/password auth, list, download, ingestion
│   ├── db.py               # PostgreSQL/pgvector database layer
│   ├── llm.py              # Multi-model LLM client (roles, embeddings, vision)
│   ├── ingest.py           # Document ingestion (PDF, images, Word, Excel)
│   ├── backup.py           # Encrypted backup & restore logic (AES-256-GCM)
│   ├── smart_search.py     # Augmented search (Calendar + Gmail + query expansion)
│   ├── url_extract.py      # URL content extraction (X/Twitter, YouTube, web)
│   ├── transcribe.py       # Speech-to-text (OpenAI Whisper, local Whisper, Groq)
│   ├── scrubber.py         # PII detection and redaction → vault
│   ├── whatsapp_import.py  # WhatsApp chat export parser & ingester
│   ├── server.py           # MCP server (stdio + SSE, 18 tools)
│   └── telegram_bot.py     # Telegram bot with auto question detection
├── tests/                  # Test suite (pytest)
│   ├── test_module_structure.py  # Package/module export verification
│   ├── test_api_routes.py        # All API routes registered
│   ├── test_file_sizes.py        # No file exceeds 400 lines
│   └── test_google_svc_logic.py  # Helper function unit tests
├── ui/
│   └── src/
│       ├── App.tsx                 # React app shell (tab navigation)
│       └── components/
│           ├── IngestTab.tsx           # Ingest view (Files + Cloud Storage tabs)
│           ├── GoogleIntegration.tsx    # Google Drive, Gmail, Calendar, Photos
│           ├── MicrosoftIntegration.tsx # Microsoft 365 (OneDrive, Outlook, Calendar)
│           ├── DropboxIntegration.tsx   # Dropbox file search & ingestion
│           ├── PCloudIntegration.tsx    # pCloud file browsing & ingestion
│           ├── MegaIntegration.tsx      # MEGA file browsing & ingestion
│           ├── ProtonImport.tsx         # Proton Mail/Drive manual import
│           ├── ICloudImport.tsx         # iCloud Mail/Drive manual import
│           ├── TutaImport.tsx           # Tuta Mail manual import
│           ├── WhatsAppImport.tsx       # WhatsApp chat import
│           ├── DashboardTab.tsx         # Memory browser, search, metrics
│           ├── ChatTab.tsx              # Chat interface with streaming
│           ├── SettingsTab.tsx          # Model config, API keys, STT, backup
│           └── LogsTab.tsx              # Real-time system event log
├── init-scripts/
│   └── schema.sql          # PostgreSQL schema (memories + vault tables)
├── docker-compose.yml      # PostgreSQL + pgvector container
├── requirements.txt        # Python dependency manifest
├── .env.example            # Template for configuration
├── install.sh              # Interactive installer (macOS / Linux)
├── install.ps1             # Interactive installer (Windows PowerShell)
├── start-openbrain.sh      # Start all services (macOS/Linux)
├── stop-openbrain.sh       # Stop all services (macOS/Linux)
├── start-openbrain.bat     # Start all services (Windows)
└── stop-openbrain.bat      # Stop all services (Windows)
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

# Run test suite
python -m pytest tests/ -v
```

### Architecture Notes

The backend follows a modular architecture:

- **`api.py`** is a thin entrypoint — app setup, CORS, and `include_router()` calls
- **`routes/`** package contains 13 domain-specific route modules, each with its own `APIRouter`
- **`google_svc/`** package splits Google integrations into 5 focused modules (auth, drive, gmail, calendar, photos)
- **`cloud_svc/`** package handles non-Google cloud integrations (Microsoft Graph, Dropbox, pCloud, MEGA) with shared credential/account helpers
- **`event_log.py`** is a shared module for the in-memory event log, avoiding circular imports between `api.py` and route modules
- No source file exceeds 400 lines (enforced by tests)

---

## 📄 License

MIT — use it, fork it, make it yours.

---

## 🙏 Credits

- Inspired by ideas from [Nate Jones](https://gemini.google.com/share/b07f16ab6580)
- Built with [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), [pgvector](https://github.com/pgvector/pgvector), [OpenRouter](https://openrouter.ai/), and [MCP](https://modelcontextprotocol.io/)
