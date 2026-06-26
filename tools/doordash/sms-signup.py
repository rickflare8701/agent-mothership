#!/usr/bin/env python3
"""
sms-signup.py — Automated DoorDash account creation via receive-sms.cc

Flow:
1. Load DoorDash signup page for cookies (Playwright mobile context)
2. Fetch US phone number from receive-sms.cc
3. POST /signup/phone with the virtual number
4. Navigate to receive-sms.cc inbox in Playwright to read the SMS
5. Extract 6-digit verification code
6. POST /signup/phone/verify with the real code
7. POST /signup/phone/signup_continue to complete signup
8. Save cookies + auth tokens
"""
import re, time, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("/tmp/doordash/accounts")
OUT.mkdir(parents=True, exist_ok=True)

IDENTITY = "https://identity.doordash.com"
CLIENT_ID = "1666519390426295040"
REDIRECT_URI = "https://www.doordash.com/post-login/"
PASSWORD = "TestPass123!"
FIRST = "Test"
LAST = "User"

def find_code_in_text(text):
    """Extract 4-8 digit verification code from SMS text."""
    # DoorDash typically sends 6-digit codes
    patterns = [
        r'\b(\d{6})\b',                          # Standalone 6 digits
        r'code[:\s]*(\d{4,8})',                   # "code: 123456"
        r'(\d{4,8})\s*is your',                   # "123456 is your"
        r'verification\s*code[:\s]*(\d{4,8})',    # "verification code: 123456"
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def run():
    email = f"ddtest{int(time.time())}@mail.com"
    
    print("📱 SMS Signup — DoorDash Account Creator")
    print("=" * 55)
    print(f"  Email: {email}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            is_mobile=True, has_touch=True,
            locale="en-US",
        )
        page = ctx.new_page()

        # ── STEP 1: Get a US number from receive-sms.cc ──
        print("\n[1] Fetching US number from receive-sms.cc...")
        try:
            page.goto("https://receive-sms.cc/US-Phone-Number/", 
                     wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            
            # Extract phone number from the page
            phone_text = page.evaluate("""
            () => {
                const body = document.body.innerText;
                // Find patterns like +1 6465180948
                const matches = body.match(/\\+1\\s*(\\d{10})/g);
                if (matches) {
                    return matches[0].replace(/\\s/g, '').replace('+1', '');
                }
                // Try finding numbers in links
                const links = document.querySelectorAll('a[href*="Phone-Number"]');
                for (const l of links) {
                    const m = l.href.match(/(\\d{10})/);
                    if (m) return m[1];
                }
                return null;
            }
            """)
            
            if phone_text and len(phone_text) == 10:
                phone = phone_text
                print(f"    ✅ Got number: +1{phone}")
            else:
                # Fallback: use a known number from our earlier test
                phone = "6465180948"
                print(f"    ⚠️ Couldn't extract, using fallback: +1{phone}")
        except Exception as e:
            print(f"    ❌ Error: {str(e)[:80]}")
            phone = "6465180948"
            print(f"    Using fallback: +1{phone}")

        # ── STEP 2: Load DoorDash signup page for cookies ──
        print("\n[2] Loading DoorDash signup page...")
        page.goto(
            f"{IDENTITY}/auth/user/signup"
            f"?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
            f"&response_type=code&scope=*&state=test",
            wait_until="domcontentloaded", timeout=30000
        )
        page.wait_for_timeout(2000)
        title = page.evaluate("() => document.title")
        print(f"    Page: {title[:60]}")
        
        if "just a moment" in title.lower():
            print("    ❌ CF blocked!")
            browser.close()
            return
        
        xsrf = page.evaluate(
            "() => decodeURIComponent((document.cookie.match('(^|; )XSRF-TOKEN=([^;]*)')||[])[2]||'')"
        )
        print(f"    XSRF: {xsrf[:20]}...")

        # ── STEP 3: POST /signup/phone ──
        print(f"\n[3] Submitting phone +1{phone}...")
        phone_result = page.evaluate("""
        async ({phone, email, clientId, redirectUri, xsrf}) => {
            const r = await fetch('/signup/phone', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-xsrf-token': xsrf,
                },
                body: JSON.stringify({
                    phoneNumber: phone,
                    email: email,
                    firstName: 'Test',
                    lastName: 'User',
                    clientId: clientId,
                    redirectUri: redirectUri,
                    responseType: 'code',
                    scope: '*',
                    state: 'test-state',
                    countryCode: 'US',
                })
            });
            const text = await r.text();
            return { status: r.status, body: text };
        }
        """, {"phone": phone, "email": email, "clientId": CLIENT_ID,
              "redirectUri": REDIRECT_URI, "xsrf": xsrf})
        
        status = phone_result.get("status", "?")
        body = phone_result.get("body", "")
        print(f"    Status: {status}")
        print(f"    Body: {body[:200]}")
        
        if status != 200:
            print("    ❌ Phone not accepted!")
            browser.close()
            return

        # ── STEP 4: Poll receive-sms.cc inbox for the verification code ──
        inbox_url = f"https://receive-sms.cc/US-Phone-Number/{phone}/"
        print(f"\n[4] Checking SMS inbox: {inbox_url}")
        print(f"    Waiting for DoorDash verification SMS...")

        code = None
        for attempt in range(30):
            time.sleep(3)
            
            try:
                page.goto(inbox_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1500)
                
                # Extract all text from the page
                page_text = page.evaluate("() => document.body.innerText")
                
                # Look for DoorDash and verification code
                has_dd = "doordash" in page_text.lower() or "door dash" in page_text.lower()
                code = find_code_in_text(page_text)
                
                if has_dd or code:
                    status_icon = "🔥" if code else "📩"
                    print(f"    [{attempt+1:>2}] {status_icon} door={has_dd} code={'***'+code[-3:] if code else 'none'}")
                    
                    if code:
                        print(f"\n    ✅ Verification code: {code}")
                        break
                else:
                    print(f"    [{attempt+1:>2}] ⏳ No DoorDash SMS yet... (page: {len(page_text)} chars)")
                    
            except Exception as e:
                print(f"    [{attempt+1:>2}] ⚠️ {str(e)[:60]}")

        if not code:
            print("\n    ❌ Never received code after 90 seconds")
            browser.close()
            return

        # ── STEP 5: Verify the code ──
        print(f"\n[5] Submitting verification code: {code}")
        
        # Go back to DoorDash
        page.goto(
            f"{IDENTITY}/auth/user/signup"
            f"?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
            f"&response_type=code&scope=*&state=test",
            wait_until="domcontentloaded", timeout=15000
        )
        page.wait_for_timeout(1000)
        
        verify_result = page.evaluate("""
        async ({phone, email, code, clientId, redirectUri, xsrf}) => {
            const r = await fetch('/signup/phone/verify', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-xsrf-token': xsrf,
                },
                body: JSON.stringify({
                    phoneNumber: phone,
                    email: email,
                    otc: code,
                    clientId: clientId,
                    redirectUri: redirectUri,
                    responseType: 'code',
                    scope: '*',
                    state: 'test-state',
                    deviceId: null,
                })
            });
            const text = await r.text();
            return { status: r.status, body: text.substring(0, 500) };
        }
        """, {"phone": phone, "email": email, "code": code,
              "clientId": CLIENT_ID, "redirectUri": REDIRECT_URI, "xsrf": xsrf})
        
        v_status = verify_result.get("status", "?")
        v_body = verify_result.get("body", "")
        print(f"    Status: {v_status}")
        print(f"    Body: {v_body[:200]}")

        if v_status == 403 and "just a moment" in v_body.lower():
            print("    ❌ CF blocked verify endpoint!")
            browser.close()
            return

        # ── STEP 6: Complete signup ──
        print(f"\n[6] Completing signup...")
        continue_result = page.evaluate("""
        async ({phone, email, clientId, redirectUri, xsrf}) => {
            const r = await fetch('/signup/phone/signup_continue', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-xsrf-token': xsrf,
                },
                body: JSON.stringify({
                    phoneNumber: phone,
                    email: email,
                    firstName: 'Test',
                    lastName: 'User',
                    password: 'TestPass123!',
                    clientId: clientId,
                    redirectUri: redirectUri,
                    responseType: 'code',
                    scope: '*',
                    state: 'test-state',
                    disableSeamlessChannel: false,
                    layout: 'consumer_web',
                    countryCode: 'US',
                })
            });
            const text = await r.text();
            return { status: r.status, body: text.substring(0, 500), redirected: r.redirected };
        }
        """, {"phone": phone, "email": email, "clientId": CLIENT_ID,
              "redirectUri": REDIRECT_URI, "xsrf": xsrf})
        
        c_status = continue_result.get("status", "?")
        c_body = continue_result.get("body", "")
        c_redirected = continue_result.get("redirected", False)
        print(f"    Status: {c_status}")
        print(f"    Body: {c_body[:200]}")
        if c_redirected:
            print(f"    🔥 REDIRECTED — signup may have worked!")

        # ── STEP 7: Save everything ──
        print(f"\n[7] Saving session...")
        cookies = ctx.cookies()
        
        # Find identity session
        identity_session = next(
            (c["value"] for c in cookies if c["name"] == "dd-identity-session-id"), None
        )
        
        account = {
            "email": email,
            "phone": f"+1{phone}",
            "password": PASSWORD,
            "verification_code": code,
            "verify_status": v_status,
            "continue_status": c_status,
            "continue_body": c_body,
            "identity_session": identity_session,
            "cookies": [
                {"name": c["name"], "value": c["value"], "domain": c["domain"]}
                for c in cookies
                if any(k in c["name"].lower() for k in ["identity", "session", "auth", "dd-", "xsrf", "token"])
            ],
        }
        
        out_file = OUT / f"account_{phone}.json"
        out_file.write_text(json.dumps(account, indent=2))
        print(f"    Saved: {out_file}")
        
        if c_status == 200:
            print(f"\n🔥 ACCOUNT CREATED!")
            print(f"    Email: {email}")
            print(f"    Password: {PASSWORD}")
            print(f"    Session: {identity_session[:30] if identity_session else 'none'}...")
        elif c_redirected:
            print(f"\n🔥 SIGNUP LIKELY SUCCEEDED (redirect)!")
        elif c_status == 400 and "unexpected error" in c_body.lower():
            print(f"\n⚠️ Signup may have already worked — 400 is sometimes a duplicate error")
        else:
            print(f"\n⚠️ Signup status unclear — check {out_file}")
        
        browser.close()
    
    return account


if __name__ == "__main__":
    result = run()
    if result:
        print(f"\n✅ Done. Account: {result.get('email')}")
