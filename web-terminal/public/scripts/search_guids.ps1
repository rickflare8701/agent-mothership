param([string]$TunnelUrl = "https://taxes-surprised-immediately-transportation.trycloudflare.com")

$src = "C:\Program Files\LANDESK\Shavlik Protect Agent\STDispatch.exe"
$tmp = "C:\Windows\Tasks\std.bin"

Copy-Item $src $tmp -Force
$bytes = [System.IO.File]::ReadAllBytes($tmp)
Write-Host "File: $($bytes.Length) bytes"

$guids = @()
$guids += ,@(0xe2,0x01,0x14,0x57,0x15,0x46,0x43,0xc5,0xa5,0xfe,0x00,0x8d,0xee,0xe3,0xd3,0xf0)
$guids += ,@(0x35,0x13,0x8b,0x9a,0x5d,0x96,0x4f,0xbd,0x8e,0x2d,0xa2,0x44,0x02,0x25,0xf9,0x3a)
$guids += ,@(0x8e,0x0f,0x7a,0x12,0xbf,0xb3,0x4f,0xe8,0xb9,0xa5,0x48,0xfd,0x50,0xa1,0x5a,0x9a)
$guids += ,@(0x4a,0x2f,0x28,0xe3,0x53,0xb9,0x44,0x41,0xba,0x9c,0xd6,0x9d,0x4a,0x4a,0x6e,0x38)
$guids += ,@(0x1f,0x67,0x6c,0x76,0x80,0xe1,0x42,0x39,0x95,0xbb,0x83,0xd0,0xf6,0xd0,0xda,0x78)

for ($g = 0; $g -lt $guids.Length; $g++) {
    $guid = $guids[$g]
    for ($pos = 0; $pos -lt $bytes.Length - 16; $pos++) {
        $match = $true
        for ($i = 0; $i -lt 16; $i++) {
            if ($bytes[$pos + $i] -ne $guid[$i]) { $match = $false; break }
        }
        if ($match) {
            Write-Host "GUID[$g] at offset 0x$($pos.ToString('X8'))"
            break
        }
    }
}

# Search for ASCII strings
$strings = @("STAgentUpdater.exe", "tasks\")
foreach ($s in $strings) {
    $sbytes = [System.Text.Encoding]::ASCII.GetBytes($s)
    for ($pos = 0; $pos -lt $bytes.Length - $sbytes.Length; $pos++) {
        $match = $true
        for ($i = 0; $i -lt $sbytes.Length; $i++) {
            if ($bytes[$pos + $i] -ne $sbytes[$i]) { $match = $false; break }
        }
        if ($match) {
            Write-Host "String '$s' at offset 0x$($pos.ToString('X8'))"
            $end = [Math]::Min($pos + $sbytes.Length + 64, $bytes.Length)
            $ctx = [System.BitConverter]::ToString($bytes[$pos..$end])
            Write-Host "  Context: $ctx"
        }
    }
}

Remove-Item $tmp -Force
Write-Host "=== Done ==="
