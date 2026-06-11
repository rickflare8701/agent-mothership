# 🤖 Agent Mothership

> **Your personal 24/7 AI agent — accessible from any browser, anywhere.**

A complete system for running Codebuff (your AI coding agent) persistently from a home server, and accessing it from ANY computer — including locked-down library PCs with AppLocker.

## Architecture

```
┌──────────────────┐     ┌─────────────────┐     ┌──────────────────────┐
│  Library PC       │     │  Cloudflare      │     │  HOME SERVER         │
│  (Chrome browser) │────▶│  Tunnel (free)   │────▶│  (Old laptop/RPi)    │
│  No installs      │     │  No CC needed    │     │  codebuff in tmux    │
│  No .exe files    │     │  trycloudflare   │     │  Web terminal (ttyd) │
└──────────────────┘     └─────────────────┘     └──────────────────────┘
                                                           │
                                                    ┌──────┴──────┐
                                                    │ GitHub Repo  │
                                                    │ Session sync │
                                                    └─────────────┘
```

### 🏠 Home Server
An old laptop, desktop, or Raspberry Pi at home running 24/7. It runs codebuff in a persistent tmux session.

### 🌐 Cloudflare Tunnel
Free tunnel that exposes your home server's web terminal to the internet. No port forwarding needed, no static IP required.

### 🪟 Browser Access
From any library PC, open Chrome → visit your Cloudflare URL → web terminal → codebuff is right there. **No downloads, no AppLocker issues.**

---

## 📦 Project Structure

```
agent-mothership/
│
├── home-server/               # 🏠 Setup your 24/7 mothership
│   ├── setup.sh               # One-command setup (any Linux machine)
│   ├── Dockerfile             # Docker-based deployment
│   └── cloudflare.service     # Auto-start tunnel on boot
│
├── library-beacon/            # 🪟 PowerShell beacon scripts
│   ├── beacon.ps1             # Main script - connects library PC to mothership
│   └── ssh-tunnel.ps1         # SSH reverse tunnel variant
│
├── web-terminal/              # 🌐 Browser-based terminal
│   ├── server.js              # Express + WebSocket terminal server
│   ├── package.json
│   └── public/index.html      # Terminal UI (xterm.js)
│
├── session-persistence/       # 💾 Never lose progress
│   └── sync.js                # Sync state to GitHub between sessions
│
├── multi-env/                 # ⚡ Rotate across free platforms
│   └── README.md              # CodeSandbox → StackBlitz → Replit → GitLab
│
└── scripts/
    ├── bootstrap.sh           # Bootstrap any fresh environment
    └── restore.sh             # Restore from GitHub backup
```

---

## 🚀 Quick Start

### Option 1: Home Server (True 24/7 — Best)

On any old laptop, Raspberry Pi, or Linux machine:

```bash
curl -fsSL https://raw.githubusercontent.com/ricksanchez8701/agent-mothership/main/home-server/setup.sh | bash
```

Or manually:
```bash
git clone https://github.com/ricksanchez8701/agent-mothership.git
cd agent-mothership/home-server
chmod +x setup.sh
./setup.sh
```

After setup, you'll get a Cloudflare URL. Open it in any browser → talk to your agent.

### Option 2: Library PC (Beacon)

From PowerShell (no admin, no downloads):

```powershell
# Option A: SSH tunnel (requires SSH on cloud side)
ssh -R 8080:localhost:3000 user@your-server

# Option B: Run the beacon script
. .\library-beacon\beacon.ps1
```

### Option 3: Free Cloud Rotation

See [`multi-env/README.md`](multi-env/README.md) for switching between:
- **CodeSandbox** (40 hrs/month) ← You are here
- **StackBlitz** (unlimited runtime, browser-based)
- **Replit** (free, GitHub signup)
- **GitHub Codespaces** (60 hrs/month)

---

## 🛡️ Security

- Cloudflare Tunnel requires NO open ports on your home network
- The tunnel URL is random (`random-name.trycloudflare.com`) — only you know it
- All traffic is HTTPS encrypted
- For production: Add Cloudflare Access (free tier) for email-based auth
- **Never share your GitHub token.** This README has no secrets.

## 📝 Session Persistence

Every conversation and file change is synced to this GitHub repo. If your environment shuts down:

1. Spin up a new one (any platform)
2. `git clone https://github.com/ricksanchez8701/agent-mothership.git`
3. Run `./scripts/restore.sh`
4. Continue exactly where you left off

---

*Built with ❤️ by you and your AI agent*
