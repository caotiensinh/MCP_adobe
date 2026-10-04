# Adobe application readiness

`AdapterInfo.connected` is retained as a transport-level compatibility field. It means the downstream MCP/WebSocket transport is alive; it is not evidence that the Adobe desktop application can execute work.

Built-in adapters declare `readiness_probe="creative.health"`. Before any non-read capability is routed, the registry fail-closes on an application-level health probe:

- Photoshop reuses upstream `photoshop_ping`, which only reports success after a script runs inside Photoshop.
- Illustrator reuses upstream `list_fonts` with `limit=1`; this executes inside Illustrator and does not require an open document.
- Adobe XD reuses the existing `xd.health` UXP/WebSocket bridge method.

Successful readiness is cached for 30 seconds so normal write batches do not ping the application for every mutation. A mutating timeout invalidates the cache because the application state is then unknown.

Read capabilities remain available without the readiness preflight so they can be used for diagnosis. Policy denial is evaluated before readiness, so a denied write does not trigger an application probe.

This boundary is deliberate:

```text
transport connected != application ready
application ready != operation verified
```

Operation verification remains a separate postcondition layer (`verified`, `accepted_unverified`, `pending_user_approval`, or timeout/unknown semantics).
