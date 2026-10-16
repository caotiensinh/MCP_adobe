"""Fail-closed eligibility decisions for Illustrator upstream reconciliation.

An unresolved job must never be cleared, replayed, or assumed failed because
its HTTP/MCP reply timed out. This module classifies read-only health/status
evidence and keeps all decisions independent of the GUI transport.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryDecision:
    safe_to_draw: bool
    reason: str
    blocking_job_id: str | None = None


def classify_readiness(
    health: Mapping[str, object], status: Mapping[str, object] | None = None
) -> RecoveryDecision:
    """Accept drawing only after both host health and reconciliation agree."""
    if not isinstance(health, Mapping):
        return RecoveryDecision(False, "health_missing")
    data = health.get("data")
    if not isinstance(data, Mapping):
        return RecoveryDecision(False, "health_data_missing")
    execution = data.get("execution")
    if not isinstance(execution, Mapping):
        return RecoveryDecision(False, "execution_evidence_missing")
    unresolved = execution.get("unresolvedJobs")
    if not isinstance(unresolved, list):
        return RecoveryDecision(False, "unresolved_inventory_missing")
    if unresolved:
        job = str(unresolved[0])
        if status is None:
            return RecoveryDecision(False, "unresolved_job_not_inspected", job)
        record = status.get("job") if isinstance(status, Mapping) else None
        if not isinstance(record, Mapping) or record.get("jobId") != job:
            return RecoveryDecision(False, "job_evidence_mismatch", job)
        effects = record.get("effects")
        if not isinstance(effects, Mapping) or effects.get("complete") is not True:
            return RecoveryDecision(False, "partial_effects_require_host_reconciliation", job)
        if record.get("awaitingHost") is True:
            return RecoveryDecision(False, "host_completion_not_proven", job)
        # Do not treat a settled job as permission while the upstream still
        # advertises it as unresolved: the coordinator must retire it first.
        return RecoveryDecision(False, "coordinator_still_quarantined", job)
    if data.get("blocking") is not None:
        return RecoveryDecision(False, "host_blocked")
    layers = data.get("layers")
    if not isinstance(layers, Mapping):
        return RecoveryDecision(False, "host_layers_missing")
    for key in ("server", "panel", "illustrator", "document"):
        value = layers.get(key)
        if not isinstance(value, Mapping) or value.get("status") != "ok":
            return RecoveryDecision(False, f"host_layer_{key}_not_ready")
    if data.get("ready") is not True or data.get("probed") is not True:
        return RecoveryDecision(False, "trusted_live_probe_required")
    return RecoveryDecision(True, "host_ready_and_reconciled")
