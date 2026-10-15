"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");

const prod = JSON.parse(fs.readFileSync("adobe-xd-plugin/manifest.json", "utf8"));
const experiment = JSON.parse(fs.readFileSync("experimental/mode2-xd-uxp/manifest.json", "utf8"));
const prodSource = fs.readFileSync("adobe-xd-plugin/main.js", "utf8");
const expSource = fs.readFileSync("experimental/mode2-xd-uxp/main.js", "utf8");
const installer = fs.readFileSync("scripts/stage_mode2_xd_experimental_plugin.ps1", "utf8");

assert.equal(prod.id, "MCPADB01");
assert.equal(experiment.id, "MCPADM2E");
assert.notEqual(prod.id, experiment.id);
assert.equal(experiment.host.app, "XD");
assert.equal(experiment.manifestVersion, 4);
assert.equal(experiment.main, "main.js");
assert.equal(experiment.entrypoints.length, 5);
assert.ok(experiment.entrypoints.some(x => x.id === "mcpAdobeMode2SelectFixture"));
assert.ok(experiment.entrypoints.some(x => x.id === "mcpAdobeMode2SelectStagedRect"));
assert.equal(experiment.entrypoints.every(x => !x.shortcut), true,
  "experimental plugin must not override production keyboard shortcuts");
assert.match(prodSource, /BRIDGE_URL = "ws:\/\/127\.0\.0\.1:8765"/);
assert.match(expSource, /BRIDGE_URL = "ws:\/\/127\.0\.0\.1:8766"/);
assert.match(expSource, /BRIDGE_BUILD = "xd-mode2-guarded-experimental-v1"/);
assert.match(installer, /MCPAdobeMode2Experiment/);
assert.match(installer, /MODE2_RELOAD_OR_ACTIVATION_PERFORMED=False/);
assert.match(installer, /MODE2_STAGE_EXISTING_DIFFERENT_CONTENT_NO_OVERWRITE/);
assert.doesNotMatch(installer, /Join-Path \$develop 'MCPAdobeBridge'\s*\n\s*Remove-Item/);
console.log("MODE2_DISTINCT_DISTRIBUTION_CONTRACT_PASS");
