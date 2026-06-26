#!/usr/bin/env python3
"""
Capture full DoorDash signup flow with DevTools Network tab.
Mobile context bypasses bot detection on /signup/phone.
Watches: Iguazu, reCAPTCHA, attestation, assess_behavior, /signup/*, GraphQL.
"""
import os, sys, json, time, random
from datetime import datetime
from collections import Counter
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

OUT_DIR = "/tmp/doordash/signup-capture"
os.makedirs(OUT_DIR, exist_ok=True)

SIGNUP_URL = (
    "https://identity.doordash.com/auth/user/signup"
    "?client_id=1666519390426295040"
    "&redirect_uri=https://www.doordash.com/post-login/"
    "&response_type=code"
    "&scope=*"
    "&state=capture-{ts}"
    "&intl=en-US"
    "&layout=consumer_web"
).replace("{ts}", str(int(time.time())))

# ─── Storage ───────────────────────────────────────────
network_log = []
console_log = []
page_errors = []
api_calls = []       # Requests to DoorDash APIs specifically

def save(data, name):
    path = f"{OUT_DIR}/{name}"
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  💾 {path} ({len(str(data)):,} bytes)")

# ─── CDP Handlers ──────────────────────────────────────
def on_request(params):
    req = params.get('request', {})
    url = req.get('url', '')[:500]
    entry = {
        'type': 'request',
        'url': url,
        'method': req.get('method', ''),
        'resourceType': params.get('type', ''),
        'timestamp': params.get('timestamp', 0),
        'postData': (req.get('postData', '') or '')[:5000],
        'headers': {k: v[:200] for k, v in list(req.get('headers', {}).items())[:20]},
    }
    network_log.append(entry)
    
    # Track DoorDash API calls specifically
    is_dd = any(d in url for d in ['doordash.com', 'cdn4dd.com'])
    is_api = any(k in url for k in ['api', 'graphql', 'signup', 'auth', 'token', 'attest', 'assess', 
                                      'iguazu', 'challenge', 'oauth', 'bff', 'rest', 'identity'])
    if is_dd and is_api:
        api_calls.append(entry)

def on_response(params):
    resp = params.get('response', {})
    network_log.append({
        'type': 'response',
        'url': resp.get('url', '')[:500],
        'status': resp.get('status', 0),
        'statusText': resp.get('statusText', ''),
        'mimeType': resp.get('mimeType', ''),
        'headers': {k: v[:200] for k, v in list(resp.get('headers', {}).items())[:20]},
    })

# ─── Main ──────────────────────────────────────────────
def main():
    print(f"🎯 Signup Flow Capture\n   URL: {SIGNUP_URL[:120]}...\n")
    email = f"test{int(time.time())}{random.randint(0,9999)}@example.com"
    phone = f"+1415555{random.randint(0,9999):04d}"
    print(f"   Test email: {email}")
    print(f"   Test phone: {phone}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        # MOBILE context — bypasses bot detection on /signup/phone
        context = browser.new_context(
            viewport={'width': 390, 'height': 844},  # iPhone 14 size
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
            is_mobile=True,
            has_touch=True,
            locale='en-US',
        )
        page = context.new_page()

        # ═══════════════════════════════════════════════
        # ENABLE CDP — Full DevTools Network/Console
        # ═══════════════════════════════════════════════
        cdp = page.context.new_cdp_session(page)
        cdp.send('Network.enable')
        cdp.on('Network.requestWillBeSent', on_request)
        cdp.on('Network.responseReceived', on_response)
        cdp.send('Runtime.enable')
        cdp.send('Log.enable')
        print("✅ CDP Network+Console monitoring ON\n")

        # ───────────────────────────────────────────────
        # PHASE 1: Load signup page
        # ───────────────────────────────────────────────
        print("━" * 60)
        print("PHASE 1: Loading signup page")
        print("━" * 60)
        
        api_calls.clear()
        network_log.clear()
        
        page.goto(SIGNUP_URL, wait_until='domcontentloaded', timeout=45000)
        print(f"   URL: {page.url[:120]}")
        print(f"   Title: {page.title()}")
        
        # Wait for Cloudflare
        for i in range(20):
            t = page.title()
            if 'just a moment' not in t.lower() and 'attention' not in t.lower():
                print(f"   CF resolved in {i+1}s")
                break
            time.sleep(1)
        
        # Wait for React to render
        page.wait_for_timeout(3000)
        
        # Dump DOM state
        print(f"\n   [DOM] Before form fill:")
        dom = page.evaluate("""() => ({
            inputs: Array.from(document.querySelectorAll('input')).map(i => ({name:i.name,id:i.id,type:i.type,placeholder:i.placeholder,autocomplete:i.autocomplete})),
            buttons: Array.from(document.querySelectorAll('button')).map(b => ({text:b.textContent.trim().slice(0,40),id:b.id})),
        })""")
        for inp in dom['inputs']:
            print(f"     input: {inp}")
        for btn in dom['buttons']:
            print(f"     button: {btn}")

        # Phase 1 API calls
        print(f"\n   [Network] Phase 1 API calls ({len(api_calls)}):")
        for c in api_calls:
            postdata = c.get('postData', '')[:200]
            pd_str = f" body={postdata}" if postdata else ""
            print(f"     [{c['method']}] {c['url'][:150]}{pd_str}")

        # Cookies after page load
        cookies = page.context.cookies()
        cf_cookies = [c for c in cookies if 'cf_' in c['name'].lower() or '__cf' in c['name']]
        xsrf = next((c for c in cookies if c['name'] == 'XSRF-TOKEN'), None)
        session = next((c for c in cookies if 'session' in c['name'].lower()), None)
        print(f"\n   [Cookies] CF: {len(cf_cookies)}, XSRF: {xsrf['value'][:20] if xsrf else 'NONE'}, Session: {session['name'] if session else 'NONE'}")

        # Screenshot
        page.screenshot(path=f"{OUT_DIR}/01-before-fill.png")
        print(f"   📸 Screenshot: {OUT_DIR}/01-before-fill.png")

        # ───────────────────────────────────────────────
        # PHASE 2: Fill signup form (mobile path)
        # ───────────────────────────────────────────────
        print(f"\n{'━' * 60}")
        print("PHASE 2: Filling signup form")
        print("━" * 60)
        
        api_calls.clear()
        
        # Fill form fields using native JS setters (for React)
        fields = {
            'input[autocomplete="given-name"], input[name="firstName"]': 'Test',
            'input[autocomplete="family-name"], input[name="lastName"]': 'User',
            'input[type="email"], input[autocomplete="email"]': email,
            'input[type="tel"], input[autocomplete="tel"]': phone.replace('+1', ''),
        }
        
        for selector, value in fields.items():
            page.evaluate("""({selector, value}) => {
                const el = document.querySelector(selector);
                if (!el) return 'not found';
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                setter.call(el, value);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                return 'filled';
            }""", {'selector': selector, 'value': value})
            print(f"   Filled {selector.split(',')[0][:50]} = {value}")
            time.sleep(0.3)

        # Wait for React to process
        page.wait_for_timeout(2000)
        page.screenshot(path=f"{OUT_DIR}/02-form-filled.png")
        print(f"   📸 Screenshot: {OUT_DIR}/02-form-filled.png")

        # ───────────────────────────────────────────────
        # PHASE 3: Click Sign Up button
        # ───────────────────────────────────────────────
        print(f"\n{'━' * 60}")
        print("PHASE 3: Clicking Sign Up")
        print("━" * 60)
        
        api_calls.clear()  # Fresh capture for this phase
        
        # Find and click the sign up button
        clicked = page.evaluate("""() => {
            const buttons = document.querySelectorAll('button');
            for (const b of buttons) {
                const text = b.textContent.trim().toLowerCase();
                if (text === 'sign up' || text.includes('sign up') || text.includes('continue')) {
                    b.click();
                    return 'clicked: ' + text;
                }
            }
            return 'no button found';
        }""")
        print(f"   Button click: {clicked}")

        # Wait for network activity to settle
        page.wait_for_timeout(6000)
        
        print(f"\n   URL after click: {page.url[:150]}")
        print(f"   Title: {page.title()}")
        
        # Check what happened
        page.screenshot(path=f"{OUT_DIR}/03-after-signup.png")
        
        # Dump all API calls from Phase 3
        print(f"\n   [Network] Phase 3 API calls ({len(api_calls)}):")
        for c in api_calls:
            postdata = c.get('postData', '')[:300]
            pd_str = f"\n       Body: {postdata}" if postdata else ""
            print(f"     [{c['method']}] {c['url'][:180]}{pd_str}")

        # Check DOM for success/error messages
        msgs = page.evaluate("""() => {
            const errors = Array.from(document.querySelectorAll('[class*="error"], [class*="Error"], [role="alert"]'))
                .map(e => e.textContent.trim().slice(0,200));
            const inputs = Array.from(document.querySelectorAll('input'))
                .map(i => ({type: i.type, name: i.name, id: i.id, placeholder: i.placeholder}));
            return {errors, inputs};
        }""")
        if msgs['errors']:
            print(f"\n   [Messages] On page: {msgs['errors']}")
        print(f"   [DOM] Inputs remaining: {len(msgs.get('inputs',[]))}")

        # ───────────────────────────────────────────────
        # PHASE 4: Check for phone verification step
        # ───────────────────────────────────────────────
        print(f"\n{'━' * 60}")
        print("PHASE 4: Checking for verification flow")
        print("━" * 60)
        
        # If we got to phone verification, there would be OTP inputs
        otp_inputs = page.evaluate("""() => {
            const inputs = document.querySelectorAll('input');
            const otps = Array.from(inputs).filter(i => 
                i.type === 'number' || i.type === 'tel' || i.maxLength === 1 || i.pattern === '[0-9]'
            );
            return otps.length;
        }""")
        
        if otp_inputs > 0:
            print(f"   🔥 SMS VERIFICATION SCREEN! {otp_inputs} OTP inputs found")
            page.screenshot(path=f"{OUT_DIR}/04-verification-screen.png")
        else:
            print(f"   No SMS verification screen detected")
        
        # Did we get a dd-identity-session-id?
        cookies = page.context.cookies()
        session_id = next((c for c in cookies if 'identity-session' in c['name'].lower()), None)
        if session_id:
            print(f"   dd-identity-session-id: {session_id['value'][:40]}")

        # ───────────────────────────────────────────────
        # SAVE EVERYTHING
        # ───────────────────────────────────────────────
        print(f"\n{'━' * 60}")
        print("SAVING CAPTURED DATA")
        print("━" * 60)
        
        save(network_log, "full-network-log.json")
        save(api_calls, "api-calls-only.json")
        save([c for c in network_log if 'postData' in c and c.get('postData')], 
             "requests-with-bodies.json")
        save(page.context.cookies(), "cookies.json")
        
        # Summary
        domains = Counter()
        for e in network_log:
            if e['type'] == 'request':
                try:
                    domains[urlparse(e['url']).netloc] += 1
                except:
                    pass
        
        print(f"\n   Domains contacted:")
        for d, c in domains.most_common(20):
            print(f"     {d}: {c} requests")

        print(f"\n✅ All data saved to {OUT_DIR}/")
        print(f"   📂 full-network-log.json — Every request/response")
        print(f"   📂 api-calls-only.json — DoorDash API calls")
        print(f"   📂 requests-with-bodies.json — POST requests with payloads")
        print(f"   📂 cookies.json — All cookies")
        print(f"   📸 01-before-fill.png, 02-form-filled.png, 03-after-signup.png")

        browser.close()

if __name__ == '__main__':
    main()
