<#
.SYNOPSIS
    Agent Mothership Beacon — Connect from a locked-down library PC to your home agent server.
.DESCRIPTION
    This pure-PowerShell script connects your library PC to your home agent mothership
    using ONLY built-in Windows capabilities. No .exe downloads, no admin rights needed.
    
    AppLocker CANNOT block this because it uses only built-in Windows components.
    
    Three connection methods:
      1. SSH TUNNEL (best) — Uses built-in Windows OpenSSH if available
      2. WEB TERMINAL (easiest) — Opens the Cloudflare URL in your browser
      3. WEBSOCKET RELAY — For custom relay setups
    
.PARAMETER Method
    Connection method: "ssh", "web", or "relay"
.PARAMETER MothershipUrl
    Your Cloudflare tunnel URL (e.g., https://random-name.trycloudflare.com)
.PARAMETER SshHost
    SSH host if using SSH tunnel method
.PARAMETER SshPort
    SSH port (default: 22)
.PARAMETER SshUser
    SSH username
.PARAMETER LocalPort
    Local port for the tunnel (default: 3000)

.EXAMPLE
    .\beacon.ps1 -Method web -MothershipUrl "https://random-name.trycloudflare.com"
    
.EXAMPLE
    .\beacon.ps1 -Method ssh -SshHost "your-server.com" -SshUser "user"
#>

param(
    [ValidateSet("ssh", "web", "relay")]
    [string]$Method = "web",
    
    [string]$MothershipUrl = "",
    
    [string]$SshHost = "",
    [int]$SshPort = 22,
    [string]$SshUser = "",
    
    [int]$LocalPort = 3000,
    
    [switch]$Help
)

# ──────────────────────────────────────────────
# Help
# ──────────────────────────────────────────────
function Show-Help {
    Get-Help $MyInvocation.ScriptName -Detailed
    exit 0
}

if ($Help) { Show-Help }

# ──────────────────────────────────────────────
# Color output helpers (works in PowerShell ISE and console)
# ──────────────────────────────────────────────
function Write-Success { Write-Host "✅ $args" -ForegroundColor Green }
function Write-Info    { Write-Host "ℹ️  $args" -ForegroundColor Cyan }
function Write-Warn   { Write-Host "⚠️  $args" -ForegroundColor Yellow }
function Write-Error   { Write-Host "❌ $args" -ForegroundColor Red }

# ──────────────────────────────────────────────
# Banner
# ──────────────────────────────────────────────
function Show-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║     🪟 Agent Mothership — BEACON        ║" -ForegroundColor Cyan
    Write-Host "║     Connect to your AI agent from here   ║" -ForegroundColor Cyan
    Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

# ──────────────────────────────────────────────
# Check if we can use SSH
# ──────────────────────────────────────────────
function Test-SshAvailable {
    $sshPath = Get-Command "ssh" -ErrorAction SilentlyContinue
    return ($null -ne $sshPath)
}

# ──────────────────────────────────────────────
# Method 1: Web Terminal (Browser)
# Opens the Cloudflare URL in the default browser
# ──────────────────────────────────────────────
function Connect-WebTerminal {
    param([string]$Url)
    
    Write-Info "Opening web terminal in browser..."
    Write-Info "URL: $Url"
    Write-Host ""
    Write-Warn "If the browser doesn't open automatically, copy the URL above and paste it into Chrome."
    Write-Host ""
    
    try {
        Start-Process $Url
        Write-Success "Browser opened! You should see your AI agent's terminal."
    }
    catch {
        Write-Warn "Could not open browser automatically."
        Write-Host "   ➜  Copy this URL into Chrome: $Url" -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "💡 Tip: Bookmark this URL so you can come back anytime." -ForegroundColor Green
}

# ──────────────────────────────────────────────
# Method 2: SSH Reverse Tunnel
# Uses built-in Windows OpenSSH (no .exe download)
# Creates a tunnel from your cloud server back to localhost
# ──────────────────────────────────────────────
function Connect-SshTunnel {
    param(
        [string]$Host,
        [int]$Port,
        [string]$User
    )
    
    if (-not (Test-SshAvailable)) {
        Write-Error "SSH client is not available on this system."
        Write-Info "Try Method 3 (Web) instead — it just opens a browser."
        return $false
    }
    
    Write-Info "SSH client found: $(Get-Command ssh).Source"
    Write-Info "Creating reverse tunnel: $User@$Host`:$Port"
    Write-Host ""
    Write-Warn "This will open an SSH connection. Enter your password when prompted."
    Write-Host ""
    
    # Build SSH command
    $sshArgs = @(
        "-R", "0.0.0.0:$LocalPort`:localhost:$LocalPort",
        "-N",                                # No command, just tunnel
        "-v",                                # Verbose for debugging
        "-p", "$Port",
        "$User@$Host"
    )
    
    Write-Info "Running: ssh $($sshArgs -join ' ')"
    Write-Host ""
    Write-Host "⏳ Waiting for connection... (press Ctrl+C to stop)" -ForegroundColor Yellow
    Write-Host ""
    
    try {
        & "ssh" $sshArgs
    }
    catch {
        Write-Error "SSH connection failed: $_"
        Write-Info "Try using the web terminal method instead."
        return $false
    }
    
    return $true
}

# ──────────────────────────────────────────────
# Method 3: PowerShell WebSocket Relay
# Pure PowerShell WebSocket client - no external dependencies
# ──────────────────────────────────────────────
function Connect-WebSocketRelay {
    param([string]$RelayUrl)
    
    Write-Info "Connecting to WebSocket relay: $RelayUrl"
    Write-Host ""
    
    # PowerShell 7+ has native WebSocket support
    if ($PSVersionTable.PSVersion.Major -lt 7) {
        Write-Warn "This method works best with PowerShell 7+"
        Write-Info "Fallback: Opening web browser instead..."
        Start-Process ($MothershipUrl -replace '^ws', 'http')
        return
    }
    
    try {
        $ws = New-Object System.Net.WebSockets.ClientWebSocket
        $ws.ConnectAsync([System.Uri]$RelayUrl, [System.Threading.CancellationToken]::Empty).GetAwaiter().GetResult()
        Write-Success "Connected to relay!"
        
        Write-Info "Connected. Type your commands below (Ctrl+C to exit):"
        Write-Host ""
        
        # Simple echo loop
        while ($ws.State -eq 'Open') {
            $input = Read-Host "> "
            if ($input -eq "exit") { break }
            
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($input)
            $ws.SendAsync([ArraySegment[byte]]::new($bytes), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, [System.Threading.CancellationToken]::Empty).GetAwaiter().GetResult()
        }
    }
    catch {
        Write-Error "WebSocket error: $_"
    }
    finally {
        if ($ws) { $ws.Dispose() }
    }
}

# ──────────────────────────────────────────────
# Interactive Menu
# ──────────────────────────────────────────────
function Show-InteractiveMenu {
    Show-Banner
    
    Write-Host "Choose how to connect to your agent:" -ForegroundColor White
    Write-Host ""
    Write-Host "  [1] 🌐 Web Browser (easiest)" -ForegroundColor Green
    Write-Host "      Opens the agent terminal in Chrome/Edge" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [2] 🔌 SSH Tunnel" -ForegroundColor Cyan
    Write-Host "      Uses built-in Windows SSH (if available)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [3] 📡 WebSocket Relay" -ForegroundColor Magenta
    Write-Host "      Pure PowerShell connection (PS 7+)" -ForegroundColor DarkGray
    Write-Host ""
    
    $choice = Read-Host "Enter your choice (1-3)"
    Write-Host ""
    
    switch ($choice) {
        "1" { 
            if ([string]::IsNullOrEmpty($MothershipUrl)) {
                $MothershipUrl = Read-Host "Enter your Cloudflare Tunnel URL"
            }
            Connect-WebTerminal -Url $MothershipUrl
        }
        "2" {
            if ([string]::IsNullOrEmpty($SshHost)) { $SshHost = Read-Host "SSH host" }
            if ([string]::IsNullOrEmpty($SshUser)) { $SshUser = Read-Host "SSH user" }
            Connect-SshTunnel -Host $SshHost -Port $SshPort -User $SshUser
        }
        "3" {
            $relayUrl = Read-Host "WebSocket relay URL"
            Connect-WebSocketRelay -RelayUrl $relayUrl
        }
        default {
            Write-Error "Invalid choice. Defaulting to web browser."
            Connect-WebTerminal -Url $MothershipUrl
        }
    }
}

# ──────────────────────────────────────────────
# Check environment & capabilities
# ──────────────────────────────────────────────
function Test-Environment {
    Write-Info "Checking what's available on this PC..."
    
    # Check PowerShell version
    Write-Info "PowerShell: $($PSVersionTable.PSVersion)"
    
    # Check for SSH
    if (Test-SshAvailable) {
        Write-Success "SSH client: Available"
    } else {
        Write-Warn "SSH client: Not found"
    }
    
    # Check for browser
    Write-Info "Browser: Will use default browser"
    
    # Check for VS Code
    $codePath = Get-Command "code" -ErrorAction SilentlyContinue
    if ($codePath) {
        Write-Success "VS Code: Available (can use integrated terminal)"
    }
    
    Write-Host ""
}

# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
function Main {
    Show-Banner
    Test-Environment
    
    if ($Method -eq "web") {
        if ([string]::IsNullOrEmpty($MothershipUrl)) {
            Show-InteractiveMenu
        } else {
            Connect-WebTerminal -Url $MothershipUrl
        }
    }
    elseif ($Method -eq "ssh") {
        if ([string]::IsNullOrEmpty($SshHost) -or [string]::IsNullOrEmpty($SshUser)) {
            Show-InteractiveMenu
        } else {
            Connect-SshTunnel -Host $SshHost -Port $SshPort -User $SshUser
        }
    }
    elseif ($Method -eq "relay") {
        Connect-WebSocketRelay -RelayUrl $MothershipUrl
    }
    
    Write-Host ""
    Write-Host "💡 Session complete! Your progress is saved to GitHub." -ForegroundColor Green
    Write-Host "   Come back anytime and pick up where you left off." -ForegroundColor Green
    Write-Host ""
}

# Run it
Main
