#!/usr/bin/env python3
"""
Anthropic API Key Hunter
Uses CloakBrowser to search for leaked sk-ant-api03* keys across multiple sources.
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from datetime import datetime

# Key patterns to search for
KEY_PATTERNS = [
    r'sk-ant-api03-[A-Za-z0-9_-]{20,}',
    r'sk-ant-[A-Za-z0-9_-]{20,}',
    r'ANTHROPIC_API_KEY["\s:=]+["\']?sk-ant',
    r'x-api-key["\s:=]+["\']?sk-ant',
    r'api[_-]?key["\s:=]+["\']?sk-ant',
    r'["\']sk-ant-api03[A-Za-z0-9_-]{20,}["\']',
]

# Search sources
SOURCES = {
    "wayback": "https://web.archive.org/cdx/search/cdx",
    "github": "https://github.com/search",
    "pastebin": "https://pastebin.com",
    "gist": "https://gist.github.com",
}

async def search_wayback(page, domain=None, keyword=None):
    """Search Wayback Machine CDX API for archived pages"""
    results = []
    
    # Search for API keys in archived pages
    queries = [
        "sk-ant-api03",
        "anthropic api key",
        "ANTHROPIC_API_KEY",
        "x-api-key sk-ant",
    ]
    
    if keyword:
        queries.append(keyword)
    
    for query in queries:
        try:
            # CDX API search
            url = f"https://web.archive.org/cdx/search/cdx?url=*&output=json&limit=50&fl=urlkey,timestamp,original&filter=mimetype:text&filter=statuscode:200&matchType=domain&query={query}"
            
            print(f"  [Wayback] Searching: {query}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            content = await page.content()
            
            # Parse CDX response
            if content and "[]" not in content:
                # Try to extract URLs
                url_pattern = re.compile(r'https?://[^\s"<>]+', re.IGNORECASE)
                found_urls = url_pattern.findall(content)
                
                for found_url in found_urls[:20]:  # Limit to 20
                    if "sk-ant" in found_url.lower() or "api" in found_url.lower():
                        results.append({
                            "source": "wayback",
                            "query": query,
                            "url": found_url,
                            "type": "url_in_response"
                        })
            
            await asyncio.sleep(2)  # Rate limiting
            
        except Exception as e:
            print(f"  [Wayback] Error: {e}")
    
    return results

async def search_github(page, query="sk-ant-api03"):
    """Search GitHub for leaked keys"""
    results = []
    
    try:
        # GitHub code search
        search_url = f"https://github.com/search?q={query}&type=code"
        print(f"  [GitHub] Searching: {query}")
        
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        content = await page.content()
        
        # Extract code results
        code_pattern = re.compile(r'sk-ant-api03[A-Za-z0-9_-]{20,}', re.IGNORECASE)
        found_keys = code_pattern.findall(content)
        
        for key in found_keys:
            results.append({
                "source": "github",
                "query": query,
                "key": key,
                "type": "api_key_found"
            })
        
        # Also search for .env files
        env_url = f"https://github.com/search?q=.env+anthropic+api+key&type=code"
        await page.goto(env_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        content = await page.content()
        found_keys = code_pattern.findall(content)
        
        for key in found_keys:
            results.append({
                "source": "github",
                "query": ".env anthropic api key",
                "key": key,
                "type": "api_key_found"
            })
        
    except Exception as e:
        print(f"  [GitHub] Error: {e}")
    
    return results

async def search_pastebin(page):
    """Search Pastebin for leaked keys"""
    results = []
    
    try:
        # Search for recent pastes
        print(f"  [Pastebin] Searching for API keys...")
        
        # Search for Anthropic-related pastes
        search_terms = [
            "anthropic api key",
            "sk-ant-api03",
            "ANTHROPIC_API_KEY",
            "claude api key",
        ]
        
        for term in search_terms:
            try:
                # Use Pastebin search (via Google site search)
                url = f"https://www.google.com/search?q=site:pastebin.com+{term}"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                
                content = await page.content()
                
                # Extract paste URLs
                url_pattern = re.compile(r'https://pastebin\.com/[A-Za-z0-9]+')
                found_urls = url_pattern.findall(content)
                
                for paste_url in found_urls[:5]:  # Limit to 5
                    results.append({
                        "source": "pastebin",
                        "query": term,
                        "url": paste_url,
                        "type": "paste_found"
                    })
                
            except Exception as e:
                print(f"  [Pastebin] Error searching '{term}': {e}")
            
            await asyncio.sleep(2)
        
    except Exception as e:
        print(f"  [Pastebin] Error: {e}")
    
    return results

async def search_npm_pypi(page):
    """Search npm and PyPI for leaked keys in packages"""
    results = []
    
    try:
        # Search npm
        print(f"  [npm] Searching for API keys...")
        npm_url = "https://www.npmjs.com/search?q=anthropic%20api%20key"
        await page.goto(npm_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        content = await page.content()
        
        # Extract package names
        package_pattern = re.compile(r'href="/package/([^"]+)"')
        packages = package_pattern.findall(content)[:10]
        
        for package in packages:
            results.append({
                "source": "npm",
                "package": package,
                "type": "package_found"
            })
        
        # Search PyPI
        print(f"  [PyPI] Searching for API keys...")
        pypi_url = "https://pypi.org/search/?q=anthropic+api+key"
        await page.goto(pypi_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        content = await page.content()
        
        # Extract package names
        package_pattern = re.compile(r'href="/project/([^/]+)/')
        packages = package_pattern.findall(content)[:10]
        
        for package in packages:
            results.append({
                "source": "pypi",
                "package": package,
                "type": "package_found"
            })
        
    except Exception as e:
        print(f"  [npm/PyPI] Error: {e}")
    
    return results

async def search_virustotal(page):
    """Search VirusTotal for URLs containing API keys"""
    results = []
    
    try:
        print(f"  [VirusTotal] Searching for API keys...")
        
        # Search for URLs containing sk-ant
        url = "https://www.virustotal.com/graph/search?q=sk-ant-api03"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        
        content = await page.content()
        
        # Extract URLs
        url_pattern = re.compile(r'https?://[^\s"<>]+sk-ant[^\s"<>]+', re.IGNORECASE)
        found_urls = url_pattern.findall(content)
        
        for found_url in found_urls[:10]:
            results.append({
                "source": "virustotal",
                "url": found_url,
                "type": "url_with_key"
            })
        
    except Exception as e:
        print(f"  [VirusTotal] Error: {e}")
    
    return results

async def search_google_dorks(page):
    """Search Google dorks for leaked keys"""
    results = []
    
    dorks = [
        '"sk-ant-api03" filetype:env',
        '"sk-ant-api03" filetype:txt',
        '"sk-ant-api03" filetype:json',
        '"sk-ant-api03" filetype:yml',
        '"sk-ant-api03" filetype:yaml',
        '"sk-ant-api03" filetype:conf',
        '"sk-ant-api03" filetype:cfg',
        '"sk-ant-api03" filetype:ini',
        '"sk-ant-api03" filetype:log',
        '"ANTHROPIC_API_KEY" filetype:env',
        '"x-api-key" "sk-ant"',
        '"anthropic" "api_key" "sk-ant"',
        'site:github.com "sk-ant-api03"',
        'site:gitlab.com "sk-ant-api03"',
        'site:bitbucket.org "sk-ant-api03"',
        'site:pastebin.com "sk-ant-api03"',
        'site:gist.github.com "sk-ant-api03"',
        'site:npmjs.com "sk-ant-api03"',
        'site:pypi.org "sk-ant-api03"',
        'site:stackoverflow.com "sk-ant-api03"',
        'site:reddit.com "sk-ant-api03"',
        'site:hastebin.com "sk-ant-api03"',
        'site:ghostbin.com "sk-ant-api03"',
        'site:dpaste.org "sk-ant-api03"',
        'site:codepen.io "sk-ant-api03"',
        'site:jsfiddle.net "sk-ant-api03"',
        'site:repl.it "sk-ant-api03"',
        'site:glitch.com "sk-ant-api03"',
    ]
    
    for dork in dorks:
        try:
            print(f"  [Google] Dorking: {dork[:50]}...")
            url = f"https://www.google.com/search?q={dork}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            
            content = await page.content()
            
            # Extract results
            result_pattern = re.compile(r'href="(https?://[^"]+)"')
            found_urls = result_pattern.findall(content)
            
            for found_url in found_urls[:5]:  # Limit to 5
                if "google" not in found_url and "gstatic" not in found_url:
                    results.append({
                        "source": "google_dorks",
                        "dork": dork,
                        "url": found_url,
                        "type": "dork_result"
                    })
            
            await asyncio.sleep(2)  # Rate limiting
            
        except Exception as e:
            print(f"  [Google] Error: {e}")
    
    return results

async def main():
    print("=" * 60)
    print("ANTHROPIC API KEY HUNTER")
    print("=" * 60)
    
    try:
        from cloakbrowser import launch_async
        browser = await launch_async(headless=True)
        context = await browser.new_context()
        
        all_results = []
        
        # 1. Search Wayback Machine
        print("\n[1/6] Searching Wayback Machine...")
        page = await context.new_page()
        results = await search_wayback(page)
        all_results.extend(results)
        print(f"  Found: {len(results)} results")
        await page.close()
        
        # 2. Search GitHub
        print("\n[2/6] Searching GitHub...")
        page = await context.new_page()
        results = await search_github(page)
        all_results.extend(results)
        print(f"  Found: {len(results)} results")
        await page.close()
        
        # 3. Search Pastebin
        print("\n[3/6] Searching Pastebin...")
        page = await context.new_page()
        results = await search_pastebin(page)
        all_results.extend(results)
        print(f"  Found: {len(results)} results")
        await page.close()
        
        # 4. Search npm/PyPI
        print("\n[4/6] Searching npm/PyPI...")
        page = await context.new_page()
        results = await search_npm_pypi(page)
        all_results.extend(results)
        print(f"  Found: {len(results)} results")
        await page.close()
        
        # 5. Search VirusTotal
        print("\n[5/6] Searching VirusTotal...")
        page = await context.new_page()
        results = await search_virustotal(page)
        all_results.extend(results)
        print(f"  Found: {len(results)} results")
        await page.close()
        
        # 6. Search Google Dorks
        print("\n[6/6] Searching Google Dorks...")
        page = await context.new_page()
        results = await search_google_dorks(page)
        all_results.extend(results)
        print(f"  Found: {len(results)} results")
        await page.close()
        
        # Save results
        output_file = Path("/tmp/anthropic-key-hunter-results.json")
        with open(output_file, "w") as f:
            json.dump(all_results, f, indent=2)
        
        print("\n" + "=" * 60)
        print(f"COMPLETE: {len(all_results)} total results")
        print(f"Results saved to: {output_file}")
        print("=" * 60)
        
        # Extract actual keys
        keys = [r for r in all_results if r.get("type") == "api_key_found"]
        if keys:
            print("\n🔴 API KEYS FOUND:")
            for key in keys:
                print(f"  - {key['key']}")
        
        # Save to keys file
        keys_file = Path("/tmp/anthropic-keys-found.txt")
        with open(keys_file, "w") as f:
            for key in keys:
                f.write(f"{key['key']}\n")
        
        await browser.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
