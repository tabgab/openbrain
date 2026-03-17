# ─────────────────────────────────────────────────────────────────────────────
# Open Brain — Interactive Installer for Windows (PowerShell)
# Run: Right-click → "Run with PowerShell"  or  powershell -ExecutionPolicy Bypass -File install.ps1
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# ── Colors & helpers ─────────────────────────────────────────────────────────

function Write-Banner {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║                                              ║" -ForegroundColor Cyan
    Write-Host "  ║         O P E N   B R A I N                  ║" -ForegroundColor Cyan
    Write-Host "  ║                                              ║" -ForegroundColor Cyan
    Write-Host "  ║       Your Personal AI Memory System         ║" -ForegroundColor Cyan
    Write-Host "  ║                                              ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Info    { param($msg) Write-Host "  i  $msg" -ForegroundColor Blue }
function Write-Ok      { param($msg) Write-Host "  +  $msg" -ForegroundColor Green }
function Write-Warn    { param($msg) Write-Host "  !  $msg" -ForegroundColor Yellow }
function Write-Fail    { param($msg) Write-Host "  x  $msg" -ForegroundColor Red }
function Write-Step    { param($msg) Write-Host "`n-- $msg" -ForegroundColor White }

function Prompt-Default {
    param([string]$Question, [string]$Default)
    $answer = Read-Host "  ?  $Question [$Default]"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
    return $answer
}

function Prompt-Secret {
    param([string]$Question)
    $secure = Read-Host "  ?  $Question" -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $plain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    return $plain
}

function Prompt-Confirm {
    param([string]$Question)
    $answer = Read-Host "  ?  $Question [Y/n]"
    return ([string]::IsNullOrWhiteSpace($answer) -or $answer -match "^[Yy]")
}

# ── Prerequisite checks ─────────────────────────────────────────────────────

function Test-Python {
    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)") {
                $major = [int]$Matches[1]; $minor = [int]$Matches[2]
                if ($major -ge 3 -and $minor -ge 10) {
                    $script:PythonCmd = $cmd
                    Write-Ok "Python found: $ver"
                    return $true
                }
            }
        } catch {}
    }
    return $false
}

function Test-Node {
    try {
        $nv = & node --version 2>&1
        $npmv = & npm --version 2>&1
        Write-Ok "Node.js found: $nv, npm $npmv"
        return $true
    } catch { return $false }
}

function Test-Docker {
    try {
        $null = & docker info 2>&1
        $dv = & docker --version 2>&1
        Write-Ok "Docker found and running: $dv"
        return $true
    } catch { return $false }
}

function Test-DockerCompose {
    try {
        $null = & docker compose version 2>&1
        $script:ComposeCmd = "docker compose"
        Write-Ok "Docker Compose found"
        return $true
    } catch {}
    try {
        $null = & docker-compose --version 2>&1
        $script:ComposeCmd = "docker-compose"
        Write-Ok "Docker Compose found"
        return $true
    } catch { return $false }
}

function Install-Prereqs-Windows {
    # Check for winget
    $hasWinget = $false
    try { $null = & winget --version 2>&1; $hasWinget = $true } catch {}

    if (-not $hasWinget) {
        Write-Warn "winget (Windows Package Manager) not found."
        Write-Warn "Please install prerequisites manually:"
        Write-Host "  - Python 3.10+:  https://www.python.org/downloads/" -ForegroundColor Yellow
        Write-Host "  - Node.js:       https://nodejs.org/" -ForegroundColor Yellow
        Write-Host "  - Docker Desktop: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
        Write-Host ""
        Write-Fail "Install the missing tools and re-run this installer."
        exit 1
    }

    if (-not $script:PythonCmd) {
        Write-Info "Installing Python via winget..."
        & winget install Python.Python.3.13 --accept-package-agreements --accept-source-agreements
        $script:PythonCmd = "python"
    }
    try { $null = & node --version 2>&1 } catch {
        Write-Info "Installing Node.js via winget..."
        & winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    }
    try { $null = & docker --version 2>&1 } catch {
        Write-Host ""
        Write-Warn "Docker Desktop is required for the database."
        Write-Host "  Please install it from: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
        Write-Host "  After installing, start Docker Desktop and re-run this installer."
        exit 1
    }
}

# ── Main ─────────────────────────────────────────────────────────────────────

Write-Banner

Write-Host "  This installer will set up Open Brain on your Windows machine:"
Write-Host "    1. Check & install prerequisites (Python, Node.js, Docker)"
Write-Host "    2. Create Python virtual environment & install packages"
Write-Host "    3. Install frontend (UI) dependencies"
Write-Host "    4. Start the PostgreSQL database (Docker)"
Write-Host "    5. Configure your API keys and settings"
Write-Host "    6. Verify everything works"
Write-Host ""

if (-not (Prompt-Confirm "Ready to begin?")) {
    Write-Host "  Cancelled. Run this script again when you're ready."
    exit 0
}

# ── Step 1: Prerequisites ────────────────────────────────────────────────────

Write-Step "Step 1/6 - Checking prerequisites"

$missing = @()
if (-not (Test-Python)) { $missing += "Python 3.10+" }
if (-not (Test-Node))   { $missing += "Node.js + npm" }
if (-not (Test-Docker)) { $missing += "Docker" }

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Warn "Missing: $($missing -join ', ')"
    if (Prompt-Confirm "Attempt to install missing prerequisites automatically?") {
        Install-Prereqs-Windows
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        if (-not (Test-Python)) { Write-Fail "Python still not available."; exit 1 }
        if (-not (Test-Node))   { Write-Fail "Node.js still not available. Restart your terminal and re-run."; exit 1 }
        if (-not (Test-Docker)) { Write-Fail "Docker still not available."; exit 1 }
    } else {
        Write-Fail "Please install the missing prerequisites and re-run this installer."
        exit 1
    }
}

if (-not (Test-DockerCompose)) {
    Write-Fail "Docker Compose is required but not found. It should be included with Docker Desktop."
    exit 1
}

# ── Step 2: Python venv & packages ───────────────────────────────────────────

Write-Step "Step 2/6 - Setting up Python environment"

if (Test-Path "venv") {
    Write-Ok "Virtual environment already exists"
} else {
    Write-Info "Creating Python virtual environment..."
    & $PythonCmd -m venv venv
    Write-Ok "Virtual environment created"
}

Write-Info "Activating virtual environment..."
& ".\venv\Scripts\Activate.ps1"

Write-Info "Installing Python dependencies (this may take a minute)..."
& pip install --upgrade pip -q 2>$null
& pip install -r requirements.txt -q 2>$null
Write-Ok "All Python packages installed"

# ── Step 3: Frontend dependencies ────────────────────────────────────────────

Write-Step "Step 3/6 - Setting up frontend (UI)"

if (Test-Path "ui\node_modules") {
    Write-Ok "UI dependencies already installed"
} else {
    Write-Info "Installing frontend dependencies..."
    Push-Location ui
    & npm install --silent 2>$null
    Pop-Location
    Write-Ok "Frontend dependencies installed"
}

# ── Step 4: Database ─────────────────────────────────────────────────────────

Write-Step "Step 4/6 - Starting PostgreSQL database"

$dbRunning = $false
$containers = & docker ps --format "{{.Names}}" 2>$null
if ($containers -match "openbrain-db") {
    Write-Ok "Database container 'openbrain-db' is already running"
    $dbRunning = $true
}

if (-not $dbRunning) {
    Write-Info "Starting PostgreSQL with pgvector via Docker..."
    if ($ComposeCmd -eq "docker compose") {
        & docker compose up -d
    } else {
        & docker-compose up -d
    }
    Write-Info "Waiting for database to be ready..."
    for ($i = 1; $i -le 30; $i++) {
        try {
            $null = & docker exec openbrain-db pg_isready -U openbrain 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Ok "Database is ready"
                $dbRunning = $true
                break
            }
        } catch {}
        Start-Sleep -Seconds 1
    }
    if (-not $dbRunning) {
        Write-Fail "Database did not start in time. Check: docker logs openbrain-db"
        exit 1
    }
}

# ── Step 5: Configuration (.env) ────────────────────────────────────────────

Write-Step "Step 5/6 - Configuration"

$configure = $true
if (Test-Path ".env") {
    Write-Warn "An .env file already exists."
    if (-not (Prompt-Confirm "Overwrite it with fresh configuration?")) {
        $configure = $false
        Write-Ok "Keeping existing .env configuration"
    }
}

if ($configure) {
    Write-Host ""
    Write-Host "  Let's configure Open Brain. Press Enter to accept defaults." -ForegroundColor White
    Write-Host ""

    # LLM
    Write-Host "  -- LLM / AI Provider --" -ForegroundColor White
    Write-Host "  Open Brain uses OpenRouter by default (access to 200+ models with one key)."
    Write-Host "  Get your free API key at: https://openrouter.ai/keys" -ForegroundColor Cyan
    Write-Host ""
    $llmKey  = Prompt-Secret "LLM API Key (OpenRouter)"
    $llmBase = Prompt-Default "LLM Base URL" "https://openrouter.ai/api/v1"
    Write-Host ""

    # Models
    Write-Host "  -- Model Selection -- (press Enter for recommended defaults)" -ForegroundColor White
    $mText   = Prompt-Default "Text model (fast/cheap)" "moonshotai/kimi-k2.5"
    $mReason = Prompt-Default "Reasoning model (complex Q&A)" "anthropic/claude-sonnet-4.6"
    $mCode   = Prompt-Default "Coding model" "minimax/minimax-m2.5"
    $mVision = Prompt-Default "Vision model (images/OCR)" "moonshotai/kimi-k2.5"
    $mEmbed  = Prompt-Default "Embedding model" "openai/text-embedding-3-small"
    Write-Host ""

    # Telegram
    Write-Host "  -- Telegram Bot (optional) --" -ForegroundColor White
    Write-Host "  Create a bot via https://t.me/BotFather and paste the token."
    Write-Host "  Leave blank to skip Telegram integration."
    Write-Host ""
    $tgToken = Prompt-Secret "Telegram Bot Token"
    Write-Host ""

    # Database
    Write-Host "  -- Database --" -ForegroundColor White
    $dbUser = Prompt-Default "PostgreSQL user" "openbrain"
    $dbPass = Prompt-Default "PostgreSQL password" "openbrain_secret_pass"
    $dbName = Prompt-Default "Database name" "openbrain_db"
    $dbHost = Prompt-Default "Database host" "localhost"
    $dbPort = Prompt-Default "Database port" "5432"
    Write-Host ""

    # STT
    Write-Host "  -- Speech-to-Text (optional) --" -ForegroundColor White
    Write-Host "  Options: openai (best quality), groq (free tier), local (offline Whisper)"
    Write-Host ""
    $sttProv = Prompt-Default "STT provider" "openai"
    $openaiKey = ""; $groqKey = ""
    if ($sttProv -eq "openai") { $openaiKey = Prompt-Secret "OpenAI API Key (for Whisper STT)" }
    elseif ($sttProv -eq "groq") { $groqKey = Prompt-Secret "Groq API Key" }
    Write-Host ""

    # Write .env
    Write-Info "Writing configuration to .env..."
    $envContent = @"
# Open Brain Configuration - generated by installer
# $(Get-Date)

# --- LLM ---
LLM_API_KEY=$llmKey
LLM_BASE_URL=$llmBase

# --- Model Roles ---
MODEL_TEXT=$mText
MODEL_REASONING=$mReason
MODEL_CODING=$mCode
MODEL_VISION=$mVision
MODEL_EMBEDDING=$mEmbed

# --- Telegram Bot ---
TELEGRAM_BOT_TOKEN=$tgToken

# --- PostgreSQL ---
POSTGRES_USER=$dbUser
POSTGRES_PASSWORD=$dbPass
POSTGRES_DB=$dbName
POSTGRES_HOST=$dbHost
POSTGRES_PORT=$dbPort

# --- Speech-to-Text ---
STT_PROVIDER=$sttProv
OPENAI_API_KEY=$openaiKey
GROQ_API_KEY=$groqKey
"@
    Set-Content -Path ".env" -Value $envContent -Encoding UTF8
    Write-Ok "Configuration saved to .env"
}

# ── Step 6: Verify ───────────────────────────────────────────────────────────

Write-Step "Step 6/6 - Verifying installation"

Write-Info "Checking Python imports..."
& ".\venv\Scripts\Activate.ps1"
$importCheck = & python -c "
import sys; sys.path.insert(0, 'src')
from fastapi import FastAPI
from dotenv import load_dotenv
import psycopg2, openai
print('ok')
" 2>$null
if ($importCheck -match "ok") {
    Write-Ok "Python dependencies OK"
} else {
    Write-Warn "Some Python imports failed - try: .\venv\Scripts\Activate.ps1; pip install -r requirements.txt"
}

Write-Info "Checking database connection..."
$dbCheck = & python -c "
import sys, os; sys.path.insert(0, 'src')
from dotenv import load_dotenv; load_dotenv()
import psycopg2
conn = psycopg2.connect(
    dbname=os.getenv('POSTGRES_DB','openbrain_db'),
    user=os.getenv('POSTGRES_USER','openbrain'),
    password=os.getenv('POSTGRES_PASSWORD','openbrain_secret_pass'),
    host=os.getenv('POSTGRES_HOST','localhost'),
    port=os.getenv('POSTGRES_PORT','5432'),
)
conn.close()
print('ok')
" 2>$null
if ($dbCheck -match "ok") {
    Write-Ok "Database connection OK"
} else {
    Write-Warn "Could not connect to database - make sure Docker is running and .env credentials match"
}

if (Test-Path "ui\node_modules") {
    Write-Ok "Frontend dependencies OK"
} else {
    Write-Warn "Frontend node_modules missing - run: cd ui; npm install"
}

# ── Done! ────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║                                              ║" -ForegroundColor Green
Write-Host "  ║    +  Open Brain installation complete! +    ║" -ForegroundColor Green
Write-Host "  ║                                              ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  To start Open Brain:" -ForegroundColor White
Write-Host "    .\start-openbrain.bat" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Then open the dashboard at:" -ForegroundColor White
Write-Host "    http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "  To stop all services:" -ForegroundColor White
Write-Host "    .\stop-openbrain.bat" -ForegroundColor Cyan
Write-Host ""
Write-Host "  To reconfigure:" -ForegroundColor White
Write-Host "    Edit .env or run .\install.ps1 again" -ForegroundColor Cyan
Write-Host ""

Read-Host "Press Enter to exit"
