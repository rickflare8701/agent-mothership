#!/usr/bin/env python3
"""
Anthropic API Key Hunter v2
More targeted approach using CloakBrowser to fetch and scan raw content.
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from datetime import datetime

# Key patterns
KEY_PATTERNS = [
    re.compile(r'sk-ant-api03-[A-Za-z0-9_-]{20,}'),
    re.compile(r'sk-ant-[A-Za-z0-9_-]{20,}'),
]

async def fetch_and_scan(page, url, source_name):
    """Fetch URL and scan for API keys"""
    results = []
    
    try:
        print(f"  [{source_name}] Fetching: {url[:80]}...")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        
        # Get raw text content
        content = await page.evaluate("document.body.innerText")
        
        if not content:
            content = await page.content()
        
        # Scan for keys
        for pattern in KEY_PATTERNS:
            found_keys = pattern.findall(content)
            for key in found_keys:
                # Filter out obviously fake/test keys
                if len(key) > 30 and not key.endswith("test") and not key.endswith("example"):
                    results.append({
                        "source": source_name,
                        "url": url,
                        "key": key,
                        "timestamp": datetime.now().isoformat()
                    })
                    print(f"    🔴 KEY FOUND: {key[:40]}...")
        
        # Also look for key patterns in code
        key_patterns = [
            r'api[_-]?key\s*[:=]\s*["\']([^"\']+)["\']',
            r'ANTHROPIC_API_KEY\s*[:=]\s*["\']([^"\']+)["\']',
            r'x-api-key\s*[:=]\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in key_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if match.startswith("sk-ant"):
                    results.append({
                        "source": source_name,
                        "url": url,
                        "key": match,
                        "type": "code_leak",
                        "timestamp": datetime.now().isoformat()
                    })
                    print(f"    🔴 CODE LEAK FOUND: {match[:40]}...")
        
    except Exception as e:
        print(f"  [{source_name}] Error: {e}")
    
    return results

async def search_github_raw(page, query):
    """Search GitHub and fetch raw file content"""
    results = []
    
    try:
        # Search GitHub
        search_url = f"https://github.com/search?q={query}&type=code"
        print(f"  [GitHub] Searching: {query}")
        
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        # Extract file links from search results
        content = await page.content()
        file_pattern = re.compile(r'href="(/[^/]+/[^/]+/blob/[^"]+)"')
        file_links = file_pattern.findall(content)[:10]  # Limit to 10
        
        for link in file_links:
            # Convert to raw URL
            raw_url = f"https://raw.githubusercontent.com{link.replace('/blob/', '/raw/')}"
            
            # Fetch raw content
            page_result = await fetch_and_scan(page, raw_url, "github_raw")
            results.extend(page_result)
            
            await asyncio.sleep(1)  # Rate limiting
        
    except Exception as e:
        print(f"  [GitHub] Error: {e}")
    
    return results

async def search_gist(page):
    """Search GitHub Gists for leaked keys"""
    results = []
    
    try:
        # Search for public gists
        search_url = "https://gist.github.com/search?q=sk-ant-api03"
        print(f"  [Gist] Searching for API keys...")
        
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        content = await page.content()
        
        # Extract gist links
        gist_pattern = re.compile(r'href="(/[a-f0-9]+)"')
        gist_links = gist_pattern.findall(content)[:10]
        
        for gist_id in gist_links:
            # Fetch gist raw content
            raw_url = f"https://gist.githubusercontent.com{gist_id}/raw"
            
            page_result = await fetch_and_scan(page, raw_url, "gist")
            results.extend(page_result)
            
            await asyncio.sleep(1)
        
    except Exception as e:
        print(f"  [Gist] Error: {e}")
    
    return results

async def search_pastebin_raw(page):
    """Search Pastebin for raw paste content"""
    results = []
    
    try:
        # Search for recent pastes via Google
        search_url = "https://www.google.com/search?q=site:pastebin.com+%22sk-ant-api03%22"
        print(f"  [Pastebin] Searching for API keys...")
        
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        content = await page.content()
        
        # Extract paste links
        paste_pattern = re.compile(r'https://pastebin\.com/([A-Za-z0-9]+)')
        paste_ids = paste_pattern.findall(content)[:10]
        
        for paste_id in set(paste_ids):  # Deduplicate
            # Fetch raw paste
            raw_url = f"https://pastebin.com/raw/{paste_id}"
            
            page_result = await fetch_and_scan(page, raw_url, "pastebin")
            results.extend(page_result)
            
            await asyncio.sleep(1)
        
    except Exception as e:
        print(f"  [Pastebin] Error: {e}")
    
    return results

async def search_env_files(page):
    """Search for exposed .env files"""
    results = []
    
    dorks = [
        'site:github.com ".env" "ANTHROPIC_API_KEY"',
        'site:gitlab.com ".env" "ANTHROPIC_API_KEY"',
        'site:bitbucket.org ".env" "ANTHROPIC_API_KEY"',
        'site:herokuapp.com ".env" "ANTHROPIC_API_KEY"',
        'site:netlify.app ".env" "ANTHROPIC_API_KEY"',
        'site:vercel.app ".env" "ANTHROPIC_API_KEY"',
        'site:github.com ".env.local" "sk-ant"',
        'site:github.com ".env.production" "sk-ant"',
        'site:github.com ".env.development" "sk-ant"',
    ]
    
    for dork in dorks:
        try:
            print(f"  [Google] Searching: {dork[:50]}...")
            url = f"https://www.google.com/search?q={dork}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            
            content = await page.content()
            
            # Extract result URLs
            result_pattern = re.compile(r'href="(https?://[^"]+)"')
            found_urls = result_pattern.findall(content)
            
            for found_url in found_urls[:5]:
                if "google" not in found_url and "gstatic" not in found_url:
                    # Try to fetch the raw file
                    if "github.com" in found_url:
                        # Convert to raw URL
                        if "/blob/" in found_url:
                            raw_url = found_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/raw/")
                            page_result = await fetch_and_scan(page, raw_url, "env_file")
                            results.extend(page_result)
                    
                    await asyncio.sleep(1)
            
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"  [Google] Error: {e}")
    
    return results

async def search_stackoverflow(page):
    """Search Stack Overflow for leaked keys"""
    results = []
    
    try:
        search_url = "https://stackoverflow.com/search?q=sk-ant-api03"
        print(f"  [StackOverflow] Searching for API keys...")
        
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        content = await page.content()
        
        # Extract question links
        question_pattern = re.compile(r'href="/questions/(\d+)"')
        question_ids = question_pattern.findall(content)[:10]
        
        for qid in question_ids:
            # Fetch question page
            url = f"https://stackoverflow.com/questions/{qid}"
            page_result = await fetch_and_scan(page, url, "stackoverflow")
            results.extend(page_result)
            
            await asyncio.sleep(1)
        
    except Exception as e:
        print(f"  [StackOverflow] Error: {e}")
    
    return results

async def main():
    print("=" * 60)
    print("ANTHROPIC API KEY HUNTER v2")
    print("Targeted search for leaked sk-ant-api03* keys")
    print("=" * 60)
    
    try:
        from cloakbrowser import launch_async
        browser = await launch_async(headless=True)
        context = await browser.new_context()
        
        all_results = []
        keys_found = []
        
        # 1. Search GitHub raw files
        print("\n[1/6] Searching GitHub raw files...")
        page = await context.new_page()
        results = await search_github_raw(page, "sk-ant-api03")
        all_results.extend(results)
        keys_found.extend([r for r in results if r.get("key")])
        await page.close()
        
        # 2. Search Gists
        print("\n[2/6] Searching GitHub Gists...")
        page = await context.new_page()
        results = await search_gist(page)
        all_results.extend(results)
        keys_found.extend([r for r in results if r.get("key")])
        await page.close()
        
        # 3. Search Pastebin
        print("\n[3/6] Searching Pastebin...")
        page = await context.new_page()
        results = await search_pastebin_raw(page)
        all_results.extend(results)
        keys_found.extend([r for r in results if r.get("key")])
        await page.close()
        
        # 4. Search .env files
        print("\n[4/6] Searching exposed .env files...")
        page = await context.new_page()
        results = await search_env_files(page)
        all_results.extend(results)
        keys_found.extend([r for r in results if r.get("key")])
        await page.close()
        
        # 5. Search Stack Overflow
        print("\n[5/6] Searching Stack Overflow...")
        page = await context.new_page()
        results = await search_stackoverflow(page)
        all_results.extend(results)
        keys_found.extend([r for r in results if r.get("key")])
        await page.close()
        
        # 6. Search Wayback Machine
        print("\n[6/6] Searching Wayback Machine...")
        page = await context.new_page()
        wayback_url = "https://web.archive.org/cdx/search/cdx?url=*&output=json&limit=100&fl=urlkey,timestamp,original&filter=mimetype:text&query=sk-ant-api03"
        await page.goto(wayback_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        content = await page.content()
        # Parse CDX response and scan each URL
        if content:
            url_pattern = re.compile(r'https?://[^\s"<>]+')
            found_urls = url_pattern.findall(content)
            
            for url in found_urls[:20]:
                if "sk-ant" in url.lower():
                    page_result = await fetch_and_scan(page, url, "wayback")
                    all_results.extend(page_result)
                    keys_found.extend([r for r in page_result if r.get("key")])
                    await asyncio.sleep(1)
        
        await page.close()
        
        # Save all results
        output_file = Path("/tmp/anthropic-key-hunter-v2-results.json")
        with open(output_file, "w") as f:
            json.dump(all_results, f, indent=2)
        
        # Save found keys
        keys_file = Path("/tmp/anthropic-keys-found-v2.txt")
        with open(keys_file, "w") as f:
            for key in keys_found:
                f.write(f"{key.get('key', '')}\n{key.get('url', '')}\n\n")
        
        print("\n" + "=" * 60)
        print(f"SCAN COMPLETE")
        print(f"Total results: {len(all_results)}")
        print(f"API keys found: {len(keys_found)}")
        print(f"Results saved to: {output_file}")
        print(f"Keys saved to: {keys_file}")
        print("=" * 60)
        
        if keys_found:
            print("\n🔴 API KEYS FOUND:")
            seen = set()
            for key in keys_found:
                k = key.get('key', '')
                if k and k not in seen:
                    seen.add(k)
                    print(f"  - {k}")
                    print(f"    Source: {key.get('url', 'N/A')}")
        
        await browser.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
