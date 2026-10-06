# Adoption plan after 5-repository audit

Audit source: `docs/UPSTREAM_AUDIT.md`

Canonical product contract: `docs/PRODUCT_SPEC.md`

Blocking completion checklist: `docs/INTERACTIVE_MCP_CHECKLIST.md`

## Goal

Convert the verified upstream work into a single client-neutral Adobe Creative MCP gateway without reimplementing mature app control or inheriting unsafe behavior.

The gateway is not considered complete if it only lets an agent generate a large script, send it to Adobe, and export a file. The required product is a persistent conversational session in which ChatGPT/Claude can directly inspect and incrementally edit the document currently open in Photoshop, Illustrator, and XD through bounded MCP tools.

GitHub Actions/self-hosted runners remain CI/E2E infrastructure. They are not the primary end-user interaction path.

## Phase 1 — Photoshop + Illustrator

### Photoshop adapter

Upstream baseline: `alisaitteke/photoshop-mcp@ecd502c666f0e5b3889d3ef7bc42e5b3eb1119c2`

Adopt first:

- health/ping;
- capabilities/state/preview;
- document open/create/save/export;
- live active-document and selection inspection;
- layer/object/text operations;
- bounded shape/selection/transform/style/mask operations where supported;
- undo/history;
- recipe operations with one-history-state semantics;
- structured error codes and recovery hints;
- persistent session/reconnect behavior.

Do not expose by default:

- arbitrary `photoshop_execute_script` as the normal product interface;
- destructive/batch operations without an explicit policy classification;
- silent file overwrite;
- upstream telemetry as gateway telemetry.

### Illustrator adapter

Upstream baseline: `ie3jp/illustrator-mcp-server@57c5c101a5192c61535493f39b653e6f92b8eb29`

Adopt first:

- document info/structure;
- live active-document, artboard, and selection inspection;
- artboards;
- object and text creation/modification;
- selection and object lookup;
- transform, fill/stroke/style operations;
- bounded path/anchor/vector-geometry editing sufficient for real logo/design refinement;
- grouping/order/pathfinder or equivalent composition operations;
- save/export;
- preflight/design-token inspection;
- version targeting;
- timeout categories;
- persistent session/reconnect behavior.

Preserve:

- Zod/schema-level parameter validation;
- default protection against overwriting files;
- local-only application execution;
- explicit Windows/macOS platform abstraction.

Generated JSX/COM eval can remain as an implementation mechanism or privileged escape hatch, but a monolithic generated script is not sufficient to satisfy the interactive Illustrator product gates.

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
creative.document.preview
creative.selection.get
creative.object.list
creative.object.select
creative.object.create
creative.object.update
creative.object.delete
creative.object.transform
creative.text.create
creative.text.update
creative.asset.place
creative.undo
creative.redo
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
-> resolve live session/document/selection
-> discover capability
-> validate target/document/object
-> evaluate policy
-> execute bounded adapter operation
-> inspect returned state/error
-> verify postcondition/preview when possible
-> record audit result
```

Transport success alone is not PASS.

For conversational editing, a result is not product-complete if the system had to create a replacement document when the user intended to edit the currently open document.

## File safety contract

- Save-as/export destinations must be explicit.
- If the destination exists, reject unless overwrite was explicitly authorized.
- Temporary files stay under a gateway-owned temporary directory where possible.
- Batch operations must report per-item success/failure rather than only a global success flag.
- Incremental live edits must preserve unrelated user layers/objects/content.

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

For the interactive product, the live session must additionally resolve/refetch active document and selection state so human changes inside Adobe do not leave the AI mutating a stale target.

## Timeout/retry rule

Read-only calls may be retried if the adapter can prove they are idempotent.

For mutating calls:

1. timeout = `UNKNOWN`, not failure;
2. inspect actual application/document state;
3. only retry after determining the first attempt did not apply, or use an idempotency mechanism.

This rule is especially important for scripting hosts where killing the external process may not abort code already running inside the Adobe application.

## XD policy

The initial audited XD repositories did not provide a verified live desktop-write bridge, so the project must supply or adopt one.

The product target is now explicitly live XD interaction:

```text
persistent XD plugin/UXP bridge
-> read current document/artboard/selection
-> create/edit supported nodes/text/properties
-> reflect human selection changes back into MCP context
-> verify applied state/preview
```

If XD requires a user gesture or explicit approval for a mutation, that restriction must be exposed honestly as part of the MCP result/UX. It must not be hidden behind a false PASS.

## Phase gates

The detailed, fixed denominator is `docs/INTERACTIVE_MCP_CHECKLIST.md`. The gates below are summary gates only and must not be used to inflate completion percentages.

### Gate A — adapter contract

- [ ] Upstream snapshots represented in adapter metadata.
- [ ] Health/capability discovery implemented.
- [ ] Risk class attached to every exposed capability.
- [ ] Native arbitrary scripting default-deny/privileged escape hatch only.
- [ ] File overwrite default-deny.
- [ ] Persistent live-session contract represented.
- [ ] Active document/selection refresh represented.

### Gate B — Photoshop live interactive E2E

- [ ] Attach to the document already open in Photoshop.
- [ ] Read state and visual preview.
- [ ] Select/create/update bounded layer/object/text/shape operations.
- [ ] Perform successive incremental transforms/styles from chat.
- [ ] Human selection change is respected by the next command.
- [ ] Undo/redo verified.
- [ ] Save/export verified without replacing unrelated user work.
- [ ] Disconnect/restart/reconnect verified.
- [ ] Timeout ambiguity test.

### Gate C — Illustrator live interactive E2E

- [ ] Attach to the document already open in Illustrator.
- [ ] Read document/artboard/selection and visual state.
- [ ] Create/modify vector objects/text through bounded tools.
- [ ] Path/anchor or equivalent granular vector editing proven.
- [ ] Successive incremental transforms/fill/stroke/composition proven.
- [ ] Human selection change is respected by the next command.
- [ ] Undo/recovery verified.
- [ ] Save `.ai` and export SVG/PNG with verified outputs.
- [ ] Restart/reconnect verified.

### Gate D — XD live interactive E2E

- [ ] Persistent XD plugin/bridge connection.
- [ ] Read active document/artboard/selection.
- [ ] Human selection changes flow back into MCP context.
- [ ] Create and modify supported nodes/text/properties.
- [ ] Required user approval semantics are explicit and verified.
- [ ] Readback/preview confirms mutation.

### Gate E — client compatibility and final acceptance

Run the same gateway/adapters with:

- [ ] Claude MCP client.
- [ ] ChatGPT/OpenAI-compatible MCP client.

Then prove the final conversational acceptance sequence from `docs/PRODUCT_SPEC.md`: existing open document -> live state/selection -> multiple small edits -> human co-edit/selection change -> preview -> undo -> save/export, all in one persistent session and without GitHub Actions as the user command transport.

The adapter layer must remain unchanged between clients.

## Out of scope until the interactive initial scope passes

- Premiere Pro
- After Effects
- InDesign
- automatic arbitrary-script enablement
- completion claims based only on generated scripts/exported files
- treating CI/runner automation as the primary product interaction path
