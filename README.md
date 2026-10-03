# MCP Adobe Creative Gateway

A vendor-neutral MCP gateway for controlling Adobe creative applications from MCP-compatible AI clients such as Claude, ChatGPT/Codex, Cursor, and other agents.

## Project goals

- One MCP-facing gateway for multiple Adobe desktop applications.
- Reuse proven community implementations instead of rewriting mature integrations.
- Normalize common creative operations while preserving app-specific native capabilities.
- Keep risky write operations observable, auditable, and reversible where the host application supports undo.
- Support Windows first, with macOS compatibility where upstream adapters provide it.

## Initial application scope

1. Adobe Photoshop
2. Adobe Illustrator
3. Adobe XD read/parse workflows
4. Premiere Pro, After Effects, and InDesign after Photoshop + Illustrator are stable

## 5-upstream audit status

The first deep audit is pinned to exact source snapshots:

- `mikechambers/adb-mcp@afe5d09cdbdd4cc60434dce6b3f46fdafe15a21c` — multi-application architecture reference.
- `alisaitteke/photoshop-mcp@ecd502c666f0e5b3889d3ef7bc42e5b3eb1119c2` — **primary Photoshop implementation candidate**.
- `ie3jp/illustrator-mcp-server@57c5c101a5192c61535493f39b653e6f92b8eb29` — **primary Illustrator implementation candidate**.
- `stephenszpak/xd-mcp@895613f0af9b14fb1c004913ad227fbbf18e4055` — XD file/share parser reference, not a desktop write adapter.
- `dekdee/adobe-xd-mcp@fb2c767bf8a46b6a503fce90eca47fceca0a474e` — XD parser/code-generation reference, not selected for runtime adoption.

The project does **not** vendor upstream source code at this stage. See:

- `docs/UPSTREAM_AUDIT.md` — evidence and decisions for all five repositories.
- `docs/ADOPTION_PLAN.md` — exactly what will be reused and the E2E gates required before a PASS claim.

## Target architecture

```text
Claude / ChatGPT / Codex / Cursor / other MCP clients
                         |
                         v
              Adobe Creative MCP Gateway
                         |
        +----------------+----------------+
        |                |                |
        v                v                v
    Photoshop        Illustrator          XD
     adapter            adapter       read/parser
        |                |                |
 AppleScript/COM    osascript/COM      XD package/share
 ExtendScript/UXP    ExtendScript       parsing
        |                |
        v                v
    Photoshop         Illustrator
```

The gateway exposes two capability tiers:

- **Common semantic capabilities** such as document open/save/export, selection, text/object creation, and undo.
- **Native application capabilities** for operations that cannot be normalized without losing power.

## Audit-derived safety rules

These are now project invariants:

- application bridges stay local by default;
- inspect state/capabilities before mutation;
- arbitrary native script execution is **default-deny**;
- save/export never overwrites an existing file implicitly;
- timeout of a mutating call is **UNKNOWN**, not automatically safe to retry;
- transport success is not PASS until document/application state is verified where possible;
- undo/rollback capability is explicit metadata, not assumed;
- every adopted adapter records its upstream repository and pinned snapshot.

## Current repository state

Implemented now:

- architecture and five-upstream audit documentation;
- adoption/E2E plan;
- typed capability registry;
- adapter contracts;
- deterministic routing rules;
- unit tests for registration, discovery, routing, and duplicate protection.

Not yet claimed:

- live Photoshop adapter integration;
- live Illustrator adapter integration;
- write-capable Adobe XD desktop control;
- production E2E with Claude + OpenAI clients.

## Development

Python 3.11+ is used for the gateway core scaffold.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Safety / reliability rule

A write operation is not considered successful merely because the MCP call returned. Production adapters must verify postconditions where possible and expose explicit undo/rollback capability metadata.

See `docs/ARCHITECTURE.md` and `docs/ADOPTION_PLAN.md`.
