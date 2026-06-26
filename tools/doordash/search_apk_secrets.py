#!/usr/bin/env python3
"""Deep search DoorDash APK for third-party secrets."""
import os, re, json
from pathlib import Path

BASE = '/tmp/dd-apk/decompiled'

# ── Secret patterns ──
PATTERNS = {
    # AWS
    'aws_access_key': r'(?:AKIA|ASIA)[A-Z0-9]{16}',
    'aws_secret_key': r'aws[_]?(?:secret|session)[\"\'\s:=]+([A-Za-z0-9+/]{40})',
    'aws_account': r'aws[_]?account[_]?id[\"\'\s:=]+(\d{12})',
    's3_bucket': r'(?:s3://|s3\.amazonaws\.com/)([a-z0-9][a-z0-9.-]{2,62})',

    # Stripe
    'stripe_publishable': r'(?:pk_live_|pk_test_)[a-zA-Z0-9]{24,99}',
    'stripe_secret': r'(?:sk_live_|sk_test_)[a-zA-Z0-9]{24,99}',
    'stripe_wh': r'whsec_[a-zA-Z0-9]{32}',

    # Branch.io
    'branch_key': r'(?:key_live_|key_test_)[a-zA-Z0-9_\-]{30,60}',
    'branch_secret': r'(?:secret_live_|secret_test_)[a-zA-Z0-9_\-]{30,60}',

    # Firebase
    'firebase_project': r'project[_]?id[\"\'\s:=]+([a-z][a-z0-9-]{4,30})',
    'firebase_app_id': r'(?:1:\d+:(?:android|ios|web):[a-f0-9]+)',

    # Amplitude
    'amplitude_key': r'amplitude[\"\'\s:=]*api[_]?key[\"\'\s:=]+([a-f0-9]{32})',

    # Intercom
    'intercom_app_id': r'intercom.*?(?:app[_]?id|api[_]?key)[\"\'\s:=]+([a-zA-Z0-9]{10,40})',

    # Mixpanel
    'mixpanel_token': r'mixpanel.*?token[\"\'\s:=]+([a-f0-9]{32})',

    # Segment
    'segment_write_key': r'segment.*?(?:write[_]?key)[\"\'\s:=]+([a-zA-Z0-9]{20,40})',

    # Sentry
    'sentry_dsn': r'(?:https?://[a-f0-9]{32}@sentry\.io/\d+)',

    # Datadog
    'datadog_key': r'datadog.*?(?:api[_]?key|client[_]?token)[\"\'\s:=]+([a-f0-9]{32})',

    # Auth0
    'auth0_domain': r'auth0.*?domain[\"\'\s:=]+([a-zA-Z0-9][a-zA-Z0-9.-]{5,40}\.auth0\.com)',
    'auth0_client': r'auth0.*?client[_]?id[\"\'\s:=]+([a-zA-Z0-9]{32})',

    # Okta
    'okta_domain': r'okta.*?domain[\"\'\s:=]+([a-zA-Z0-9][a-zA-Z0-9.-]{5,40}\.okta\.com)',

    # Generic secrets in config files
    'generic_key': r'(?:api[_]?key|api[_]?secret|app[_]?secret|client[_]?secret)[\"\'\s:=]+([a-zA-Z0-9_\-+/=]{20,100})',

    # Internal IPs / hosts
    'internal_host': r'(?:internal|private|staging|dev|sandbox)[a-z0-9-]*\.doordash\.com',
}

# File extensions to scan
EXTS = {'.xml', '.json', '.smali', '.txt', '.properties', '.yml', '.yaml', '.js', '.java', '.kt'}

all_finds = {}

file_count = 0
for root, dirs, files in os.walk(BASE):
    for fn in files:
        ext = os.path.splitext(fn)[1].lower()
        if ext not in EXTS:
            continue
        fpath = os.path.join(root, fn)
        try:
            with open(fpath, 'r', errors='ignore') as f:
                content = f.read()
        except:
            continue
        file_count += 1

        rel = os.path.relpath(fpath, BASE)

        for name, pat in PATTERNS.items():
            matches = re.findall(pat, content, re.IGNORECASE | re.MULTILINE)
            if matches:
                for m in matches:
                    val = m.strip() if isinstance(m, str) else m[0].strip() if isinstance(m, tuple) else str(m).strip()
                    if len(val) < 4:
                        continue
                    if name not in all_finds:
                        all_finds[name] = []
                    all_finds[name].append((val, rel[:80]))

print(f"Scanned {file_count} files\n")

# Print findings grouped by category
for cat in ['aws', 'stripe', 'branch', 'firebase', 'amplitude', 'intercom', 'mixpanel', 'segment', 'sentry', 'datadog', 'auth0', 'okta', 'generic', 'internal']:
    cat_finds = {k: v for k, v in all_finds.items() if k.startswith(cat) or cat in k}
    if not cat_finds:
        continue
    print(f"\n{'='*60}")
    print(f"  {cat.upper()}")
    print(f"{'='*60}")
    for name, entries in cat_finds.items():
        # Deduplicate by value
        seen = set()
        for val, loc in entries:
            if val not in seen:
                seen.add(val)
                print(f"\n  [{name}] ({len(seen)} found)")
                print(f"    Value: {val[:120]}")
                print(f"    File:  {loc[:100]}")
                if len(seen) >= 5:
                    print(f"    ... and {len(entries) - len(seen)} more")
                    break

# Also dump to file
with open('/tmp/dd-apk/secrets.txt', 'w') as f:
    for name, entries in all_finds.items():
        f.write(f'\n[{name}] ({len(entries)} matches)\n')
        seen = set()
        for val, loc in entries:
            if val not in seen:
                seen.add(val)
                f.write(f'  {val}  |  {loc}\n')
                if len(seen) >= 10:
                    f.write(f'  ... and {len(entries) - len(seen)} more\n')
                    break

print(f"\n\nFull report: /tmp/dd-apk/secrets.txt")
