#!/usr/bin/env python3
"""Phase 7: Full OAuth flow test with PKCE."""
import asyncio, json, os, hashlib, base64, secrets

OUTPUT_DIR = "/tmp/anthropic-phase7"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CLIENT_ID = "48b99b32-62ba-47ff-9e53-534d86f3dc5d"
CLIENT_SECRET = "a612021aede865f5c843e0c0d805549b8b3a6789c60f151c6c9c7621fb1c364c"
REDIRECT_URI = "http://localhost"

async def main():
    from cloakbrowser import launch_async
    browser = await launch_async(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    # Generate PKCE
    code_verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')

    print(f"code_verifier: {code_verifier}")
    print(f"code_challenge: {code_challenge}")

    # Step 1: Visit authorization URL
    auth_url = f"https://api.anthropic.com/authorize?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope=openid+profile+email+admin&code_challenge={code_challenge}&code_challenge_method=S256"

    print(f"\n🌐 Step 1: Visiting authorization URL...")
    print(f"   {auth_url}")

    # Capture redirects
    redirects = []
    async def handle_response(response):
        redirects.append({"url": response.url, "status": response.status})
    page.on("response", handle_response)

    try:
        await page.goto(auth_url, wait_until="networkidle", timeout=30000)
    except:
        pass

    await asyncio.sleep(3)

    print(f"\n   Current URL: {page.url}")
    print(f"   Redirects captured: {len(redirects)}")

    for r in redirects:
        print(f"      {r['status']} {r['url'][:120]}")

    # Check page content
    content = await page.content()
    if "login" in content.lower():
        print("\n   🔥 Login page detected!")
    if "consent" in content.lower():
        print("\n   🔥 Consent page detected!")
    if "authorize" in content.lower():
        print("\n   🔥 Authorization page detected!")

    # Extract any interesting content
    title = await page.title()
    print(f"   Page title: {title}")

    # Take screenshot description
    text_content = await page.evaluate("() => document.body?.innerText?.substring(0, 2000) || ''")
    print(f"   Page text: {text_content[:500]}")

    # Step 2: Try with redirect to our server (if we had one)
    print(f"\n🌐 Step 2: Test with different redirect URIs...")
    test_uris = [
        "http://localhost",
        "http://localhost:3000",
        "http://127.0.0.1",
        "http://attacker.com",
        "https://evil.com/callback",
        "javascript:alert(1)",
    ]

    for uri in test_uris:
        # Register new client with this redirect URI
        import subprocess
        result = subprocess.run([
            "curl", "-s", "-X", "POST", "https://api.anthropic.com/register",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"client_name": "test", "redirect_uris": [uri]})
        ], capture_output=True, text=True, timeout=10)

        try:
            reg = json.loads(result.stdout)
            cid = reg.get("client_id", "")
            print(f"   redirect_uri={uri:40s} → client_id={cid}")
        except:
            print(f"   redirect_uri={uri:40s} → ERROR: {result.stdout[:100]}")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
