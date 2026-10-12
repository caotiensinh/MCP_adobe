const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const htmlPath = process.env.CEP_TRANSPORT_UNDER_TEST ||
  path.join(__dirname, '../scripts/illustrator_cep_fallback_transport.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
const tick = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };

function harness() {
  let now = 0, counter = 0;
  const timers = new Map(), sockets = [], calls = [];
  class Socket {
    constructor() { this.readyState = 0; this.frames = []; sockets.push(this); }
    send(raw) { if (this.readyState !== 1) throw Error('offline'); this.frames.push(JSON.parse(raw)); }
    open() { this.readyState = 1; this.onopen(); }
    message(data) { this.onmessage({data: JSON.stringify(data)}); }
    close() { this.readyState = 3; this.onclose({code: 1006}); }
  }
  const timer = (fn, delay, repeat = false) => {
    const id = ++counter; timers.set(id, {fn, at: now + delay, delay, repeat}); return id;
  };
  const window = {
    setTimeout: (fn, delay) => timer(fn, delay), clearTimeout: id => timers.delete(id),
    setInterval: (fn, delay) => timer(fn, delay, true), clearInterval: id => timers.delete(id)
  };
  class CSInterface {
    requestOpenExtension() {}
    evalScript(source, callback) {
      calls.push({source, callback});
      if (source.startsWith('mcp_payload_read(')) {
        const owner = JSON.parse(source.slice('mcp_payload_read('.length, -1));
        callback(JSON.stringify({payloadId: owner.payloadId, offset: owner.offset, data: 'e30='}));
      } else if (source.startsWith('mcp_payload_release(')) callback('{"released":true}');
    }
  }
  vm.runInNewContext(script, {window, WebSocket: Socket, CSInterface, Date: {now: () => now}, console});
  function advance(ms) {
    const until = now + ms;
    while (true) {
      const next = [...timers.entries()].filter(([,v]) => v.at <= until).sort((a,b) => a[1].at-b[1].at)[0];
      if (!next) break;
      const [id,v] = next; now = v.at;
      if (v.repeat) v.at += v.delay; else timers.delete(id);
      v.fn();
    }
    now = until;
  }
  advance(6000); sockets[0].open();
  const request = {id: 51, script: 'read_current_document()', requestToken: 'token-51', jobId: 'job-51',
    connectionGeneration: 2, transport: {version: 1, sessionId: 'session-1'}};
  const descriptor = {version: 1, pageBytes: 12288, byteLength: 2, payloadId: 'payload-51'};
  const hostCalls = () => calls.filter(c => c.source.startsWith('mcp_handle_request('));
  return {advance, sockets, calls, request, descriptor, hostCalls,
    finish: () => hostCalls()[0].callback(JSON.stringify({payloadDescriptor: descriptor}))};
}

test('30-second waiter deadline does not fabricate completion or discard the late native callback', async () => {
  const h = harness(), s = h.sockets[0]; s.message(h.request);
  h.advance(31000); await tick();
  assert.equal(s.frames.filter(f => f.type === 'complete').length, 0);
  assert.equal(s.frames.filter(f => f.type === 'heartbeat').at(-1).busy, true);
  h.finish(); await tick();
  assert.equal(s.frames.filter(f => f.type === 'payload_descriptor').length, 1);
  assert.equal(s.frames.filter(f => f.type === 'payload_chunk').length, 1);
  assert.equal(s.frames.filter(f => f.type === 'complete').length, 1);
  assert.equal(h.hostCalls().length, 1);
});

test('rejects another native dispatch while a late callback is outstanding', async () => {
  const h = harness(), s = h.sockets[0]; s.message(h.request);
  h.advance(31000); await tick();
  s.message({...h.request, id: 52, requestToken: 'token-52'}); await tick();
  assert.equal(h.hostCalls().length, 1);
  assert.match(s.frames.filter(f => f.id === 52).at(-1).error, /BUSY/);
});

test('retains busy fence until an ACK matching the completed token', async () => {
  const h = harness(), s = h.sockets[0]; s.message(h.request); h.finish(); await tick();
  assert.equal(s.frames.filter(f => f.type === 'heartbeat').at(-1).busy, true);
  s.message({type: 'completion_ack', requestToken: 'other-token'});
  assert.equal(s.frames.filter(f => f.type === 'heartbeat').at(-1).busy, true);
  s.message({type: 'completion_ack', requestToken: h.request.requestToken});
  assert.equal(s.frames.filter(f => f.type === 'heartbeat').at(-1).busy, false);
});

test('reconnect replays identical completion bytes without running the native body again', async () => {
  const h = harness(), s = h.sockets[0]; s.message(h.request); h.finish(); await tick();
  const before = s.frames.filter(f => f.type !== 'heartbeat'); s.close(); h.advance(3000);
  const reconnected = h.sockets.at(-1); reconnected.open(); await tick();
  assert.deepEqual(reconnected.frames.filter(f => f.type !== 'heartbeat'), before);
  assert.equal(h.hostCalls().length, 1);
  reconnected.message({type: 'completion_ack', requestToken: h.request.requestToken});
  reconnected.close(); h.advance(3000); const third = h.sockets.at(-1); third.open();
  assert.equal(third.frames.filter(f => f.type === 'complete').length, 0);
});

test('completion while disconnected survives reconnect', async () => {
  const h = harness(), s = h.sockets[0]; s.message(h.request); s.close(); h.finish(); await tick();
  h.advance(3000); const next = h.sockets.at(-1); next.open(); await tick();
  assert.equal(next.frames.filter(f => f.type === 'complete').length, 1);
  assert.equal(next.frames.filter(f => f.type === 'payload_chunk').length, 1);
  assert.equal(h.hostCalls().length, 1);
});

test('keeps the original host error when the descriptor is absent', async () => {
  const h = harness(), s = h.sockets[0]; s.message(h.request);
  h.hostCalls()[0].callback('EvalScript error.'); await tick();
  const result = s.frames.find(f => f.type === 'complete');
  assert.match(result.error, /EvalScript error\./);
  assert.equal(result.hostDiagnostic, 'EvalScript error.');
  assert.equal(s.frames.filter(f => f.type === 'payload_descriptor').length, 0);
});

test('keeps descriptor evidence when payload page validation fails', async () => {
  const h = harness(), s = h.sockets[0]; s.message(h.request);
  h.hostCalls()[0].callback(JSON.stringify({payloadDescriptor: {...h.descriptor, version: 999}})); await tick();
  assert.equal(s.frames.filter(f => f.type === 'payload_descriptor').length, 1);
  assert.match(s.frames.find(f => f.type === 'complete').error, /invalid payload descriptor/);
  assert.equal(h.hostCalls().length, 1);
});
