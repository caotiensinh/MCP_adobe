# MCP Adobe Product Specification

Status: **canonical and blocking**

This document defines what MCP Adobe is. If an implementation, test, roadmap item, or pull request conflicts with this specification, the specification wins unless this file is explicitly revised.

## Product goal

MCP Adobe must make Photoshop, Illustrator, and Adobe XD behave as live creative tools available to an MCP client such as ChatGPT or Claude.

The intended user experience is conversational, stateful, and direct:

```text
user in ChatGPT / Claude
        <-> MCP Adobe
        <-> persistent local Adobe bridge
        <-> the document currently open in Photoshop / Illustrator / XD
```

A user must be able to say things such as:

- select this layer/object;
- move it 12 px;
- make the selected object darker;
- edit this anchor/path/text;
- create a rectangle or artboard;
- undo the last change;
- show me the current document;

and see the active Adobe application change directly during the same live session.

## Non-negotiable product boundary

The following is **not** the finished product:

```text
LLM -> generate a large script/program -> CI/agent runner -> Adobe -> export a file -> return the file
```

That path is useful for compatibility tests, regression tests, automation, and proving that Adobe can be controlled. It is not a substitute for live interactive MCP control.

GitHub Actions/self-hosted runners are test infrastructure only. They must not become the primary end-user interaction transport.

Arbitrary `execute_script` / `eval` capability may exist as a privileged escape hatch, but it must not be the main interaction model or the basis for claiming interactive MCP completion.

## Required interaction model

### Persistent session

The bridge must remain connected while the creative session is active. Normal conversational edits must not require launching a fresh CI job or rebuilding a one-shot script for each user instruction.

The session must preserve at least:

- application;
- active document;
- active artboard when applicable;
- current selection;
- relevant layer/object identity;
- undo/history context where the host exposes it.

### Granular tool control

The model must interact through bounded semantic/native tools rather than only through arbitrary code execution.

Required classes include:

- document read/create/open/save/export;
- state and preview;
- layer/object list/select/create/delete/rename;
- selection read/change;
- move/scale/rotate/transform;
- shape/path creation and editing;
- fill/stroke/style edits;
- text creation and editing;
- grouping/ordering where supported;
- masks/clipping where supported;
- undo/redo where supported.

Application-specific operations remain under `photoshop.*`, `illustrator.*`, and `xd.*` where semantics differ.

### Bidirectional state

The system must not be AI -> Adobe only.

MCP Adobe must be able to observe changes made by the human directly in Adobe. At minimum the architecture must support refreshing, polling, or receiving changes for:

- active document;
- selection;
- layer/object state;
- active artboard;
- save/history state.

The target state is event-aware behavior such that a user can click an object in Adobe and then say "move this" without re-identifying it manually.

### Visual verification

The client must be able to request a current preview/snapshot of the active document during the same session.

A successful write is not enough. The system should verify the resulting application state and, for visual work, support preview-based confirmation before claiming the requested edit is complete.

### Direct editing of the active document

The default target for conversational editing is the document the user currently has open, not a newly generated replacement file.

The system must support incremental edits to that document while preserving unrelated user work.

## Application requirements

### Photoshop

Must support live control of at least document state, layers, selections, text, shapes, transforms, fills/styles, masks where available, preview, undo/redo, save, and export.

### Illustrator

Must support live vector editing. Completion requires object/path-level operations, including selection, path/shape creation, transform, fill/stroke, text, grouping/order, artboards, path/anchor editing or an equivalent bounded vector-edit surface, preview/state, undo/redo, save, and export.

A logo/vector workflow is not considered complete if Illustrator is used only as a destination for a monolithic generated JSX script.

### Adobe XD

Must support live document/selection awareness and direct design operations available through the verified XD plugin/UXP bridge. If Adobe API restrictions require explicit user approval for a mutation, that limitation must be represented honestly in the MCP contract and UX rather than hidden.

## Client requirements

The same product contract must work with both:

- Claude MCP clients;
- ChatGPT/OpenAI-compatible MCP clients.

Application adapters must not be rewritten per client.

## Latency target

Conversational tool calls should feel interactive. The target for ordinary local selection/edit/preview operations is approximately 200 ms to 1.5 s when the Adobe host operation itself permits it.

Long Adobe operations may take longer, but a multi-minute GitHub Actions round trip is never considered acceptable interactive latency.

## Safety and reliability

Existing evidence-first rules remain mandatory:

- transport connected != Adobe application ready;
- application ready != requested operation verified;
- mutation timeout = UNKNOWN until actual application state is inspected;
- do not blindly retry ambiguous writes;
- explicit target validation before mutation;
- overwrite and destructive operations remain explicitly gated;
- preserve user documents and unrelated objects/layers;
- undo/rollback support must be accurately reported.

## Definition of Done

MCP Adobe is **not complete** merely because it can launch an Adobe app, run code, create a document, save a PSD/AI/XD-related artifact, or export PNG/SVG.

The product may be called complete for the initial Photoshop + Illustrator + XD scope only when the live checklist in `docs/INTERACTIVE_MCP_CHECKLIST.md` is satisfied with real application evidence.

The decisive acceptance test is conversational:

1. user opens an existing document in an Adobe application;
2. ChatGPT/Claude reads the live document and current selection;
3. user gives several small successive design instructions;
4. MCP Adobe invokes bounded tools that directly change the open document;
5. the user may manually change the selection in Adobe and the next instruction uses that new context;
6. preview/state is returned to the client;
7. undo/recovery works;
8. the session remains live without using GitHub Actions as the command transport.

Until that sequence is proven for the required applications, the project remains in progress.