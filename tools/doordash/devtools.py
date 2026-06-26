#!/usr/bin/env python3
"""
Chrome DevTools equivalent via Playwright + CDP.
Gives us: Network tab, Console tab, Elements tab, Application tab.
Usage: python3 devtools.py <url>
Output: /tmp/doordash/devtools/{network,console,dom,screenshots}/
"""

import os, sys, json, time
from datetime import datetime
from collections import Counter
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

OUT_DIR = "/tmp/doordash/devtools"
os.makedirs(f"{OUT_DIR}/screenshots", exist_ok=True)
os.makedirs(f"{OUT_DIR}/network", exist_ok=True)

# ─── Storage ───────────────────────────────────────────
network_log = []    # All network events
console_log = []    # All console messages
page_errors = []    # Uncaught JS errors
har_entries = []    # HAR-format entries

# ─── Helper: save session ──────────────────────────────
def save_session(data, name):
    path = f"{OUT_DIR}/{name}"
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"  💾 Saved: {path} ({len(str(data)):,} bytes)")

# ─── CDP Handlers ──────────────────────────────────────
def on_request(params):
    req = params.get('request', {})
    url = req.get('url', '')[:300]
    entry = {
        'type': 'request',
        'url': url,
        'method': req.get('method', ''),
        'resourceType': params.get('type', ''),
        'timestamp': params.get('timestamp', 0),
        'postData': (req.get('postData', '') or '')[:5000],
    }
    network_log.append(entry)
    
    # HAR entry
    har_entries.append({
        'startedDateTime': str(datetime.now()),
        'request': {
            'method': req.get('method', ''),
            'url': url,
            'headers': [{'name': k, 'value': v} for k, v in req.get('headers', {}).items()],
            'postData': {'text': (req.get('postData', '') or '')[:5000]},
        },
    })

def on_response(params):
    resp = params.get('response', {})
    entry = {
        'type': 'response',
        'url': resp.get('url', '')[:300],
        'status': resp.get('status', 0),
        'statusText': resp.get('statusText', ''),
        'mimeType': resp.get('mimeType', ''),
        'remoteIP': resp.get('remoteIPAddress', ''),
    }
    network_log.append(entry)

def on_console(params):
    msg = params.get('message', {})
    text = msg.get('description', msg.get('text', ''))
    # Deduplicate — Playwright page.on('console') also fires, we only want one
    if not any(c.get('text') == text for c in console_log[-10:]):
        console_log.append({
            'level': params.get('type', 'log'),
            'text': text,
            'url': msg.get('url', ''),
            'line': msg.get('lineNumber', 0),
        })

# ─── Main ──────────────────────────────────────────────
def main(url=None):
    target = url or "https://identity.doordash.com/auth/user/signup?client_id=1666519390426295040&redirect_uri=https://www.doordash.com/post-login/&response_type=code&scope=*&state=devtools-test"
    print(f"🎯 Target: {target[:100]}...\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            locale='en-US',
        )
        page = context.new_page()

        # ═══════════════════════════════════════════════
        # ENABLE CDP — Chrome DevTools Protocol
        # ═══════════════════════════════════════════════
        cdp = page.context.new_cdp_session(page)
        
        # Network tab
        cdp.send('Network.enable')
        cdp.on('Network.requestWillBeSent', on_request)
        cdp.on('Network.responseReceived', on_response)
        print("✅ Network tab: ON (capturing all requests/responses)")

        # Console tab
        cdp.send('Runtime.enable')
        cdp.send('Log.enable')
        cdp.on('Log.entryAdded', on_console)
        print("✅ Console tab: ON (capturing all JS console output)")

        # Page errors (red errors in Console) — only CDP version, Playwright console duplicates
        page.on('pageerror', lambda err: page_errors.append({'error': str(err), 'time': str(datetime.now())}))

        # ═══════════════════════════════════════════════
        # NAVIGATE
        # ═══════════════════════════════════════════════
        print(f"\n[1] Navigating...")
        page.goto(target, wait_until='domcontentloaded', timeout=30000)
        
        # Wait for CF if needed
        for i in range(20):
            t = page.title()
            if 'just a moment' not in t.lower() and 'attention' not in t.lower():
                print(f"    Page loaded in {i+1}s: {t}")
                break
            time.sleep(1)
        else:
            print(f"    ⚠️  CF still active: {page.title()}")

        # Get cookies (Application tab)
        cookies = page.context.cookies()
        
        # Screenshot
        page.screenshot(path=f"{OUT_DIR}/screenshots/page.png", full_page=False)
        print(f"    📸 Screenshot: {OUT_DIR}/screenshots/page.png")

        # ═══════════════════════════════════════════════
        # ELEMENTS TAB — DOM Inspection
        # ═══════════════════════════════════════════════
        print(f"\n[2] DOM inspection...")
        dom_info = page.evaluate("""() => ({
            title: document.title,
            url: location.href,
            inputs: Array.from(document.querySelectorAll('input')).map(i => ({
                name: i.name, id: i.id, type: i.type, 
                autocomplete: i.autocomplete, placeholder: (i.placeholder||'').slice(0,30)
            })),
            buttons: Array.from(document.querySelectorAll('button')).map(b => ({
                text: b.textContent.trim().slice(0,30), id: b.id, type: b.type
            })),
            forms: Array.from(document.querySelectorAll('form')).map(f => ({
                id: f.id, action: f.action, method: f.method
            })),
            scripts: Array.from(document.scripts).map(s => s.src || 'inline').slice(0, 20),
            metaTags: Array.from(document.querySelectorAll('meta[name]')).map(m => ({
                name: m.name, content: (m.content||'').slice(0,80)
            })),
            links: Array.from(document.querySelectorAll('link[rel]')).map(l => ({
                rel: l.rel, href: (l.href||'').slice(0,80)
            })),
            hasRecaptcha: typeof grecaptcha !== 'undefined',
            hasRecaptchaBadge: !!document.querySelector('.grecaptcha-badge'),
            localStorage: Object.keys(localStorage).length + ' keys',
            sessionStorage: Object.keys(sessionStorage).length + ' keys',
        })""")
        print(f"    Inputs: {len(dom_info.get('inputs',[]))}")
        print(f"    Buttons: {len(dom_info.get('buttons',[]))}")
        print(f"    Scripts: {len(dom_info.get('scripts',[]))}")
        print(f"    reCAPTCHA: {dom_info.get('hasRecaptcha', False)}")
        print(f"    Forms: {len(dom_info.get('forms',[]))}")

        # ═══════════════════════════════════════════════
        # NETWORK TAB — Analysis
        # ═══════════════════════════════════════════════
        print(f"\n[3] Network analysis ({len(network_log)} events)...")
        
        # By resource type
        req_types = Counter(e.get('resourceType', '?') for e in network_log if e['type'] == 'request')
        print(f"    Resource types:")
        for t, c in req_types.most_common(10):
            print(f"      {t}: {c}")

        # By domain
        domains = Counter()
        for e in network_log:
            if e['type'] == 'request':
                try:
                    domain = urlparse(e['url']).netloc
                    domains[domain] += 1
                except:
                    pass
        print(f"\n    Domains called:")
        for d, c in domains.most_common(15):
            print(f"      {d}: {c} requests")

        # API calls (filter out analytics noise)
        NOISE = {'sentry.io', 'segment.com', 'cloudflareinsights.com', 'google-analytics', 'googletagmanager', 'doubleclick', 'facebook.net'}
        api_calls = [e for e in network_log if e['type'] == 'request' and any(
            k in e.get('url','') for k in ['api', 'graphql', 'auth', 'token', 'signup', 'oauth', 'attestation', 'assess', 'iguazu', 'bff', 'rest']
        ) and not any(d in e.get('url','') for d in NOISE)]
        print(f"\n    🔍 API/interesting calls ({len(api_calls)}):")
        for e in api_calls:
            print(f"      [{e['method']}] {e['url'][:150]}")

        # Status codes
        statuses = Counter(str(e.get('status',0)) for e in network_log if e['type'] == 'response')
        print(f"\n    Status codes:")
        for s, c in statuses.most_common(10):
            print(f"      {s}: {c}")

        # ═══════════════════════════════════════════════
        # CONSOLE TAB — JS Output
        # ═══════════════════════════════════════════════
        print(f"\n[4] Console output ({len(console_log)} entries)...")
        errors = [c for c in console_log if c['level'] in ('error', 'warning')]
        if errors:
            print(f"    ⚠️  {len(errors)} errors/warnings:")
            for c in errors[:10]:
                print(f"      [{c['level']}] {str(c['text'])[:120]}")
        
        if page_errors:
            print(f"    🔴 {len(page_errors)} uncaught errors:")
            for e in page_errors[:5]:
                print(f"      {e['error'][:120]}")

        # ═══════════════════════════════════════════════
        # APPLICATION TAB — Storage
        # ═══════════════════════════════════════════════
        print(f"\n[5] Application storage...")
        print(f"    Cookies: {len(cookies)}")
        for c in cookies:
            print(f"      {c['name']:30} = {c['value'][:50]}")

        # ═══════════════════════════════════════════════
        # SAVE EVERYTHING
        # ═══════════════════════════════════════════════
        print(f"\n[6] Saving session...")
        save_session(network_log, "network/traffic.json")
        save_session(har_entries, "network/har.json")
        save_session(console_log, "network/console.json")
        save_session(page_errors, "network/errors.json")
        save_session(dom_info, "network/dom.json")
        save_session([{'name': c['name'], 'value': c['value'], 'domain': c['domain']} for c in cookies], 
                     "network/cookies.json")

        browser.close()

    print(f"\n✅ All DevTools output saved to: {OUT_DIR}/")
    print(f"   📂 {OUT_DIR}/network/traffic.json — Full network log")
    print(f"   📂 {OUT_DIR}/network/har.json — HAR format")
    print(f"   📂 {OUT_DIR}/network/console.json — Console output")
    print(f"   📂 {OUT_DIR}/network/errors.json — JS errors")
    print(f"   📂 {OUT_DIR}/network/dom.json — DOM inspection")
    print(f"   📂 {OUT_DIR}/network/cookies.json — Cookies")
    print(f"   📸 {OUT_DIR}/screenshots/page.png — Screenshot")

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
