# Illustrator MCP callback repair, 2026-10-13

## Confirmed cause

The installed panel loads `dist/index.html`, a compatibility transport generated
from `scripts/illustrator_cep_fallback_transport.html`. It does not load the React
transport in `dist/assets/index.js`.

The compatibility transport's initial `evalHost(..., 30000)` rejects its Promise
at 30 seconds and drops any subsequent native callback (`if (settled) return`).
Its catch handler then sends `complete` without a payload descriptor and marks
the panel idle. Python correctly refuses to treat that as a verified host outcome
and quarantines the job. Reconnect also loses responses because the compatibility
transport ignores completion ACKs and has no retained completion buffer.

Observed production request 516 (`query_items`, job `job_899aaac76db7`):

- 01:20:27.575: dispatch.
- 01:20:57.598: Python waiter timeout, R005, outcome unknown.
- 01:20:57.635: matching CEP `complete`, no descriptor/chunks.
- Job inspection: C014 `missing_descriptor`, awaitingHost=true.
- Subsequent health: connected panel, fresh idle heartbeat, ready=false,
  blockedAt=unresolved_job. Idle is not proof that the native call stopped.

This identifies the callback loss and false completion mechanism. Why this
particular object query exceeded 30 seconds has not been measured on the host.
Do not claim that object-query performance has been fixed.

## Repair

- Retain the initial native callback without an artificial CEP deadline. The
  Python waiter remains bounded and can return UNKNOWN without cancelling Adobe.
- Keep busy admission until the native callback and correlated completion ACK.
- Retain immutable descriptor/page/completion bytes across reconnect. Resend bytes
  only; never repeat the native script.
- Preserve descriptor evidence on page delivery errors and bounded original host
  diagnostics on descriptor failures.
- Keep Python digest/identity checks, UNKNOWN quarantine, and no-replay behavior.

## Validation

- Node transport regression tests: installed baseline 0/7, repaired candidate 7/7.
- Installed Python bridge integration tests: 3/3. Verified late bytes release the
  execution fence; corrupt bytes and idle-only observations do not.
- Existing gateway/installer/bootstrap regression tests: 28/28 against this
  checkout's gateway source. Total scoped local validation: 38 passed.
- Run transport tests with `node --test tests/illustrator_cep_transport.test.cjs`.
  The dedicated GitHub Actions workflow uses a hosted runner and never installs
  or edits the Adobe desktop extension.
- Run the Python integration tests using the pinned Illustrator backend's Python
  environment: `python -B tests/illustrator_late_callback_integration.py`.
  They are intentionally outside ordinary `test_*.py` discovery because the
  optional upstream backend is not a gateway package dependency.
- These tests use virtual CEP/transport callbacks, not a live Illustrator edit.
- Live repaired-panel acceptance remains pending. Filesystem permission requests
  returned no write grant for the installed panel. The repair is packaged for
  user installation; it has not been applied to the running extension.
- Existing UNKNOWN request is not replayed. Save and close Illustrator before
  installation to end the old host runtime; restart the verified MCP gateway,
  reopen Illustrator, and read fresh document/selection state.

The separately prepared local repair installer checks the diagnosed original
SHA256, backs up before overwriting, rolls back file replacement failures, and
refuses changed files. It does not modify Illustrator artwork or terminate
Illustrator. That machine-specific installer is not part of this source patch;
the repository's normal backend installer consumes the repaired HTML template.

## Product checklist checkpoint

No additional live product gate is proven by this scoped transport regression.
The repository's persisted 50-gate checklist is currently unchecked.

HOÀN THÀNH: 0/50
CÒN LẠI: 50
TIẾN ĐỘ CẢI THIỆN PHIÊN VỪA RỒI: +0 blocking gates
