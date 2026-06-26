# 🎯 DoorDash HackerOne — Attack Gameplan

> **Last updated:** June 24, 2026
> **Status:** Phase 1 in progress

---

## 🥅 GOAL

Find HIGH/CRITICAL severity bugs on DoorDash's bounty scope. Priority targets with ZERO existing reports:
- **`com.dd.doordash` (Android)** — 0 reports, 0% signal — completely untapped!  
- **`doordash.DoorDashConsumer` (iOS)** — 0 reports, 0% signal — completely untapped!  
- **`www.doordash.com` (Domain)** — 7 reports, 88% signal — well-tested already

**Strategy:** Attack the mobile apps (static analysis) and unauthenticated APIs. Skip account creation since we have no phone.

---

## ⚔️ RULES OF ENGAGEMENT

| Rule | Detail |
|------|--------|
| **No SMS** | We cannot receive text messages. Dead end. Don't revisit. |
| **No real accounts** | We can't create accounts (requires phone or real OAuth). |
| **No social login** | Requires real Google/Facebook/etc accounts + browser popup flow. |
| **Datacenter IP** | GitHub Codespace = Azure IP. Cloudflare + Iguazu detect this. |
| **Mobile context is our friend** | Mobile user-agent + viewport bypasses bot detection on some endpoints. |
| **Document everything** | Every test goes in `/tmp/doordash/` with timestamp. Findings → this file. |
| **Don't repeat dead ends** | Check the checklist below before testing anything. |

---

## 🧰 TOOLS WE HAVE

```
✅ Playwright 1.60.0 (Python + Node.js) — headless browser automation
✅ requests 2.34.2 — HTTP client
✅ ffuf — web fuzzer
✅ nuclei — vulnerability scanner (templates)
✅ unzip — APK extraction
✅ cf_clearance cookie extraction (Cloudflare bypass confirmed)
⚠️ apktool — NEEDS INSTALL (apt install apktool)
⚠️ jadx — NEEDS INSTALL (or download .deb)
⚠️ Clairvoyance — NEEDS INSTALL (pip, for GraphQL schema reconstruction)
```

---

## 📋 WHAT WE'VE ALREADY TRIED (DO NOT REPEAT)

### Account Creation — ALL DEAD ENDS ❌
- [x] Desktop `/signup` → 403 `user_assessment_bot` (reCAPTCHA Enterprise + Iguazu attestation)
- [x] Mobile `/signup/phone` → 200 but needs SMS code (we have no phone)
- [x] "Use password instead" → submits to `/signup` (same attestation block)
- [x] `/signup/phone/signup_continue` → "Missing MFA session"
- [x] Social auth `signupStart` (Google/Facebook/Apple/Amazon/Line) → SPA, needs real OAuth popup
- [x] Social auth `signupComplete` → "Missing server_state in session"
- [x] Guest conversion → 403 Cloudflare
- [x] SMS brute force → 5 attempts per 30 min, 1M combos impossible
- [x] SMS resend → doesn't reset attempt counter

### Attestation Bypass Attempts — ALL FAILED ❌
- [x] Fake Iguazu server (return TRUSTED responses) → server-side scoring still blocks
- [x] reCAPTCHA token injection → 403 (server-side independent scoring)
- [x] Camoufox fingerprint rotation → still detected as datacenter
- [x] Mobile layout params on desktop → still 403
- [x] Blocking Iguazu/attestation endpoints entirely → still fails

### Auth/Token Attacks — ALL FAILED ❌
- [x] `scope=*` exploit attempt → 403 on `/signup` (can't test without account)
- [x] Direct `/identity-bff/v1/oauth2/token` → needs valid session
- [x] JWT token exchange → no token to exchange
- [x] Session cookie manipulation → "Missing MFA session"

### Other Tested — INFO ONLY ℹ️
- [x] Cloudflare bypass → WORKING (Playwright + wait)
- [x] Subdomain enumeration → 80+ found
- [x] JS bundle extraction → 243 bundles, 683 endpoints, 167 GraphQL ops
- [x] GraphQL introspection → DISABLED (explicitly blocked)
- [x] Sentry DSN leak → CONFIRMED but low impact
- [x] S3 bucket `dd-web-assets` → CONFIRMED but ListBucket denied
- [x] No CORS on risk-bff / consumer-mobile-bff → CONFIRMED but untested for cross-origin attacks
- [x] SMS verification info leak → CONFIRMED (attempt counter in error messages)

---

## 🗺️ ATTACK PHASES — IN ORDER OF PRIORITY

### PHASE 1: MOBILE APK STATIC ANALYSIS 🔥🔥🔥
> *Target: com.dd.doordash (Android) — 0 reports, completely fresh surface*

**Goal:** Extract hardcoded secrets, mobile-only endpoints, and auth bypass paths from the APK without running it.

✅ **apktool 2.7.0** (apt)
✅ **jadx 1.5.1** (manual install to /usr/local/jadx/) — requires `JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`
✅ **clairvoyance 2.5.5** (pip)

**Steps:**
- [x] **1.1** Install `apktool` and `jadx` ✅ DONE
- [ ] **1.2** Download latest DoorDash APK from apkmirror/apkpure — direct curl/wget fails (JS challenge). Use Playwright to automate download, or try `pip install google-play-scraper` to pull from Play Store directly.
- [ ] **1.3** Decompile with `apktool d` — extract `AndroidManifest.xml`, resources, libs
- [ ] **1.4** Decompile with `jadx` — get readable Java/Kotlin source
- [ ] **1.5** Grep for secrets: `client_id`, `client_secret`, `api_key`, `authorization`, `Bearer`, `scope`
- [ ] **1.6** Grep for API endpoints: `https://`, `api.doordash`, `doordash.com`, GraphQL URLs
- [ ] **1.7** Find deep link schemas: `doordash://`, custom URL handlers
- [ ] **1.8** Extract mobile-specific GraphQL operations and mutations
- [ ] **1.9** Look for phone verification bypass: `bypass`, `skip`, `phonevalidation`, `verification`
- [ ] **1.10** Find mobile `clientId` — likely different from web `1666519390426295040`
- [ ] **1.11** Extract any crypto/encryption keys that might be used for auth tokens
- [ ] **1.12** Document ALL findings → gameplan findings section

**Why this works:** Mobile apps often have different `client_id` values, different auth flows, hardcoded API keys, dev/staging endpoints, and sometimes even bypass URLs. Nobody has reported on the Android scope yet.

---

### PHASE 2: UNAUTHENTICATED API & GRAPHQL ATTACKS 🔥🔥
> *Target: risk-bff.doordash.com (no JWT, no CORS) + www.doordash.com GraphQL*

**Goal:** Find IDORs, info leaks, and schema details without authentication.

**Steps:**
- [ ] **2.1** Install Clairvoyance: `pip3 install clairvoyance`
- [ ] **2.2** Run Clairvoyance against `www.doordash.com/api/graphql` to reconstruct schema from field suggestions
- [ ] **2.3** Test `__type` and `__schema` meta-fields (Apollo-specific introspection bypasses)
- [ ] **2.4** Fuzz risk-bff GraphQL with extracted operations:
  - `scanPaymentCardRisk` — inject arbitrary IDs
  - `resumeOrderForCheckoutRisk` — inject arbitrary order IDs
  - `threeDSecureVerifyRisk` — manipulate payment IDs
  - `generateCivRisk` — test input validation
  - `verifyPaymentCardBFFRisk` — card detail enumeration
- [ ] **2.5** Test OT challenge endpoints for IDOR:
  - `GET /risk/v1/guest/challenges/otp/{challenge_id}/send` — brute-force challenge IDs
  - `POST /risk/v1/guest/challenges/otp/{challenge_id}/verify` — attempt verification for other users
  - `GET /risk/v1/guest/challenges/{challenge_id}/metadata` — extract PII from challenge metadata
- [ ] **2.6** Test rate limits on risk endpoints — can we spam challenges?
- [ ] **2.7** Attempt to forge GraphQL queries without auth to consumer-mobile-bff (even though it returns 401, try different query shapes)
- [ ] **2.8** Test `risk-bff` for mutation without required params → error-based schema leak

---

### PHASE 3: OAUTH & CONFIGURATION-BASED ATTACKS 🔥
> *Target: identity.doordash.com — the auth server*

**Goal:** Exploit OAuth2 misconfigurations, open redirects, and parameter tampering.

**Steps:**
- [ ] **3.1** `redirect_uri` fuzzing — try:
  - `https://evil.com` (open redirect → token leak)
  - `https://www.doordash.com.evil.com` (subdomain confusion)
  - `//evil.com` (protocol-relative bypass)
  - `https://www.doordash.com@evil.com` (userinfo abuse)
  - `javascript:alert(1)` (if not validated)
- [ ] **3.2** `client_id` fuzzing:
  - Try different DoorDash-owned client IDs (mobile, dasher, merchant)
  - Try `client_id=*` or `client_id=null`
- [ ] **3.3** `scope` manipulation:
  - Try combining scopes: `* admin`, `* dasher`, `* merchant`
  - Try standard OIDC scopes with `*`: `openid *`, `profile *`
- [ ] **3.4** `response_type` manipulation:
  - Try `token` (implicit flow — might skip some checks)
  - Try `id_token token` (hybrid flow)
  - Try `code id_token` or `code token`
- [ ] **3.5** Parameter pollution on signup endpoints:
  - Send `phoneNumber` + `password` to `/signup/phone`
  - Send `email` + `phoneNumber` to `/signup`
  - Duplicate parameters: `phoneNumber=415...&phoneNumber=650...`
- [ ] **3.6** HTTP method overrides:
  - `GET /signup` instead of `POST`
  - `PUT /signup/phone`
  - `PATCH /signup/phone`
- [ ] **3.7** Content-Type abuse:
  - `application/xml` instead of `application/json`
  - `multipart/form-data` signup
  - `text/plain` or `application/x-www-form-urlencoded`
- [ ] **3.8** Test `response_type` with `token` on the signup URL to see if implicit grant behaves differently

---

### PHASE 4: INFRASTRUCTURE & ASSET EXPANSION 🔥
> *Target: All DoorDash infrastructure*

**Goal:** Find forgotten/dev/staging environments, source leaks, and misconfigured cloud assets.

**Steps:**
- [ ] **4.1** Subdomain bruteforce with ffuf:
  ```bash
  ffuf -u https://FUZZ.doordash.com -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt -mc 200,301,302,403,401
  ```
  Wordlist focus: `dev`, `staging`, `stage`, `qa`, `test`, `internal`, `admin`, `api2`, `api-v2`, `v2`, `legacy`, `old`, `new`, `beta`, `alpha`, `sandbox`, `uat`, `demo`, `preprod`, `prod2`, `mobile`, `dasher`, `merchant`, `partner`, `graphql`, `graphiql`, `playground`, `docs`, `wiki`, `jira`, `confluence`, `jenkins`, `slack`, `mail`, `status`, `monitor`, `metrics`, `logs`, `debug`, `backup`, `vpn`, `remote`, `bastion`

- [ ] **4.2** S3 bucket enumeration:
  ```bash
  # Common DoorDash bucket name patterns
  ffuf -u https://FUZZ.s3.amazonaws.com -w patterns.txt
  ```
  Patterns: `dd-mobile-assets`, `doordash-mobile`, `dd-android`, `dd-ios`, `doordash-dev`, `doordash-staging`, `dd-web-assets-dev`, `dd-web-assets-staging`, `dd-config`, `doordash-config`, `dd-secrets`, `dd-logs`, `dd-build`, `doordash-build`, `doordash-ci`, `dd-artifacts`

- [ ] **4.3** GitHub secret scanning:
  - Search GitHub for `doordash` + `client_secret`
  - Search for `doordash.com` + `password` or `api_key`
  - Search for DoorDash internal URLs in public repos
  - Search for `1666519390426295040` (web client ID — might be in other codebases)

- [ ] **4.4** Nuclei scan on discovered subdomains:
  ```bash
  nuclei -l subdomains.txt -t exposures/ -t misconfiguration/ -t cves/ -severity critical,high
  ```

- [ ] **4.5** Check for common dev files:
  - `.env`, `.env.local`, `.env.development` on discovered subdomains
  - `/graphiql`, `/playground`, `/swagger`, `/api-docs`, `/swagger-ui.html`
  - `/actuator/health`, `/actuator/env`, `/actuator/mappings` (Spring Boot)
  - `/phpinfo.php`, `/debug`, `/trace`
  - `robots.txt` (look for Disallow paths — often reveals admin panels)
  - `sitemap.xml` (reveals all indexed URLs)

- [ ] **4.6** Certificate Transparency log search:
  - Use `crt.sh` for more subdomains: `%.doordash.com`
  - Check recent certs for dev/staging subdomains

---

## 📊 FINDINGS LOG

### Finding #1: Mobile Signup Has No Bot Detection (Medium)
**Status:** DOCUMENTED in `findings-doordash.md`  
**Scope:** `www.doordash.com`  
**Summary:** `/signup/phone` returns 200 from mobile context, 403 from desktop. No attestation/behavioral checks on mobile path.

### Finding #2: SMS Verification Info Leak (Low)
**Status:** DOCUMENTED  
**Summary:** `/signup/phone/verify` reveals remaining attempt count in error messages.

### Finding #3-#10: [See findings-doordash.md]

### Finding #11: *(New findings from this gameplan go here)*
**[TEMPLATE]**
- **Finding #**: 
- **Date discovered**: 
- **Scope**: 
- **Severity guess**: 
- **Endpoint**: 
- **Description**: 
- **Steps to reproduce**: 
- **Impact**: 
- **Evidence file**: `/tmp/doordash/finding-XX-*.txt`

---

## 📁 SESSION FILE ORGANIZATION

All session artifacts go in `/tmp/doordash/`:

```
/tmp/doordash/
├── apk/                    # APK analysis
│   ├── doordash.apk
│   ├── apktool-output/
│   ├── jadx-output/
│   └── secrets.txt
├── graphql/                # GraphQL results
│   ├── clairvoyance-output.json
│   └── schema-reconstructed.graphql
├── fuzzing/                # Fuzzing results
│   ├── subdomain-brute.txt
│   ├── s3-enum.txt
│   └── redirect-fuzzing.txt
├── findings/               # Evidence for each finding
│   ├── finding-XX-request.txt
│   └── finding-XX-response.json
├── cookies/                # Session cookies
│   └── cookies-YYYY-MM-DD.json
└── nuclei/                 # Nuclei scan results
    └── scan-YYYY-MM-DD.txt
```

---

## 🔁 SESSION ROUTINE

At the start of each session:
1. Check this file for pending/blocked tasks
2. Resume from last completed phase
3. Verify tools are still installed: `which playwright apktool jadx ffuf nuclei`

At the end of each session:
1. Update this file with results + mark completed tasks
2. Save evidence to /tmp/doordash/findings/
3. Commit to git: `git add gameplan-doordash.md && git commit -m "Session YYYY-MM-DD: <summary>"`

---

## ⚡ QUICK WINS (Start with these!)

If you have < 15 minutes, do these in order:
1. **Download APK** — highest leverage, completely untapped surface
2. **Install jadx + apktool** — needed for Phase 1
3. **Clairvoyance scan** — reconstruct GraphQL schema without introspection
4. **`redirect_uri=//evil.com` test** — 10-second OAuth misconfig check
5. **Nuclei scan** on known subdomains — automated vuln detection
