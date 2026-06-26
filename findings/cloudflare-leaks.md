# Cloudflare — Complete Reference: Architecture, Bypass Techniques, Leaks & Secrets

> Compiled June 2026. Covers everything we know about how Cloudflare ticks, how to bypass it, and what's been leaked.

---

## 1. ARCHITECTURE — How Cloudflare Works

### Core Components
| Component | Internal Name | Role |
|-----------|--------------|------|
| Edge Proxy | **FL** (Frontline), **FL2** (successor) | Core reverse proxy, runs at every edge node |
| WAF | Ruleset Engine | Blocks malicious requests before they reach origin |
| Bot Management | JSD (JavaScript Detections) + ML | Scores every request 1-99, challenges high-risk traffic |
| DDoS Protection | Gatebot + FL | Absorbs volumetric attacks at the edge |
| Challenge Platform | `/cdn-cgi/challenge-platform/` | Serves obfuscated JS challenges, Turnstile |
| DNS | 1.1.1.1 infrastructure | Authoritative + recursive DNS |
| Workers | V8 isolates at edge | Serverless compute at every PoP |
| Zero Trust / Access | Identity-aware proxy | OIDC/SAML-based access control |
| Database | **ClickHouse** clusters | Powers analytics, feature flag distribution |

### How a Request Flows Through Cloudflare
```
Client → Edge (FL/FL2 Proxy) → WAF Rules → Bot Score Check →
  ├── Pass → Origin Server
  ├── Challenge → /cdn-cgi/challenge-platform/ JS → cf_clearance cookie → Retry → Origin
  └── Block → 403/1020
```

### Key Insight: Feature Files
From the Nov 2025 outage postmortem, Cloudflare distributes **dynamically generated "feature files"** to all edge nodes. These files contain WAF rules, rate limits, and bot detection logic. A ClickHouse query change caused these files to bloat, crashing Rust-based proxy nodes. This reveals:
- Edge nodes don't have hardcoded rules — they pull dynamic configs from a centralized database
- The proxy logic is written in **Rust** (FL2)
- If you could poison/predict these feature files, you could potentially weaken rules globally

---

## 2. BOT DETECTION — The Full Stack

### Layer 1: TLS Fingerprinting (Pre-HTTP)
Cloudflare inspects the TLS handshake BEFORE any HTTP request is processed.

| What's Checked | How | Bypass Tool |
|---------------|-----|-------------|
| JA3/JA4 hash | Cipher suites + extensions + curves | `curl_cffi` (impersonates Chrome/Firefox TLS stack) |
| HTTP/2 SETTINGS frame | Order, values, window size | `curl_cffi` with browser profile (`chrome130`, `firefox120`) |
| ALPN negotiation | h2 vs http/1.1 | Standard browsers negotiate h2 |
| SNI | Server Name Indication | Must match Host header |

**Key fact**: JA3 is now deprecated by Cloudflare. They use **JA4** + **JA4 Signals** (inter-request behavior over time, not just single hash). JA4 sorts ClientHello extensions for stability across browser versions.

### Layer 2: HTTP Header Fingerprinting
| What's Checked | Normal | Automation Red Flag |
|---------------|--------|---------------------|
| Header order | Browser-specific order | Alphabetical or random |
| `Accept-Language` | `en-US,en;q=0.9` | Missing or `*` |
| `Sec-CH-UA` | Chrome version + "Chromium" | Missing or wrong format |
| `Sec-Fetch-*` headers | Set by browser automatically | Missing entirely |
| User-Agent vs TLS match | Chrome UA + Chrome TLS | Python-requests UA + Go TLS |

### Layer 3: JavaScript Detections (JSD)
The challenge page injects obfuscated JS via `/cdn-cgi/challenge-platform/scripts/jsd/`. This script:

| Check | What It Tests | Why Automations Fail |
|-------|--------------|---------------------|
| `navigator.webdriver` | Automation flag | Puppeteer/Selenium set this to `true` by default |
| `window.chrome` | Chrome-specific APIs | Headless Chrome has different `chrome.runtime` behavior |
| `navigator.plugins` | Browser plugins array | Real Chrome has PDF Viewer, Chrome PDF Plugin; automations have empty array |
| `navigator.permissions` | Permissions API | Headless often returns different permission states |
| Canvas fingerprint | GPU rendering quirks | Headless uses SwiftShader (software) → different Canvas output |
| WebGL fingerprint | `WEBGL_debug_renderer_info` | Headless returns "Google Inc. (SwiftShader)" vs real GPU name |
| AudioContext fingerprint | Audio processing differences | Slight floating-point differences in headless |
| Font enumeration | Installed fonts | Headless has minimal/empty font list |
| `chrome.csi()` | Chrome Speed Index | Missing in headless |
| `chrome.loadTimes()` | Deprecated Chrome API | Missing in newer Chrome but present in some automation setups |
| Screen resolution | `screen.width/height` | 800x600 default vs common user resolutions |
| `navigator.hardwareConcurrency` | CPU cores | Headless often reports 1-2 vs real machines |
| Timezone | `Intl.DateTimeFormat` | UTC vs user's actual timezone |

### Layer 4: Behavioral Analysis (BLISS)
Cloudflare's **BLISS** (Bot Learning & Intelligent Scoring System) analyzes:
- **Request cadence**: Time between requests (humans have variable timing, bots are regular)
- **Mouse movement**: Whether mouse events exist before clicks
- **Scroll behavior**: Natural vs programmatic scrolling
- **Touch events**: On mobile, real touches vs simulated
- **Session continuity**: `__cf_bm` cookie tracks session behavior over time
- **Geo-consistency**: IP location matches declared locale/timezone

### Layer 5: AI Labyrinth (2026)
New defensive honeypot mechanism:
- When Cloudflare suspects an AI scraper, it serves **AI-generated decoy pages**
- These pages contain hidden links to decoy networks
- Bots that crawl these links are identified with high confidence
- The interaction data feeds back into ML models

---

## 3. COOKIES — cf_clearance and __cf_bm

### `cf_clearance` — The "You Passed" Token
- **Issued after**: Successfully completing a JS challenge, Turnstile, or CAPTCHA
- **Format**: Opaque, cryptographically bound to the client's fingerprint
- **Validation**: Server-side at the edge. Cloudflare says it's "securely tied" to the visitor's environment
- **Cannot be forged**: Must be generated by solving the actual challenge
- **Not transferable**: Bound to IP, TLS fingerprint, and browser fingerprint
- **Expires**: Time-limited (typically hours to days, site-dependent)

### `__cf_bm` — Bot Management Cookie
- **Purpose**: Tracks request patterns over time to build a consistent Bot Score
- **Not a clearance token**: Having `__cf_bm` doesn't mean you passed
- **Used for session continuity**: Helps Cloudflare verify requests are from the same client

### Cookie Extraction Flow (how bypass tools work)
```
1. Launch real Chromium browser (headless or headful)
2. Navigate to target URL
3. Browser executes Cloudflare's challenge JS natively
4. Cloudflare issues cf_clearance cookie
5. Tool extracts the cookie
6. Subsequent requests include cf_clearance → pass through
```

---

## 4. BYPASS TOOLS — Current State (2026)

### Working / Viable
| Tool | How It Works | Status |
|------|-------------|--------|
| **curl_cffi** | C-level TLS impersonation, matches browser JA4 fingerprints exactly | ✅ Working |
| **Playwright + stealth** | Patches JS environment, but requires constant updates | ✅ Works with maintenance |
| **puppeteer-extra-stealth** | Injects `page.evaluateOnNewDocument()` to overwrite browser properties | ⚠️ Needs frequent patching |
| **undetected-chromedriver** | Patches CDP communication, renames automation markers | ⚠️ Cat-and-mouse game |
| **CloakBrowser** | 58 C++ source-level patches to Chromium | ✅ Working (used in our Anthropic testing) |
| **Residential proxies** | IPs from consumer ISPs | ✅ Essential baseline |
| **Managed scraping APIs** | BrightData, ScrapingAnt, etc. handle all layers | ✅ Most reliable |

### Obsolete / Broken
| Tool | Why It Failed |
|------|--------------|
| **cloudscraper** | Only solved simple JS challenges, can't handle Turnstile |
| **cfscrape** | Same — outdated JS challenge solver |
| **flaresolverr** | Relies on unpatched browser instances, quickly flagged |
| **Simple cookie replay** | cf_clearance is bound to fingerprint, can't reuse across sessions/IPs |

### curl_cffi — The Current Gold Standard
```python
from curl_cffi import requests as curl_requests

# Impersonates Chrome 130's TLS stack EXACTLY
resp = curl_requests.get(
    "https://cloudflare-protected-site.com",
    impersonate="chrome130"
)
# TLS fingerprint matches real Chrome → passes pre-HTTP checks
```

---

## 5. CLOUDFLARE SECURITY INCIDENTS & LEAKS

### Salesloft Drift Breach (Aug 2025)
- **Actor**: GRUB1 (advanced threat actor)
- **Vector**: Supply-chain vulnerability via Salesloft's Drift chat agent → Salesforce
- **Data exposed**: Support ticket contents, logs, passwords from tickets, **104 Cloudflare API tokens**
- **Methodology**: Used `TruffleHog` to scan for secrets, `Salesforce-Multi-Org-Fetcher` to map environment
- **Impact**: API tokens rotated, no infrastructure compromise

### November 2025 Outage
- **Root cause**: ClickHouse query change caused feature files to bloat
- **Revealed**: Edge nodes use Rust-based proxy (FL2), dynamically load feature files from ClickHouse
- **Internal naming**: FL (Frontline) = original proxy, FL2 = Rust rewrite

### GitHub Supply Chain Attack (May 2026)
- ~3,800 internal GitHub repositories potentially affected
- This was GitHub infrastructure compromise, not Cloudflare-specific

### Known Internal Subdomains
These are public or semi-public (from cert transparency logs, DNS enumeration):
- `dash.cloudflare.com` — Dashboard
- `api.cloudflare.com` — REST API
- `developers.cloudflare.com` — Docs
- `blog.cloudflare.com` — Engineering blog
- `community.cloudflare.com` — Forums
- `support.cloudflare.com` — Support portal
- `static.cloudflare.com` — Static assets
- `cftracing.com` — Internal tracing (from cert transparency)

---

## 6. BYPASS STRATEGY — What Actually Works in 2026

### The "Emulation" Strategy (not "Exploitation")
Cloudflare doesn't have a single "bug" to exploit. Instead, you must perfectly emulate a legitimate browser across ALL layers simultaneously:

| Layer | Requirement | Tool |
|-------|------------|------|
| **TLS** | JA4 fingerprint matching real browser | `curl_cffi` with `impersonate="chrome130"` |
| **HTTP/2** | SETTINGS frame, pseudo-header order matching browser | `curl_cffi` handles this |
| **HTTP Headers** | Browser-correct header order, Sec-* headers, Accept-Language | Copy from real browser |
| **IP Reputation** | Residential/mobile IP, not datacenter | Residential proxy network |
| **JavaScript** | Pass all JS detection checks | Real browser (Playwright/Chromium) with stealth patches |
| **Behavior** | Human-like timing, mouse movements, scrolling | Randomized delays, human-like interaction patterns |
| **Geo-consistency** | IP location matches timezone, language, locale | Set locale/timezone to match proxy location |

### The Minimal Viable Bypass
For API-only access (no JS execution needed):
1. `curl_cffi` with `impersonate="chrome130"` — handles TLS + HTTP/2 fingerprinting
2. Residential proxy IP
3. Correct browser headers (order matters!)
4. Reuse `cf_clearance` cookie obtained from a prior browser session

### For Full Browser Access
1. Playwright + `puppeteer-extra-plugin-stealth` + constant patching
2. OR: CloakBrowser (58 C++ patches to Chromium)
3. OR: Managed scraping API (BrightData/ScrapingAnt)
4. Residential proxy
5. Human-like interaction patterns

---

## 7. WHAT DOESN'T WORK ANYMORE

- ❌ Simple User-Agent spoofing (TLS fingerprint still exposes you)
- ❌ `cloudscraper` / `cfscrape` (can't solve modern challenges)
- ❌ `flaresolverr` (quickly flagged)
- ❌ Static cookie replay across IPs/fingerprints
- ❌ Datacenter IPs without browser-level fingerprinting
- ❌ Headless Chrome without stealth patches (detected by `navigator.webdriver`, WebGL, chrome.runtime)
- ❌ HTTP-only requests with browser User-Agent (TLS mismatch gives you away)

---

## 8. KEY REFERENCE LINKS

- Cloudflare Bot Detection Engines: https://developers.cloudflare.com/bots/concepts/bot-detection-engines/
- JavaScript Detections: https://developers.cloudflare.com/cloudflare-challenges/challenge-types/javascript-detections/
- Cloudflare Cookies: https://developers.cloudflare.com/fundamentals/reference/policies-compliances/cloudflare-cookies/
- JA4 Signals: https://blog.cloudflare.com/ja4-signals/
- Turnstile + Challenge Redesign: https://blog.cloudflare.com/ (Feb 2026)
- Salesloft Drift Breach Response: https://blog.cloudflare.com/response-to-salesloft-drift-incident/
- November 2025 Outage Postmortem: https://blog.cloudflare.com/18-november-2025-outage/
- `curl_cffi`: https://github.com/yifeikong/curl_cffi
- `puppeteer-extra-stealth`: https://github.com/berstend/puppeteer-extra

---

## 9. WHAT WE'VE TRIED AGAINST CLOUDFLARE

From our Anthropic bounty testing:
| Technique | Result |
|-----------|--------|
| Direct HTTP requests (aiohttp) to `claude.ai/api/*` | ❌ 403 "Just a moment..." |
| Browser-like headers only | ❌ Still 403 (TLS fingerprint mismatch) |
| Origin IP bypass (160.79.104.10) | ❌ SSL handshake failure (SNI mismatch) |
| Origin IP HTTP | ❌ 400 "This request was sent over HTTP" |
| Origin IP HTTPS with `ssl=False` | ❌ SSLV3_ALERT_HANDSHAKE_FAILURE |
| `api.anthropic.com` (no Cloudflare) | ✅ Works! (billing-gift-validate returns 200) |
| `a-api.anthropic.com` (Segment, no CF) | ✅ Works! (Segment write key accepted) |
| CloakBrowser (from session-010) | ✅ Bypasses Cloudflare on claude.ai |

---

## 10. ACTIONABLE NEXT STEPS

1. **Install `curl_cffi`** — enables TLS-level impersonation of Chrome, bypassing JA4 fingerprinting
2. **Set up residential proxy** — essential for avoiding IP-based bot scoring
3. **Combine `curl_cffi` + origin IP bypass** for endpoints where Cloudflare is on the domain
4. **Use `api.anthropic.com`** where possible — it's NOT behind Cloudflare
5. **Build a CloakBrowser-like setup** — 58 Chromium C++ patches for headless Cloudflare bypass
