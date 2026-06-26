#!/usr/bin/env python3
"""Phase 3: Intercept all network requests from claude.ai to discover API endpoints."""
import asyncio, json, os

OUTPUT_DIR = "/tmp/anthropic-idor-phase3"
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def main():
    from cloakbrowser import launch_async
    browser = await launch_async(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    api_calls = []

    # Intercept all requests
    async def handle_request(route, request):
        url = request.url
        if any(d in url for d in ["claude.ai", "anthropic.com", "segment", "statsig", "launchdarkly", "sentry", "posthog", "amplitude"]):
            api_calls.append({
                "url": url,
                "method": request.method,
                "headers": dict(request.headers),
                "post_data": request.post_data
            })
        await route.continue_()

    await context.route("**/*", handle_request)

    print("🌐 Loading claude.ai and intercepting requests...")
    await page.goto("https://claude.ai", wait_until="networkidle", timeout=60000)
    await asyncio.sleep(5)

    # Try navigating to different pages
    for path in ["/login", "/new", "/settings", "/organizations", "/pricing"]:
        try:
            await page.goto(f"https://claude.ai{path}", wait_until="networkidle", timeout=15000)
            await asyncio.sleep(2)
        except:
            pass

    print(f"\n📊 Captured {len(api_calls)} API calls:")

    # Filter and categorize
    anthropic_calls = [c for c in api_calls if "anthropic" in c["url"] and "segment" not in c["url"] and "sentry" not in c["url"]]
    segment_calls = [c for c in api_calls if "segment" in c["url"] or "a-api" in c["url"]]
    other_calls = [c for c in api_calls if c not in anthropic_calls and c not in segment_calls]

    print(f"\n🔵 Anthropic calls: {len(anthropic_calls)}")
    for c in anthropic_calls:
        print(f"   {c['method']:6s} {c['url'][:100]}")
        if c.get('post_data'):
            print(f"         Body: {str(c['post_data'])[:200]}")

    print(f"\n🟡 Segment calls: {len(segment_calls)}")
    for c in segment_calls[:10]:
        print(f"   {c['method']:6s} {c['url'][:100]}")

    print(f"\n⚪ Other calls: {len(other_calls)}")
    for c in other_calls[:10]:
        print(f"   {c['method']:6s} {c['url'][:100]}")

    # Save all
    with open(f"{OUTPUT_DIR}/all-calls.json", "w") as fp:
        json.dump(api_calls, fp, indent=2, default=str)

    with open(f"{OUTPUT_DIR}/anthropic-calls.json", "w") as fp:
        json.dump(anthropic_calls, fp, indent=2, default=str)

    # Extract unique API paths
    import re
    paths = set()
    for c in anthropic_calls:
        parsed = re.match(r'https?://([^/]+)(/.*)', c["url"])
        if parsed:
            host = parsed.group(1)
            path = parsed.group(2).split("?")[0]
            paths.add(f"{host}{path}")

    print(f"\n📋 Unique Anthropic API paths:")
    for p in sorted(paths):
        print(f"   {p}")

    with open(f"{OUTPUT_DIR}/discovered-paths.json", "w") as fp:
        json.dump(sorted(list(paths)), fp, indent=2)

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
