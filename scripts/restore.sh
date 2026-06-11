#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 🔄 Restore — Restore your session from GitHub backup
# ============================================================
# Run this when starting in a fresh environment to pick up
# where you left off.
#
# Usage:
#   ./scripts/restore.sh
# ============================================================

REPO_URL="https://github.com/ricksanchez8701/agent-mothership.git"
SESSION_BRANCH="sessions"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     🔄 Restoring Previous Session        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${PROJECT_DIR}"

# Try to fetch session from GitHub
info "Fetching session from GitHub..."
git fetch origin "${SESSION_BRANCH}" 2>/dev/null || {
    warn "Could not fetch session branch. No saved session found."
    exit 0
}

# Checkout the session snapshot
if git ls-tree -r "${SESSION_BRANCH}" --name-only 2>/dev/null | grep -q "session-snapshot.json"; then
    git checkout "${SESSION_BRANCH}" -- session-snapshot.json 2>/dev/null
    log "Session snapshot restored from GitHub"
    
    # Move to .session directory
    mkdir -p .session
    cp session-snapshot.json .session/session.json
    
    # Show session info
    SESSION_TIME=$(node -e "console.log(JSON.parse(require('fs').readFileSync('.session/session.json','utf8')).timestamp)" 2>/dev/null || echo "unknown")
    FILE_COUNT=$(node -e "console.log(Object.keys(JSON.parse(require('fs').readFileSync('.session/session.json','utf8')).files||{}).length)" 2>/dev/null || echo "unknown")
    
    log "Session from: ${SESSION_TIME}"
    log "Files tracked: ${FILE_COUNT}"
    
    # Return to main branch
    git checkout main 2>/dev/null || git checkout master 2>/dev/null || true
else
    warn "No session snapshot found on GitHub."
    log "This is normal if you haven't saved a session yet."
    log "Run 'npm run sync' after working to save your progress."
fi

echo ""
log "Done. You're ready to continue working!"
echo ""
