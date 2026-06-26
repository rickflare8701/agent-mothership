#!/usr/bin/env python3
"""Download DoorDash APK via direct methods"""
import requests, os, time

APK_PATH = "/tmp/doordash/apk/doordash.apk"
os.makedirs("/tmp/doordash/apk", exist_ok=True)

headers = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36',
    'Accept': '*/*',
}

# Source 1: APKCombo downloader API
print("=== Source 1: APKCombo API ===")
try:
    # APKCombo has a direct downloader
    resp = requests.get(
        'https://apkcombo.com/downloader/',
        params={'package': 'com.dd.doordash', 'type': 'json'},
        headers=headers,
        timeout=20
    )
    print(f"  Status: {resp.status_code}, size: {len(resp.content)}")
    print(f"  Content: {resp.text[:300]}")
except Exception as e:
    print(f"  Failed: {e}")

# Source 2: APKPure API v2
print("\n=== Source 2: APKPure v2 ===")
try:
    resp = requests.get(
        'https://apkpure.com/api/v2/app/com.dd.doordash/versions',
        headers=headers,
        timeout=20
    )
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  Keys: {list(data.keys())[:10] if isinstance(data, dict) else 'list'}")
except Exception as e:
    print(f"  Failed: {e}")

# Source 3: Direct APKPure download (trying different endpoints)
print("\n=== Source 3: APKPure direct download ===")
apk_urls = [
    'https://d.apkpure.com/b/APK/com.dd.doordash?version=latest',
    'https://apkpure.com/doordash-food-delivery/com.dd.doordash/download',
]
for url in apk_urls:
    try:
        resp = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        ct = resp.headers.get('content-type', '')
        print(f"  {url[:80]}: {resp.status_code} | {ct[:60]} | {len(resp.content)} bytes")
        if resp.status_code == 200 and len(resp.content) > 500000:
            with open(APK_PATH, 'wb') as f:
                f.write(resp.content)
            print(f"  ✅ DOWNLOADED! {len(resp.content):,} bytes")
            break
    except Exception as e:
        print(f"  {url[:80]}: {e}")

# Source 4: APK-DL
print("\n=== Source 4: APK-DL ===")
try:
    resp = requests.get(
        'https://apk-dl.com/com.dd.doordash',
        headers=headers,
        timeout=20
    )
    print(f"  Status: {resp.status_code}, size: {len(resp.content)}")
except Exception as e:
    print(f"  Failed: {e}")

# Source 5: Aptoide
print("\n=== Source 5: Aptoide ===")
try:
    resp = requests.get(
        'https://ws75.aptoide.com/api/7/app/get',
        params={'package_name': 'com.dd.doordash'},
        headers=headers,
        timeout=20
    )
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, dict):
            print(f"  Keys: {list(data.keys())[:10]}")
            # Aptoide returns download URLs in 'nodes' or 'file' fields
            for key in ['file', 'downloads', 'nodes', 'data']:
                if key in data:
                    print(f"  {key}: {str(data[key])[:200]}")
except Exception as e:
    print(f"  Failed: {e}")

# Check final result
if os.path.exists(APK_PATH):
    size = os.path.getsize(APK_PATH)
    print(f"\n📦 {APK_PATH}: {size:,} bytes ({size/1024/1024:.1f} MB)")
else:
    print(f"\n❌ No APK downloaded")
