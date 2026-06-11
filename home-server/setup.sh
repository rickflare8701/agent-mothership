#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 🏠 Agent Mothership - One-Command Home Server Setup
# ============================================================
# This script transforms any Linux machine (old laptop, RPi,
# desktop) into your 24/7 AI agent server.
#
# Usage:
#   curl -fsSL https://git.io/agent-mothership | bash
#   # OR
#   chmod +x setup.sh && ./setup.sh
# ============================================================

MOTHERSHIP_DIR="${HOME}/agent-mothership"
NODE_VERSION="20"
REPO_URL="https://github.com/ricksanchez8701/agent-mothership.git"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }

# ──────────────────────────────────────────────
# Check system requirements
# ──────────────────────────────────────────────
check_system() {
    echo ""
    info "🔍 Checking system requirements..."
    
    # OS check
    if [ ! -f /etc/os-release ]; then
        err "This script requires a Linux-based system."
        exit 1
    fi
    
    # Architecture
    ARCH=$(uname -m)
    info "Architecture: ${ARCH}"
    
    # Memory check (recommend at least 512MB)
    TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
    if [ "${TOTAL_MEM}" -lt 512 ]; then
        warn "Low memory (${TOTAL_MEM}MB). 512MB+ recommended for Node.js."
    else
        log "Memory: ${TOTAL_MEM}MB"
    fi
    
    # Disk space
    FREE_SPACE=$(df -h "${HOME}" | awk 'NR==2{print $4}')
    log "Free disk space: ${FREE_SPACE}"
    
    echo ""
}

# ──────────────────────────────────────────────
# Install system dependencies
# ──────────────────────────────────────────────
install_deps() {
    echo ""
    info "📦 Installing system dependencies..."
    
    # Detect package manager
    if command -v apt-get &>/dev/null; then
        PKG_MANAGER="apt-get"
        INSTALL_CMD="sudo apt-get install -y"
        UPDATE_CMD="sudo apt-get update -qq"
    elif command -v yum &>/dev/null; then
        PKG_MANAGER="yum"
        INSTALL_CMD="sudo yum install -y"
        UPDATE_CMD="sudo yum check-update"
    elif command -v pacman &>/dev/null; then
        PKG_MANAGER="pacman"
        INSTALL_CMD="sudo pacman -S --noconfirm"
        UPDATE_CMD="sudo pacman -Sy"
    elif command -v apk &>/dev/null; then
        PKG_MANAGER="apk"
        INSTALL_CMD="sudo apk add"
        UPDATE_CMD="sudo apk update"
    else
        err "Could not detect package manager. Install git, curl, tmux manually."
        exit 1
    fi
    
    log "Package manager: ${PKG_MANAGER}"
    
    # Update and install essentials
    ${UPDATE_CMD} 2>/dev/null || true
    ${INSTALL_CMD} git curl tmux build-essential 2>/dev/null || \
    ${INSTALL_CMD} git curl tmux 2>/dev/null || true
    
    log "System dependencies installed"
}

# ──────────────────────────────────────────────
# Install Node.js
# ──────────────────────────────────────────────
install_nodejs() {
    echo ""
    info "🟢 Installing Node.js ${NODE_VERSION}..."
    
    if command -v node &>/dev/null; then
        CURRENT_NODE=$(node --version)
        log "Node.js already installed: ${CURRENT_NODE}"
        return
    fi
    
    # Install via NodeSource
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_VERSION}.x" | sudo -E bash -
    sudo apt-get install -y nodejs
    
    log "Node.js $(node --version) installed"
}

# ──────────────────────────────────────────────
# Install Codebuff
# ──────────────────────────────────────────────
install_codebuff() {
    echo ""
    info "🤖 Installing Codebuff..."
    
    # Install free version of codebuff
    npm install -g freebuff 2>/dev/null || npm install -g codebuff 2>/dev/null || {
        warn "Could not install codebuff globally. Will use npx instead."
    }
    
    if command -v codebuff &>/dev/null; then
        log "Codebuff installed: $(codebuff --version 2>/dev/null || echo 'ok')"
    else
        log "Codebuff available via npx codebuff"
    fi
}

# ──────────────────────────────────────────────
# Setup project files
# ──────────────────────────────────────────────
setup_project() {
    echo ""
    info "📁 Setting up project in ${MOTHERSHIP_DIR}..."
    
    if [ -d "${MOTHERSHIP_DIR}" ]; then
        warn "Directory already exists. Updating..."
        cd "${MOTHERSHIP_DIR}"
        git pull origin main
    else
        git clone "${REPO_URL}" "${MOTHERSHIP_DIR}"
        cd "${MOTHERSHIP_DIR}"
    fi
    
    # Install npm dependencies for web terminal
    if [ -f "${MOTHERSHIP_DIR}/web-terminal/package.json" ]; then
        cd "${MOTHERSHIP_DIR}/web-terminal"
        npm install --production 2>/dev/null || true
        cd "${MOTHERSHIP_DIR}"
    fi
    
    log "Project files ready"
}

# ──────────────────────────────────────────────
# Setup tmux session
# ──────────────────────────────────────────────
setup_tmux() {
    echo ""
    info "💻 Setting up persistent tmux session..."
    
    # Create a tmux session for codebuff if not already running
    if tmux has-session -t mothership 2>/dev/null; then
        log "Tmux session 'mothership' already exists"
    else
        tmux new-session -d -s mothership -n codebuff
        tmux send-keys -t mothership:codebuff "cd ${MOTHERSHIP_DIR} && echo '🚀 Agent Mothership Ready'" Enter
        log "Tmux session 'mothership' created"
    fi
    
    # Create a startup script for tmux
    cat > "${MOTHERSHIP_DIR}/scripts/start-mothership.sh" << 'TMUXEOF'
#!/usr/bin/env bash
SESSION="mothership"

# Kill existing session if it exists
tmux kill-session -t $SESSION 2>/dev/null || true

# Create new session
tmux new-session -d -s $SESSION -n codebuff

# Send commands
tmux send-keys -t $SESSION:codebuff "cd ${MOTHERSHIP_DIR}" Enter
tmux send-keys -t $SESSION:codebuff "echo '🤖 Agent Mothership Ready — type codebuff to start'" Enter

# Attach if interactive
if [ -t 0 ]; then
    tmux attach-session -t $SESSION
fi
TMUXEOF
    chmod +x "${MOTHERSHIP_DIR}/scripts/start-mothership.sh"
    
    log "Tmux startup script created"
}

# ──────────────────────────────────────────────
# Setup Cloudflare Tunnel
# ──────────────────────────────────────────────
setup_cloudflare() {
    echo ""
    info "🌐 Setting up Cloudflare Tunnel..."
    
    # Install cloudflared
    if ! command -v cloudflared &>/dev/null; then
        info "Installing cloudflared..."
        
        # Detect architecture
        ARCH=$(uname -m)
        case "${ARCH}" in
            x86_64)  CLOUD_ARCH="amd64" ;;
            aarch64) CLOUD_ARCH="arm64" ;;
            armv7l)  CLOUD_ARCH="arm" ;;
            *)       CLOUD_ARCH="amd64" ;;
        esac
        
        # Download cloudflared
        curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CLOUD_ARCH}" \
            -o /tmp/cloudflared
        chmod +x /tmp/cloudflared
        sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
        log "cloudflared installed"
    else
        log "cloudflared already installed: $(cloudflared --version)"
    fi
    
    # Create tunnel startup script
    cat > "${MOTHERSHIP_DIR}/home-server/start-tunnel.sh" << 'TUNNELSCRIPT'
#!/usr/bin/env bash
# Start Cloudflare Quick Tunnel to expose web terminal
# The web terminal runs on port 3000
# cloudflared creates a public URL: https://random-name.trycloudflare.com

WEB_TERMINAL_PORT="${1:-3000}"

echo "🌐 Starting Cloudflare Tunnel → localhost:${WEB_TERMINAL_PORT}"
echo ""
echo "   Your agent will be available at the URL shown below 👇"
echo "   Open it in ANY browser (library PC, phone, etc.)"
echo ""
echo "   Press Ctrl+C to stop the tunnel"
echo ""

cloudflared tunnel --url "http://localhost:${WEB_TERMINAL_PORT}"
TUNNELSCRIPT
    chmod +x "${MOTHERSHIP_DIR}/home-server/start-tunnel.sh"
    
    # Create systemd service for auto-start on boot
    sudo tee /etc/systemd/system/cloudflare-mothership.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=Cloudflare Tunnel for Agent Mothership
After=network.target

[Service]
Type=simple
User=CLOUD_USER
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:3000
Restart=on-failure
RestartSec=5
Environment="HOME=/root"

[Install]
WantedBy=multi-user.target
SERVICEEOF
    
    log "Cloudflare Tunnel configured"
    log ""
    warn "┌─────────────────────────────────────────────────────┐"
    warn "│ To complete Cloudflare setup:                      │"
    warn "│                                                     │"
    warn "│  1. Start the web terminal:   npm start             │"
    warn "│  2. Start the tunnel:         ./start-tunnel.sh     │"
    warn "│  3. Open the URL in your browser!                   │"
    warn "│                                                     │"
    warn "│  For auto-start on boot:                            │"
    warn "│    Edit the .service file above with your username   │"
    warn "│    sudo systemctl enable cloudflare-mothership      │"
    warn "└─────────────────────────────────────────────────────┘"
}

# ──────────────────────────────────────────────
# Print summary
# ──────────────────────────────────────────────
print_summary() {
    echo ""
    echo "╔════════════════════════════════════════════════════╗"
    echo "║        🏠  AGENT MOTHERSHIP — READY!              ║"
    echo "╠════════════════════════════════════════════════════╣"
    echo "║                                                    ║"
    echo "║  Your home server is set up. To start your         ║"
    echo "║  personal AI agent and access it from anywhere:    ║"
    echo "║                                                    ║"
    echo "║  1. Start the web terminal:                        ║"
    echo "║     cd ~/agent-mothership                          ║"
    echo "║     npm start                                      ║"
    echo "║                                                    ║"
    echo "║  2. In another terminal, start the tunnel:         ║"
    echo "║     ./home-server/start-tunnel.sh                  ║"
    echo "║                                                    ║"
    echo "║  3. Open the Cloudflare URL in any browser         ║"
    echo "║     → You're talking to your agent!                ║"
    echo "║                                                    ║"
    echo "║  4. OR use tmux directly:                          ║"
    echo "║     tmux attach -t mothership                      ║"
    echo "║                                                    ║"
    echo "║  All files are synced to GitHub:                   ║"
    echo "║  https://github.com/ricksanchez8701/agent-mothership║"
    echo "║                                                    ║"
    echo "╚════════════════════════════════════════════════════╝"
    echo ""
}

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
main() {
    echo ""
    echo "╔══════════════════════════════════════════════╗"
    echo "║     🏠 Agent Mothership — Setup Wizard       ║"
    echo "╚══════════════════════════════════════════════╝"
    
    check_system
    install_deps
    install_nodejs
    install_codebuff
    setup_project
    setup_tmux
    setup_cloudflare
    print_summary
}

main "$@"
