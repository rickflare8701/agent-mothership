#!/usr/bin/env python3
"""Decompile DoorDash APK and extract API endpoints, secrets, client IDs."""
import subprocess, os, re

os.chdir('/tmp/dd-apk')

# 1. Install apktool
r = subprocess.run(['which', 'apktool'], capture_output=True, text=True)
if r.returncode != 0:
    print('[1] Installing apktool...')
    subprocess.run(['apt-get', 'update', '-qq'], capture_output=True)
    subprocess.run(['apt-get', 'install', '-y', '-qq', 'apktool'], capture_output=True)
    print('    Done')

# 2. Decompile APK
print('[2] Decompiling APK (this takes ~2 min)...')
result = subprocess.run(
    ['apktool', 'd', '-f', '-o', 'decompiled', 'doordash.apk'],
    capture_output=True, text=True, timeout=300
)
print(result.stdout[-500:] if result.stdout else '')
if result.stderr:
    print('STDERR:', result.stderr[-300:])

print(f'\n[3] Directory sizes:')
subprocess.run(['du', '-sh', 'decompiled/'], text=True)

# 3. Extract key files
print('\n[4] Searching for secrets...')

patterns = {
    'client_id': r'(client[_]?id["' + "'" + r':\s]*)([a-zA-Z0-9_\-]{10,50})',
    'api_key': r'(api[_]?key["' + "'" + r':\s]*)([a-zA-Z0-9_\-]{10,50})',
    'scope': r'(scope["' + "'" + r':\s]*)([a-zA-Z0-9_\-*]{3,30})',
    'base_url': r'(base[_]?url["' + "'" + r':\s]*)(https?://[^\s"\'<>\[\]]{5,80})',
    'redirect_uri': r'(redirect[_]?uri["' + "'" + r':\s]*)(https?://[^\s"\'<>\[\]]{5,80})',
}

extensions = {'.xml', '.json', '.smali', '.txt', '.properties', '.yml', '.yaml', '.js'}

all_findings = {}

for root, dirs, files in os.walk('decompiled'):
    for fn in files:
        ext = os.path.splitext(fn)[1].lower()
        if ext not in extensions:
            continue
        fpath = os.path.join(root, fn)
        try:
            with open(fpath, 'r', errors='ignore') as f:
                content = f.read()
        except:
            continue

        for name, pat in patterns.items():
            matches = re.findall(pat, content, re.IGNORECASE)
            if matches:
                key = f"{name} ({os.path.relpath(fpath)})"
                vals = set()
                for m in matches:
                    val = m[1] if isinstance(m, tuple) else m
                    vals.add(val)
                if key not in all_findings:
                    all_findings[key] = set()
                all_findings[key].update(vals)

print(f'\n[5] Findings ({len(all_findings)} files with matches):')
with open('/tmp/dd-apk/findings.txt', 'w') as out:
    for loc, vals in sorted(all_findings.items()):
        print(f'\n--- {loc} ---')
        out.write(f'\n--- {loc} ---\n')
        for v in sorted(vals)[:5]:
            print(f'    {v}')
            out.write(f'    {v}\n')

# 6. Quick grep for doordash domains
print('\n[6] Domain grep:')
r = subprocess.run(
    ['grep', '-rohP', r'https?://[a-zA-Z0-9._-]*\.?doordash\.com[a-zA-Z0-9._\-/]*', 'decompiled/'],
    capture_output=True, text=True, timeout=60
)
urls = set(r.stdout.strip().split('\n')) if r.stdout else set()
print(f'    Found {len(urls)} unique doordash URLs')
with open('/tmp/dd-apk/urls.txt', 'w') as f:
    for u in sorted(urls)[:100]:
        print(f'    {u}')
        f.write(u + '\n')

print('\nDone!')
