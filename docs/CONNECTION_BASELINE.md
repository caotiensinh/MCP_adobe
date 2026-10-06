# Adobe connection baseline

Status: **frozen unless a reproducible interaction blocker/regression is proven**

The project has already established the application-connection architecture for Photoshop, Illustrator, and Adobe XD. From this checkpoint onward, connection/bootstrap/discovery work is not the development focus.

## Freeze rule

Do not refactor, replace, or reopen the Photoshop/Illustrator/XD connection layer merely to improve structure, style, abstraction, or test aesthetics.

Connection-layer changes are allowed only when there is concrete evidence that the existing layer blocks a required interactive gate from `docs/INTERACTIVE_MCP_CHECKLIST.md`, or when a reproducible regression prevents an application from being reached.

When such a blocker exists:

1. capture the exact failing interactive command and application state;
2. identify the connection-layer root cause;
3. make the smallest repair that restores the interactive path;
4. re-run the failing interaction against the fresh exact head;
5. return immediately to interactive-tool development.

## Development priority

The active product work is now:

```text
persistent conversational session
-> live active-document/selection context
-> bounded granular Photoshop / Illustrator / XD tools
-> incremental direct edits in the open document
-> state/preview feedback
-> human selection changes reflected back to MCP
-> undo/recovery
```

GitHub Actions, runner bootstrap, install discovery, COM/UXP/WebSocket diagnostics, and one-shot script execution remain support/test infrastructure. They are not roadmap progress unless they unblock one of the interactive gates.

## Evidence wording

This freeze does not redefine evidence standards. `transport connected`, `application ready`, and `interactive operation verified` remain different states. Freezing connection work means "do not spend development effort there without evidence of a blocker"; it does not permit a false live-PASS claim.
