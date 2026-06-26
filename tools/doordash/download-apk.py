#!/usr/bin/env python3
"""Use Camoufox + CDP (Chrome DevTools Protocol) to find and download DoorDash APK.
Camoufox = stealth fingerprinting to bypass Cloudflare
CDP = full Network tab visibility to capture the real download URL
"""
import os, time, json
from camoufox import Camoufox

APK_PATH = "/tmp/doordash/apk/doordash.apk"
os.makedirs("/tmp/doordash/apk", exist_ok=True)

# Track all network requests
network_log = []
download_urls = []

def on_request_sent(params):
    url = params.get('request', {}).get('url', '')
    method = params.get('request', {}).get('method', '')
    rtype = params.get('type', '')
    network_log.append({'type': 'request', 'url': url, 'method': method, 'rtype': rtype})
    
    # Flag any URL that looks like an APK download
    if any(k in url.lower() for k in ['apk', 'download.php', 'cdn', '.zip']):
        download_urls.append(url)
        print(f"  🔗 APK candidate: {url[:150]}")

def on_response_received(params):
    url = params.get('response', {}).get('url', '')
    status = params.get('response', {}).get('status', 0)
    mime = params.get('response', {}).get('mimeType', '')
    
    if 'apk' in mime or 'vnd.android' in mime or 'octet-stream' in mime:
        print(f"  📦 APK MIME response: {status} {url[:120]} (mime: {mime})")
        download_urls.append(url)
    
    # Also track redirects
    if status in (301, 302, 303, 307, 308):
        location = params.get('response', {}).get('headers', {}).get('location', '')
        print(f"  ↪ Redirect {status}: {url[:80]} → {location[:80] if location else '?'}")

with Camoufox(
    headless=True,
    viewport={'width': 1920, 'height': 1080},
    locale='en-US',
    timezone_id='America/Los_Angeles',
    humanize=True,
    screen={'width': 1920, 'height': 1080},
    geoip=True,
    os=['windows', 'macos'],
) as browser:
    
    page = browser.pages[0] if browser.pages else browser.new_page()
    
    # === Enable CDP Network monitoring (like Chrome DevTools Network tab) ===
    cdp = page.context.new_cdp_session(page)
    cdp.send('Network.enable')
    cdp.on('Network.requestWillBeSent', on_request_sent)
    cdp.on('Network.responseReceived', on_response_received)
    
    # === Navigate to APKMirror ===
    print("[1] Navigating to APKMirror with Camoufox...")
    page.goto(
        "https://www.apkmirror.com/apk/doordash/doordash-food-delivery/",
        wait_until='domcontentloaded',
        timeout=45000
    )
    
    # Wait for CF to resolve (Camoufox fingerprint should help)
    print("[2] Waiting for Cloudflare challenge...")
    for i in range(25):
        title = page.title()
        if 'just a moment' not in title.lower() and 'attention' not in title.lower():
            print(f"    ✅ CF resolved after {i+1}s! Title: {title}")
            break
        time.sleep(1)
    else:
        print(f"    ⚠️ CF still active — title: {page.title()}")
    
    # Wait for page to fully load
    page.wait_for_timeout(3000)
    
    # === Dump console messages (like Console tab) ===
    page.on('console', lambda msg: None)  # suppress but we could log
    page.on('pageerror', lambda err: print(f"  🔴 Page error: {err}"))
    
    # === Find download links ===
    print("[3] Scanning page for download links...")
    links = page.locator('a[href]').all()
    for link in links:
        try:
            href = link.get_attribute('href') or ''
            text = link.inner_text().strip()[:50]
            if 'download' in href.lower() or 'apk' in href.lower() or 'download' in text.lower():
                print(f"    {text} → {href[:120]}")
        except:
            pass
    
    # === Try to click download and capture the URL via CDP ===
    print("[4] Attempting to click download and capture via CDP...")
    
    # Find variant links
    variant_links = page.locator('a[href*="/apk/doordash/doordash-food-delivery/"]').all()
    print(f"    Found {len(variant_links)} variant links")
    
    for link in variant_links:
        try:
            href = link.get_attribute('href')
            if href and '/variant/' not in href and 'download' not in href.lower():
                print(f"    → Clicking: {href[:100]}")
                link.click()
                page.wait_for_timeout(5000)
                print(f"    → Now at: {page.url[:120]}")
                break
        except:
            continue
    
    # Wait for any CF on variant page
    for i in range(15):
        if 'just a moment' not in page.title().lower():
            break
        time.sleep(1)
    
    # Look for the download button on variant page
    print("[5] Looking for download button on variant page...")
    
    # Try clicking download and capturing
    for sel in ['a[href*="download.php"]', 'a:has-text("Download APK")', '.downloadButton', 'a.downloadButton']:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                href = btn.get_attribute('href')
                print(f"    Found button: {sel} → {href[:100] if href else 'none'}")
                
                # Clear download URLs list to capture fresh ones
                download_urls.clear()
                
                # Click and see what happens in network
                btn.click()
                page.wait_for_timeout(5000)
                
                # Check if any APK URLs were captured
                if download_urls:
                    print(f"    📦 Captured {len(download_urls)} potential APK URLs!")
                    for u in download_urls:
                        print(f"       {u[:150]}")
                
                break
        except:
            continue
    
    # === Summary of all network activity ===
    print(f"\n[6] CDP captured {len(network_log)} total network events")
    
    # Filter for interesting URLs
    interesting = [e for e in network_log if any(
        k in e.get('url', '') for k in ['download', 'apk', 'cdn', 'googleapis']
    )]
    print(f"    {len(interesting)} interesting URLs:")
    for e in interesting[:20]:
        print(f"    {e.get('method','?')} {e.get('url','')[:120]}")
    
    # === Try direct download of captured URLs ===
    if download_urls:
        print("[7] Trying direct download of captured URLs...")
        for url in download_urls:
            try:
                resp = page.context.request.get(url, timeout=30000)
                ct = resp.headers.get('content-type', '')
                size = len(resp.body())
                print(f"    {url[:80]}: {resp.status} | {ct[:50]} | {size:,} bytes")
                if size > 500000 and 'html' not in ct:
                    with open(APK_PATH, 'wb') as f:
                        f.write(resp.body())
                    print(f"    ✅ APK DOWNLOADED! {size:,} bytes")
                    break
            except Exception as e:
                print(f"    Failed: {e}")
    
    browser.close()

# Final check
if os.path.exists(APK_PATH):
    size = os.path.getsize(APK_PATH)
    print(f"\n📦 {APK_PATH}: {size:,} bytes ({size/1024**2:.1f} MB)")
    if size > 500000:
        print("✅ DONE!")
    else:
        print("❌ Too small")
else:
    print("\n❌ No APK downloaded")
