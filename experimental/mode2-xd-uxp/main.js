const application = require("application");
const { entrypoints } = require("uxp");
const scenegraph = require("scenegraph");
const { Rectangle, Ellipse, Path, Text, Color } = scenegraph;

// Dedicated experimental listener. The production bridge stays on port 8765.
const BRIDGE_URL = "ws://127.0.0.1:8766";
const STATUS_LIMIT = 200;
const BRIDGE_BUILD = "xd-mode2-guarded-experimental-v1";

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
let stagedDisposableSelection = null;

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

// Read-only scenegraph snapshot. All node bounds are global canvas coordinates.
// This never calls application.editDocument and never changes selection.
function xdScenegraphSnapshot() {
  const root = scenegraph.root;
  if (!root || !root.guid) {
    throw new Error("XD root has no stable identity; scenegraph unavailable");
  }
  const visited = {};
  let count = 0;
  function walk(node, depth) {
    if (++count > 20000 || depth > 100) throw new Error("XD scenegraph limit exceeded");
    const id = node && node.guid;
    if (!id || visited[id]) throw new Error("XD scenegraph missing/duplicate guid");
    visited[id] = true;
    let bounds;
    try {
      const b = node.globalBounds;
      if (b && Number.isFinite(b.x) && Number.isFinite(b.y) &&
          Number.isFinite(b.width) && Number.isFinite(b.height) &&
          b.width > 0 && b.height > 0) {
        bounds = {left:b.x, top:b.y, right:b.x+b.width, bottom:b.y+b.height};
      }
    } catch (_) {}
    const children = [];
    if (node.children) {
      for (let i=0; i<node.children.length; i++) children.push(walk(node.children.at(i),depth+1));
    }
    return {id, name:node.name || "", type:node.constructor && node.constructor.name || "SceneNode",
      visible:node.visible !== false, locked:node.locked === true,
      bounds: bounds || null, children};
  }
  const nodes = [];
  for (let i=0; i<root.children.length; i++) nodes.push(walk(root.children.at(i),0));
  return {document_id:String(root.guid), complete:true, coordinate_space:"global",
    nodes, node_count:count};
}

// A document-coordinate frame derived from artboards, not desktop pixels.
// The preview must be a full-frame image of this rectangle.
function xdCanvasFrame() {
  const root=scenegraph.root;
  if(!root || !root.guid || !root.children)throw new Error("XD root unavailable");
  let left=Infinity,top=Infinity,right=-Infinity,bottom=-Infinity,count=0;
  for(let i=0;i<root.children.length;i++){
    const node=root.children.at(i);
    if(!node || !node.guid)continue;
    const type=node.constructor && node.constructor.name || "";
    if(type!=="Artboard")continue;
    const b=node.globalBounds;
    if(!b || ![b.x,b.y,b.width,b.height].every(Number.isFinite) || b.width<=0 || b.height<=0)continue;
    count++;
    left=Math.min(left,b.x);top=Math.min(top,b.y);
    right=Math.max(right,b.x+b.width);bottom=Math.max(bottom,b.y+b.height);
  }
  if(!count)throw new Error("XD artboard frame unavailable");
  return {document_id:String(root.guid),coordinate_space:"global",
    left,top,right,bottom,width:right-left,height:bottom-top,artboard_count:count};
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

// Read-only prepare on WebSocket, actual selection only via a user-invoked
// XD menu command. This intentionally rejects all existing Panda components.
const MODE2_DISPOSABLE_RECT_NAME = "MODE2_DISPOSABLE_FILL_RECT_GUID_E2E";
const MODE2_DISPOSABLE_DOC = "98d6635b-3767-4254-b200-ec8442b69ad2";

function attestDisposableRect(params) {
  const root = scenegraph.root;
  if (!root || String(root.guid) !== MODE2_DISPOSABLE_DOC ||
      !params || String(params.document_id) !== MODE2_DISPOSABLE_DOC ||
      params.name !== MODE2_DISPOSABLE_RECT_NAME ||
      params.isolated_test_copy !== true ||
      typeof params.node_id !== "string" ||
      !/^[0-9a-fA-F-]{36}$/.test(params.node_id)) {
    throw new Error("MODE2_DISPOSABLE_RECT_IDENTITY_REJECTED");
  }
  const expected = params.bounds;
  if (!expected || Object.keys(expected).sort().join(",") !== "bottom,left,right,top" ||
      ![expected.left,expected.top,expected.right,expected.bottom].every(Number.isFinite) ||
      expected.right <= expected.left || expected.bottom <= expected.top) {
    throw new Error("MODE2_DISPOSABLE_RECT_BOUNDS_REJECTED");
  }
  if (pendingWrites.length !== 0) throw new Error("MODE2_SELECTION_PENDING_WRITE_QUEUE");
  const graph = xdScenegraphSnapshot();
  if (graph.node_count !== 34 || graph.document_id !== MODE2_DISPOSABLE_DOC) {
    throw new Error("MODE2_DISPOSABLE_RECT_SCENE_NOT_PLUS_ONE");
  }
  const node = scenegraph.getNodeByGUID(params.node_id);
  if (!node || String(node.guid) !== params.node_id ||
      node.name !== MODE2_DISPOSABLE_RECT_NAME ||
      !node.constructor || node.constructor.name !== "Rectangle" ||
      node.visible === false || node.locked === true || !("fill" in node)) {
    throw new Error("MODE2_DISPOSABLE_RECT_WRONG_NODE");
  }
  const b = node.globalBounds;
  if (!b || ![b.x,b.y,b.width,b.height].every(Number.isFinite) ||
      b.width <= 0 || b.height <= 0 ||
      Math.abs(b.x - expected.left) > .01 ||
      Math.abs(b.y - expected.top) > .01 ||
      Math.abs(b.x + b.width - expected.right) > .01 ||
      Math.abs(b.y + b.height - expected.bottom) > .01) {
    throw new Error("MODE2_DISPOSABLE_RECT_BOUNDS_CHANGED");
  }
  return node;
}

function stageDisposableSelection(params) {
  if (stagedDisposableSelection) throw new Error("MODE2_SELECTION_ALREADY_STAGED");
  // A preparation does not change XD selection or native scenegraph.
  attestDisposableRect(params);
  stagedDisposableSelection = {
    document_id: params.document_id,
    node_id: params.node_id,
    name: params.name,
    isolated_test_copy: true,
    bounds: {...params.bounds},
    expires_at: Date.now() + 90000
  };
  return {status:"awaiting_user_menu", approval_required:true,
    node_id:params.node_id, expires_in_seconds:90};
}

function selectStagedDisposableCommand(selection, documentRoot) {
  const request = stagedDisposableSelection;
  stagedDisposableSelection = null; // one-shot, including failed requests
  if (!request || Date.now() > request.expires_at ||
      !documentRoot || String(documentRoot.guid) !== MODE2_DISPOSABLE_DOC) {
    throw new Error("MODE2_STAGED_SELECTION_EXPIRED_OR_WRONG_DOC");
  }
  const node = attestDisposableRect(request);
  selection.items = [node]; // only in XD's explicit plugin command context
  const proof = mode2InspectSelectedNode(request);
  if (proof.selection_count !== 1 || proof.node_id !== request.node_id) {
    throw new Error("MODE2_DISPOSABLE_SELECTION_NOT_EXACT");
  }
  snapshot(selection, documentRoot);
  return {selected:true, document_id:proof.document_id, node_id:proof.node_id,
    bounds:proof.bounds};
}

// Mode 2 guarded node ownership. Reads only; never changes the active selection.
function mode2InspectSelectedNode(params) {
  const root = scenegraph.root;
  if (!root || !root.guid || String(root.guid) !== String(params.document_id || "")) {
    throw new Error("MODE2_DOCUMENT_ID_MISMATCH");
  }
  const items = scenegraph.selection && scenegraph.selection.items;
  if (!items || items.length !== 1) throw new Error("MODE2_SELECTION_NOT_UNIQUE");
  const node = items.at(0);
  if (!node || !node.guid || String(node.guid) !== String(params.node_id || "")) {
    throw new Error("MODE2_NODE_ID_MISMATCH");
  }
  if (node.visible === false || node.locked === true || !("fill" in node)) {
    throw new Error("MODE2_NODE_NOT_EDITABLE");
  }
  const b = node.globalBounds, expected = params.bounds;
  if (!b || !expected || ![b.x,b.y,b.width,b.height].every(Number.isFinite) ||
      ![expected.left,expected.top,expected.right,expected.bottom].every(Number.isFinite) ||
      Math.abs(b.x-expected.left)>0.01 || Math.abs(b.y-expected.top)>0.01 ||
      Math.abs(b.x+b.width-expected.right)>0.01 ||
      Math.abs(b.y+b.height-expected.bottom)>0.01) {
    throw new Error("MODE2_NODE_BOUNDS_CHANGED");
  }
  return {document_id:String(root.guid),node_id:String(node.guid),
    bounds:{left:b.x,top:b.y,right:b.x+b.width,bottom:b.y+b.height},
    locked:false,visible:true,selection_count:1};
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
    // MCP x/y are global canvas positions, not insertion-parent offsets.
    // Artboards may be located away from (0,0); absolute placement is required.
    const desiredX = safeNumber(params.x, NaN);
    const desiredY = safeNumber(params.y, NaN);
    const before = node.globalBounds;
    if (![desiredX, desiredY].every(Number.isFinite) ||
        !before || ![before.x, before.y, before.width, before.height].every(Number.isFinite) ||
        !(before.width > 0) || !(before.height > 0)) {
      throw new Error("XD shape has invalid global placement geometry");
    }
    node.moveInParentCoordinates(desiredX - before.x, desiredY - before.y);
    const placed = node.globalBounds;
    if (!placed || Math.abs(placed.x - desiredX) > 2 ||
        Math.abs(placed.y - desiredY) > 2) {
      throw new Error("XD shape global placement verification failed");
    }
    return nodeInfo(node);
  }

  if (item.method === "xd.queue.path_create") {
    // A single editable vector component per queued MCP write. Never accept
    // imported SVG documents or arbitrary script/markup as pathData.
    const data = params.pathData;
    const x = Number(params.x);
    const y = Number(params.y);
    if (typeof data !== "string" || data.length < 6 || data.length > 8192 ||
        !/^M[ ,.0-9+-]/i.test(data) ||
        !/^[-+0-9eE., MmLlHhVvCcSsQqTtAaZz]+$/.test(data) ||
        ![x,y].every(Number.isFinite) ||
        Math.abs(x) > 100000 || Math.abs(y) > 100000) {
      throw new Error("XD path requires bounded SVG path commands and finite global position");
    }
    const node = new Path();
    node.pathData = data;
    node.fill = new Color(params.fill || "#FFFFFF");
    if (params.name) node.name = String(params.name).slice(0, 160);
    selection.insertionParent.addChild(node);
    const initial = node.globalBounds;
    if (!initial || ![initial.x, initial.y, initial.width, initial.height].every(Number.isFinite) ||
        !(initial.width > 0) || !(initial.height > 0) ||
        initial.width > 20000 || initial.height > 20000) {
      throw new Error("XD vector path has invalid or degenerate bounds");
    }
    node.moveInParentCoordinates(x - initial.x, y - initial.y);
    const actual = node.globalBounds;
    if (!actual || Math.abs(actual.x - x) > 2 || Math.abs(actual.y - y) > 2) {
      throw new Error("XD path global bounds could not be verified");
    }
    return { ...nodeInfo(node), globalBounds: {
      left:actual.x, top:actual.y, right:actual.x+actual.width,
      bottom:actual.y+actual.height
    } };
  }

  if (item.method === "xd.queue.ellipse_create") {
    const node = new Ellipse();
    // Adobe XD's Ellipse API exposes radii, not writable width/height.
    const width = Math.max(1, safeNumber(params.width, 100));
    const height = Math.max(1, safeNumber(params.height, 100));
    node.radiusX = width / 2;
    node.radiusY = height / 2;
    node.fill = new Color(params.fill || "#FFFFFF");
    if (params.name) node.name = String(params.name);
    selection.insertionParent.addChild(node);
    const initial = node.globalBounds;
    if (!initial || !(initial.width > 0) || !(initial.height > 0)) {
      throw new Error("XD Ellipse has zero visible geometry after radius assignment");
    }
    node.moveInParentCoordinates(
      safeNumber(params.x, 0) - initial.x,
      safeNumber(params.y, 0) - initial.y
    );
    const measured = node.globalBounds;
    if (!measured || Math.abs(measured.width - width) > 1 ||
        Math.abs(measured.height - height) > 1) {
      throw new Error("XD Ellipse rendered size differs from requested size");
    }
    return nodeInfo(node);
  }

  if (item.method === "xd.queue.rectangle_position_repair") {
    // Read-before-write optimistic concurrency: repair one known shifted
    // Rectangle GUID only. Repeated or stale commands fail closed.
    const documentId = String(params.document_id || "");
    const guid = String(params.guid || "");
    const name = String(params.name || "");
    const x = Number(params.x), y = Number(params.y);
    const beforeX = Number(params.beforeX), beforeY = Number(params.beforeY);
    if (!/^[a-f0-9-]{36}$/.test(guid) || !documentId || !name ||
        !scenegraph.root || scenegraph.root.guid !== documentId ||
        ![x,y,beforeX,beforeY].every(Number.isFinite) ||
        Math.abs(x)>100000 || Math.abs(y)>100000) {
      throw new Error("XD rectangle repair document identity or input is invalid");
    }
    const matches = [];
    function find(node) {
      if (!node) return;
      if (node.guid === guid) matches.push(node);
      if (node.children) {
        for (let i=0; i<node.children.length; i++) find(node.children.at(i));
      }
    }
    find(scenegraph.root);
    if (matches.length!==1 || !(matches[0] instanceof Rectangle) ||
        matches[0].name!==name) {
      throw new Error("XD rectangle repair target GUID/name/type mismatch");
    }
    const node=matches[0];
    const actualBefore=node.globalBounds;
    if (!actualBefore || ![actualBefore.x,actualBefore.y,
        actualBefore.width,actualBefore.height].every(Number.isFinite) ||
        !(actualBefore.width>0) || !(actualBefore.height>0) ||
        Math.abs(actualBefore.x-beforeX)>1 || Math.abs(actualBefore.y-beforeY)>1 ||
        (Math.abs(actualBefore.x-x)<=1 && Math.abs(actualBefore.y-y)<=1)) {
      throw new Error("XD rectangle repair source changed or already fixed; no replay");
    }
    node.moveInParentCoordinates(x-actualBefore.x,y-actualBefore.y);
    const after=node.globalBounds;
    if (!after || Math.abs(after.x-x)>2 || Math.abs(after.y-y)>2 ||
        Math.abs(after.width-actualBefore.width)>1 ||
        Math.abs(after.height-actualBefore.height)>1) {
      throw new Error("XD rectangle repair readback mismatch");
    }
    return {guid:node.guid,name:node.name,
      before:{x:actualBefore.x,y:actualBefore.y},after:{x:after.x,y:after.y},
      width:after.width,height:after.height,repaired:true};
  }

  if (item.method === "xd.queue.ellipse_geometry_repair") {
    const guid = String(params.guid || "");
    const name = String(params.name || "");
    const expectedDocument = String(params.document_id || "");
    if (!/^[a-f0-9-]{36}$/.test(guid) || !name || !expectedDocument ||
        !scenegraph.root || scenegraph.root.guid !== expectedDocument) {
      throw new Error("XD geometry repair requires exact node/document identity");
    }
    const matches = [];
    function visit(parent) {
      if (!parent) return;
      if (parent.guid === guid) matches.push(parent);
      if (parent.children) {
        for (let i = 0; i < parent.children.length; i += 1) {
          visit(parent.children.at(i));
        }
      }
    }
    visit(scenegraph.root);
    if (matches.length !== 1 || !(matches[0] instanceof Ellipse) ||
        matches[0].name !== name) {
      throw new Error("XD repair target is missing, ambiguous or not an Ellipse");
    }
    const node = matches[0];
    if (node.radiusX !== 0 || node.radiusY !== 0) {
      throw new Error("XD target already has nonzero radii: read state, do not repeat repair");
    }
    const width = safeNumber(params.width, NaN);
    const height = safeNumber(params.height, NaN);
    const x = safeNumber(params.x, NaN);
    const y = safeNumber(params.y, NaN);
    if (![width, height, x, y].every(Number.isFinite) ||
        !(width > 0) || !(height > 0) || width > 1500 || height > 1500) {
      throw new Error("XD ellipse geometry repair has invalid bounded dimensions");
    }
    node.radiusX = width / 2;
    node.radiusY = height / 2;
    const beforeMove = node.globalBounds;
    if (!beforeMove || beforeMove.width < 1 || beforeMove.height < 1) {
      throw new Error("XD repair did not produce visible ellipse geometry");
    }
    node.moveInParentCoordinates(x - beforeMove.x, y - beforeMove.y);
    const after = node.globalBounds;
    if (!after || Math.abs(after.width - width) > 1 ||
        Math.abs(after.height - height) > 1 ||
        Math.abs(after.x - x) > 2 || Math.abs(after.y - y) > 2) {
      throw new Error("XD repaired ellipse bounds differ from intended canvas geometry");
    }
    return {guid: node.guid, name: node.name, bounds: {
      left: after.x, top: after.y, width: after.width, height: after.height
    }, repaired: true};
  }

  if (item.method === "xd.queue.text_create") {
    const node = new Text();
    node.text = params.text == null ? "Text" : String(params.text);
    if (params.fontSize != null) node.fontSize = Math.max(1, safeNumber(params.fontSize, 24));
    node.fill = new Color(params.fill || "#000000");
    if (params.name) node.name = String(params.name);
    selection.insertionParent.addChild(node);
    // MCP x/y are global canvas positions, not insertion-parent offsets.
    // Artboards may be located away from (0,0); absolute placement is required.
    const desiredX = safeNumber(params.x, NaN);
    const desiredY = safeNumber(params.y, NaN);
    const before = node.globalBounds;
    if (![desiredX, desiredY].every(Number.isFinite) ||
        !before || ![before.x, before.y, before.width, before.height].every(Number.isFinite) ||
        !(before.width > 0) || !(before.height > 0)) {
      throw new Error("XD shape has invalid global placement geometry");
    }
    node.moveInParentCoordinates(desiredX - before.x, desiredY - before.y);
    const placed = node.globalBounds;
    if (!placed || Math.abs(placed.x - desiredX) > 2 ||
        Math.abs(placed.y - desiredY) > 2) {
      throw new Error("XD shape global placement verification failed");
    }
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

  if (item.method === "xd.queue.mode2_fill") {
    const inspected=mode2InspectSelectedNode(params);
    if (params.isolated_test_copy !== true || params.user_confirmed !== true ||
        !/^#[0-9a-fA-F]{6}$/.test(params.fill || "")) {
      throw new Error("MODE2_COPY_CONFIRMATION_OR_COLOR_MISSING");
    }
    const target=selection.items.at(0);
    target.fill=new Color(params.fill);
    return {node_id:inspected.node_id,document_id:inspected.document_id,bounds:inspected.bounds};
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

  if (method === "xd.canvas.frame") {
    return xdCanvasFrame();
  }

  if (method === "xd.scenegraph.snapshot") {
    return xdScenegraphSnapshot();
  }

  if (method === "xd.mode2.node.inspect") return mode2InspectSelectedNode(params || {});
  if (method === "xd.mode2.selection.stage_disposable") return stageDisposableSelection(params || {});

  if (method === "xd.selection.get") {
    try { snapshot(scenegraph.selection, scenegraph.root); } catch (_) {}
    return { items: latestSnapshot.selection || [] };
  }

  if (method === "xd.export.png") return exportPandaPng(params || {});

  if (method === "xd.queue.clear") {
    return clearPending(params && params.reason ? String(params.reason) : "MCP queue reset");
  }

  if (method === "xd.queue.status") {
    const operationId = params && params.operation_id ? String(params.operation_id) : "";
    if (!operationId) throw new Error("operation_id is required");
    return operationStatus[operationId] || { status: "unknown", operation_id: operationId };
  }

  // Reject an unverified Mode 2 operation BEFORE queueing. Revalidate again at
  // Apply time via mode2InspectSelectedNode to catch selection/document changes.
  // These flags do NOT attest the native copy's on-disk provenance.
  if (method === "xd.queue.mode2_fill") {
    const p = params || {};
    if (p.isolated_test_copy !== true || p.user_confirmed !== true ||
        !/^#[0-9a-fA-F]{6}$/.test(p.fill || "")) {
      throw new Error("MODE2_COPY_CONFIRMATION_OR_COLOR_MISSING");
    }
    if (pendingWrites.length !== 0) {
      throw new Error("MODE2_QUEUE_MUST_BE_EMPTY");
    }
    mode2InspectSelectedNode(p);
    return queueMutation(method, p);
  }

  if (
    method === "xd.queue.rectangle_create" ||
    method === "xd.queue.path_create" ||
    method === "xd.queue.ellipse_create" ||
    method === "xd.queue.rectangle_position_repair" ||
    method === "xd.queue.ellipse_geometry_repair" ||
    method === "xd.queue.text_create" ||
    method === "xd.queue.selection_resize" ||
    method === "xd.queue.selection_fill"
  ) {
    return queueMutation(method, params || {});
  }

  throw new Error(`unsupported Adobe XD bridge method: ${method}`);
}

async function exportPandaPng(params) {
  // A real XD rendition from its actual scenegraph, never an imported image.
  const filename = String((params && params.filename) || "");
  if (!/^MCP_Mode1_Panda_XD_[A-Za-z0-9_-]+\.png$/.test(filename)) {
    throw new Error("export filename must be a bounded unique panda PNG");
  }
  const root = scenegraph.root;
  let artboard = null;
  for (let i = 0; root && root.children && i < root.children.length; i += 1) {
    const node = root.children.at(i);
    if (node && node.constructor && node.constructor.name === "Artboard") {
      artboard = node;
      break;
    }
  }
  if (!artboard) throw new Error("XD has no artboard for PNG rendition");
  const fs = require("uxp").storage.localFileSystem;
  const folder = await fs.getDataFolder();
  const file = await folder.createFile(filename, {overwrite: false});
  await application.createRenditions([{
    node: artboard,
    outputFile: file,
    type: application.RenditionType.PNG,
    scale: 1
  }]);
  return {status: "exported", filename, nativePath: file.nativePath, artboardGuid: artboard.guid};
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
      Promise.resolve(dispatch(request.method, request.params || {}))
        .then(result => send({ id: request.id, ok: true, result }))
        .catch(error => send({ id: request.id, ok: false,
          error: error && error.message ? error.message : String(error) }));
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

// This experiment selects only the already-attested Panda Right Ear fixture.
// It is a user-invoked XD menu command, never a WebSocket-triggered edit.
// Selecting is not permission to modify the Panda node or original document.
const MODE2_SELECTION_FIXTURE = Object.freeze({
  document_id: "98d6635b-3767-4254-b200-ec8442b69ad2",
  node_id: "130fdb64-c691-4374-ab46-66fd3f9e077c",
  name: "11 XD Panda Right Ear",
  bounds: Object.freeze({left: 484, top: 166, right: 584, bottom: 280})
});

function selectMode2FixtureCommand(selection, documentRoot) {
  const fixture = MODE2_SELECTION_FIXTURE;
  if (!documentRoot || String(documentRoot.guid) !== fixture.document_id ||
      !scenegraph.root || String(scenegraph.root.guid) !== fixture.document_id) {
    throw new Error("MODE2_FIXTURE_DOCUMENT_NOT_EXACT");
  }
  if (pendingWrites.length !== 0) throw new Error("MODE2_FIXTURE_PENDING_QUEUE_NONEMPTY");
  const node = scenegraph.getNodeByGUID(fixture.node_id);
  if (!node || String(node.guid) !== fixture.node_id ||
      String(node.name) !== fixture.name ||
      !node.constructor || node.constructor.name !== "Ellipse" ||
      node.visible === false || node.locked === true ||
      !("fill" in node)) {
    throw new Error("MODE2_FIXTURE_IDENTITY_OR_TYPE_MISMATCH");
  }
  const b = node.globalBounds, expected = fixture.bounds;
  if (!b || ![b.x,b.y,b.width,b.height].every(Number.isFinite) ||
      b.width <= 0 || b.height <= 0 ||
      Math.abs(b.x - expected.left) > 0.01 ||
      Math.abs(b.y - expected.top) > 0.01 ||
      Math.abs(b.x + b.width - expected.right) > 0.01 ||
      Math.abs(b.y + b.height - expected.bottom) > 0.01) {
    throw new Error("MODE2_FIXTURE_BOUNDS_MISMATCH");
  }
  // Called directly from XD's explicit Plugins menu command.
  // Adobe XD checks that this node is in the current edit context.
  selection.items = [node];
  const selected = selection.items;
  if (!selected || selected.length !== 1 ||
      String(selected[0].guid) !== fixture.node_id) {
    throw new Error("MODE2_FIXTURE_SELECTION_NOT_CONFIRMED");
  }
  snapshot(selection, documentRoot);
  renderStatus();
  return {document_id: fixture.document_id, node_id: fixture.node_id, selected: true};
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
    mcpAdobeApply: applyPendingCommand,
    mcpAdobeMode2SelectFixture: selectMode2FixtureCommand,
    mcpAdobeMode2SelectStagedRect: selectStagedDisposableCommand
  },
  panels: {
    mcpAdobeBridge: {
      show,
      update
    }
  }
});
