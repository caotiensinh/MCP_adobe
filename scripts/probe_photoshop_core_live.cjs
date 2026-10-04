const fs = require('fs');
const path = require('path');

const serverDir = process.env.CORE_SERVER_DIR;
if (!serverDir) throw new Error('CORE_SERVER_DIR is required');
const { WebSocketServer } = require(path.join(serverDir, 'node_modules', 'ws'));

const port = Number(process.env.PS_BRIDGE_PORT || '8765');
const outDir = process.env.PHOTOSHOP_PROBE_OUT || process.cwd();
const psdPath = path.join(outDir, 'mcp_adobe_ps24_probe.psd');
const pngPath = path.join(outDir, 'mcp_adobe_ps24_probe.png');
for (const p of [psdPath, pngPath]) { try { fs.rmSync(p, { force: true }); } catch {} }

const wss = new WebSocketServer({ host: '127.0.0.1', port });
let socket;
let nextId = 1;
const pending = new Map();

function command(command, params = {}, timeoutMs = 30000) {
  if (!socket || socket.readyState !== socket.OPEN) throw new Error('Photoshop bridge is not connected');
  const id = nextId++;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`UNKNOWN: timeout waiting for ${command}; inspect Photoshop before retry`));
    }, timeoutMs);
    pending.set(id, { resolve, reject, timer, command });
    socket.send(JSON.stringify({ id, command, params }));
  });
}

function assertOk(name, result) {
  if (!result || result.ok !== true) throw new Error(`${name} failed: ${JSON.stringify(result)}`);
  return result;
}

function waitForFile(p, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const poll = () => {
      try {
        if (fs.existsSync(p) && fs.statSync(p).size > 0) return resolve();
      } catch {}
      if (Date.now() >= deadline) return reject(new Error(`output not materialized: ${p}`));
      setTimeout(poll, 250);
    };
    poll();
  });
}

const connectionDeadline = Date.now() + 180000;
const deadlineTimer = setInterval(() => {
  if (!socket && Date.now() >= connectionDeadline) {
    clearInterval(deadlineTimer);
    console.error('PHOTOSHOP_CORE_PANEL_CONNECT=TIMEOUT');
    console.error('Open Photoshop > Plugins > MCP Bridge and keep the panel open.');
    process.exitCode = 2;
    wss.close();
  }
}, 500);

wss.on('connection', (ws) => {
  socket = ws;
  clearInterval(deadlineTimer);
  console.log('PHOTOSHOP_CORE_PANEL_CONNECTED=PASS');
  ws.on('message', (raw) => {
    let msg;
    try { msg = JSON.parse(raw.toString()); } catch { return; }
    const id = Number(msg.id);
    const item = pending.get(id);
    if (!item) return;
    pending.delete(id);
    clearTimeout(item.timer);
    item.resolve(msg);
  });
  ws.on('close', () => { if (socket === ws) socket = undefined; });

  (async () => {
    try {
      const host = assertOk('app.get_info', await command('app.get_info'));
      console.log(`PHOTOSHOP_CORE_HOST_INFO=${JSON.stringify(host.data || {})}`);
      const version = String((host.data || {}).version || '');
      if (!version.startsWith('24.')) throw new Error(`expected Photoshop 24.x live host, got ${version || 'unknown'}`);
      console.log('PHOTOSHOP_24_HOST_VERIFIED=PASS');

      const created = assertOk('doc.new', await command('doc.new', {
        width: 320, height: 240, resolution: 72, name: 'MCP Adobe PS24 Probe', colorMode: 'rgb', fillColor: 'white'
      }));
      console.log(`PHOTOSHOP_CORE_CREATE=${JSON.stringify(created.data || {})}`);

      const saved = assertOk('doc.save', await command('doc.save', { filePath: psdPath, format: 'psd' }, 60000));
      console.log(`PHOTOSHOP_CORE_SAVE=${JSON.stringify(saved.data || {})}`);
      await waitForFile(psdPath, 30000);
      const psdSig = fs.readFileSync(psdPath).subarray(0, 4).toString('ascii');
      if (psdSig !== '8BPS') throw new Error(`invalid PSD signature: ${JSON.stringify(psdSig)}`);
      console.log('PHOTOSHOP_CORE_PSD_VERIFY=PASS');

      const exported = assertOk('export.png', await command('export.png', { filePath: pngPath, quality: 'maximum' }, 60000));
      console.log(`PHOTOSHOP_CORE_EXPORT=${JSON.stringify(exported.data || {})}`);
      await waitForFile(pngPath, 30000);
      const pngSig = fs.readFileSync(pngPath).subarray(0, 8);
      const expected = Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]);
      if (!pngSig.equals(expected)) throw new Error('invalid PNG signature');
      console.log('PHOTOSHOP_CORE_PNG_VERIFY=PASS');
      console.log('PHOTOSHOP_24_LIVE_OPERATION_VERIFY=PASS');
      ws.close(1000, 'probe complete');
      wss.close(() => process.exit(0));
    } catch (err) {
      console.error(`PHOTOSHOP_CORE_PROBE_FAIL=${err && err.stack ? err.stack : err}`);
      try { ws.close(1011, 'probe failed'); } catch {}
      wss.close(() => process.exit(1));
    }
  })();
});

wss.on('listening', () => console.log(`PHOTOSHOP_CORE_PROBE_LISTENING=127.0.0.1:${port}`));
wss.on('error', (err) => { console.error(`PHOTOSHOP_CORE_PROBE_SERVER_FAIL=${err.stack || err}`); process.exit(1); });
