#!/usr/bin/env bash
# Start Cloudflare Quick Tunnel to expose web terminal
# The web terminal runs on port 3000
# cloudflared creates a public URL: https://random-name.trycloudflare.com

set -euo pipefail

PORT="${1:-3000}"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     🌐 Starting Cloudflare Tunnel             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}  Tunnel to:${NC} http://localhost:${PORT}"
echo ""
echo -e "${YELLOW}  Your agent will be available at the URL shown below 👇${NC}"
echo -e "${YELLOW}  Open it in ANY browser (library PC, phone, etc.)${NC}"
echo ""
echo -e "${YELLOW}  Press Ctrl+C to stop the tunnel${NC}"
echo ""

cloudflared tunnel --url "http://localhost:${PORT}"
