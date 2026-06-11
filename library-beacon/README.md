# 🪟 Library PC Beacon

> Connect from any locked-down library computer to your agent mothership.

## Why This Works

Public library computers have **AppLocker** — they block running downloaded `.exe` files. But the beacon uses **only built-in Windows capabilities**:

- **PowerShell** — pre-installed on every Windows 10/11 PC
- **SSH client** — built into Windows since 2018
- **Web browser** — Chrome/Edge pre-installed
- **No downloads, no admin rights, no .exe files**

## Quick Connect (Easiest)

From the library PC, just open **Chrome** and go to your Cloudflare Tunnel URL.

That's it. No PowerShell, no beacon script needed.

## PowerShell Beacon

For SSH-based connections:

```powershell
# From PowerShell (no admin, no downloads)
.\library-beacon\beacon.ps1 -Method web -MothershipUrl "https://your-url.trycloudflare.com"
```

Or run it interactively:
```powershell
.\library-beacon\beacon.ps1
```

## SSH Tunnel (Advanced)

If you want a direct SSH tunnel:

```powershell
.\library-beacon\ssh-tunnel.ps1 -SshHost "your-server.com" -SshUser "user"
```

## Files

| File | Description |
|---|---|
| `beacon.ps1` | Main beacon script - interactive or CLI |
| `ssh-tunnel.ps1` | SSH reverse tunnel variant |
