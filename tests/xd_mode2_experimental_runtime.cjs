"use strict";
// Execute the *actual* experimental XD UXP bridge, not a regex-only contract.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("experimental/mode2-xd-uxp/main.js", "utf8");
const DOC = "98d6635b-3767-4254-b200-ec8442b69ad2";
const NODE = "130fdb64-c691-4374-ab46-66fd3f9e077c";
const bounds = { left: 10, top: 20, right: 40, bottom: 60 };
const shape = {
  guid: NODE, name: "Disposable Only", locked: false, visible: true,
  fill: "#112233",
  globalBounds: { x: 10, y: 20, width: 30, height: 40 },
  localBounds: { x: 10, y: 20, width: 30, height: 40 },
  constructor: { name: "Rectangle" }
};
const root = { guid: DOC, children: { length: 1, at: () => shape } };
const selection = { items: [shape], insertionParent: root };
const scenegraph = { root, selection };
let registered;
const sent = [];
class FakeWebSocket {
  constructor(url) { this.url = url; this.readyState = 1; FakeWebSocket.current = this; }
  send(message) { sent.push(JSON.parse(message)); }
}
class Color {
  constructor(hex) { this.hex = hex; }
}
const application = {
  version: "test-xd-uxp", appLanguage: "en",
  editDocument(_label, mutate) { mutate(selection); }
};
const sandbox = {
  console, WebSocket: FakeWebSocket,
  setTimeout() { return 0; }, clearTimeout() {},
  require(id) {
    if (id === "application") return application;
    if (id === "scenegraph") return { ...scenegraph, Rectangle: class {}, Ellipse: class {}, Path: class {}, Text: class {}, Color };
    if (id === "uxp") return { entrypoints: { setup(config) { registered = config; } } };
    throw new Error("Unexpected XD plugin import: " + id);
  }
};
vm.runInNewContext(source, sandbox, { filename: "mode2-xd-uxp/main.js", timeout: 2000 });
assert.ok(registered?.commands?.mcpAdobeConnect);
assert.ok(registered?.commands?.mcpAdobeApply);
registered.commands.mcpAdobeConnect(selection, root);
const socket = FakeWebSocket.current;
assert.ok(socket, "must connect via experimental UXP entrypoint");
let counter = 0;
async function call(method, params = {}) {
  const id = "runtime-" + (++counter);
  socket.onmessage({ data: JSON.stringify({ id, method, params }) });
  for (let i = 0; i < 8; i++) await Promise.resolve();
  const result = sent.find(item => item.id === id);
  assert.ok(result, "missing bridge response " + method);
  return result;
}
const args = {
  document_id: DOC, node_id: NODE, bounds,
  isolated_test_copy: true, user_confirmed: true, fill: "#A1B2C3"
};
(async () => {
  const host = await call("xd.health");
  assert.equal(host.ok, true);
  assert.equal(host.result.bridge_build, "xd-mode2-guarded-experimental-v1");
  let reply = await call("xd.mode2.node.inspect", {
    document_id: DOC, node_id: NODE, bounds
  });
  assert.equal(reply.ok, true);
  assert.equal(reply.result.selection_count, 1);

  for (const bad of [
    { node_id: "other" }, { document_id: "wrong" },
    { bounds: { ...bounds, right: 99 } },
    { isolated_test_copy: false }, { user_confirmed: false }, { fill: "#NOTHEX" }
  ]) {
    reply = await call("xd.queue.mode2_fill", { ...args, ...bad });
    assert.equal(reply.ok, false, "bad Mode 2 queue must fail immediately");
    assert.equal((await call("xd.health")).result.pending_count, 0);
  }
  // Queue an operation while the target is valid, then change its geometry.
  reply = await call("xd.queue.mode2_fill", args);
  assert.equal(reply.ok, true);
  assert.equal(reply.result.status, "queued");
  const firstOperation = reply.result.operation_id;
  reply = await call("xd.queue.mode2_fill", args);
  assert.equal(reply.ok, false, "a second write may not share a Mode 2 queue");
  shape.globalBounds.x = 12;
  assert.throws(() => registered.commands.mcpAdobeApply(selection, root),
    /MODE2_NODE_BOUNDS_CHANGED/);
  assert.equal(shape.fill, "#112233", "stale target must never change");
  reply = await call("xd.queue.status", { operation_id: firstOperation });
  assert.equal(reply.result.status, "failed");
  assert.equal((await call("xd.health")).result.pending_count, 0);

  // One fresh, explicitly approved isolated operation can still Apply.
  shape.globalBounds.x = 10;
  reply = await call("xd.queue.mode2_fill", args);
  assert.equal(reply.result.status, "queued");
  registered.commands.mcpAdobeApply(selection, root);
  assert.ok(shape.fill instanceof Color);
  assert.equal(shape.fill.hex, "#A1B2C3");
  const done = await call("xd.queue.status", { operation_id: reply.result.operation_id });
  assert.equal(done.result.status, "applied");
  assert.equal(done.result.result.node_id, NODE);
  assert.equal((await call("xd.health")).result.pending_count, 0);
  console.log("MODE2_XD_EXPERIMENTAL_RUNTIME_PASS");
})().catch(e => { console.error(e); process.exitCode = 1; });
