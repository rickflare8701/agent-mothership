# Anthropic Subdomains with Exposed Origin IPs

## Subdomain Enumeration Results

### Source: certspotter.com
- Total subdomains found: 56
- Exposed origin IPs: 22

## Exposed Origin IPs

| # | Subdomain | Origin IP | HTTP | Notes |
|---|-----------|-----------|------|-------|
| 1 | api.anthropic.com | 160.79.104.10 | 404 | Main API |
| 2 | console.anthropic.com | 160.79.104.10 | 302 | Console |
| 3 | www.anthropic.com | 160.79.104.10 | 200 | Website |
| 4 | docs.anthropic.com | 160.79.104.10 | 301 | Documentation |
| 5 | platform.anthropic.com | 160.79.104.10 | 301 | Platform |
| 6 | billing.anthropic.com | 160.79.104.10 | 200 | Billing |
| 7 | assets.anthropic.com | 160.79.104.10 | 302 | Assets |
| 8 | assets-proxy.anthropic.com | 160.79.104.10 | 403 | Assets proxy |
| 9 | brand.anthropic.com | 160.79.104.10 | 200 | Brand |
| 10 | feedback.anthropic.com | 34.160.232.196 | 302 | Feedback |
| 11 | ilinks.anthropic.com | 160.79.104.10 | 303 | Links |
| 12 | legal.anthropic.com | 160.79.104.10 | 302 | Legal |
| 13 | links.anthropic.com | 160.79.104.10 | 303 | Links |
| 14 | privacy.anthropic.com | 160.79.104.10 | 302 | Privacy |
| 15 | red.anthropic.com | 160.79.104.10 | 301 | Red team |
| 16 | www-cdn.anthropic.com | 160.79.104.10 | 404 | CDN |
| 17 | alignment.anthropic.com | 160.79.104.10 | 200 | Alignment |
| 18 | api-release-candidate-2.anthropic.com | 160.79.104.10 | 401 | Release candidate |
| 19 | prod-rudolph.he.anthropic.com | 3.221.57.21 | 400 | Production |
| 20 | statsig.anthropic.com | 160.79.104.10 | 200 | Statsig |

## Internal IPs (Not Accessible)

| Subdomain | IP | Notes |
|-----------|-----|-------|
| sandbox.api.anthropic.com | 10.104.0.8 | Internal |
| sandbox.staging.api.anthropic.com | 10.104.0.117 | Internal |

## Cloudflare-Protected

| Subdomain | IP | Status |
|-----------|-----|--------|
| evals.anthropic.com | Unknown | Protected |

## Key Findings

1. **All major subdomains on same IP** — 160.79.104.10 hosts api, console, www, docs, platform, billing, assets, etc.
2. **Internal IPs exposed** — sandbox.api.anthropic.com → 10.104.0.8, sandbox.staging.api.anthropic.com → 10.104.0.117
3. **Production endpoint exposed** — prod-rudolph.he.anthropic.com → 3.221.57.21

## Attack Vectors

1. **Direct API access** — Bypass Cloudflare WAF/rate-limiting
2. **Internal network access** — sandbox.api.anthropic.com → 10.104.0.8
3. **Production endpoint** — prod-rudolph.he.anthropic.com → 3.221.57.21
4. **SSRF** — Test redirect_uri with internal IPs
5. **Auth bypass** — Test without API keys

## 🔥 KEY FINDINGS FROM TESTING

### 1. feedback.anthropic.com (34.160.232.196)
**Response:** `Invalid GCIP ID token: empty token`
- Uses **Google Cloud Identity Platform (GCIP)**
- Requires ID token for authentication
- Potential bypass: GCIP token forgery

### 2. api-release-candidate-2.anthropic.com (160.79.104.10)
**Response:** `Jwt is missing`
- API release candidate endpoint
- Requires JWT authentication
- Potential bypass: JWT forgery/none algorithm

### 3. prod-rudolph.he.anthropic.com (3.221.57.21)
**Response:** `{"message":"Something went wrong"}`
- Production endpoint accessible
- Returns JSON error
- Potential bypass: Error message exploitation

### 4. alignment.anthropic.com (160.79.104.10)
**Response:** Full HTML page (Alignment Science Blog)
- Public blog accessible
- No authentication required

### 5. brand.anthropic.com (160.79.104.10)
**Response:** Full HTML page (Standards site)
- Public standards site
- No authentication required

### 6. sandbox.api.anthropic.com (10.104.0.8)
**Response:** No response
- Internal IP exposed
- Not accessible from outside

### 7. sandbox.staging.api.anthropic.com (10.104.0.117)
**Response:** No response
- Internal IP exposed
- Not accessible from outside

## Attack Vectors

1. **GCIP Token Forgery** — feedback.anthropic.com uses Google Cloud Identity Platform
2. **JWT Forgery** — api-release-candidate-2.anthropic.com requires JWT
3. **Error Message Exploitation** — prod-rudolph.he.anthropic.com returns detailed errors
4. **Internal Network Access** — sandbox.api.anthropic.com → 10.104.0.8
5. **Production Endpoint** — prod-rudolph.he.anthropic.com → 3.221.57.21

## Next Steps

1. ✅ Test api.github.com endpoints — DONE
2. ✅ Test Anthropic internal endpoints — DONE
3. Test GCIP token forgery on feedback.anthropic.com
4. Test JWT forgery on api-release-candidate-2.anthropic.com
5. Repeat for other companies
