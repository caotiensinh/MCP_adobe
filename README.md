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

## Reuse baseline

The audited upstream snapshots are:

- `mikechambers/adb-mcp@afe5d09cdbdd4cc60434dce6b3f46fdafe15a21c` — multi-application architecture reference.
- `alisaitteke/photoshop-mcp@ecd502c666f0e5b3889d3ef7bc42e5b3eb1119c2` — primary Photoshop implementation.
- `ie3jp/illustrator-mcp-server@57c5c101a5192c61535493f39b653e6f92b8eb29` — primary Illustrator implementation.
- `stephenszpak/xd-mcp@895613f0af9b14fb1c004913ad227fbbf18e4055` — XD parser reference only.
- `dekdee/adobe-xd-mcp@fb2c767bf8a46b6a503fce90eca47fceca0a474e` — XD parser/code-generation reference only.

The gateway does not reimplement MCP framing. It reuses the official MCP Python SDK for stdio subprocess lifecycle, initialize, tool discovery and tool calls.

Pinned runtime launchers currently use:

```text
Photoshop  -> npx -y @alisaitteke/photoshop-mcp@1.7.32
Illustrator -> npx -y illustrator-mcp-server@1.10.3
```

See `docs/UPSTREAM_AUDIT.md` and `docs/ADOPTION_PLAN.md` for evidence and adoption decisions.

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
        |                |
        +------- official MCP SDK -------+
                         |
                    stdio MCP
                         |
        +----------------+----------------+
        |                                 |
 Photoshop upstream MCP         Illustrator upstream MCP
        |                                 |
    Photoshop                         Illustrator
```

## Current implemented surface

Photoshop common mappings include health, capabilities, document state/preview, create, open, save, export and undo. Arbitrary native script remains default-deny.

Illustrator common mappings include document info/structure, selection, create, open, save, export, PDF export and undo.

The common gateway policy additionally enforces fail-closed risk classification, write-disable mode, explicit destructive/native-script/external-AI authorization and existing-output overwrite protection.

## Audit-derived safety rules

- application bridges stay local by default;
- inspect state/capabilities before mutation;
- arbitrary native script execution is default-deny;
- save/export never overwrites an existing file implicitly;
- timeout of a mutating call is UNKNOWN, not automatically safe to retry;
- transport success is not PASS until document/application state is verified where possible;
- undo/rollback capability is explicit metadata, not assumed;
- every adopted adapter records its upstream repository and pinned snapshot.

## Development

Python 3.11+ is used for the gateway core. The project depends on MCP Python SDK 2.x.

```bash
python -m pip install -e .
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Real Adobe smoke test

The smoke runner uses the same pinned upstream launchers and official MCP SDK transport as the gateway.

Read-only first:

```bash
PYTHONPATH=src python scripts/real_e2e.py photoshop
PYTHONPATH=src python scripts/real_e2e.py illustrator
```

Write verification must be enabled explicitly:

```bash
PYTHONPATH=src python scripts/real_e2e.py photoshop --write --output-dir C:\\Temp\\mcp_adobe_photoshop
PYTHONPATH=src python scripts/real_e2e.py illustrator --write --output-dir C:\\Temp\\mcp_adobe_illustrator
```

Write mode creates a small document, saves it, exports a PNG and verifies the resulting files exist. It refuses to overwrite existing smoke output files. A machine without the corresponding Adobe application must not be reported as a real E2E PASS.

## Not yet claimed

- real Photoshop desktop E2E PASS on the target Windows machine;
- real Illustrator desktop E2E PASS on the target Windows machine;
- write-capable Adobe XD desktop control;
- production E2E from both Claude and OpenAI clients.

## Safety / reliability rule

A write operation is not considered successful merely because the MCP call returned. Production adapters must verify postconditions where possible and expose explicit undo/rollback capability metadata.
