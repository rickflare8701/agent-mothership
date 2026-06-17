$wins = @(
    "$env:WINDIR\Temp",
    "$env:WINDIR\Tasks",
    "$env:WINDIR\debug\wdi",
    "$env:WINDIR\System32\spool\drivers\color",
    "$env:WINDIR\Registration\CRMLog",
    "$env:WINDIR\System32\Tasks",
    "$env:WINDIR\System32\spool\PRINTERS",
    "$env:WINDIR\System32\FxsTmp",
    "$env:WINDIR\System32\com\dmp",
    "$env:ProgramData\LANDESK\Shavlik Protect\Agent"
)
$results = @{}
foreach ($d in $wins) {
    try {
        $t = Join-Path $d "test_$([guid]::NewGuid().ToString().Substring(0,8)).tmp"
        [System.IO.File]::WriteAllText($t, "x")
        Remove-Item $t -Force -ErrorAction SilentlyContinue
        $results[$d] = "WRITABLE"
        Write-Host "WRITABLE: $d"
    } catch {
        $results[$d] = "BLOCKED"
        Write-Host "BLOCKED: $d"
    }
}
$results | ConvertTo-Json | Out-File "$env:TEMP\writable_results.json" -Force
Write-Host "`nSaved to TEMP\writable_results.json"
