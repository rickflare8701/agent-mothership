# 🏠 Home Server Setup

> Turn any old laptop, Raspberry Pi, or desktop into your 24/7 AI agent server.

## Requirements

- **Hardware:** Any Linux-capable machine (old laptop, RPi 3+, old desktop)
- **Internet:** Home internet connection
- **Power:** Can stay on 24/7 (or just when you need it)
- **OS:** Ubuntu/Debian/Raspberry Pi OS recommended, any Linux works

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/ricksanchez8701/agent-mothership/main/home-server/setup.sh | bash
```

This will:
1. Install Node.js 20
2. Install git, curl, tmux
3. Clone this repository
4. Install Codebuff
5. Set up a persistent tmux session
6. Install and configure Cloudflare Tunnel

## Manual Setup

```bash
# 1. Clone the repo
git clone https://github.com/ricksanchez8701/agent-mothership.git
cd agent-mothership

# 2. Install Codebuff
npm install -g codebuff
# or use the free version:
npm install -g freebuff

# 3. Start the web terminal
npm start

# 4. In another terminal, start the tunnel
./home-server/start-tunnel.sh
```

## Auto-Start on Boot

```bash
# Edit the service file with your username
sudo nano /etc/systemd/system/cloudflare-mothership.service

# Enable the service
sudo systemctl enable cloudflare-mothership
sudo systemctl start cloudflare-mothership
```

## Access from Library PC

Once the tunnel is running, you'll see a URL like:
```
https://random-name.trycloudflare.com
```

Open that URL in **any browser** → you're connected to your agent.

## Files

| File | Description |
|---|---|
| `setup.sh` | One-command automated setup |
| `Dockerfile` | Docker-based deployment alternative |
| `start-tunnel.sh` | Script to start Cloudflare Tunnel |
| `cloudflare.service` | Systemd service for auto-start on boot |
