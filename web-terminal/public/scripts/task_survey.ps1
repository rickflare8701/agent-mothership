# Phase 1: Task File Attack
# Step 1: Survey existing files and patterns, then deploy

$agentDir = "C:\ProgramData\LANDESK\Shavlik Protect\Agent"
$newDir = Join-Path $agentDir "New"
$oldDir = Join-Path $agentDir "Old"
$ftqDir = Join-Path $agentDir "FTQ"

Write-Output "=== Survey ==="
Write-Output "New dir contents:"
Get-ChildItem $newDir -Force | Select-Object Name, Length, LastWriteTime, Attributes
Write-Output "Old dir contents:"
Get-ChildItem $oldDir -Force | Select-Object Name, Length, LastWriteTime, Attributes
Write-Output "FTQ dir contents:"
Get-ChildItem $ftqDir -Force | Select-Object Name, Length, LastWriteTime, Attributes

Write-Output "`n=== Checking for watcher processes ==="
Get-Process | Where-Object { $_.ProcessName -match "STDispatch|STAgent" } | Select-Object Id, ProcessName, StartTime

Write-Output "`n=== Checking for file locks on existing files ==="
# Check store.dat and dataCache.dat format
Write-Output "store.dat contents (hex):"
$bytes = [IO.File]::ReadAllBytes((Join-Path $agentDir "store.dat"))
Write-Output ($bytes | ForEach { "{0:X2}" -f $_ }) -join " "

Write-Output "`ndataCache.dat first 100 bytes (hex):"
if ((Get-Item (Join-Path $agentDir "dataCache.dat")).Length -gt 0) {
    $bytes = [byte[]]::new(100)
    $fs = [IO.File]::OpenRead((Join-Path $agentDir "dataCache.dat"))
    $fs.Read($bytes, 0, 100) | Out-Null
    $fs.Close()
    Write-Output ($bytes | ForEach { "{0:X2}" -f $_ }) -join " "
} else {
    Write-Output "(empty)"
}

Write-Output "`n=== Checking STDispatch log for recent activity ==="
$log = "C:\ProgramData\LANDESK\Shavlik Protect\Logs\STDispatch.log"
if (Test-Path $log) { Get-Content $log -Tail 20 } else { Write-Output "No log" }

Write-Output "`n=== Searching for *.txt in New dir patterns from other sources ==="
Get-ChildItem "C:\ProgramData\LANDESK\Shavlik Protect" -Recurse -Include "*.txt","*.xml","*.json" -File | Select-Object FullName, Length, LastWriteTime | Sort-Object LastWriteTime -Descending | Select-Object -First 20
