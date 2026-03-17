#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Open Brain — Interactive Installer for macOS & Linux
# ─────────────────────────────────────────────────────────────────────────────

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# ── Colors & helpers ─────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

banner() {
    echo ""
    echo -e "${CYAN}${BOLD}"
    echo "  ╔══════════════════════════════════════════════╗"
    echo "  ║                                              ║"
    echo "  ║        🧠  O P E N   B R A I N  🧠          ║"
    echo "  ║                                              ║"
    echo "  ║       Your Personal AI Memory System         ║"
    echo "  ║                                              ║"
    echo "  ╚══════════════════════════════════════════════╝"
    echo -e "${NC}"
}

info()    { echo -e "  ${BLUE}ℹ${NC}  $1"; }
success() { echo -e "  ${GREEN}✓${NC}  $1"; }
warn()    { echo -e "  ${YELLOW}⚠${NC}  $1"; }
fail()    { echo -e "  ${RED}✗${NC}  $1"; }
step()    { echo -e "\n${BOLD}── $1${NC}"; }
ask()     { echo -en "  ${CYAN}?${NC}  $1"; }

# Prompt with default value: prompt_default "Question" "default"
prompt_default() {
    local answer
    ask "$1 ${YELLOW}[$2]${NC}: "
    read -r answer
    echo "${answer:-$2}"
}

# Prompt for secret (no echo): prompt_secret "Question" "default"
prompt_secret() {
    local answer
    ask "$1: "
    read -rs answer
    echo ""
    echo "${answer:-$2}"
}

# Yes/no prompt: confirm "Question?" (default Y)
confirm() {
    local answer
    ask "$1 ${YELLOW}[Y/n]${NC}: "
    read -r answer
    [[ -z "$answer" || "$answer" =~ ^[Yy] ]]
}

# ── OS Detection ─────────────────────────────────────────────────────────────

detect_os() {
    case "$(uname -s)" in
        Darwin*) OS="macos" ;;
        Linux*)  OS="linux" ;;
        *)       OS="unknown" ;;
    esac
}

# ── Prerequisite checks ─────────────────────────────────────────────────────

check_python() {
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            local ver
            ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
            local major minor
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if (( major >= 3 && minor >= 10 )); then
                PYTHON_CMD="$cmd"
                success "Python found: $($cmd --version)"
                return 0
            fi
        fi
    done
    return 1
}

check_node() {
    if command -v node &>/dev/null && command -v npm &>/dev/null; then
        success "Node.js found: $(node --version), npm $(npm --version)"
        return 0
    fi
    return 1
}

check_docker() {
    if command -v docker &>/dev/null; then
        if docker info &>/dev/null; then
            success "Docker found and running: $(docker --version | head -1)"
            return 0
        else
            warn "Docker is installed but not running"
            return 1
        fi
    fi
    return 1
}

check_docker_compose() {
    if docker compose version &>/dev/null 2>&1; then
        success "Docker Compose found: $(docker compose version --short 2>/dev/null || echo 'v2+')"
        COMPOSE_CMD="docker compose"
        return 0
    elif command -v docker-compose &>/dev/null; then
        success "Docker Compose found: $(docker-compose --version | head -1)"
        COMPOSE_CMD="docker-compose"
        return 0
    fi
    return 1
}

install_prereqs() {
    if [[ "$OS" == "macos" ]]; then
        if ! command -v brew &>/dev/null; then
            warn "Homebrew not found. It's the easiest way to install dependencies on macOS."
            if confirm "Install Homebrew?"; then
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            else
                fail "Please install the missing prerequisites manually and re-run this installer."
                exit 1
            fi
        fi
        if [[ -z "${PYTHON_CMD:-}" ]]; then
            info "Installing Python 3..."
            brew install python@3.13
            PYTHON_CMD="python3"
        fi
        if ! command -v node &>/dev/null; then
            info "Installing Node.js..."
            brew install node
        fi
        if ! command -v docker &>/dev/null; then
            info "Docker Desktop is required for the database."
            echo ""
            echo -e "  ${YELLOW}Please install Docker Desktop from:${NC}"
            echo -e "  ${BOLD}https://www.docker.com/products/docker-desktop/${NC}"
            echo ""
            echo "  After installing, start Docker Desktop and re-run this installer."
            exit 1
        fi
    elif [[ "$OS" == "linux" ]]; then
        local pkg_mgr=""
        if command -v apt-get &>/dev/null; then pkg_mgr="apt";
        elif command -v dnf &>/dev/null; then pkg_mgr="dnf";
        elif command -v pacman &>/dev/null; then pkg_mgr="pacman";
        fi

        if [[ -z "${PYTHON_CMD:-}" ]]; then
            info "Installing Python 3..."
            case "$pkg_mgr" in
                apt) sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip ;;
                dnf) sudo dnf install -y python3 python3-pip ;;
                pacman) sudo pacman -S --noconfirm python python-pip ;;
                *) fail "Could not detect package manager. Please install Python 3.10+ manually."; exit 1 ;;
            esac
            PYTHON_CMD="python3"
        fi
        if ! command -v node &>/dev/null; then
            info "Installing Node.js..."
            case "$pkg_mgr" in
                apt) sudo apt-get install -y nodejs npm ;;
                dnf) sudo dnf install -y nodejs npm ;;
                pacman) sudo pacman -S --noconfirm nodejs npm ;;
                *) fail "Please install Node.js manually."; exit 1 ;;
            esac
        fi
        if ! command -v docker &>/dev/null; then
            info "Installing Docker..."
            if [[ "$pkg_mgr" == "apt" ]]; then
                curl -fsSL https://get.docker.com | sudo sh
                sudo usermod -aG docker "$USER"
                warn "You may need to log out and back in for Docker permissions to take effect."
            else
                fail "Please install Docker manually: https://docs.docker.com/engine/install/"
                exit 1
            fi
        fi
    fi
}

# ── Main installer ───────────────────────────────────────────────────────────

banner
detect_os

if [[ "$OS" == "unknown" ]]; then
    fail "Unsupported operating system. Please use macOS or Linux (or install.ps1 for Windows)."
    exit 1
fi

info "Detected OS: ${BOLD}$OS${NC}"
echo ""
echo -e "  This installer will set up Open Brain on your machine:"
echo -e "    ${BOLD}1.${NC} Check & install prerequisites (Python, Node.js, Docker)"
echo -e "    ${BOLD}2.${NC} Create Python virtual environment & install packages"
echo -e "    ${BOLD}3.${NC} Install frontend (UI) dependencies"
echo -e "    ${BOLD}4.${NC} Start the PostgreSQL database (Docker)"
echo -e "    ${BOLD}5.${NC} Configure your API keys and settings"
echo -e "    ${BOLD}6.${NC} Verify everything works"
echo ""

if ! confirm "Ready to begin?"; then
    echo "  Cancelled. Run this script again when you're ready."
    exit 0
fi

# ── Step 1: Prerequisites ────────────────────────────────────────────────────

step "Step 1/6 — Checking prerequisites"

MISSING=()
if ! check_python; then MISSING+=("Python 3.10+"); fi
if ! check_node; then MISSING+=("Node.js + npm"); fi
if ! check_docker; then MISSING+=("Docker"); fi

if (( ${#MISSING[@]} > 0 )); then
    echo ""
    warn "Missing: ${MISSING[*]}"
    if confirm "Attempt to install missing prerequisites automatically?"; then
        install_prereqs
        # Re-check
        check_python || { fail "Python still not available."; exit 1; }
        check_node || { fail "Node.js still not available."; exit 1; }
        check_docker || { fail "Docker still not available."; exit 1; }
    else
        fail "Please install the missing prerequisites and re-run this installer."
        exit 1
    fi
fi

check_docker_compose || {
    fail "Docker Compose is required but not found."
    fail "It should be included with Docker Desktop (macOS) or can be installed separately on Linux."
    exit 1
}

# ── Step 2: Python virtual environment & packages ────────────────────────────

step "Step 2/6 — Setting up Python environment"

if [[ -d "venv" ]]; then
    success "Virtual environment already exists"
else
    info "Creating Python virtual environment..."
    $PYTHON_CMD -m venv venv
    success "Virtual environment created"
fi

info "Activating virtual environment..."
source venv/bin/activate

info "Installing Python dependencies (this may take a minute)..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
success "All Python packages installed"

# ── Step 3: Frontend dependencies ────────────────────────────────────────────

step "Step 3/6 — Setting up frontend (UI)"

if [[ -d "ui/node_modules" ]]; then
    success "UI dependencies already installed"
else
    info "Installing frontend dependencies..."
    (cd ui && npm install --silent 2>/dev/null)
    success "Frontend dependencies installed"
fi

# ── Step 4: Database ─────────────────────────────────────────────────────────

step "Step 4/6 — Starting PostgreSQL database"

DB_RUNNING=false
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "openbrain-db"; then
    success "Database container 'openbrain-db' is already running"
    DB_RUNNING=true
fi

if [[ "$DB_RUNNING" == false ]]; then
    info "Starting PostgreSQL with pgvector via Docker..."
    $COMPOSE_CMD up -d
    info "Waiting for database to be ready..."
    for i in $(seq 1 30); do
        if docker exec openbrain-db pg_isready -U openbrain &>/dev/null; then
            success "Database is ready"
            DB_RUNNING=true
            break
        fi
        sleep 1
    done
    if [[ "$DB_RUNNING" == false ]]; then
        fail "Database did not start in time. Check: docker logs openbrain-db"
        exit 1
    fi
fi

# ── Step 5: Configuration (.env) ────────────────────────────────────────────

step "Step 5/6 — Configuration"

if [[ -f ".env" ]]; then
    warn "An .env file already exists."
    if confirm "Overwrite it with fresh configuration?"; then
        CONFIGURE=true
    else
        CONFIGURE=false
        success "Keeping existing .env configuration"
    fi
else
    CONFIGURE=true
fi

if [[ "$CONFIGURE" == true ]]; then
    echo ""
    echo -e "  ${BOLD}Let's configure Open Brain. Press Enter to accept defaults.${NC}"
    echo ""

    # ── LLM (required)
    echo -e "  ${BOLD}── LLM / AI Provider ──${NC}"
    echo -e "  Open Brain uses ${BOLD}OpenRouter${NC} by default (access to 200+ models with one key)."
    echo -e "  Get your free API key at: ${CYAN}https://openrouter.ai/keys${NC}"
    echo ""
    LLM_KEY=$(prompt_secret "  LLM API Key (OpenRouter)" "")
    LLM_BASE=$(prompt_default "LLM Base URL" "https://openrouter.ai/api/v1")
    echo ""

    # ── Models
    echo -e "  ${BOLD}── Model Selection ──${NC} (press Enter for recommended defaults)"
    M_TEXT=$(prompt_default "Text model (fast/cheap)" "moonshotai/kimi-k2.5")
    M_REASON=$(prompt_default "Reasoning model (complex Q&A)" "anthropic/claude-sonnet-4.6")
    M_CODE=$(prompt_default "Coding model" "minimax/minimax-m2.5")
    M_VISION=$(prompt_default "Vision model (images/OCR)" "moonshotai/kimi-k2.5")
    M_EMBED=$(prompt_default "Embedding model" "openai/text-embedding-3-small")
    echo ""

    # ── Telegram (optional)
    echo -e "  ${BOLD}── Telegram Bot (optional) ──${NC}"
    echo -e "  Create a bot via ${CYAN}https://t.me/BotFather${NC} and paste the token."
    echo -e "  Leave blank to skip Telegram integration."
    echo ""
    TG_TOKEN=$(prompt_secret "  Telegram Bot Token" "")
    echo ""

    # ── Database
    echo -e "  ${BOLD}── Database ──${NC}"
    DB_USER=$(prompt_default "PostgreSQL user" "openbrain")
    DB_PASS=$(prompt_default "PostgreSQL password" "openbrain_secret_pass")
    DB_NAME=$(prompt_default "Database name" "openbrain_db")
    DB_HOST=$(prompt_default "Database host" "localhost")
    DB_PORT=$(prompt_default "Database port" "5432")
    echo ""

    # ── Speech-to-text (optional)
    echo -e "  ${BOLD}── Speech-to-Text (optional) ──${NC}"
    echo -e "  Options: ${BOLD}openai${NC} (best quality, needs OpenAI key),"
    echo -e "           ${BOLD}groq${NC} (free tier), ${BOLD}local${NC} (offline Whisper)"
    echo ""
    STT_PROV=$(prompt_default "STT provider" "openai")
    OPENAI_KEY=""
    GROQ_KEY=""
    if [[ "$STT_PROV" == "openai" ]]; then
        OPENAI_KEY=$(prompt_secret "  OpenAI API Key (for Whisper STT)" "")
    elif [[ "$STT_PROV" == "groq" ]]; then
        GROQ_KEY=$(prompt_secret "  Groq API Key" "")
    fi
    echo ""

    # ── Write .env
    info "Writing configuration to .env..."
    cat > .env <<ENVEOF
# Open Brain Configuration — generated by installer
# $(date)

# --- LLM ---
LLM_API_KEY=$LLM_KEY
LLM_BASE_URL=$LLM_BASE

# --- Model Roles ---
MODEL_TEXT=$M_TEXT
MODEL_REASONING=$M_REASON
MODEL_CODING=$M_CODE
MODEL_VISION=$M_VISION
MODEL_EMBEDDING=$M_EMBED

# --- Telegram Bot ---
TELEGRAM_BOT_TOKEN=$TG_TOKEN

# --- PostgreSQL ---
POSTGRES_USER=$DB_USER
POSTGRES_PASSWORD=$DB_PASS
POSTGRES_DB=$DB_NAME
POSTGRES_HOST=$DB_HOST
POSTGRES_PORT=$DB_PORT

# --- Speech-to-Text ---
STT_PROVIDER=$STT_PROV
OPENAI_API_KEY=$OPENAI_KEY
GROQ_API_KEY=$GROQ_KEY
ENVEOF
    success "Configuration saved to .env"
fi

# ── Step 6: Verify ───────────────────────────────────────────────────────────

step "Step 6/6 — Verifying installation"

# Check Python imports
info "Checking Python imports..."
if source venv/bin/activate && python -c "
import sys; sys.path.insert(0, 'src')
from fastapi import FastAPI
from dotenv import load_dotenv
import psycopg2
import openai
print('ok')
" 2>/dev/null | grep -q "ok"; then
    success "Python dependencies OK"
else
    warn "Some Python imports failed — try: source venv/bin/activate && pip install -r requirements.txt"
fi

# Check DB connection
info "Checking database connection..."
if source venv/bin/activate && python -c "
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
" 2>/dev/null | grep -q "ok"; then
    success "Database connection OK"
else
    warn "Could not connect to database — make sure Docker is running and .env credentials match"
fi

# Check UI
if [[ -d "ui/node_modules" ]]; then
    success "Frontend dependencies OK"
else
    warn "Frontend node_modules missing — run: cd ui && npm install"
fi

# ── Done! ────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║                                              ║"
echo "  ║    ✓  Open Brain installation complete! ✓    ║"
echo "  ║                                              ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${BOLD}To start Open Brain:${NC}"
echo -e "    ${CYAN}./start-openbrain.sh${NC}"
echo ""
echo -e "  ${BOLD}Then open the dashboard at:${NC}"
echo -e "    ${CYAN}http://localhost:5173${NC}"
echo ""
echo -e "  ${BOLD}To stop all services:${NC}"
echo -e "    ${CYAN}./stop-openbrain.sh${NC}"
echo ""
echo -e "  ${BOLD}To reconfigure:${NC}"
echo -e "    Edit ${CYAN}.env${NC} or run ${CYAN}./install.sh${NC} again"
echo ""
