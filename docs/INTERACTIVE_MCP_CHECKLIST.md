# Interactive MCP Completion Checklist

Status: **canonical blocking checklist**

Product contract: `docs/PRODUCT_SPEC.md`

This checklist has a fixed denominator of **50 blocking gates** for the initial Photoshop + Illustrator + Adobe XD product scope. Do not inflate progress by adding completed sub-items to the denominator. If the product specification changes materially, version this checklist deliberately and record the old/new denominator.

## Progress rules

- `[x]` requires persisted, reproducible evidence.
- A mocked adapter, unit test, package validation, process detection, tool listing, or transport handshake is not sufficient for a live gate.
- `execute_script`/generated JSX/COM automation can prove a lower-level bridge, but cannot by itself satisfy a granular interactive-control gate.
- GitHub Actions can run validation but must not be the user-facing command path for interactive gates.
- A write timeout is UNKNOWN until the live Adobe state is inspected.
- Do not rerun a failed live test blindly; inspect the failing step/log/state, fix the cause, then run against the fresh exact head.
- Every live PASS must identify application/version, target document, command/tool, observed postcondition, and evidence location.

## A. Product-direction guardrails — 5 gates

1. [ ] `docs/PRODUCT_SPEC.md` is referenced as the canonical product contract from top-level project documentation.
2. [ ] Architecture explicitly states that live conversational Adobe control is the product, while CI/runner automation is test infrastructure.
3. [ ] Arbitrary native script execution is documented and enforced as an escape hatch, not the primary interaction API.
4. [ ] Project status reporting distinguishes automation proof from interactive-product completion.
5. [ ] No release/completion claim is allowed unless all blocking gates applicable to the initial scope pass.

## B. Persistent live-session foundation — 7 gates

6. [ ] MCP client can establish a persistent local session to the Adobe gateway without GitHub Actions in the command path.
7. [ ] Session preserves active application identity across multiple conversational commands.
8. [ ] Session preserves active document identity across multiple conversational commands.
9. [ ] Session exposes current selection identity/state.
10. [ ] Session reconnects after Adobe application restart without requiring product reinstallation/reconfiguration.
11. [ ] Ordinary granular edit round trip is measured and normally remains within the interactive target of about 200 ms–1.5 s when Adobe itself permits it.
12. [ ] Session teardown/reconnect does not corrupt or replace the user's open document.

## C. Photoshop live interactive control — 10 gates

13. [ ] Read the document that is already open in Photoshop and identify the active document/layer.
14. [ ] Return a current visual preview of that active Photoshop document to the MCP client.
15. [ ] List/select a layer through a bounded Photoshop tool and verify Photoshop selection changed.
16. [ ] Create/delete/rename a layer through bounded tools with state verification.
17. [ ] Create/edit text through bounded tools and verify the visible result.
18. [ ] Create/edit a shape or selection through bounded tools without relying on a monolithic generated script as the product API.
19. [ ] Move/scale/rotate the selected Photoshop object/layer incrementally across successive chat instructions.
20. [ ] Change fill/style/mask or equivalent visual properties through bounded tools and verify the result.
21. [ ] Undo/redo a conversational Photoshop edit and verify state recovery.
22. [ ] Save/export the edited active document while preserving unrelated layers/work and verifying output postconditions.

## D. Illustrator live vector control — 10 gates

23. [ ] Attach to the Illustrator document already open by the user and read document/artboard/selection state.
24. [ ] Return a current preview or equivalent visual verification of the active Illustrator document.
25. [ ] List/select vector objects through bounded Illustrator tools and verify the live selection.
26. [ ] Create primitive vector shapes through bounded tools.
27. [ ] Create/edit text through bounded Illustrator tools.
28. [ ] Move/scale/rotate vector objects incrementally across successive chat instructions.
29. [ ] Change fill/stroke/style through bounded Illustrator tools and verify the live result.
30. [ ] Create/edit paths, anchors, or an equivalent bounded vector-geometry surface sufficient for real logo/design refinement.
31. [ ] Group/order/pathfinder or equivalent composition operations are available through bounded tools, with undo/recovery evidence.
32. [ ] Save `.ai` and export SVG/PNG from the interactively edited document with verified postconditions.

## E. Adobe XD live control — 8 gates

33. [ ] XD plugin/bridge connects persistently to the gateway in a normal desktop session.
34. [ ] Read the currently open XD document/artboard and current selection.
35. [ ] Reflect a user selection change made directly in XD back into MCP context.
36. [ ] Create at least one design node through the verified live XD bridge.
37. [ ] Modify a selected node's geometry/property through the live bridge.
38. [ ] Create/edit text through the live XD bridge where the host API permits it.
39. [ ] Preview/readback verifies the applied XD mutation.
40. [ ] Any XD host requirement for explicit user approval is represented honestly in the tool result/UX and proven end-to-end.

## F. Bidirectional context and human co-editing — 4 gates

41. [ ] Human changes selection directly in Adobe; MCP observes/refetches it before the next ambiguous command such as "move this".
42. [ ] Human changes active document/artboard directly in Adobe; MCP does not continue mutating the stale previous target.
43. [ ] After each material edit, state/preview can be refreshed without creating a replacement document or exporting/reopening as the normal feedback loop.
44. [ ] The same live session supports alternating human edits and AI edits without losing object/document context.

## G. ChatGPT + Claude client parity — 3 gates

45. [ ] Claude can perform the same persistent live Photoshop/Illustrator/XD contract through MCP without application-adapter forks.
46. [ ] ChatGPT/OpenAI-compatible MCP client can perform the same persistent live Photoshop/Illustrator/XD contract without application-adapter forks.
47. [ ] A cross-client compatibility test proves that adapter capability names/semantics and safety policy remain unchanged between the two clients.

## H. Final interactive acceptance — 3 gates

48. [ ] Real conversational design session: open existing document -> read state -> at least five successive small edits -> previews -> undo, all without GitHub Actions as command transport.
49. [ ] Selection-aware test: user manually selects a different object in Adobe -> says an ambiguous follow-up such as "make this smaller" -> correct newly selected object is edited.
50. [ ] Initial-scope release gate: Photoshop + Illustrator + XD required live gates pass on real desktop applications, evidence is persisted, and no completion claim depends solely on generated scripts or exported artifacts.

## Current interpretation of existing evidence

Previously demonstrated Photoshop scripting that creates layers/files and verifies PSD/PNG proves important lower-level connectivity and automation. It does **not** automatically check gates 13–22, 41–50 because those require persistent, granular, conversational control of the document the user is actively working on.

Likewise, an Illustrator MCP server starting or listing tools does not satisfy Illustrator live gates until it successfully controls the real open Illustrator document through the required bounded vector operations.

## Required checkpoint format

For substantial development sessions, report progress against this fixed checklist:

```text
HOÀN THÀNH: X/50
CÒN LẠI: 50-X
TIẾN ĐỘ CẢI THIỆN PHIÊN VỪA RỒI: +Z blocking gates
```

Only increment `X` for gates with persisted evidence.