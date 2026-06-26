#!/usr/bin/env python3
"""
Cloudflare cf_clearance cookie extractor.
Uses Playwright+CDP to get fresh cf_clearance (solves the JS challenge in-browser),
then exports cookies in curl/requests format for fast subsequent API calls.
Usage: python3 cf_extract.py <url>
"""
import os, sys, json, time
from datetime import datetime
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

COOKIE_DIR = "/tmp/doordash/cookies"
os.makedirs(COOKIE_DIR, exist_ok=True)

def extract_cf_clearance(target_url, wait_seconds=25):
    """
    Open fresh browser, navigate to Cloudflare-protected site,
    wait for challenge to resolve, extract cf_clearance cookie.
    Returns dict of cookies.
    """
    print(f"🎯 Target: {target_url}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        # FRESH context — no cookies, no localStorage
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            locale='en-US',
        )
        page = context.new_page()

        # ═══ Enable CDP Network monitoring ═══
        cdp = page.context.new_cdp_session(page)
        cdp.send('Network.enable')

        # Track all requests to find the Cloudflare challenge
        cf_requests = []
        def on_request(params):
            url = params.get('request', {}).get('url', '')
            if 'cdn-cgi' in url or 'challenge' in url or 'cloudflare' in url:
                cf_requests.append({
                    'url': url[:200],
                    'method': params.get('request', {}).get('method', ''),
                    'time': params.get('timestamp', 0),
                })
        cdp.on('Network.requestWillBeSent', on_request)

        # ═══ Navigate and wait for CF challenge ═══
        print("[1] Navigating with fresh browser...")
        page.goto(target_url, wait_until='domcontentloaded', timeout=30000)

        print("[2] Waiting for Cloudflare challenge to resolve...")
        cookies_before = page.context.cookies()
        cf_cookie_before = [c for c in cookies_before if 'cf_clearance' in c['name']]
        print(f"    Before wait: {len(cf_cookie_before)} cf_clearance cookies")

        # Wait for cf_clearance to appear
        for i in range(wait_seconds):
            cookies = page.context.cookies()
            cf_cookies = [c for c in cookies if 'cf_clearance' in c['name'] or '__cf_bm' in c['name']]
            
            # Check if page loaded (not still on challenge)
            title = page.title()
            challenge_active = 'just a moment' in title.lower() or 'attention' in title.lower()
            
            if cf_cookies and not challenge_active:
                print(f"    ✅ CF resolved after {i+1}s! Title: {title}")
                break
            elif i % 5 == 0:
                print(f"    ... {i+1}s: {'challenge active' if challenge_active else 'waiting for cookies'}")
            time.sleep(1)
        else:
            print(f"    ⚠️  CF may not have resolved. Title: {page.title()}")

        # ═══ Extract all cookies ═══
        all_cookies = page.context.cookies()
        print(f"\n[3] Cookies captured: {len(all_cookies)}")

        # Separate Cloudflare cookies from site cookies
        cf_cookies = [c for c in all_cookies if any(
            k in c['name'] for k in ['cf_clearance', '__cf_bm', '__cfruid', '_cfuvid', '__cfwaitingroom', 'cf_chl']
        )]
        site_cookies = [c for c in all_cookies if c not in cf_cookies]

        print(f"    Cloudflare: {len(cf_cookies)}")
        for c in cf_cookies:
            print(f"      {c['name']} = {c['value'][:40]}... (expires: {datetime.fromtimestamp(c.get('expires', 0)) if c.get('expires', -1) > 0 else 'session'})")

        print(f"\n    Site: {len(site_cookies)}")
        for c in site_cookies:
            print(f"      {c['name']} = {c['value'][:40]}...")

        # ═══ Show Cloudflare challenge requests ═══
        if cf_requests:
            print(f"\n[4] Cloudflare challenge requests ({len(cf_requests)}):")
            for r in cf_requests:
                print(f"    [{r['method']}] {r['url'][:150]}")
        else:
            print(f"\n[4] Cloudflare challenge requests: none detected (CF may use opaque URLs)")

        browser.close()

    return all_cookies

def export_cookies(cookies, domain):
    """Export cookies in multiple formats"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # JSON format
    json_path = f"{COOKIE_DIR}/{domain}_{timestamp}.json"
    with open(json_path, 'w') as f:
        json.dump(cookies, f, indent=2)
    print(f"\n💾 JSON: {json_path}")
    
    # Netscape format (for curl -b cookies.txt)
    netscape_path = f"{COOKIE_DIR}/{domain}_{timestamp}_netscape.txt"
    with open(netscape_path, 'w') as f:
        f.write("# Netscape HTTP Cookie File\n")
        for c in cookies:
            domain_tab = c.get('domain', '')
            # Netscape format: domain flag path secure expiration name value
            flag = 'TRUE' if domain_tab.startswith('.') else 'FALSE'
            path = c.get('path', '/')
            secure = 'TRUE' if c.get('secure', False) else 'FALSE'
            expires = str(int(c.get('expires', 0))) if c.get('expires', -1) > 0 else '0'
            f.write(f"{domain_tab}\t{flag}\t{path}\t{secure}\t{expires}\t{c['name']}\t{c['value']}\n")
    print(f"💾 Netscape: {netscape_path}")
    
    # Python dict format (for requests library)
    cookie_dict = {c['name']: c['value'] for c in cookies}
    
    return cookie_dict, netscape_path

def test_with_requests(url, cookies_dict):
    """Test if the extracted cookies work in requests"""
    print(f"\n[5] Testing cookies with Python requests...")
    try:
        import requests
        resp = requests.get(url, cookies=cookies_dict, timeout=15, 
                          headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        print(f"    Status: {resp.status_code}")
        print(f"    Content-Type: {resp.headers.get('content-type', '?')[:60]}")
        print(f"    Size: {len(resp.content):,} bytes")
        
        # Check if it's a CF challenge page
        if 'just a moment' in resp.text.lower() or 'cf-browser-verification' in resp.text.lower():
            print(f"    ❌ Still got Cloudflare challenge — cookies didn't help")
        elif resp.status_code == 200:
            print(f"    ✅ Cookies WORK — got 200 response!")
            # Check for interesting content
            if 'graphql' in resp.text.lower() or 'json' in resp.headers.get('content-type', ''):
                print(f"    Response preview: {resp.text[:200]}")
        
        return resp.status_code == 200 and 'just a moment' not in resp.text.lower()
    except Exception as e:
        print(f"    Transport error (not CF-related): {e}")
        return None

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://identity.doordash.com"
    domain = urlparse(url).netloc.replace('www.', '').replace('.', '_')
    
    cookies = extract_cf_clearance(url)
    
    if not cookies:
        print("\n❌ No cookies captured")
        return 1
    
    cookie_dict, netscape_path = export_cookies(cookies, domain)
    
    # Test if cookies work in requests
    success = test_with_requests(url, cookie_dict)
    
    print(f"\n📝 To use in curl:")
    print(f"   curl -b {netscape_path} '{url}'")
    
    print(f"\n📝 To use in Python:")
    print(f"   import requests")
    print(f"   cookies = {json.dumps({k: v[:20]+'...' for k,v in cookie_dict.items()})}")
    print(f"   r = requests.get('{url}', cookies=cookies)")
    
    return 0 if success else 0  # Always return 0 — cookies are useful even if this domain still challenges

if __name__ == '__main__':
    sys.exit(main())
