# Architecture

Canonical product contract: `docs/PRODUCT_SPEC.md`

Blocking completion checklist: `docs/INTERACTIVE_MCP_CHECKLIST.md`

If an implementation convenience conflicts with the live interactive product contract, the product contract wins.

## Principles

1. **Reuse before rewrite** — mature app-specific integrations are adapted, not reimplemented without evidence.
2. **Client-neutral MCP** — Claude, OpenAI clients, Cursor, and other MCP clients should use the same gateway contract.
3. **Capability discovery before execution** — agents query what is connected and supported instead of inventing operations.
4. **Common + native tools** — normalize universal operations but keep access to application-specific power.
5. **No false PASS** — execution success and verified application state are separate concepts.
6. **Interactive first** — the product is persistent conversational control of the live Adobe document; CI/runner automation is validation infrastructure, not the end-user command transport.
7. **Granular control over monolithic scripts** — bounded semantic/native tools are the normal interaction surface. Arbitrary script execution is a privileged escape hatch only.
8. **Bidirectional context** — the gateway must observe/refetch document and selection state changed by the human inside Adobe, not only send commands into Adobe.

## Core model

```text
MCP Client
   |
   v
Gateway
   |
   +--> Session / live context
   |       +--> active application
   |       +--> active document/artboard
   |       +--> current selection
   |       +--> preview/state refresh
   |
   +--> Capability Registry
   |
   +--> Router
           |
           +--> PhotoshopAdapter <--> persistent Photoshop bridge <--> Photoshop
           +--> IllustratorAdapter <--> persistent Illustrator bridge <--> Illustrator
           +--> XDAdapter <--> persistent XD plugin/bridge <--> XD
           +--> future adapters
```

The target interaction loop is:

```text
user instruction
-> bounded MCP tool
-> live Adobe mutation
-> state/preview verification
-> next user instruction in the same session
```

The following is testing/automation only and cannot be treated as the product interaction loop:

```text
user -> generated script -> GitHub Actions/self-hosted runner -> Adobe -> exported artifact
```

## Adapter contract

Each adapter reports:

- application identifier;
- connection state;
- application version when available;
- supported common capabilities;
- supported native capabilities;
- whether undo is available;
- whether writes are enabled;
- live readiness;
- active document/selection context when the host allows it;
- reconnect/state-refresh behavior.

The gateway resolves a requested capability only against adapters that explicitly advertise it.

## Planned MCP surfaces

### Common semantic surface

- `creative.health`
- `creative.capabilities`
- `creative.document.info`
- `creative.document.open`
- `creative.document.create`
- `creative.document.save`
- `creative.document.export`
- `creative.document.preview`
- `creative.selection.get`
- `creative.object.list`
- `creative.object.select`
- `creative.object.create`
- `creative.object.update`
- `creative.object.delete`
- `creative.object.transform`
- `creative.text.create`
- `creative.text.update`
- `creative.asset.place`
- `creative.undo`
- `creative.redo`

### Native surface

Application-specific capabilities stay explicit where semantics differ, for example:

- `photoshop.layer.*`, `photoshop.selection.*`, `photoshop.mask.*`, `photoshop.*`;
- `illustrator.path.*`, `illustrator.anchor.*`, `illustrator.pathfinder.*`, `illustrator.*`;
- `xd.selection.*`, `xd.node.*`, `xd.*`.

Native arbitrary execution such as `photoshop.execute_script`, generated JSX, COM eval, or equivalent must be policy-gated and must not be the primary product API.

## Transport strategy

The application bridge and MCP transport are intentionally separate concerns.

Target desktop path:

```text
ChatGPT / Claude
      <-> MCP transport
      <-> gateway persistent session
      <-> local bridge/plugin
      <-> active Adobe application/document
```

The gateway should support stdio for local clients and a remote Streamable HTTP mode where a client requires it. The application-side bridge stays local unless there is a deliberate authenticated remote deployment.

GitHub Actions/self-hosted runners remain appropriate for CI, compatibility, installer, regression, and unattended E2E. They are not an acceptable substitute for persistent interactive transport.

## Reliability requirements for live adapters

Before a mutating capability is marked production-ready, it must have:

1. input validation;
2. explicit application/document/object targeting;
3. persistent-session behavior appropriate to the host;
4. timeout and reconnect behavior;
5. observable error propagation;
6. post-operation verification where the Adobe API allows it;
7. state/preview refresh after material edits;
8. undo/rollback metadata;
9. regression tests;
10. real Adobe end-to-end evidence using the document currently open in the host where applicable;
11. evidence that human-made selection/document changes do not leave the AI mutating stale context;
12. evidence required by `docs/INTERACTIVE_MCP_CHECKLIST.md`.
