#!/usr/bin/env python3
"""Phase 6: Bootstrap deep analysis, more endpoint fuzzing, timing analysis on auth endpoints."""
import asyncio, json, os, re, time
from urllib.parse import urlencode

OUTPUT_DIR = "/tmp/anthropic-phase6"
os.makedirs(OUTPUT_DIR, exist_ok=True)

FINDINGS = []

async def test_fetch(page, url, method="GET", body=None):
    try:
        body_json = json.dumps(body) if body else "null"
        has_body = body is not None
        if has_body:
            r = await page.evaluate(f"""async () => {{
                const start = performance.now();
                try {{
                    const resp = await fetch('{url}', {{
                        method: '{method}',
                        credentials: 'include',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({body_json})
                    }});
                    const text = await resp.text();
                    return {{status: resp.status, body: text.substring(0, 20000), size: text.length, time: performance.now() - start}};
                }} catch(e) {{ return {{error: e.message}}; }}
            }}""")
        else:
            r = await page.evaluate(f"""async () => {{
                const start = performance.now();
                try {{
                    const resp = await fetch('{url}', {{
                        method: '{method}',
                        credentials: 'include'
                    }});
                    const text = await resp.text();
                    return {{status: resp.status, body: text.substring(0, 20000), size: text.length, time: performance.now() - start}};
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
    # 1. BOOTSTRAP JSON DEEP ANALYSIS
    # =========================================================================
    print("\n" + "="*70)
    print("1. BOOTSTRAP JSON DEEP ANALYSIS")
    print("="*70)

    r = await test_fetch(page, "https://claude.ai/edge-api/bootstrap")
    body = r.get("body", "")

    # Parse incrementally to avoid memory issues
    # Extract key sections using regex
    print(f"   Response size: {r.get('size', 0)} bytes")

    # Find all top-level keys
    top_keys = re.findall(r'"(\w+)":', body[:500])
    print(f"   Top-level keys: {top_keys}")

    # Extract account section
    account_match = re.search(r'"account":\s*(\{[^}]*\}|null)', body)
    if account_match:
        print(f"   Account: {account_match.group(1)}")

    # Extract statsig values
    statsig_values_match = re.search(r'"values":\s*\{([^}]{0,5000})\}', body)
    if statsig_values_match:
        values_str = statsig_values_match.group(1)
        # Find all feature flag keys
        flag_keys = re.findall(r'"([^"]+)":', values_str)
        print(f"\n   Statsig feature flags ({len(flag_keys)} total):")
        for k in flag_keys[:30]:
            print(f"      {k}")

    # Extract growthbook features
    gb_match = re.search(r'"features":\s*\{(.*?)\}\s*\}', body)
    if gb_match:
        gb_str = gb_match.group(1)
        # Find feature IDs
        feat_ids = re.findall(r'"([^"]+)":\s*\{', gb_str)
        print(f"\n   GrowthBook features ({len(feat_ids)} total):")
        for f_id in feat_ids[:30]:
            print(f"      {f_id}")

    # Search for sensitive keywords
    sensitive_keywords = ["key", "secret", "token", "password", "api_key", "auth", "credential", "private", "internal", "admin", "debug", "flag", "feature", "experiment", "beta"]
    print(f"\n   Searching for sensitive keywords in bootstrap response...")
    for kw in sensitive_keywords:
        matches = re.findall(rf'"{kw}[^"]*":\s*"[^"]*"', body, re.IGNORECASE)
        if matches:
            print(f"   🔥 [{kw}] ({len(matches)} matches):")
            for m in matches[:3]:
                print(f"      {m[:120]}")

    # =========================================================================
    # 2. TIMING ANALYSIS — Auth endpoints with session cookie
    # =========================================================================
    print("\n" + "="*70)
    print("2. TIMING ANALYSIS — Auth endpoints")
    print("="*70)

    timing_endpoints = [
        ("login_methods_generic", "https://claude.ai/api/auth/login_methods?email=test@gmail.com&source=claude-ai"),
        ("login_methods_anthropic", "https://claude.ai/api/auth/login_methods?email=admin@anthropic.com&source=claude-ai"),
        ("login_methods_nonexist", "https://claude.ai/api/auth/login_methods?email=nonexist12345@notexist999.com&source=claude-ai"),
        ("gift_validate_normal", "https://claude.ai/api/billing/gift/validate?code=TEST"),
        ("gift_validate_long", "https://claude.ai/api/billing/gift/validate?code=" + "A"*1000),
        ("account_profile", "https://claude.ai/api/account_profile"),
        ("organizations", "https://claude.ai/api/organizations"),
        ("referral", "https://claude.ai/api/referral"),
        ("billing_credits", "https://claude.ai/api/billing/credits"),
        ("bootstrap", "https://claude.ai/edge-api/bootstrap"),
    ]

    timing_results = {}
    for name, url in timing_endpoints:
        times = []
        for _ in range(5):
            r = await test_fetch(page, url)
            t = r.get("time", 0)
            times.append(t)
            await asyncio.sleep(0.1)
        avg = sum(times) / len(times)
        variance = max(times) - min(times)
        timing_results[name] = {"avg_ms": avg, "variance_ms": variance, "min_ms": min(times), "max_ms": max(times)}
        print(f"   {name:30s} → avg={avg:7.1f}ms var={variance:7.1f}ms [{min(times):.1f}-{max(times):.1f}]")

    # =========================================================================
    # 3. MORE ENDPOINT DISCOVERY — Test common admin/internal paths
    # =========================================================================
    print("\n" + "="*70)
    print("3. ADDITIONAL ENDPOINT DISCOVERY")
    print("="*70)

    more_endpoints = [
        # From JS extraction — admin settings
        "/admin-settings",
        "/admin-settings/billing",
        "/admin-settings/members",
        "/admin-settings/roles",
        "/admin-settings/usage",
        "/admin-settings/organization",
        "/admin-settings/data-privacy-controls",
        "/admin-settings/grants",
        "/admin-settings/groups",
        "/admin-settings/directory/submissions",

        # OAuth
        "/oauth/authorize",
        "/oauth/device",
        "/oauth/code/success",

        # Settings
        "/settings/account",
        "/settings/admin",
        "/settings/billing",
        "/settings/features",
        "/settings/identity",
        "/settings/members",
        "/settings/organization",
        "/settings/usage",
        "/settings/privacy",
        "/settings/profile",
        "/settings/team",
        "/settings/cowork",
        "/settings/connectors",
        "/settings/integrations",
        "/settings/capabilities",

        # Gift/Redeem
        "/gift",
        "/gift/redeem",

        # MCP
        "/mcp/playground",
        "/connect/mcp/drive/callback",

        # Code/Artifacts
        "/code/artifact",
        "/code/artifacts",
        "/code/notifications",
        "/code/session",
        "/artifacts",
        "/artifacts/my",

        # Cowork
        "/cowork-artifact",
        "/cowork/project",
        "/cowork/projects",
        "/cowork/projects/create",

        # Team
        "/team/annual",
        "/team/billing",
        "/team/invites",
        "/team/name",
        "/team/pending",

        # Auth
        "/login/app-google-auth",
        "/login/popup-google-auth",
        "/logout/all-sessions",

        # Other
        "/epitaxy/projects/browse",
        "/home/user",
        "/no-organization",
        "/unauthorized",
        "/drive-auth",
        "/create/billing",
        "/create/team",
        "/ccr-agent-proxy-oauth-done",
        "/chats",
        "/chat/new",
        "/chat",
    ]

    for path in more_endpoints:
        url = f"https://claude.ai{path}"
        r = await test_fetch(page, url)
        status = r.get("status", 0)
        body = r.get("body", "")
        size = r.get("size", 0)

        # Only report non-SPA responses
        if "<!doctype html" not in body.lower() or size < 9000:
            print(f"   {path:45s} → {status} | {size:6d} bytes | {body[:80]}")
            FINDINGS.append({"technique": "additional-endpoint", "path": path, "status": status, "body": body[:2000], "size": size})
            with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
                json.dump(FINDINGS, fp, indent=2)
        await asyncio.sleep(0.1)

    # =========================================================================
    # 4. api.anthropic.com — Direct curl tests
    # =========================================================================
    print("\n" + "="*70)
    print("4. api.anthropic.com — Direct tests (via curl from server)")
    print("="*70)

    # These can't be fetched from page context due to CORS, test via subprocess
    import subprocess

    api_tests = [
        ("models", "GET", "https://api.anthropic.com/v1/models"),
        ("me", "GET", "https://api.anthropic.com/v1/me"),
        ("oauth-metadata", "GET", "https://api.anthropic.com/.well-known/oauth-authorization-server"),
        ("mcp-registry", "GET", "https://api.anthropic.com/mcp-registry/v0/servers?version=latest&limit=10"),
        ("register", "POST", "https://api.anthropic.com/register"),
        ("token", "POST", "https://api.anthropic.com/token"),
        ("authorize", "POST", "https://api.anthropic.com/authorize"),
        ("revoke", "POST", "https://api.anthropic.com/revoke"),
    ]

    for name, method, url in api_tests:
        try:
            if method == "GET":
                result = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url], capture_output=True, text=True, timeout=10)
            else:
                result = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", "POST", url, "-H", "Content-Type: application/json", "-d", "{}"], capture_output=True, text=True, timeout=10)
            status = result.stdout.strip()
            print(f"   {name:25s} → {status}")
            FINDINGS.append({"technique": "api-direct", "endpoint": name, "url": url, "status": status})
        except Exception as e:
            print(f"   {name:25s} → ERROR: {e}")
        await asyncio.sleep(0.2)

    # =========================================================================
    # SAVE
    # =========================================================================
    with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
        json.dump(FINDINGS, fp, indent=2)

    with open(f"{OUTPUT_DIR}/timing.json", "w") as fp:
        json.dump(timing_results, fp, indent=2)

    print(f"\n{'='*70}")
    print(f"📊 PHASE 6 COMPLETE — {len(FINDINGS)} findings")
    print(f"{'='*70}")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
