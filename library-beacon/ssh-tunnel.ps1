<#
.SYNOPSIS
    SSH Reverse Tunnel — Lightweight variant of the beacon for SSH-only connections.
.DESCRIPTION
    Connects from a library PC to your mothership server via SSH reverse tunnel.
    Uses ONLY the built-in Windows OpenSSH client. No downloads, no AppLocker issues.
    
    After connecting, your mothership can reach services on THIS PC.
.EXAMPLE
    .\ssh-tunnel.ps1 -SshHost "your-server.com" -SshUser "user"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$SshHost,
    
    [Parameter(Mandatory=$true)]
    [string]$SshUser,
    
    [int]$SshPort = 22,
    [int]$RemotePort = 8080,
    [int]$LocalPort = 3000,
    [switch]$KeepAlive
)

# Check SSH availability
$sshPath = Get-Command "ssh" -ErrorAction SilentlyContinue
if (-not $sshPath) {
    Write-Error "❌ SSH client not found."
    Write-Error "   Windows 10/11 includes OpenSSH. Try enabling it:"
    Write-Error "   Settings → Apps → Optional Features → Add OpenSSH Client"
    exit 1
}

Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     🔌 Beacon: SSH Reverse Tunnel       ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "   Host:    $SshHost`:$SshPort" -ForegroundColor Green
Write-Host "   User:    $SshUser" -ForegroundColor Green
Write-Host "   Tunnel:  localhost:$LocalPort → remote:$RemotePort" -ForegroundColor Green
Write-Host ""

$sshArgs = @(
    "-R", "0.0.0.0:${RemotePort}:localhost:${LocalPort}",
    "-N",
    "-v",
    "-p", "$SshPort",
    "$SshUser@$SshHost"
)

if ($KeepAlive) {
    $sshArgs += @(
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3"
    )
}

Write-Host "⏳ Connecting... (press Ctrl+C to stop)" -ForegroundColor Yellow
Write-Host ""

try {
    & "ssh" $sshArgs
}
catch {
    Write-Error "Connection failed: $_"
    exit 1
}
