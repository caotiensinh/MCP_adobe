# Adobe MCP — Mode 1 → Mode 2 acceptance checkpoint (2026-10-13)

## User-authorized workflow

- **Mode 1 — LIVE DRAWING:** each Adobe operation creates/edits one stroke or component; host readback and durable checkpoint after every step. Do not reconstruct an entire poster in one imported/flattened image.
- **Mode 2 — REGION TARGETING:** select an area on a real document preview → map document coordinates to the correct stable layer/node → apply an explicitly authorized scoped edit → host readback and visual verification → durable native checkpoint.
- Only one of Illustrator, XD and Photoshop may own the desktop at a time. No replay after unknown mutation; preserve native source files and SHA-256.

## Verified evidence

- XD v4 installed only after clean-desktop gate; rollback copy retained: [run 38407485322](https://github.com/caotiensinh/MCP_adobe/actions/runs/38407485322).
- XD native document `MCP_Mode1_Panda_XD_38136531800.xd` verified, one artboard with **32 children**, 0 invalid geometry, pinned document ID `98d6635b-3767-4254-b200-ec8442b69ad2` and original SHA-256 unchanged: [run 38408023833](https://github.com/caotiensinh/MCP_adobe/actions/runs/38408023833).
- XD Fast Session READ-ONLY pass (12 samples each): health p50 75.209ms / p95 224.545ms; scenegraph p50 22.965ms / p95 74.832ms; 0 writes. Do not interpret as proven speedup: [run 38408431187](https://github.com/caotiensinh/MCP_adobe/actions/runs/38408431187).
- Illustrator installed gateway adapters hash-match checkout: [run 38410943224](https://github.com/caotiensinh/MCP_adobe/actions/runs/38410943224).
- Illustrator GUI + CEP idle preflight PASS, no unresolved jobs, **no document open** (not native creation E2E): [run 38411324323](https://github.com/caotiensinh/MCP_adobe/actions/runs/38411324323).
- Illustrator close gate reports already exited: [run 38413249692](https://github.com/caotiensinh/MCP_adobe/actions/runs/38413249692).
- Photoshop installed gateway adapter matches checkout: [run 38410943224](https://github.com/caotiensinh/MCP_adobe/actions/runs/38410943224).
- Photoshop GUI launched but `creative.health` failed with an MCP tool error after ~30.542s, not an outer 15s timeout: [run 38414321686](https://github.com/caotiensinh/MCP_adobe/actions/runs/38414321686).
- Photoshop upstream process census found two node processes identified as `photoshop-mcp`, distinct parent `cmd.exe` processes; **root cause not yet proven**: [run 38414722328](https://github.com/caotiensinh/MCP_adobe/actions/runs/38414722328).

## Gate status

- **XD v4 native readback:** PASS.
- **Illustrator live native rectangle/save + SHA/readback:** NOT ACCEPTED in the current handoff.
- **Photoshop live host health and native rectangle/save + SHA/readback:** BLOCKED.
- **Three-app serial one-rectangle E2E:** NOT ACCEPTED.
- **Safe close of Photoshop without losing a document:** NOT VERIFIED; do not force kill.
- **Mode 2 active editing:** NOT AUTHORIZED TO CLAIM COMPLETE. Mode 2 may undergo independent read-only design/contract tests, but do not call the overall Mode 1 → Mode 2 transition accepted until the above gates pass.

## Mode 2 implementation contract

1. Obtain a full-document preview from the actual host along with document ID, generation, canvas geometry and native checkpoint; refuse screenshot-only or stale-document selection.
2. Map user's bounded rectangle in preview pixel space into global document coordinates using an explicit invertible transform; reject missing scale/offset or aspect mismatch.
3. Read the complete scenegraph with globally expressed bounds and stable IDs. Ignore hidden/locked nodes; enforce unique candidate selection or request disambiguation.
4. Before mutation, assert app, PID/session, document ID/generation, node ID and original node bounds; single-writer queue and no unknown-operation replay.
5. Apply one scoped reversible edit with explicit authorization; perform host readback of node identity/bounds/style, save native separately, calculate SHA-256 and publish a bounded E2E report.
6. Regression: prevent any new Mode 2 implementation from modifying known-good XD v4 bridge, Illustrator CEP adapter or Photoshop core without targeted evidence and protected tests.

**Next unblocked priority:** diagnose upstream Photoshop readiness without indiscriminate process termination; then finish AI/PS native E2E and close applications safely.
