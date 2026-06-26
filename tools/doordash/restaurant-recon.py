#!/usr/bin/env python3
"""
wayback-restaurant-recon.py
Queries Wayback Machine CDX API for restaurant chains, extracts subdomains + endpoints,
then checks origin IPs for Cloudflare bypass opportunities.
"""
import subprocess
import json
import re
import sys
import os
import time
from collections import defaultdict
from urllib.parse import urlparse

OUTPUT_DIR = "/tmp/restaurant-recon"
os.makedirs(OUTPUT_DIR, exist_ok=True)

DOMAINS = [
    "kfc.com",
    "pizzahut.com",
    "swisschalet.com",
    "pizzapizza.ca",
    "timhortons.com",
    "timhortons.ca",
]

def fetch_wayback(domain, limit=10000):
    """Query Wayback CDX API for all archived URLs of a domain."""
    url = f"https://web.archive.org/cdx/search/cdx?url={domain}&matchType=domain&output=json&limit={limit}&fl=urlkey,timestamp,original,mimetype,status"
    print(f"  📡 Querying Wayback for {domain} ...")
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "120", url],
            capture_output=True, text=True, timeout=130
        )
        if result.returncode != 0:
            print(f"    ❌ curl failed: {result.stderr[:200]}")
            return []
        lines = result.stdout.strip().split("\n")
        if len(lines) <= 1:
            print(f"    ⚠️  No results (got {len(lines)} lines)")
            return []
        print(f"    ✅ Got {len(lines)-1} snapshots")
        return lines
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return []

def parse_wayback_results(lines, domain):
    """Parse CDX JSON output into structured subdomain/endpoint data."""
    if not lines or len(lines) < 2:
        return {"subdomains": set(), "endpoints": [], "by_subdomain": defaultdict(set)}
    
    subdomains = set()
    endpoints = []
    by_subdomain = defaultdict(set)
    
    # First line is header
    for line in lines[1:]:
        try:
            parts = json.loads(line)
            if len(parts) < 3:
                continue
            url = parts[2] if len(parts) > 2 else parts[0]
            status = parts[4] if len(parts) > 4 else "?"
            mimetype = parts[3] if len(parts) > 3 else "?"
            
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            path = parsed.path or "/"
            
            # Extract subdomain
            if hostname.endswith(domain):
                subdomains.add(hostname)
                by_subdomain[hostname].add(path)
            
            endpoints.append({
                "url": url,
                "subdomain": hostname,
                "path": path,
                "status": status,
                "mimetype": mimetype
            })
        except:
            continue
    
    return {
        "subdomains": subdomains,
        "endpoints": endpoints,
        "by_subdomain": {k: list(v) for k, v in by_subdomain.items()}
    }

def check_origin_ip(subdomain):
    """Check if a subdomain has an exposed origin IP (not behind Cloudflare)."""
    try:
        # Get IP
        result = subprocess.run(
            ["dig", "+short", subdomain, "A"],
            capture_output=True, text=True, timeout=10
        )
        ips = [ip for ip in result.stdout.strip().split("\n") if ip and not ip.startswith(";")]
        if not ips:
            return {"ip": None, "cloudflare": False, "reachable": False}
        
        ip = ips[0]
        
        # Check if Cloudflare IP range
        cf_ranges = ["104.", "172.64", "172.65", "172.66", "172.67", "172.68", "172.69", "172.70"]
        cf_subnets = ["103.21", "103.22", "103.31", "141.101", "162.158", "173.245", "188.114", "190.93", "197.234", "198.41"]
        is_cf = any(ip.startswith(r) for r in cf_ranges + cf_subnets)
        
        # Try direct HTTPS connection
        reachable = False
        try:
            probe = subprocess.run(
                ["curl", "-sk", "--max-time", "8", "--resolve", f"{subdomain}:443:{ip}", f"https://{subdomain}/"],
                capture_output=True, text=True, timeout=10
            )
            if probe.returncode == 0 and "cloudflare" not in probe.stdout.lower():
                reachable = True
        except:
            pass
        
        return {"ip": ip, "cloudflare": is_cf, "reachable": reachable, "all_ips": ips}
    except Exception as e:
        return {"ip": None, "cloudflare": False, "reachable": False, "error": str(e)}

def main():
    all_findings = {}
    
    print("=" * 70)
    print("🍗 RESTAURANT CHAIN RECON — Wayback Machine + Origin IP Check")
    print("=" * 70)
    
    # PHASE 1: Fetch Wayback data
    print("\n📡 PHASE 1: Fetching Wayback Machine archives...\n")
    for domain in DOMAINS:
        print(f"🔍 {domain}")
        lines = fetch_wayback(domain)
        parsed = parse_wayback_results(lines, domain)
        
        print(f"    Subdomains found: {len(parsed['subdomains'])}")
        print(f"    Endpoints found:  {len(parsed['endpoints'])}")
        
        all_findings[domain] = parsed
    
    # Save Wayback data
    with open(f"{OUTPUT_DIR}/wayback-summary.json", "w") as f:
        summary = {}
        for domain, data in all_findings.items():
            summary[domain] = {
                "subdomains": sorted(list(data["subdomains"])),
                "subdomain_count": len(data["subdomains"]),
                "endpoint_count": len(data["endpoints"]),
                "by_subdomain": {k: v[:20] for k, v in data["by_subdomain"].items()}
            }
        json.dump(summary, f, indent=2)
    
    # PHASE 2: Check origin IPs
    print("\n\n📡 PHASE 2: Checking origin IP exposure...\n")
    
    all_subdomains = set()
    for domain, data in all_findings.items():
        all_subdomains.update(data["subdomains"])
    
    print(f"Total unique subdomains to check: {len(all_subdomains)}\n")
    
    origin_results = {}
    checked = 0
    for subdomain in sorted(all_subdomains):
        checked += 1
        if checked % 10 == 0:
            print(f"  ... {checked}/{len(all_subdomains)} checked ...")
        
        result = check_origin_ip(subdomain)
        origin_results[subdomain] = result
        
        if result.get("reachable"):
            print(f"  🔴 EXPOSED: {subdomain} → {result['ip']} (direct access, no Cloudflare)")
        elif result.get("ip") and not result.get("cloudflare"):
            print(f"  🟡 NON-CF:  {subdomain} → {result['ip']} (not Cloudflare but not confirmed reachable)")
        
        time.sleep(0.3)  # Be polite
    
    # Save origin IP results
    with open(f"{OUTPUT_DIR}/origin-ips.json", "w") as f:
        json.dump(origin_results, f, indent=2)
    
    # PHASE 3: Endpoint analysis
    print("\n\n📡 PHASE 3: Interesting endpoint analysis...\n")
    
    for domain, data in all_findings.items():
        interesting = []
        for ep in data["endpoints"]:
            path = ep["path"].lower()
            # Interesting keywords
            keywords = ["admin", "api", "dev", "stage", "test", "internal", "debug", 
                       "config", "backup", "login", "auth", "upload", "graphql",
                       "swagger", "openapi", "health", "status", "metrics", "env",
                       ".env", "password", "secret", "token", "key", "db", "database",
                       "phpinfo", "console", "jenkins", "kibana", "grafana", "prometheus"]
            for kw in keywords:
                if kw in path:
                    interesting.append(ep)
                    break
        
        if interesting:
            print(f"  🎯 {domain}: {len(interesting)} interesting endpoints")
            for ep in interesting[:10]:
                print(f"     {ep['url'][:100]}")
    
    with open(f"{OUTPUT_DIR}/interesting-endpoints.json", "w") as f:
        json.dump(interesting if 'interesting' in dir() else [], f, indent=2)
    
    # PHASE 4: Subdomain exposure report
    print("\n\n" + "=" * 70)
    print("📊 EXPOSED ORIGIN IPs (no Cloudflare)")
    print("=" * 70)
    
    exposed = {s: r for s, r in origin_results.items() if r.get("reachable")}
    non_cf = {s: r for s, r in origin_results.items() if r.get("ip") and not r.get("cloudflare") and not r.get("reachable")}
    
    if exposed:
        print(f"\n🔴 DIRECTLY EXPOSED ({len(exposed)}):")
        for subdomain, result in sorted(exposed.items()):
            print(f"   {subdomain:50s} → {result['ip']}")
    else:
        print("\n   No subdomains directly exposed.")
    
    if non_cf:
        print(f"\n🟡 NOT CLOUDFLARE ({len(non_cf)}):")
        for subdomain, result in sorted(non_cf.items()):
            print(f"   {subdomain:50s} → {result['ip']}")
    
    # PHASE 5: Subdomain summary per domain
    print("\n\n" + "=" * 70)
    print("📊 SUBDOMAIN SUMMARY PER DOMAIN")
    print("=" * 70)
    
    for domain in DOMAINS:
        data = all_findings[domain]
        subs = sorted(data["subdomains"])
        exposed_for_domain = [s for s in subs if s in exposed]
        non_cf_for_domain = [s for s in subs if s in non_cf]
        
        print(f"\n  🏪 {domain}")
        print(f"     Subdomains: {len(subs)}")
        if exposed_for_domain:
            print(f"     🔴 EXPOSED: {exposed_for_domain}")
        if non_cf_for_domain:
            print(f"     🟡 NOT CF:  {non_cf_for_domain}")
        # Show all subdomains
        for s in subs[:30]:
            marker = "🔴" if s in exposed else ("🟡" if s in non_cf else "  ")
            ip = origin_results.get(s, {}).get("ip", "?")
            cf = origin_results.get(s, {}).get("cloudflare", False)
            cf_mark = "[CF]" if cf else "[  ]"
            print(f"     {marker} {cf_mark} {s:45s} → {ip}")
        if len(subs) > 30:
            print(f"     ... and {len(subs)-30} more subdomains")

    # Save full report
    with open(f"{OUTPUT_DIR}/full-report.json", "w") as f:
        json.dump({
            "wayback": {d: {"subdomains": sorted(list(v["subdomains"]))} for d, v in all_findings.items()},
            "origin_ips": {s: r for s, r in origin_results.items() if r.get("ip")},
            "exposed": {s: r for s, r in exposed.items()},
            "non_cloudflare": {s: r for s, r in non_cf.items()}
        }, f, indent=2)
    
    print(f"\n\n💾 All results saved to {OUTPUT_DIR}/")
    print(f"   wayback-summary.json      — Subdomain + endpoint summary")
    print(f"   origin-ips.json           — Full origin IP check results")
    print(f"   interesting-endpoints.json — API/admin/dev endpoints found")
    print(f"   full-report.json          — Consolidated report")

if __name__ == "__main__":
    main()
