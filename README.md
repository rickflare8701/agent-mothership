# Agent Mothership — AI File Tree

> **AI-optimized directory map.** Organized 2026-06-26 from 117+ loose root files into logical hierarchy. Bloat deleted, findings preserved.

## Root

| Path | Purpose |
|------|---------|
| `CONTEXT.md` | Full operational context — Track A (Ivanti RE) + Track B (Anthropic bounty) |
| `RESEARCH.md` | Ivanti protocol RE findings |
| `GOLDEN_KEY.md` | Ivanti admin bypass / key finding |
| `README.md` | This file — AI directory map |

## `bounties/` — Anthropic HackerOne Bounty (Track B)

Well-organized, left as-is. 13 session docs + evidence + submissions.
- `bounties/README.md` — Bounty methodology overview
- `bounties/methodology.md` — Bounty hunting methodology
- `bounties/anthropic/` — **STASHED LOCALLY** at `.submission/anthropic/` (pre-submission sensitive — gitignored, not committed)

## `findings/` — All Findings & Documentation

Security research findings, session notes, recon results, research docs.

| File | What it is |
|------|------------|
| `findings-doordash.md` | DoorDash bounty findings |
| `gameplan-doordash.md` | DoorDash attack gameplan (4 phases) |
| `cloudflare-leaks.md` | Cloudflare leak/origin IP findings |
| `session-notes.md` | Daily session notes (DoorDash testing) |
| `session_plan.md` | Ivanti session 3 plan — RPC + network pivot |
| `github-repos.md` | GitHub repos research for Claude Code free usage |
| `prompt-to-gemini.md` | Gemini prompt — provider mode auth bypass debrief |
| `prompt-to-grok.md` | Grok prompt — attack vector brainstorming |
| `tool-inventory.md` | Tool inventory (go binaries, Python scanners) installed on PC |

### `findings/origin-ip-research/` — Origin IP & Subdomain Recon

| File | What it is |
|------|------------|
| `companies/anthropic-subdomains.md` | Anthropic subdomain enumeration |
| `companies/github-subdomains.md` | GitHub subdomain enumeration |
| `companies/exposed-origins.md` | Exposed origin IPs batch 1 |
| `companies/exposed-origins-batch2.md` | Exposed origin IPs batch 2 |
| `companies/deep-dive-results.md` | Deep dive on promising origin IPs |
| `companies/github-findings.md` | GitHub-related origin IP findings |
| `companies/subdomain-results.md` | Full subdomain enumeration results |

### `findings/our-tools-and-techniques/` — Tooling Notes

| File | What it is |
|------|------------|
| `README.md` | Custom tooling / techniques documentation |

## `tools/` — Exploit & Recon Scripts (organized by target)

### `tools/anthropic/` — Claude Code Bounty Tools (22 scripts)

**IDOR testing:**
| File | What it does |
|------|-------------|
| `anthropic-idor.py` | Main IDOR fuzzer — 11+ bypass techniques on Anthropic endpoints |
| `anthropic-idor-focused.py` | Focused IDOR with incremental findings saving |
| `anthropic-idor-phase2.py` | Phase 2 — JS source analysis + fuzz new endpoints |
| `anthropic-idor-phase4.py` | Phase 4 — test endpoints from network interception |
| `anthropic-idor-userdata.py` | IDOR focused on user data endpoints |

**Interception & credential hunting:**
| File | What it does |
|------|-------------|
| `anthropic-intercept.py` | Intercept Anthropic traffic |
| `cred-interceptor.py` | Real-time token capture & validation |
| `cred-interceptor-v2.py` | Aggressive multi-vector credential hunter |
| `session-key-hunter.py` | 2FA bypass cookie collector |

**Reconnaissance:**
| File | What it does |
|------|-------------|
| `anthropic-recon-engine.py` | Full recon engine for Anthropic infra |
| `wayback-anthropic-recon.py` | Wayback Machine recon for Anthropic URLs/endpoints |
| `anthropic-key-hunter.py` | API key hunter |
| `anthropic-key-hunter-v2.py` | API key hunter v2 |
| `gift-brute.py` | Gift code brute-forcer (smart combos) |
| `playwright_anthropic_auth_hunter.py` | Browser-based auth entry point hunter |

**Tampering:**
| File | What it does |
|------|-------------|
| `anthropic-tamper.py` | Tamper analysis — 4 techniques applied to ALL findings |
| `anthropic-tamper-detail.py` | Capture exact login_methods responses per email domain |
| `tamper_engine.py` | SQLMap-inspired payload obfuscation (shared with DoorDash tools) |

**Phase scripts:**
| File | What it does |
|------|-------------|
| `anthropic-phase5.py` | JS bundle fetch + API endpoint extraction |
| `anthropic-phase6.py` | Deep analysis + endpoint fuzzing + timing analysis |
| `anthropic-phase7.py` | Full OAuth flow test with PKCE |

**Shared utility:**
| File | What it does |
|------|-------------|
| `playwright_patched.py` | Drop-in Playwright replacement with stealth patches (used by auth_hunter) |

### `tools/doordash/` — DoorDash Bounty Tools (16 scripts)

**IDOR:**
| File | What it does |
|------|-------------|
| `doorbash-idor.py` | IDOR fuzzer — 11+ bypass techniques on DoorDash |
| `doorbash-idor-cloak.py` | IDOR fuzzer with cloak techniques |

**Auth bypass:**
| File | What it does |
|------|-------------|
| `auth-fuzzer.py` | Auth techniques on DoorDash identity stack |
| `bac-test.py` | Broken access control tests |
| `otp-bypass.py` | OTP verification bypass for phone signup |
| `capture-signup.py` | Capture full signup flow with DevTools |

**APK analysis:**
| File | What it does |
|------|-------------|
| `download-apk.py` | Download DoorDash APK via Camoufox + CDP |
| `dl-apk-direct.py` | Direct APK download (simpler, may not work) |
| `decompile_apk.py` | Decompile APK, extract endpoints/secrets |
| `search_apk_secrets.py` | Deep search APK for third-party secrets |

**Recon:**
| File | What it does |
|------|-------------|
| `devtools.py` | Chrome DevTools equiv via Playwright + CDP |
| `cf_extract.py` | Cloudflare cf_clearance cookie extractor |
| `restaurant-recon.py` | Wayback Machine recon for DoorDash restaurant endpoints |

**Attacks:**
| File | What it does |
|------|-------------|
| `attack-doordash.js` | DoorDash signup attack suite (5 angles) |
| `attack-doordash.py` | Python version of attack suite |

### `tools/general/` — General Purpose Tools

| File | What it does |
|------|-------------|
| `github-idor.py` | IDOR fuzzer for GitHub API endpoints |

## `infrastructure/` — Deployment & Operations

### `web-terminal/` — Beacon relay server

The express server + public assets served to target PCs during operations.

| Key file | Purpose |
|----------|---------|
| `server.js` | Express + WebSocket beacon relay server |
| `package.json` | Node deps |
| `beacon_persist.py` | Persistent beacon script |
| `deploy_beacon.py` | Beacon deployment script |
| `public/index.html` | Terminal UI (xterm.js) |
| `public/connect-schtasks.hta` | HTA payload for AppLocker-bypass delivery |
| `public/beacon-launch.vbs` | VBS launcher for beacon |
| `public/scripts/` | PowerShell scripts deployed to target PC (bypass_admin, schtasks_sideload, rpc_test, run_patched, etc.) |
| `public/dll/STServiceProcess.dll` | Proxy DLL for Ivanti sideloading |
| `public/AgentUpdateUI.dll` | Agent update UI DLL |

### `home-server/` — 24/7 server setup

| File | Purpose |
|------|---------|
| `setup.sh` | One-command setup for any Linux machine |
| `Dockerfile` | Docker deployment |
| `cloudflare.service` | Auto-start tunnel on boot |
| `start-tunnel.sh` | Start Cloudflare tunnel |
| `start-daily.sh` | Daily restart script |

### `proxy_dll/` — Ivanti Proxy DLL (Track A)

| File | Purpose |
|------|---------|
| `dllmain.c` | DLL proxy main — for STServiceProcess.dll hijacking |
| `STServiceProcess.def` | Module definition file |
| `STServiceProcess.dll` | Compiled proxy DLL |
| `libSTServiceProcess.a` | Import library |

### `spartacus/` — DLL Hijack Scanner

| File | Purpose |
|------|---------|
| `Spartacus.exe` | Compiled DLL hijack scanner executable |
| `CommandLineGenerator.html` | Command line generator UI |
| `Examples.md` | Usage examples |
| `Assets/` | Prototypes CSV, solution files, proxy.rc, dllmain.cpp |

### `scripts/` — Shell Scripts

| File | Purpose |
|------|---------|
| `bootstrap.sh` | Bootstrap any fresh environment |
| `load-memory.sh` | Load memory from GitHub backup |
| `restore.sh` | Restore session from GitHub |

## `data/` — Data Files

| File | Purpose |
|------|---------|
| `wietze_dll_hijack_candidates.csv` | Wietze's DLL hijack candidate database (78KB) |

## `infrastructure/plugins/` — OpenCode Plugins

| Plugin | Source | Location |
|--------|--------|----------|
| **Superpowers** | `obra/superpowers` | Plugin via `git+https://github.com/obra/superpowers.git` |
| **Headroom** | `headroomlabs-ai/headroom` | Local copy at `infrastructure/plugins/headroom-opencode/` |

### Superpowers (obra/superpowers)

A skill-based development methodology. Auto-loads 16 skills at session start:
`brainstorming`, `writing-plans`, `subagent-driven-development`, `test-driven-development`, `systematic-debugging`, `verification-before-completion`, `finishing-a-development-branch`, etc.

Skills auto-trigger based on task type. Use the `skill` tool to invoke.

### Headroom (headroomlabs-ai/headroom)

Context compression layer — claims 60-95% token reduction. Two parts:

1. **Headroom proxy** — local server that compresses context before sending to the LLM
2. **headroom-opencode plugin** — intercepts opencode provider traffic in-process + exposes `headroom_retrieve` tool

**Session startup (run before first task):**
```bash
pip install "headroom-ai[proxy]" --break-system-packages 2>/dev/null
headroom proxy --port 8787 &
export HEADROOM_PROXY_URL=http://127.0.0.1:8787
```

## `config/` — Configuration

| Path | Purpose |
|------|---------|
| `.devcontainer/devcontainer.json` | Dev container config |
| `.codesandbox/` | CodeSandbox environment config |
| `.env.memory.template` | Memory env var template |

## Deleted (Bloat / Failed Tests)

| File | Reason |
|------|--------|
| `attack-fast.py` | "10-min sprint" temp test — not a real tool |
| `prompt-to-gemini-fuzzing.md` | 5-line stub, incomplete |
| `__pycache__/` | Python bytecode cache |

## Already Deleted (pre-organization, staged)

Previous session already cleaned these stale files:
- `grok_prompt4.txt`, `grok_prompt5.txt` — old prompts
- `run_patched.ps1`, `run_patched_simple.ps1` — superseded by web-terminal/public/scripts/ versions
- `web-terminal/public/grok_prompt.txt` — old prompt
- `web-terminal/public/scripts/debug_pe.py`, `debug_pe_runner.ps1`, `deploy_and_run.ps1`, `explore_binaries.ps1`, `explore_tasks.ps1`, `list-exports.py`, `open_grok.ps1`, `rpc_mgmt.ps1`, `run_exports.ps1`, `run_exports_2.ps1`, `search_guids.ps1`, `search_guids.py` — stale debug/explore scripts

## Gitignored (not committed)

- `node_modules/` — web-terminal npm deps
- `tmp/` — DoorDash/Keycloak page captures
- `.tunnel-url` — Cloudflare tunnel URL (changes each session)
- `.env` / `.env.memory` / `.env.local` — secrets
- `*.log` — log files
- `package-lock.json` — npm lockfile
- `.submission/` — Pre-submission bounty content (see below)

## `.submission/` — Pre-Submission Bounty Content (LOCAL ONLY)

**Not committed to GitHub.** Stashed locally until you're ready to submit.

| Path | Content |
|------|---------|
| `.submission/anthropic/` | Full Anthropic bounty: HACKERONE-SUBMISSION.md, 13 session docs, evidence (strace logs, mock servers, proof files), IDOR findings log, etc. |

To restore when ready to submit:
```bash
mv .submission/anthropic bounties/anthropic
git add bounties/anthropic
git commit -m "Add bounty submission files"
git push
```

For now, all bounty methodology docs remain public at `bounties/methodology.md` and `bounties/README.md`.
