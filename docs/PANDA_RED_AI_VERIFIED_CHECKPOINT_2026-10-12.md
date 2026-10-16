# Kung Fu Panda 4 red poster — verified checkpoint (2026-10-12 JST)

## Verified deliverables

- **Photoshop:** 60/60 native layers (including three editable Type layers), polished PSD and PNG. Evidence: GitHub Actions run [38151836136](https://github.com/caotiensinh/MCP_adobe/actions/runs/38151836136), artifact 11707470265.
- **Adobe XD:** native document scenegraph/UXP recovery verified in run [38157143339](https://github.com/caotiensinh/MCP_adobe/actions/runs/38157143339). This does **not** verify a complete red-poster XD scene.
- **Illustrator:** first independent red background rectangle persisted in a native .ai in run [38157335430](https://github.com/caotiensinh/MCP_adobe/actions/runs/38157335430). The second (880 × 700 orange-red field) received C014 on CEP; it was *not replayed*. The exact unsaved active document was saved with one gated Illustrator Ctrl+S in run [38194275753](https://github.com/caotiensinh/MCP_adobe/actions/runs/38194275753).

## Stable Illustrator evidence — do not overwrite

- Original first-vector checkpoint SHA-256: `25d46aaacc766759d11c920872d9ee1cc26861a145826143161698e97ca14b77`.
- Exact immutable first-vector comparison source: `%USERPROFILE%\Documents\MCPAdobe\rect2_before_uia_save_38194275753\source_before.ai`.
- Second-vector native checkpoint: `%USERPROFILE%\Documents\MCPAdobe\MCP_KFP4_Red_AI_Fresh_38157628243_5shapes.ai`.
- Verified second-vector file SHA-256: `ec6d2239b3547845c16c80997ca716f50fb8e5f4f5f3f8d57e85079581fa89a2` (207,437 bytes).
- Run [38194704829](https://github.com/caotiensinh/MCP_adobe/actions/runs/38194704829) PASS: compares native PDF-compatible geometry without opening any Adobe app. Drawing operators went **2 → 4**, including a **filled 880 × 700** rectangle with approximate RGB **(244, 45, 8)**. Source and target SHA stayed unchanged throughout. The downloadable .ai, rendered native PNG, and JSON evidence are in [artifact 11722669173](https://github.com/caotiensinh/MCP_adobe/actions/runs/38194704829/artifacts/11722669173).
- Offline PDF parser unit regression **5/5 PASS**: [38194628095](https://github.com/caotiensinh/MCP_adobe/actions/runs/38194628095).
- **Limit:** PDF drawing operations do not unambiguously count Illustrator pageItems. Treat component 002 as persisted **vector geometry**, not a proven fresh scenegraph readback.

## Source divergence observed and safely isolated

[Read-only file forensic run 38194617505](https://github.com/caotiensinh/MCP_adobe/actions/runs/38194617505) discovered that the *separate original source path* was later modified on 2026-10-12 02:04:42 UTC, SHA `18fcc83d33e133c8ad11c0d0361473af8f503fe1e283e6186bbbfcd1df4b5f2a` with spaces removed (207,196 bytes). This is **after** the gated target Ctrl+S. Its author/cause is not established. The pre-save source and target backups both retained the original `25d46...` SHA. No workflow should now use the mutable source path as the baseline.

## Next engineering acceptance gates

1. Confirm live MRCAO Illustrator process, currently active document, user session, and whether any unresolved C014 job remains. Never assume a previous run's PID or job state still applies.
2. For shape 003, create a **new unique .ai** based on the verified second-vector native checkpoint. Check source SHA and duplicate names before *any* GUI or host mutation; do not overwrite the current second-vector file or the immutable backup.
3. Prefer a bounded atomic Illustrator operation with a separately persisted host receipt; do not enqueue dependent readbacks/telemetry if a previous host operation is ambiguous. If the host returns UNKNOWN, inspect the native file and host job first. Never blindly resend the shape creation or Ctrl+S.
4. Verify actual Illustrator pageItem identities via stable native readback when the CEP path becomes reliable; where unavailable, use independent PDF geometry evidence with explicit limitations.
5. Measure full **write → host result → native save → disk readback**, not just MCP ping latency. Keep existing Adobe projects and GPU workloads undisturbed.
6. Continue to 60 native editable Illustrator objects and finish actual XD red-poster editing; only then run the requested **PS → XD → AI** production-speed E2E.

## Session progress (fixed Illustrator denominator 60)

- **HOÀN THÀNH:** 2/60 Illustrator component geometries persisted (first native pageItem, second independently verified native PDF geometry).
- **CÒN LẠI:** 58/60 Illustrator components, Illustrator scenegraph count verification, and complete XD red-poster E2E.
- **TIẾN ĐỘ CẢI THIỆN PHIÊN VỪA RỒI:** +1/60 Illustrator component persisted and verified against the previous 1/60 checkpoint.
- **Do not confuse:** 100% Photoshop layer construction with 100% three-app end-to-end acceptance.
