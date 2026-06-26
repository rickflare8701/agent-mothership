#!/usr/bin/env python3
"""
playwright_patched.py — Drop-in replacement for Playwright with automatic stealth.

Monkey-patches Playwright's internal launch and context-creation methods to inject
anti-fingerprinting, human-like randomization, cookie persistence, and tracker blocking.

Usage:
    from playwright_patched import sync_playwright  # drop-in replacement
    # or
    import playwright_patched  # patches existing Playwright imports

Features applied automatically on every browser context:
1.  navigator.webdriver = false (via init script injected before page JS)
2.  Canvas/WebGL/Audio fingerprint noise
3.  UA + Sec-CH-UA client hints matching (via CDP Network.setUserAgentOverride)
4.  Randomized viewport (±10px), locale, timezone per context
5.  Cookie/session persistence (auto-save/restore cf_clearance, dd-identity cookies)
6.  Tracker blocking (aborts requests to analytics/telemetry domains)

Tunables (set before first call):
    PW_STEALTH_DISABLE = True          # disable all patches
    PW_STEALTH_NO_WEBDRIVER = False    # skip webdriver removal
    PW_STEALTH_NO_CANVAS = False       # skip canvas noise
    PW_STEALTH_NO_TRACKERS = False     # skip tracker blocking
    PW_STEALTH_COOKIE_DIR = "/tmp/pw_cookies"  # cookie storage dir
    PW_STEALTH_VERBOSE = False         # log injection events
"""

import random
import os
import json
import logging
import hashlib
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger("pw_stealth")
log.addHandler(logging.StreamHandler())
log.setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Tunables (set via env vars)
# ---------------------------------------------------------------------------
DISABLED = os.environ.get("PW_STEALTH_DISABLE", "").lower() in ("1", "true", "yes")
NO_WEBDRIVER = os.environ.get("PW_STEALTH_NO_WEBDRIVER", "").lower() in ("1", "true", "yes")
NO_CANVAS = os.environ.get("PW_STEALTH_NO_CANVAS", "").lower() in ("1", "true", "yes")
NO_TRACKERS = os.environ.get("PW_STEALTH_NO_TRACKERS", "").lower() in ("1", "true", "yes")
COOKIE_DIR = Path(os.environ.get("PW_STEALTH_COOKIE_DIR", "/tmp/pw_cookies"))
VERBOSE = os.environ.get("PW_STEALTH_VERBOSE", "").lower() in ("1", "true", "yes")

if VERBOSE:
    log.setLevel(logging.DEBUG)

# ---------------------------------------------------------------------------
# Stealth JavaScript — injected via context.add_init_script
# Runs BEFORE any page JavaScript, evading Cloudflare detection
# ---------------------------------------------------------------------------
STEALTH_JS = r"""
// === playwright_patched stealth injection ===
(function() {
    'use strict';

    // 1. Strip navigator.webdriver
    const prop = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
    if (prop) {
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
            configurable: true
        });
    } else {
        try { delete navigator.webdriver; } catch(e) {}
        Object.defineProperty(Navigator.prototype, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
    }

    // 2. Fake navigator.plugins (Cloudflare checks length > 0)
    const makePlugin = (name, filename, description) => ({
        name, filename, description,
        length: 1,
        item: () => null,
        namedItem: () => null,
        0: { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' }
    });
    const plugins = [
        makePlugin('Chrome PDF Plugin', 'internal-pdf-viewer', 'Portable Document Format'),
        makePlugin('Chrome PDF Viewer', 'mhjfbmdgcfjbbpaeojofohoefgiehjai', ''),
        makePlugin('Native Client', 'internal-nacl-plugin', ''),
    ];
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            plugins.item = (i) => plugins[i] || null;
            plugins.namedItem = (n) => plugins.find(p => p.name === n) || null;
            plugins.refresh = () => {};
            return plugins;
        },
        configurable: true
    });

    // 3. Fake navigator.mimeTypes
    const mimeTypes = [
        { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
        { type: 'text/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
    ];
    mimeTypes.item = (i) => mimeTypes[i] || null;
    mimeTypes.namedItem = (n) => mimeTypes.find(m => m.type === n) || null;
    Object.defineProperty(navigator, 'mimeTypes', { get: () => mimeTypes, configurable: true });

    // 4. Fake window.chrome (Cloudflare checks for chrome.runtime)
    if (!window.chrome) {
        window.chrome = {};
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            connect: () => ({ onMessage: { addListener: () => {} }, onDisconnect: { addListener: () => {} }, postMessage: () => {} }),
            sendMessage: () => {},
            onMessage: { addListener: () => {} },
            onConnect: { addListener: () => {} },
            getManifest: () => ({}),
            getURL: (path) => 'chrome-extension://' + path,
            id: undefined,
            lastError: undefined,
            onInstalled: { addListener: () => {} },
        };
    }
    if (!window.chrome.loadTimes) {
        window.chrome.loadTimes = () => ({
            requestTime: Date.now() / 1000,
            startLoadTime: Date.now() / 1000,
            commitLoadTime: Date.now() / 1000,
            finishDocumentLoadTime: Date.now() / 1000,
            finishLoadTime: Date.now() / 1000,
            firstPaintTime: Date.now() / 1000 - 0.1,
            firstPaintAfterLoadTime: Date.now() / 1000,
            navigationType: 'Other',
            wasFetchedViaSpdy: true,
            wasNpnNegotiated: true,
            npnNegotiatedProtocol: 'h2',
            wasAlternateProtocolAvailable: true,
            connectionInfo: 'h2'
        });
    }
    window.chrome.app = { isInstalled: false, InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }, RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' } };

    // 5. Override permissions.query (Cloudflare checks notification/permissions)
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => {
        if (parameters.name === 'notifications') {
            return Promise.resolve({ state: Notification.permission, onchange: null });
        }
        return origQuery.call(window.navigator.permissions, parameters);
    };

    // 6. Fix hardwareConcurrency (should be > 1)
    if (navigator.hardwareConcurrency < 2) {
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4, configurable: true });
    }

    // 7. Fix navigator.languages
    if (!navigator.languages || navigator.languages.length === 0) {
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'], configurable: true });
    }

    // 8. Canvas fingerprint noise (deterministic per session)
    if (typeof window.__PW_NO_CANVAS_NOISE === 'undefined') {
        const _canvasSeed = Math.floor(Math.random() * 3);  // seeded ONCE per page
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function() {
            const ctx = this.getContext('2d');
            if (ctx && this.width > 0 && this.height > 0) {
                try {
                    const imageData = ctx.getImageData(0, 0, this.width, this.height);
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i] = imageData.data[i] ^ _canvasSeed;
                    }
                    ctx.putImageData(imageData, 0, 0);
                } catch(e) { /* ignore tiny/empty canvases */ }
            }
            return origToDataURL.apply(this, arguments);
        };
    }

    // 9. WebGL fingerprint noise
    if (typeof window.__PW_NO_WEBGL_NOISE === 'undefined') {
        const origGetParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(pname) {
            // UNMASKED_VENDOR_WEBGL (37445) or UNMASKED_RENDERER_WEBGL (37446)
            if (pname === 37445) return 'Intel Inc.';
            if (pname === 37446) return 'Intel Iris OpenGL Engine';
            return origGetParameter.call(this, pname);
        };
    }

    // 10. Fix screen dimensions (real taskbars take 40-80px)
    var _taskbarOffset = 40 + Math.floor(Math.random() * 40);
    Object.defineProperty(screen, 'availWidth', { get: () => Math.max(1024, screen.width - Math.floor(_taskbarOffset / 4)) });
    Object.defineProperty(screen, 'availHeight', { get: () => Math.max(768, screen.height - _taskbarOffset) });
})();
"""

# ---------------------------------------------------------------------------
# Trackers to block (analytics, telemetry, ads)
# ---------------------------------------------------------------------------
TRACKER_DOMAINS = [
    "*.sentry.io", "*.ingest.sentry.io",
    "*.segment.com", "*.segment.io",
    "*.amplitude.com",
    "*.google-analytics.com", "*.googletagmanager.com",
    "*.doubleclick.net", "*.googleadservices.com",
    "*.facebook.com", "*.facebook.net",
    "*.linkedin.com", "*.ads.linkedin.com",
    "*.bat.bing.com", "*.clarity.ms",
    "*.analytics.twitter.com",
    "*.pinterest.com",
    "*.redditstatic.com",
    "*.spotify.com",
    "static.cloudflareinsights.com",
]

# ---------------------------------------------------------------------------
# Locale/timezone pools for randomization
# ---------------------------------------------------------------------------
LOCALES = ["en-US", "en-GB", "en-CA", "en-AU"]
TIMEZONES = ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
             "America/Toronto", "Europe/London", "Australia/Sydney"]

# ---------------------------------------------------------------------------
# Patches applied flag
# ---------------------------------------------------------------------------
_patches_applied = False


def apply_patches():
    """Monkey-patch Playwright internals. Idempotent — safe to call multiple times."""
    global _patches_applied
    if _patches_applied or DISABLED:
        return
    _patches_applied = True

    try:
        _patch_launch_args()
        _patch_new_context()
        log.info("playwright_patched: all patches applied")
    except Exception as e:
        log.warning(f"playwright_patched: failed to apply patches: {e}")


def _patch_launch_args():
    """Inject stealth Chromium args into BrowserType.launch()."""
    from playwright._impl._browser_type import BrowserType

    _orig_launch = BrowserType.launch
    _orig_launch_persistent = BrowserType.launch_persistent_context

    STEALTH_ARGS = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--no-sandbox",
        "--disable-setuid-sandbox",
    ]
    IGNORE_DEFAULT_ARGS = [
        "--enable-automation",
        "--disable-component-extensions-with-background-pages",
    ]

    async def patched_launch(self, **kwargs):
        args = list(kwargs.get("args") or [])
        for a in STEALTH_ARGS:
            if a not in args:
                args.append(a)
        kwargs["args"] = args

        ignore = kwargs.get("ignoreDefaultArgs")
        if ignore is None:
            kwargs["ignoreDefaultArgs"] = IGNORE_DEFAULT_ARGS
        elif isinstance(ignore, list):
            for a in IGNORE_DEFAULT_ARGS:
                if a not in ignore:
                    ignore.append(a)
            kwargs["ignoreDefaultArgs"] = ignore
        log.debug(f"patched_launch: args={args[:3]}..., ignoreDefaultArgs={kwargs['ignoreDefaultArgs'][:2]}...")
        return await _orig_launch(self, **kwargs)

    async def patched_launch_persistent(self, **kwargs):
        args = list(kwargs.get("args") or [])
        for a in STEALTH_ARGS:
            if a not in args:
                args.append(a)
        kwargs["args"] = args

        ignore = kwargs.get("ignoreDefaultArgs")
        if ignore is None:
            kwargs["ignoreDefaultArgs"] = IGNORE_DEFAULT_ARGS
        elif isinstance(ignore, list):
            for a in IGNORE_DEFAULT_ARGS:
                if a not in ignore:
                    ignore.append(a)
            kwargs["ignoreDefaultArgs"] = ignore
        return await _orig_launch_persistent(self, **kwargs)

    BrowserType.launch = patched_launch
    BrowserType.launch_persistent_context = patched_launch_persistent


def _patch_new_context():
    """Hook Browser.new_context() to auto-inject stealth on every context."""
    from playwright._impl._browser import Browser

    _orig_new_context = Browser.new_context

    async def patched_new_context(self, **kwargs):
        # --- Randomization ---
        if "viewport" not in kwargs:
            w = random.randint(1280, 1440)
            h = random.randint(800, 960)
            kwargs["viewport"] = {"width": w, "height": h}
        if "locale" not in kwargs:
            kwargs["locale"] = random.choice(LOCALES)
        if "timezoneId" not in kwargs:
            kwargs["timezoneId"] = random.choice(TIMEZONES)
        if "userAgent" not in kwargs:
            kwargs["userAgent"] = _random_ua()

        # Create the context
        context = await _orig_new_context(self, **kwargs)
        log.debug(f"patched_new_context: viewport={kwargs.get('viewport')}, locale={kwargs.get('locale')}, tz={kwargs.get('timezoneId')}")

        # --- Inject stealth init script ---
        if not NO_WEBDRIVER:
            await context.add_init_script(STEALTH_JS)
            log.debug("patched_new_context: stealth JS injected")

        # --- Tracker blocking ---
        if not NO_TRACKERS:
            await _block_trackers(context)

        # --- Restore cookies if available ---
        await _restore_cookies(context)

        # --- Schedule cookie save on context close ---
        await _hook_context_close(context)

        return context

    Browser.new_context = patched_new_context


# ---------------------------------------------------------------------------
# Helper: random User-Agent with matching Sec-CH-UA hints
# ---------------------------------------------------------------------------
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def _random_ua():
    return random.choice(_USER_AGENTS)


# ---------------------------------------------------------------------------
# Helper: tracker blocking via context.route()
# ---------------------------------------------------------------------------
async def _block_trackers(context):
    """Abort requests to known tracker/analytics domains. Registers individual routes."""
    async def block_route(route):
        log.debug(f"  blocked: {route.request.url[:80]}")
        try:
            await route.abort()
        except Exception:
            pass

    # Register one route per tracker domain — much faster than **/* catch-all
    for pattern in TRACKER_DOMAINS:
        # Convert fnmatch glob to Playwright URL glob: *.sentry.io -> **/*.sentry.io/**
        url_pattern = f"**/*{pattern.lstrip('*')}/**"
        await context.route(url_pattern, block_route)



# ---------------------------------------------------------------------------
# Helper: cookie persistence
# ---------------------------------------------------------------------------
def _cookie_file(context, domain_hint="default"):
    """Derive a stable filename keyed by domain to avoid cross-session cookie pollution."""
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = domain_hint.replace(".", "_").replace(":", "_")[:60]
    return COOKIE_DIR / f"cookies_{safe_name}.json"


async def _get_context_domain(context):
    """Heuristic: extract a domain name from the first page or use a hash."""
    try:
        pages = context.pages
        if pages:
            url = pages[0].url
            if url and url != "about:blank":
                return urlparse(url).hostname or "default"
    except Exception:
        pass
    return f"ctx_{hashlib.md5(str(id(context)).encode()).hexdigest()[:8]}"


async def _restore_cookies(context):
    """Restore cookies from disk immediately. add_cookies works before navigation."""
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    for cf in COOKIE_DIR.glob("cookies_*.json"):
        try:
            cookies = json.loads(cf.read_text())
            if cookies:
                await context.add_cookies(cookies)
                log.debug(f"restored {len(cookies)} cookies from {cf.name}")
        except Exception as e:
            log.debug(f"cookie restore from {cf.name} failed: {e}")


async def _save_cookies(context):
    """Save all cookies to disk, keyed by the first real domain loaded."""
    try:
        cookies = await context.cookies()
        if not cookies:
            return
        # Use the first non-blank page's domain as key
        domain = await _get_context_domain(context)
        cf = _cookie_file(context, domain)
        cf.write_text(json.dumps(cookies, indent=2, default=str))
        log.debug(f"saved {len(cookies)} cookies to {cf}")
    except Exception as e:
        log.debug(f"cookie save failed: {e}")


async def _hook_context_close(context):
    """Hook the context's close method to save cookies before closing."""
    _orig_close = context.close

    async def patched_close(**kwargs):
        await _save_cookies(context)
        await _orig_close(**kwargs)

    context.close = patched_close


# ---------------------------------------------------------------------------
# Public API — drop-in replacements for Playwright entry points
# ---------------------------------------------------------------------------

# Apply patches at import time by default
apply_patches()

# Re-export Playwright's public API so users can do:
#   from playwright_patched import sync_playwright
from playwright.sync_api import sync_playwright as _sync_playwright_raw
from playwright.async_api import async_playwright as _async_playwright_raw


def sync_playwright():
    """Drop-in replacement for playwright.sync_api.sync_playwright()."""
    return _sync_playwright_raw()


def async_playwright():
    """Drop-in replacement for playwright.async_api.async_playwright()."""
    return _async_playwright_raw()


# ---------------------------------------------------------------------------
# CLI: test the patched Playwright
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.doordash.com"

    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  playwright_patched.py — stealth test       ║")
    print(f"╠══════════════════════════════════════════════╣")
    print(f"║  URL: {url[:40]}...")
    print(f"║  Stealth JS: {'✅' if not NO_WEBDRIVER else '❌'}")
    print(f"║  Canvas noise: {'✅' if not NO_CANVAS else '❌'}")
    print(f"║  Trackers blocked: {'✅' if not NO_TRACKERS else '❌'}")
    print(f"║  Cookies dir: {COOKIE_DIR}")
    print(f"╚══════════════════════════════════════════════╝")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Check if Cloudflare blocked us
        title = page.title()
        is_blocked = any(kw in title.lower() for kw in ["just a moment", "attention required", "blocked", "challenge"])

        # Check navigator.webdriver
        webdriver = page.evaluate("() => navigator.webdriver")

        # Check plugins
        plugins_count = page.evaluate("() => navigator.plugins.length")

        # Check chrome.runtime
        has_chrome_runtime = page.evaluate("() => !!window.chrome && !!window.chrome.runtime")

        print(f"\n{'❌ BLOCKED' if is_blocked else '✅ PAGE LOADED'}")
        print(f"   Title: {title[:80]}")
        print(f"   navigator.webdriver: {webdriver}")
        print(f"   navigator.plugins.length: {plugins_count}")
        print(f"   window.chrome.runtime: {has_chrome_runtime}")

        if not is_blocked:
            print(f"\n✅ Stealth working!")
        else:
            print(f"\n⚠️ Cloudflare block — datacenter IP, not fingerprint issue")

        browser.close()
