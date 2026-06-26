# Our Tools & Techniques

A portable toolkit of security testing techniques, bypass methods, and automation scripts built during bounty research.

---

## 🛠️ TOOLS

### playwright_patched.py
**Purpose:** Drop-in replacement for Playwright with automatic stealth.
**Location:** `../playwright_patched.py`

**10 auto-applied features:**
1. Strip `navigator.webdriver` (injected before page JS)
2. Canvas/WebGL fingerprint noise (deterministic per session)
3. Fake `navigator.plugins` (length=3) + `navigator.mimeTypes`
4. Fake `window.chrome` (runtime, loadTimes, app)
5. Random User-Agent per context (Chrome 124-125, Win/Mac/Linux)
6. Random viewport (1280-1440×800-960) + realistic `availHeight`
7. Random locale/timezone (en-US/GB/CA/AU, US/UK/AU timezones)
8. Cookie persistence (auto-save/restore, domain-keyed files)
9. Tracker blocking (Sentry, Segment, GA, Facebook, LinkedIn, etc.)
10. Stealth Chrome args (`--disable-blink-features=AutomationControlled`)

**Usage:**
```python
from playwright_patched import sync_playwright
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context()  # stealth auto-applied
    page = context.new_page()
    page.goto("https://target.com")
    # navigator.webdriver = False, plugins = 3, chrome.runtime = True
```

**Env vars:** `PW_STEALTH_DISABLE=1`, `PW_STEALTH_NO_WEBDRIVER=1`, `PW_STEALTH_NO_TRACKERS=1`, `PW_STEALTH_VERBOSE=1`

**How it works:** Monkey-patches `playwright._impl._browser_type.BrowserType.launch()` and `playwright._impl._browser.Browser.new_context()` at the `_impl` level. Affects both sync and async APIs.

**Key lessons:**
- `context.route("**/*", ...)` kills performance — use individual routes per domain
- Canvas noise must be deterministic (seeded per session, not per-call)
- Cookie files must be keyed by domain to avoid cross-session pollution
- Monkey-patching at `_impl` level works for both sync and async APIs
- `add_cookies()` works before navigation — no need for deferred restore

---

### devtools.py
**Purpose:** Full Chrome DevTools via Playwright CDP — Network, Console, Elements, Application tabs.
**Location:** `../devtools.py`

**Captures:** Network traffic (all requests/responses incl. POST bodies), console logs, DOM structure, cookies, screenshots, HAR export.

**Usage:**
```bash
python3 devtools.py                          # identity.doordash.com
python3 devtools.py https://target.com/signup
cat /tmp/doordash/devtools/network/traffic.json
```

---

### doorbash-idor.py
**Purpose:** IDOR fuzzer applying 14 bypass techniques to any REST/GraphQL endpoint.
**Location:** `../doorbash-idor.py`

**14 bypass techniques:**
1. %20 space bypass (`/users/9%20`)
2. Trailing slash (`/users/9/`)
3. Double slash (`/users//9`)
4. Dot tricks (`/v1/./users/9`, `/v1/../v1/users/9`)
5. API version downgrade (`/v5/users/9` → `/v1/users/9`)
6. Sub-path variants (`/users/9/details`, `/users/9/orders`, 14 child paths)
7. HTTP Parameter Pollution (`?id=10&id=9`)
8. JSON array injection (`{"id": [10, 9]}`)
9. Bracket notation (`?id[]=10&id[]=9`)
10. Leading zeros (`?id=00009`)
11. SQL wildcards (`?id=9%`, `?id=9*`, `?id=9_`)
12. Null byte injection (`/users/9%00`, `/users/9%2500`)
13. Method switching (GET→POST→PUT→PATCH)
14. Proxy header injection (X-Original-URL, X-Forwarded-For, X-Forwarded-Host, X-Rewrite-URL, X-HTTP-Method-Override, X-Custom-IP-Authorization)

**Detection engine:**
- Status change detection (4xx→2xx, 4xx→3xx flagged as STATUS_DROP)
- Body size ratio analysis (>30% change flagged)
- Data leak keyword scanning (token, session, key, secret, password, email, phone, name, address, payment, card)

**Usage:**
```bash
python3 doorbash-idor.py                  # all targets
python3 doorbash-idor.py dasher           # dasher-mobile-bff only
python3 doorbash-idor.py --quick          # fast subset of techniques
```

**Execution modes:**
- Direct requests for non-CF targets (dasher-mobile-bff, api.doordash.com, risk-bff)
- Playwright browser for CF-protected targets (www.doordash.com)

---

### cf_extract.py
**Purpose:** Captures Cloudflare cookies from a fresh browser session, exports in JSON/Netscape/Python dict formats.
**Location:** `../cf_extract.py`

**Limitation:** cf_clearance cookies are bound to the browser session — cannot be reused in plain `requests`. But they persist within Playwright sessions.

---

### capture-signup.py
**Purpose:** Watches a full DoorDash signup flow via CDP and captures every API call.
**Location:** `../capture-signup.py`

**Key finding:** Mobile signup flow has ZERO bot detection — no reCAPTCHA execution, no `assess_behavior`, no attestation on `/signup/phone`.

---

### bac-test.py
**Purpose:** Broken Access Control tester — gets a valid signup session, tests protected endpoints, session manipulation, verification bypass.
**Location:** `../bac-test.py`

**Key finding:** `dasher-mobile-bff.doordash.com` is publicly accessible with no auth.

---

## 🎯 TECHNIQUE CATALOG

### IDOR Bypass Techniques (Battle-Tested)

| Technique | Example | Success Rate | Best For |
|-----------|---------|-------------|----------|
| **Sub-path variants** | `/users/9/details` | ⭐⭐⭐⭐⭐ 98 hits | REST APIs with nested resources |
| **Null byte injection** | `/users/9%00` | ⭐⭐⭐⭐ 20 hits | Path-based access control |
| **HPP (param pollution)** | `?id=10&id=9` | ⭐⭐⭐⭐ 20 hits | Query parameter authorization |
| **Bracket notation** | `?id[]=10&id[]=9` | ⭐⭐⭐⭐ 20 hits | Node.js/Express backends (qs parser) |
| **Version downgrade** | `/v5/→/v1/` | ⭐⭐⭐ 15 hits | Versioned APIs with legacy paths |
| **Method switching** | GET→POST→PUT→PATCH | ⭐⭐⭐ | 405/404 endpoints that process differently |
| **JSON array injection** | `{"id": [10, 9]}` | ⭐⭐ | JSON API endpoints |
| **Trailing slash** | `/users/9/` | ⭐⭐ | Router middleware bypass |
| **Wildcards** | `?id=9%` | ⭐⭐ | SQL-backed ID lookups |
| **Proxy headers** | `X-Original-URL: /admin` | ⭐ | Reverse proxy misconfiguration |

### Stealth/Anti-Detection Techniques

| Technique | What It Defeats |
|-----------|----------------|
| `--disable-blink-features=AutomationControlled` | Chrome's built-in automation flag |
| Delete `navigator.webdriver` | Basic bot detection scripts |
| Fake `navigator.plugins` (length > 0) | Cloudflare plugin check |
| Fake `window.chrome.runtime` | Chrome-specific feature detection |
| Deterministic canvas noise | Canvas fingerprinting |
| WebGL vendor spoofing | WebGL fingerprinting |
| Realistic `availHeight` (screen.height - 40-80px) | Taskbar detection |
| Matching UA + viewport | Inconsistency detection |
| Randomized locale/timezone | Geolocation leak detection |

### Reconnaissance Workflow

1. **Subdomain discovery** — ffuf with targeted wordlist
2. **Technology fingerprinting** — response headers, error pages, favicons
3. **Endpoint mapping** — crawl + CDP network capture
4. **Auth bypass testing** — method switching, version downgrade, path traversal
5. **IDOR fuzzing** — apply all 14 bypass techniques systematically
6. **Diff analysis** — compare status codes, body sizes, content patterns

---

## 📦 PREREQUISITES

```bash
pip install playwright playwright-stealth
playwright install chromium
npm install -g @playwright/mcp@latest
```

---

## 🏆 PROVEN FINDINGS (DoorDash)

| Finding | Severity | Technique |
|---------|----------|-----------|
| `dasher-mobile-bff` publicly accessible (no auth) | Medium | Direct access |
| `www-orders-drive` 404→204 on POST/PUT/PATCH | High | Method switching |
| `www-api-graphql` token leaks in 403 responses | High | Subpath + HPP |
| `dasher-auth` token leaks in 403 responses | Medium | Subpath + null-byte |
| `api.doordash.com/drive` endpoint exists (401, not 404) | Low | Path discovery |
| `wiki.doordash.com` → Atlassian Confluence | Low | Subdomain bruteforce |
| Mobile signup has zero bot detection | Medium | CDP capture |


### auth-fuzzer.py
**Purpose:** AmrSec's auth techniques applied to OAuth/OIDC identity stacks.
**Location:** `../auth-fuzzer.py`

**6 checks:**
1. JWKS/OIDC discovery — probes `/.well-known/openid-configuration`, extracts jwks_uri
2. Cookie flag analysis — HttpOnly, SameSite, Secure, domain scope
3. OAuth state validation — tests if state can be omitted
4. Implicit flow — `response_type=token` (deprecated, dangerous if supported)
5. ROPC grant_type — `grant_type=password` (master credential exposure)
6. Redirect URI traversal — path tricks on registered redirect_uri

**Usage:**
```bash
python3 auth-fuzzer.py
cat /tmp/doordash/auth-fuzz/summary.txt
```

**DoorDash Results (June 24):**
| Check | Result |
|-------|--------|
| JWKS/OIDC | ✅ `/.well-known/openid-configuration` exposed (normal), JWKS protected (403) |
| Cookie flags | ⚠️ `__cf_bm` missing SameSite (Cloudflare's own cookie, minor) |
| State validation | 🔒 Server enforces state — 403 on missing/bad state |
| Implicit flow | 🔒 Rejected — 403 |
| ROPC | 🔒 Rejected — 403 at all token endpoints |
| Redirect URI | 🔒 Strict validation — all traversal attempts 403 |

**Conclusion:** DoorDash's OAuth implementation follows OAuth 2.1 best practices.
