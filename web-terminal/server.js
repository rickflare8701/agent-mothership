const express = require('express');
const http = require('http');
const ws = require('ws');
const path = require('path');
const { spawn } = require('child_process');

// ──────────────────────────────────────────────
// Configuration
// ──────────────────────────────────────────────
const PORT = process.env.PORT || 3000;
const SHELL = process.env.SHELL || '/bin/bash';
const STARTUP_DIR = process.env.HOME || '/root';

// ──────────────────────────────────────────────
// Express app
// ──────────────────────────────────────────────
const app = express();
const server = http.createServer(app);

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', uptime: process.uptime() });
});

// ──────────────────────────────────────────────
// WebSocket server
// ──────────────────────────────────────────────
const wss = new ws.WebSocketServer({ server });

wss.on('connection', (ws) => {
  console.log('[terminal] New client connected');
  
  // Spawn a shell (bash)
  const shell = spawn(SHELL, [], {
    cwd: STARTUP_DIR,
    env: {
      ...process.env,
      TERM: 'xterm-256color',
      COLORTERM: 'truecolor',
    },
  });

  // Shell → WebSocket
  shell.stdout.on('data', (data) => {
    if (ws.readyState === ws.OPEN) {
      ws.send(data.toString('base64'));
    }
  });

  shell.stderr.on('data', (data) => {
    if (ws.readyState === ws.OPEN) {
      ws.send(data.toString('base64'));
    }
  });

  // WebSocket → Shell
  ws.on('message', (data) => {
    const msg = data.toString();
    
    // Handle resize
    if (msg.startsWith('{')) {
      try {
        const json = JSON.parse(msg);
        if (json.type === 'resize' && shell.pid) {
          shell.stdout.setEncoding('utf8');
        }
        return;
      } catch (e) {}
    }
    
    shell.stdin.write(msg);
  });

  // Handle disconnection
  ws.on('close', () => {
    console.log('[terminal] Client disconnected');
    shell.kill('SIGTERM');
  });

  // Handle shell exit
  shell.on('exit', (code) => {
    console.log(`[terminal] Shell exited with code ${code}`);
    if (ws.readyState === ws.OPEN) {
      ws.close();
    }
  });
});

// ──────────────────────────────────────────────
// Start
// ──────────────────────────────────────────────
server.listen(PORT, '0.0.0.0', () => {
  console.log(`
╔══════════════════════════════════════════════╗
║     🌐 Agent Mothership — Web Terminal       ║
║                                              ║
║     Local:  http://localhost:${PORT}${
    ' '.repeat(5 - String(PORT).length)
  }         ║
║     Shell:  ${SHELL}                         ║
║                                              ║
║  Now start your Cloudflare Tunnel:           ║
║  cloudflared tunnel --url http://localhost:${PORT}${
    ' '.repeat(5 - String(PORT).length)
  }   ║
╚══════════════════════════════════════════════╝
  `);
});
