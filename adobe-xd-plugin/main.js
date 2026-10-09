const application = require("application");
const { entrypoints } = require("uxp");
const scenegraph = require("scenegraph");
const { Rectangle, Text, Color } = scenegraph;

const BRIDGE_URL = "ws://127.0.0.1:8765";
const STATUS_LIMIT = 200;
const BRIDGE_BUILD = "xd-one-click-v2";

let panel;
let socket;
let reconnectTimer;
let latestSnapshot = {
  document: null,
  selection: []
};
let pendingWrites = [];
let operationStatus = {};
let operationOrder = [];
let operationCounter = 0;

function safeNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function nodeInfo(node) {
  if (!node) return null;
  let bounds = null;
  try {
    const b = node.localBounds;
    if (b) {
      bounds = {
        x: safeNumber(b.x, 0),
        y: safeNumber(b.y, 0),
        width: safeNumber(b.width, 0),
        height: safeNumber(b.height, 0)
      };
    }
  } catch (_) {}

  return {
    guid: node.guid || null,
    name: node.name || null,
    type: node.constructor && node.constructor.name ? node.constructor.name : "SceneNode",
    visible: node.visible !== false,
    bounds
  };
}

function snapshot(selection, rootNode) {
  const items = [];
  if (selection && selection.items) {
    for (let i = 0; i < selection.items.length; i += 1) {
      items.push(nodeInfo(selection.items[i]));
    }
  }

  let rootChildren = 0;
  try {
    rootChildren = rootNode && rootNode.children ? rootNode.children.length : 0;
  } catch (_) {}

  const insertionParentChildren = [];
  try {
    const parent = selection && selection.insertionParent
      ? selection.insertionParent
      : null;
    if (parent && parent.children) {
      for (let i = 0; i < parent.children.length; i += 1) {
        insertionParentChildren.push(nodeInfo(parent.children.at(i)));
      }
    }
  } catch (_) {}

  latestSnapshot = {
    document: {
      rootChildren,
      insertionParent: selection && selection.insertionParent
        ? nodeInfo(selection.insertionParent)
        : null,
      insertionParentChildren
    },
    selection: items
  };
}

function rememberOperation(operationId, value) {
  operationStatus[operationId] = value;
  operationOrder.push(operationId);
  while (operationOrder.length > STATUS_LIMIT) {
    const old = operationOrder.shift();
    delete operationStatus[old];
  }
}

function nextOperationId() {
  operationCounter += 1;
  return `xd-${Date.now()}-${operationCounter}`;
}

function queueMutation(method, params) {
  const operationId = nextOperationId();
  pendingWrites.push({ operationId, method, params: params || {} });
  rememberOperation(operationId, {
    status: "queued",
    method,
    queuedAt: Date.now()
  });
  renderStatus();
  if (panel) {
    const applyButton = panel.querySelector("#apply");
    if (applyButton) {
      try { applyButton.focus(); } catch (_) {}
    }
  }
  return {
    status: "queued",
    approval_required: true,
    operation_id: operationId,
    pending_count: pendingWrites.length
  };
}

function requireSelection(selection) {
  if (!selection || !selection.items || selection.items.length === 0) {
    throw new Error("Adobe XD operation requires at least one selected node");
  }
}

function applyMutation(item, selection) {
  const params = item.params || {};

  if (item.method === "xd.queue.rectangle_create") {
    const node = new Rectangle();
    node.width = Math.max(1, safeNumber(params.width, 100));
    node.height = Math.max(1, safeNumber(params.height, 100));
    node.fill = new Color(params.fill || "#4F7CFF");
    if (params.name) node.name = String(params.name);
    selection.insertionParent.addChild(node);
    node.moveInParentCoordinates(safeNumber(params.x, 0), safeNumber(params.y, 0));
    return nodeInfo(node);
  }

  if (item.method === "xd.queue.text_create") {
    const node = new Text();
    node.text = params.text == null ? "Text" : String(params.text);
    if (params.fontSize != null) node.fontSize = Math.max(1, safeNumber(params.fontSize, 24));
    node.fill = new Color(params.fill || "#000000");
    if (params.name) node.name = String(params.name);
    selection.insertionParent.addChild(node);
    node.moveInParentCoordinates(safeNumber(params.x, 0), safeNumber(params.y, 0));
    return nodeInfo(node);
  }

  if (item.method === "xd.queue.selection_resize") {
    requireSelection(selection);
    const width = params.width == null ? null : Math.max(1, safeNumber(params.width, 1));
    const height = params.height == null ? null : Math.max(1, safeNumber(params.height, 1));
    if (width == null && height == null) {
      throw new Error("selection resize requires width and/or height");
    }
    const changed = [];
    for (let i = 0; i < selection.items.length; i += 1) {
      const node = selection.items[i];
      if (width != null) node.width = width;
      if (height != null) node.height = height;
      changed.push(nodeInfo(node));
    }
    return { changed };
  }

  if (item.method === "xd.queue.selection_fill") {
    requireSelection(selection);
    const color = new Color(params.fill || "#000000");
    const changed = [];
    for (let i = 0; i < selection.items.length; i += 1) {
      const node = selection.items[i];
      if (!("fill" in node)) {
        throw new Error(`selected node does not support fill: ${node.name || node.guid || i}`);
      }
      node.fill = color;
      changed.push(nodeInfo(node));
    }
    return { changed };
  }

  throw new Error(`unsupported queued XD mutation: ${item.method}`);
}

function applyPending() {
  if (pendingWrites.length === 0) return;

  const batch = pendingWrites.slice();
  pendingWrites = [];
  const results = {};

  try {
    application.editDocument(
      { editLabel: `MCP Adobe Bridge (${batch.length})` },
      function(selection) {
        for (let i = 0; i < batch.length; i += 1) {
          const item = batch[i];
          results[item.operationId] = applyMutation(item, selection);
        }
      }
    );

    for (let i = 0; i < batch.length; i += 1) {
      const item = batch[i];
      rememberOperation(item.operationId, {
        status: "applied",
        method: item.method,
        appliedAt: Date.now(),
        result: results[item.operationId]
      });
    }
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    for (let i = 0; i < batch.length; i += 1) {
      const item = batch[i];
      rememberOperation(item.operationId, {
        status: "failed",
        method: item.method,
        failedAt: Date.now(),
        error: message
      });
    }
  }

  renderStatus();
}

function clearPending(reason) {
  const batch = pendingWrites.slice();
  pendingWrites = [];
  for (let i = 0; i < batch.length; i += 1) {
    const item = batch[i];
    rememberOperation(item.operationId, {
      status: "rejected",
      method: item.method,
      rejectedAt: Date.now(),
      reason: reason || "queue cleared"
    });
  }
  renderStatus();
  return {
    status: "cleared",
    rejected_count: batch.length,
    pending_count: pendingWrites.length
  };
}

function rejectPending() {
  const batch = pendingWrites.slice();
  pendingWrites = [];
  for (let i = 0; i < batch.length; i += 1) {
    const item = batch[i];
    rememberOperation(item.operationId, {
      status: "rejected",
      method: item.method,
      rejectedAt: Date.now()
    });
  }
  renderStatus();
}

function dispatch(method, params) {
  if (method === "xd.health") {
    return {
      application: "xd",
      version: application.version,
      appLanguage: application.appLanguage,
      bridge: "connected",
      pending_count: pendingWrites.length,
      bridge_build: BRIDGE_BUILD
    };
  }

  if (method === "xd.document.info") {
    try { snapshot(scenegraph.selection, scenegraph.root); } catch (_) {}
    return latestSnapshot.document || { rootChildren: 0, insertionParent: null };
  }

  if (method === "xd.selection.get") {
    try { snapshot(scenegraph.selection, scenegraph.root); } catch (_) {}
    return { items: latestSnapshot.selection || [] };
  }

  if (method === "xd.queue.clear") {
    return clearPending(params && params.reason ? String(params.reason) : "MCP queue reset");
  }

  if (method === "xd.queue.status") {
    const operationId = params && params.operation_id ? String(params.operation_id) : "";
    if (!operationId) throw new Error("operation_id is required");
    return operationStatus[operationId] || { status: "unknown", operation_id: operationId };
  }

  if (
    method === "xd.queue.rectangle_create" ||
    method === "xd.queue.text_create" ||
    method === "xd.queue.selection_resize" ||
    method === "xd.queue.selection_fill"
  ) {
    return queueMutation(method, params || {});
  }

  throw new Error(`unsupported Adobe XD bridge method: ${method}`);
}

function send(payload) {
  if (!socket || socket.readyState !== 1) return;
  socket.send(JSON.stringify(payload));
}

function connect() {
  if (socket && (socket.readyState === 0 || socket.readyState === 1)) return;
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  try {
    socket = new WebSocket(BRIDGE_URL);
  } catch (_) {
    scheduleReconnect();
    renderStatus();
    return;
  }

  socket.onopen = function() {
    send({
      type: "hello",
      application: "xd",
      version: application.version,
      protocol: 1,
      bridgeBuild: BRIDGE_BUILD
    });
    renderStatus();
  };

  socket.onmessage = function(event) {
    let request;
    try {
      request = JSON.parse(event.data);
      const result = dispatch(request.method, request.params || {});
      send({ id: request.id, ok: true, result });
    } catch (error) {
      send({
        id: request && request.id ? request.id : null,
        ok: false,
        error: error && error.message ? error.message : String(error)
      });
    }
  };

  socket.onerror = function() {
    renderStatus();
  };

  socket.onclose = function() {
    renderStatus();
    scheduleReconnect();
  };
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(function() {
    reconnectTimer = null;
    connect();
  }, 2000);
}

function renderStatus() {
  if (!panel) return;
  const connection = panel.querySelector("#connection");
  const pending = panel.querySelector("#pending");
  if (connection) {
    connection.textContent = socket && socket.readyState === 1
      ? `Connected ${BRIDGE_URL}`
      : `Disconnected ${BRIDGE_URL}`;
  }
  if (pending) pending.textContent = `Pending approvals: ${pendingWrites.length}`;
}

function create() {
  panel = document.createElement("div");
  panel.innerHTML = `
    <style>
      .mcp-wrap { padding: 8px; }
      .mcp-row { margin: 6px 0; }
      .mcp-actions { display: flex; gap: 6px; flex-wrap: wrap; }
      .mcp-note { color: #777; font-size: 11px; }
    </style>
    <div class="mcp-wrap">
      <h3>MCP Adobe Bridge</h3>
      <div class="mcp-row" id="connection">Disconnected</div>
      <div class="mcp-row" id="pending">Pending approvals: 0</div>
      <div class="mcp-actions">
        <button id="reconnect">Reconnect</button>
        <button id="apply" autofocus uxp-variant="cta" uxp-edit-label="Apply MCP Adobe operations">Apply pending</button>
        <button id="reject">Reject pending</button>
      </div>
      <p class="mcp-note">Read requests use the latest XD panel snapshot. Write requests are queued and applied together with one explicit Apply click, as required by the XD plugin edit lifecycle.</p>
    </div>
  `;

  panel.querySelector("#reconnect").addEventListener("click", connect);
  panel.querySelector("#apply").addEventListener("click", applyPending);
  panel.querySelector("#reject").addEventListener("click", rejectPending);
  connect();
  renderStatus();
  return panel;
}

function show(rootNodeOrEvent) {
  const rootNode = rootNodeOrEvent && rootNodeOrEvent.node
    ? rootNodeOrEvent.node
    : rootNodeOrEvent;
  if (!panel) rootNode.appendChild(create());
  connect();
  renderStatus();
}

function update(selection, documentRoot) {
  snapshot(selection, documentRoot);
  renderStatus();
}

function connectCommand(selection, documentRoot) {
  snapshot(selection, documentRoot);
  connect();
  renderStatus();
}

function applyPendingCommand(selection, documentRoot) {
  if (pendingWrites.length === 0) {
    snapshot(selection, documentRoot);
    return;
  }

  const batch = pendingWrites.slice();
  pendingWrites = [];
  const results = {};

  try {
    for (let i = 0; i < batch.length; i += 1) {
      const item = batch[i];
      results[item.operationId] = applyMutation(item, selection);
    }

    for (let i = 0; i < batch.length; i += 1) {
      const item = batch[i];
      rememberOperation(item.operationId, {
        status: "applied",
        method: item.method,
        appliedAt: Date.now(),
        result: results[item.operationId]
      });
    }
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    for (let i = 0; i < batch.length; i += 1) {
      const item = batch[i];
      rememberOperation(item.operationId, {
        status: "failed",
        method: item.method,
        failedAt: Date.now(),
        error: message
      });
    }
    throw error;
  } finally {
    try { snapshot(scenegraph.selection, scenegraph.root); } catch (_) {
      snapshot(selection, documentRoot);
    }
    renderStatus();
  }
}

// Manifest v4 entrypoints are registered through UXP entrypoints.setup().
entrypoints.setup({
  plugin: {
    create() {
      connect();
    }
  },
  commands: {
    mcpAdobeConnect: connectCommand,
    mcpAdobeApply: applyPendingCommand
  },
  panels: {
    mcpAdobeBridge: {
      show,
      update
    }
  }
});
