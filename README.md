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
3. Adobe XD
4. Premiere Pro, After Effects, and InDesign after the first two applications are stable

## Verified upstream baselines

The project does **not** vendor upstream source code at this stage. The following repositories are reference/adapter candidates and must be integrated according to their licenses and verified capabilities:

- `mikechambers/adb-mcp` — MIT — multi-application architecture reference; tested by its author with Claude Desktop and OpenAI Agent SDK.
- `alisaitteke/photoshop-mcp` — MIT — Photoshop-specific MCP implementation with broad tool coverage.
- `ie3jp/illustrator-mcp-server` — MIT — Illustrator-specific MCP implementation for stable Illustrator.
- `stephenszpak/xd-mcp` — no GitHub license metadata observed during the initial audit; do not copy its code unless licensing is clarified.

See `docs/UPSTREAM_AUDIT.md` for the current reuse policy.

## Target architecture

```text
Claude / ChatGPT / Codex / Cursor / other MCP clients
                         |
                         v
              Adobe Creative MCP Gateway
                         |
        +----------------+----------------+
        |                |                |
   Photoshop        Illustrator          XD
    adapter            adapter         adapter
        |                |                |
  UXP / script      CEP/UXP/script     XD bridge
        |                |                |
   Photoshop         Illustrator         XD
```

The gateway exposes two capability tiers:

- **Common semantic capabilities** such as document open/save/export, selection, text/object creation, and undo.
- **Native application capabilities** for operations that cannot be normalized without losing power.

## Current repository state

This initial commit provides:

- architecture and upstream audit documentation;
- a typed capability registry;
- adapter contracts;
- deterministic routing rules;
- unit tests for registration, discovery, routing, and duplicate protection.

It does **not** yet claim live Photoshop/Illustrator control. Live application adapters will be added only after end-to-end validation against real Adobe applications.

## Development

Python 3.11+ is used for the gateway core scaffold.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Safety / reliability rules

A write operation is not considered successful merely because the MCP call returned. Production adapters should verify postconditions where possible and expose explicit undo/rollback capability metadata.

See `docs/ARCHITECTURE.md`.
