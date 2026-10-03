# Upstream audit — 5 source repositories

Audit date: 2026-10-04

This audit is pinned to exact upstream snapshots. Do not silently treat future upstream `main`/`master` as equivalent; refresh the audit before importing code or changing adapter behavior.

## Pinned snapshots

| Repository | Snapshot | Primary role | Reuse decision |
|---|---|---|---|
| `mikechambers/adb-mcp` | `main@afe5d09cdbdd4cc60434dce6b3f46fdafe15a21c` | Multi-Adobe architecture reference | Reuse architecture patterns; do not use as production runtime unchanged |
| `alisaitteke/photoshop-mcp` | `master@ecd502c666f0e5b3889d3ef7bc42e5b3eb1119c2` | Photoshop implementation | Primary Photoshop adapter candidate |
| `ie3jp/illustrator-mcp-server` | `main@57c5c101a5192c61535493f39b653e6f92b8eb29` | Illustrator implementation | Primary Illustrator adapter candidate |
| `stephenszpak/xd-mcp` | `main@895613f0af9b14fb1c004913ad227fbbf18e4055` | XD parser/spec extractor | Parser/design-token reference only; not a desktop write adapter |
| `dekdee/adobe-xd-mcp` | `main@fb2c767bf8a46b6a503fce90eca47fceca0a474e` | XD parser/code generator | Reference only; not selected for runtime integration |

## 1. mikechambers/adb-mcp

### Verified architecture

The project is explicitly a proof of concept. It uses separate MCP servers plus a Node command proxy and Adobe-side plugins:

```text
MCP client -> Python MCP server -> Socket.IO command proxy -> UXP/CEP plugin -> Adobe app
```

It covers Photoshop, Premiere Pro, InDesign, After Effects and Illustrator. Photoshop/Premiere/InDesign use UXP; Illustrator/After Effects use CEP/ExtendScript. Upstream documents testing with Claude Desktop on Windows/macOS and OpenAI Agent SDK.

### Strengths to reuse

- Multi-application separation.
- Local proxy pattern when an Adobe plugin cannot listen as a server.
- App-specific MCP surfaces behind a common conceptual architecture.
- MIT license with explicit license file.
- Demonstrated Claude + OpenAI compatibility at protocol level.

### Weaknesses / production gaps

- Upstream calls itself a proof of concept.
- No automated test suite was found in the repository search performed for this audit.
- The documented install flow requires developer tools/plugin loading and manual connect steps.
- `socket_client.py` creates a connection per command, waits on a queue, then disconnects; it has timeout/error handling but is not a durable connection/session manager.
- A proxy/plugin failure is surfaced mainly as connection/timeout failure; our gateway needs richer health and reconnect state.

### Decision

Use this repository as the **architecture reference for multi-app bridging**, not as the primary implementation for Photoshop or Illustrator.

---

## 2. alisaitteke/photoshop-mcp

### Verified scope

- MIT licensed.
- TypeScript / Node 18+.
- 127 tools documented at the audited snapshot: 111 atomic tools + 16 recipe tools.
- Local-first MCP server over stdio.
- Default automation uses ExtendScript through AppleScript on macOS and COM on Windows.
- Optional UXP bridge is used for capabilities such as Neural Filters that need `batchPlay`.
- Windows and macOS are both supported by upstream.

### Reliability strengths

- Structured error envelopes with machine-readable error codes and suggested recovery tools.
- State-before-action model (`get_state`, preview, capabilities).
- Mutating operations can target a document explicitly instead of trusting only the active UI tab.
- Recipe tools group multi-step edits into one Photoshop history state, allowing a single Undo for the recipe.
- Upstream development documentation records a live Photoshop integration sweep of **119 pass / 0 fail / 4 intentional skips** on Photoshop 26.5.0 macOS; the project also has unit-test and packaging verification commands.
- Explicit script timeout handling exists.

### Risk surfaces that must be gated in MCP_adobe

- `photoshop_execute_script` executes arbitrary custom ExtendScript. This must be considered a **high-risk native capability**, disabled by default in the unified gateway unless explicitly authorized.
- File open/save/export and batch operations can affect user data; overwrite must require explicit intent.
- Generative AI operations depend on Adobe account state/credits and may require longer timeouts.
- Anonymous usage analytics are enabled upstream by default but opt-out. If we embed code instead of subprocess/adaptor integration, telemetry behavior must be reviewed and must not silently become gateway telemetry.

### Decision

**Primary Photoshop implementation candidate.** Prefer adapter/subprocess composition around its MCP/tool layer before copying source. Preserve its structured errors, state-before-action model and recipe/undo semantics.

---

## 3. ie3jp/illustrator-mcp-server

### Verified scope

- MIT licensed with LICENSE file.
- TypeScript / Node 20+.
- 66 tools at the audited snapshot.
- Supports read, create, modify, save, export, preflight and design-system workflows.
- Illustrator 2024+ is documented as verified; older 2020–2023 versions are expected but unverified.
- Local stdio transport.
- ExtendScript is executed with `osascript` on macOS or PowerShell COM automation on Windows.
- Security documentation states the server is local-only and makes no network requests.

### Reliability/security strengths

- Zod input schemas validate operation parameters.
- Save/export behavior is conservative: existing files are not overwritten unless explicitly requested for the relevant operations.
- CI runs build + tests on Ubuntu, macOS and Windows, with Node 20 and 22.
- Timeouts are split between normal and heavy operations and are configurable with validated environment variables.
- Security policy explicitly documents filesystem access and local execution model.
- Search of the audited source did not find a generic arbitrary-script MCP tool comparable to Photoshop's `photoshop_execute_script`; native script execution remains an internal implementation mechanism rather than an exposed catch-all capability.

### Remaining verification before adoption

- Run its unit suite locally from the pinned snapshot.
- Build a Windows real-Illustrator E2E matrix for the exact Illustrator version used by this project.
- Verify undo/history behavior for each modifying tool category; unlike Photoshop recipes, one-call/one-undo semantics are not assumed globally.
- Confirm behavior after Illustrator restart and multi-version selection on Windows.

### Decision

**Primary Illustrator implementation candidate.** Its input validation, overwrite safety and cross-platform CI patterns should be adopted into the gateway contract.

---

## 4. stephenszpak/xd-mcp

### Verified scope

The README describes an XD-file parser/design-token server rather than a controller for a running Adobe XD application. Source inspection shows five MCP tools at the audited snapshot:

- `get_specs`
- `list_artboards`
- `get_artboard_specs`
- `extract_tokens`
- `fetch_from_xd_share`

It reads local/remote XD data, can use an Adobe XD share/viewer endpoint, and can optionally write/update SCSS output. It does **not** provide desktop XD create/edit/delete operations.

### License/test findings

- `package.json` declares `MIT`.
- No LICENSE file is present in the repository root at the audited snapshot, and GitHub repository metadata did not resolve a license.
- `package.json` has build/dev/start scripts but no test script.

### Decision

Do **not** treat this as an XD desktop adapter. It is useful as a design-spec/parser reference. Do not copy implementation code into this repository until license text/permission is clarified; independent implementation of the parsing approach remains available.

---

## 5. dekdee/adobe-xd-mcp

### Verified scope

This is also a file-processing MCP, not a live XD application controller. It exposes three tools:

- `get_xd_info`
- `generate_react_component`
- `extract_colors`

Its focus is XD analysis, React generation and color extraction.

### Maturity findings

- Only the initial upstream commit exists at the pinned snapshot, dated 2025-07-14.
- It uses the old `@modelcontextprotocol/sdk` `^0.5.0` API.
- `package.json` and README declare MIT, but the README says to see a LICENSE file and no LICENSE file is present in the repository root at the audited snapshot.
- `package.json` declares `test: tsx src/test.ts`, but the audited `src/` tree contains no `test.ts`; therefore the declared test command is not backed by the current tree.
- Tool errors are returned as normal text content rather than a typed/structured error contract.

### Decision

Do not adopt as runtime code. Keep only as a historical/reference implementation for XD file parsing and generated-code workflows.

---

# Cross-repository conclusions

## What we will reuse

1. **adb-mcp:** multi-application bridge/proxy architecture patterns.
2. **photoshop-mcp:** Photoshop implementation, structured errors, state-before-action, recipe/undo patterns.
3. **illustrator-mcp-server:** Illustrator implementation, schema validation, overwrite protection, cross-platform execution/CI patterns.
4. **XD repos:** parsing/design-token concepts only until a real XD desktop bridge is independently verified.

## What we will not inherit blindly

- Arbitrary script execution exposed to an LLM without a policy gate.
- File overwrite without explicit `overwrite=true`/equivalent user intent.
- Manual plugin/developer-tool setup as the final UX.
- Upstream telemetry defaults.
- Claims of E2E support that were not reproduced on our target Windows/Adobe versions.
- "MIT" package metadata without the expected license text when copying source.

## Gateway invariants derived from this audit

1. Application bridges stay local by default.
2. Discovery/state read happens before mutating execution.
3. Native arbitrary-script capability is high-risk and default-deny.
4. Existing files are never overwritten implicitly.
5. A successful transport call is not equivalent to verified document state.
6. Mutating operations expose undo/rollback capability metadata when available.
7. Each adapter records its upstream source and pinned snapshot.
8. Claude/OpenAI compatibility is implemented at the MCP boundary; adapters must not depend on a specific model vendor.

## Next implementation gate

Phase 1 now narrows to two real adapters:

- Photoshop adapter around `alisaitteke/photoshop-mcp` pinned/audited behavior.
- Illustrator adapter around `ie3jp/illustrator-mcp-server` pinned/audited behavior.

XD remains read/parse-only until a verified write-capable desktop bridge is found or built.
