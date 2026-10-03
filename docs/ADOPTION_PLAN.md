# Adoption plan after 5-repository audit

Audit source: `docs/UPSTREAM_AUDIT.md`

## Goal

Convert the verified upstream work into a single client-neutral Adobe Creative MCP gateway without reimplementing mature app control or inheriting unsafe behavior.

## Phase 1 — Photoshop + Illustrator

### Photoshop adapter

Upstream baseline: `alisaitteke/photoshop-mcp@ecd502c666f0e5b3889d3ef7bc42e5b3eb1119c2`

Adopt first:

- health/ping;
- capabilities/state/preview;
- document open/create/save/export;
- layer/object/text operations;
- undo/history;
- recipe operations with one-history-state semantics;
- structured error codes and recovery hints.

Do not expose by default:

- arbitrary `photoshop_execute_script`;
- destructive/batch operations without an explicit policy classification;
- silent file overwrite;
- upstream telemetry as gateway telemetry.

### Illustrator adapter

Upstream baseline: `ie3jp/illustrator-mcp-server@57c5c101a5192c61535493f39b653e6f92b8eb29`

Adopt first:

- document info/structure;
- artboards;
- object and text creation/modification;
- selection and object lookup;
- save/export;
- preflight/design-token inspection;
- version targeting;
- timeout categories.

Preserve:

- Zod/schema-level parameter validation;
- default protection against overwriting files;
- local-only application execution;
- explicit Windows/macOS platform abstraction.

## Unified capability model

The gateway should expose a common semantic surface when semantics genuinely match:

```text
creative.health
creative.capabilities
creative.document.info
creative.document.open
creative.document.create
creative.document.save
creative.document.export
creative.selection.get
creative.object.create
creative.object.update
creative.object.delete
creative.object.transform
creative.text.create
creative.text.update
creative.asset.place
creative.undo
```

Application-specific power remains available under native namespaces:

```text
photoshop.*
illustrator.*
xd.*
```

The common surface must not pretend that unlike operations are equivalent. If an operation cannot preserve semantics across apps, keep it native.

## Capability risk classes

Every mutating capability will be assigned one of these classes before it is enabled:

| Class | Meaning | Default policy |
|---|---|---|
| `read` | document/app inspection only | allow when app is connected |
| `write_reversible` | edit expected to be undoable | allow after target validation |
| `file_write` | save/export/create filesystem output | require explicit path and no implicit overwrite |
| `destructive` | flatten/merge/delete/close-without-save or equivalent | require explicit intent |
| `native_script` | arbitrary app scripting/eval surface | deny by default; explicit privileged enable only |
| `external_ai` | operation consumes remote Adobe/other AI service | require capability/entitlement disclosure |

## Execution contract

A gateway write is considered PASS only when all available checks succeed:

```text
resolve application
-> discover capability
-> validate target/document
-> evaluate policy
-> execute adapter operation
-> inspect returned state/error
-> verify postcondition when possible
-> record audit result
```

Transport success alone is not PASS.

## File safety contract

- Save-as/export destinations must be explicit.
- If the destination exists, reject unless overwrite was explicitly authorized.
- Temporary files stay under a gateway-owned temporary directory where possible.
- Batch operations must report per-item success/failure rather than only a global success flag.

## Connection contract

Adapters must report at least:

```json
{
  "application": "photoshop",
  "connected": true,
  "version": "...",
  "transport": "...",
  "upstream": {
    "repository": "...",
    "snapshot": "..."
  },
  "writes_enabled": true,
  "undo_supported": true
}
```

Health and connection state are explicit. An adapter must not convert a timeout into a generic success or silently retry a mutating command after an ambiguous timeout.

## Timeout/retry rule

Read-only calls may be retried if the adapter can prove they are idempotent.

For mutating calls:

1. timeout = `UNKNOWN`, not failure;
2. inspect actual application/document state;
3. only retry after determining the first attempt did not apply, or use an idempotency mechanism.

This rule is especially important for scripting hosts where killing the external process may not abort code already running inside the Adobe application.

## XD policy

The two audited XD repositories parse XD files/share data; neither is a verified live desktop write bridge.

Current XD scope:

```text
read/parse design document
extract artboards/specs/tokens
optionally generate code/assets through gateway-controlled output paths
```

Not yet claimed:

```text
create/edit/delete nodes inside a running Adobe XD application
```

A real XD write adapter requires either a separately verified plugin/UXP bridge or a new implementation.

## Phase gates

### Gate A — adapter contract

- [ ] Upstream snapshots represented in adapter metadata.
- [ ] Health/capability discovery implemented.
- [ ] Risk class attached to every exposed capability.
- [ ] Native arbitrary scripting default-deny.
- [ ] File overwrite default-deny.

### Gate B — Photoshop real E2E

- [ ] Windows Photoshop detected.
- [ ] Read state.
- [ ] Create document.
- [ ] Create/update text/layer.
- [ ] Save to new path.
- [ ] Export to new path.
- [ ] Undo verified.
- [ ] Disconnect/restart/reconnect verified.
- [ ] Timeout ambiguity test.

### Gate C — Illustrator real E2E

- [ ] Windows Illustrator detected.
- [ ] Read document structure.
- [ ] Create artboard/object/text.
- [ ] Modify object.
- [ ] Save to new path.
- [ ] Export to new path.
- [ ] Existing-output rejection verified.
- [ ] Restart/reconnect verified.

### Gate D — client compatibility

Run the same gateway build with:

- [ ] Claude MCP client.
- [ ] OpenAI/Codex MCP client.

The adapter layer must remain unchanged between clients.

## Out of scope until Phase 1 passes

- Premiere Pro
- After Effects
- InDesign
- remote/non-local Adobe application control
- automatic arbitrary-script enablement
- production claims for XD editing
