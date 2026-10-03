# Architecture

## Principles

1. **Reuse before rewrite** — mature app-specific integrations are adapted, not reimplemented without evidence.
2. **Client-neutral MCP** — Claude, OpenAI clients, Cursor, and other MCP clients should use the same gateway contract.
3. **Capability discovery before execution** — agents query what is connected and supported instead of inventing operations.
4. **Common + native tools** — normalize universal operations but keep access to application-specific power.
5. **No false PASS** — execution success and verified application state are separate concepts.

## Core model

```text
MCP Client
   |
   v
Gateway
   |
   +--> Capability Registry
   |
   +--> Router
           |
           +--> PhotoshopAdapter
           +--> IllustratorAdapter
           +--> XDAdapter
           +--> future adapters
```

## Adapter contract

Each adapter reports:

- application identifier;
- connection state;
- application version when available;
- supported common capabilities;
- supported native capabilities;
- whether undo is available;
- whether writes are enabled.

The gateway resolves a requested capability only against adapters that explicitly advertise it.

## Planned MCP surfaces

### Common semantic surface

- `creative.document.open`
- `creative.document.create`
- `creative.document.save`
- `creative.document.export`
- `creative.selection.get`
- `creative.object.create`
- `creative.object.update`
- `creative.object.delete`
- `creative.object.transform`
- `creative.text.create`
- `creative.text.update`
- `creative.asset.place`
- `creative.undo`

### Native surface

- `photoshop.execute`
- `illustrator.execute`
- `xd.execute`

Native execution must be policy-gated and application-scoped.

## Transport strategy

The application bridge and MCP transport are intentionally separate concerns.

Typical desktop path:

```text
MCP client <-> gateway <-> local bridge/proxy <-> Adobe plugin/script host
```

The gateway should support stdio for local clients and a remote Streamable HTTP mode where a client requires it. The application-side bridge stays local unless there is a deliberate authenticated remote deployment.

## Reliability requirements for live adapters

Before a mutating capability is marked production-ready, it should have:

1. input validation;
2. explicit application/document targeting;
3. timeout and reconnect behavior;
4. observable error propagation;
5. post-operation verification where the Adobe API allows it;
6. undo/rollback metadata;
7. regression tests;
8. real Adobe end-to-end evidence.
