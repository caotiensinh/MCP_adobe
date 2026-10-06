# MCP Adobe contributor guardrails

Before changing this repository, read:

1. `docs/PRODUCT_SPEC.md` — canonical product contract.
2. `docs/INTERACTIVE_MCP_CHECKLIST.md` — fixed 50-gate completion checklist.
3. `docs/ARCHITECTURE.md` — architecture aligned to that contract.

These requirements are blocking:

- The product is persistent conversational control of the Adobe document the user is actively working on in Photoshop, Illustrator, and Adobe XD.
- ChatGPT/Claude must interact through bounded granular MCP tools with live state/selection/preview feedback.
- Human changes inside Adobe must be observable/refetched so stale selection/document context is not mutated.
- GitHub Actions/self-hosted runners are CI/E2E infrastructure, not the primary end-user command transport.
- Generating a large script/JSX/program and sending it to Adobe can be an implementation fallback or test, but it is not sufficient to claim the interactive product is complete.
- Arbitrary native script execution remains privileged/default-deny and must not replace the granular tool surface.
- Do not claim PASS from transport/process/tool-list success alone. Verify real Adobe state/postconditions.
- Mutation timeout is UNKNOWN until actual application state is inspected; do not blindly rerun writes.
- Preserve existing user documents and unrelated layers/objects.
- Do not change the 50-gate denominator to inflate progress. Only mark a gate complete with persisted evidence.

For substantial development sessions report:

```text
HOÀN THÀNH: X/50
CÒN LẠI: 50-X
TIẾN ĐỘ CẢI THIỆN PHIÊN VỪA RỒI: +Z blocking gates
```

If a proposed implementation conflicts with `docs/PRODUCT_SPEC.md`, stop and change the implementation rather than silently changing the product direction.