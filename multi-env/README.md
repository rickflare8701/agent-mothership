# ⚡ Multi-Environment Rotation

> **Stretch your free hours across multiple platforms — the same code, same session, everywhere.**

## The Strategy

No single free platform gives unlimited persistent compute. But by rotating across platforms, you can **keep working without paying**.

```
┌─────────────────────────────────────────────────┐
│              ROTATION CYCLE                      │
│                                                  │
│  CodeSandbox (40 hrs) ──→ StackBlitz (∞ hrs)     │
│       ↑                           ↓              │
│  Replit (free) ←── GitLab IDE ←── GitHub Codesp. │
│                                                  │
│  All synced via GitHub ←→ session-persistence    │
└─────────────────────────────────────────────────┘
```

## Platform Breakdown

### 1. CodeSandbox
- **Free hours:** ~40 hrs/month
- **Signup:** GitHub
- **Best for:** Current primary environment
- **Limitation:** Hours cap

### 2. StackBlitz
- **Free hours:** Unlimited (browser-based)
- **Signup:** GitHub
- **Best for:** When CodeSandbox hours run out
- **Limitation:** Environment dies when tab closes (WebContainers)
- **Setup:** Open [stackblitz.com](https://stackblitz.com), create a new Node.js project, clone this repo

### 3. GitHub Codespaces
- **Free hours:** 60 hrs/month (free GitHub account), 90 (Pro)
- **Signup:** GitHub (no CC/phone needed)
- **Best for:** Full cloud VM, install anything
- **Setup:** Create a codespace → `git clone https://github.com/ricksanchez8701/agent-mothership.git`

### 4. Replit
- **Free hours:** Unlimited (repls may sleep)
- **Signup:** GitHub
- **Best for:** Quick prototyping
- **Setup:** Create Node.js repl → import from GitHub

### 5. GitLab Web IDE
- **Free hours:** Unlimited
- **Signup:** GitLab (any email, no CC)
- **Best for:** Backup environment
- **Setup:** Create a free GitLab account, import the GitHub repo

## How to Rotate

### Before leaving a session:
```bash
# Save everything
cd /path/to/agent-mothership
npm run sync
```

### When starting a new session:
```bash
# On any platform
git clone https://github.com/ricksanchez8701/agent-mothership.git
cd agent-mothership
./scripts/restore.sh
```

### Automate it:
```bash
# Start with auto-save (syncs every 5 minutes)
npm start &  # web terminal
node session-persistence/sync.js --auto  # auto-save
```

## Pro Tips

1. **Keep the repo cloned on ALL platforms.** When your CodeSandbox hours run out at 40h, you switch to StackBlitz, pull the latest, and keep going.

2. **StackBlitz has unlimited runtime** but dies when the tab is closed. Use it for burst work sessions.

3. **GitHub Codespaces** auto-saves your changes but stops after 30 min inactivity. Your session is preserved in the repo.

4. **You can rotate mid-task** — the session persistence saves your file states and git status. Nothing is lost.

## Total Available Free Hours

| Platform | Free Hours/Month | 
|---|---|
| CodeSandbox | 40 |
| GitHub Codespaces | 60 |
| StackBlitz | Unlimited* |
| Replit | Unlimited* |
| **Total effective** | **Effectively unlimited** |

*\*Some limitations apply (sleep after inactivity, environment resets)*
