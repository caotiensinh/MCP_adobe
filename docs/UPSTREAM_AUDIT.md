# Upstream audit baseline

Audit date: 2026-10-04

## Reuse policy

Do not copy third-party implementation code merely because a repository is public. Integration must respect the upstream license and preserve required notices. Prefer adapters/subprocess integration or clearly attributed vendoring only when technically justified.

## Baseline repositories

### mikechambers/adb-mcp

- Role: multi-Adobe-app architecture reference.
- License: MIT.
- Relevant applications documented by upstream: Photoshop, Premiere Pro, InDesign, After Effects, Illustrator.
- Upstream architecture: MCP server -> Node command proxy -> Adobe plugin -> application.
- Upstream README states testing with Claude Desktop and OpenAI Agent SDK.
- Decision: reuse architecture ideas and evaluate adapter-level reuse. Do not treat the proof-of-concept as production-ready without hardening.

### alisaitteke/photoshop-mcp

- Role: Photoshop implementation candidate.
- License: MIT.
- GitHub description at audit time advertises 118 tools and control from Cursor, Claude, or custom LLMs.
- Decision: primary Photoshop candidate for deeper code/tool/E2E audit.

### ie3jp/illustrator-mcp-server

- Role: Illustrator implementation candidate.
- License: MIT.
- GitHub description at audit time advertises 63 tools covering read/create/export on stable Illustrator.
- Decision: primary Illustrator candidate for deeper code/tool/E2E audit.

### stephenszpak/xd-mcp

- Role: XD research candidate.
- License: GitHub repository metadata did not expose a license during the audit.
- Decision: do not copy source into this project until licensing is clarified. Architecture may be studied; independent implementation remains an option.

## Next audit gates

For Photoshop and Illustrator candidates, verify before code reuse:

- exact tool inventory;
- transport and bridge implementation;
- error propagation;
- reconnect behavior;
- file-system permissions;
- arbitrary script execution surfaces;
- undo support;
- application version assumptions;
- test quality and real-application E2E evidence;
- dependency/license compatibility.
