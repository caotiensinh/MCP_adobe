from mcp_adobe.illustrator_recovery import classify_readiness


def ready():
    return {"data": {
        "ready": True, "probed": True, "blocking": None,
        "execution": {"unresolvedJobs": []},
        "layers": {k: {"status": "ok"} for k in ("server", "panel", "illustrator", "document")},
    }}


def test_accept_verified_live_host():
    outcome = classify_readiness(ready())
    assert outcome.safe_to_draw and outcome.reason == "host_ready_and_reconciled"


def test_unknown_job_is_never_replayed_even_with_partial_created_object():
    health = ready()
    health["data"]["execution"]["unresolvedJobs"] = ["job_bb227cf2e04a"]
    status = {"job": {
        "jobId": "job_bb227cf2e04a", "status": "unknown", "awaitingHost": True,
        "effects": {"created": ["mcp_884589d3-e58a-4cb0-8cbc-b57faee2f152"], "complete": False},
    }}
    decision = classify_readiness(health, status)
    assert not decision.safe_to_draw
    assert decision.reason == "partial_effects_require_host_reconciliation"
    assert decision.blocking_job_id == "job_bb227cf2e04a"


def test_coordinator_inventory_must_be_retired_even_if_ledger_says_complete():
    health = ready()
    health["data"]["execution"]["unresolvedJobs"] = ["job_x"]
    status = {"job": {"jobId": "job_x", "awaitingHost": False, "effects": {"complete": True}}}
    assert classify_readiness(health, status).reason == "coordinator_still_quarantined"


def test_timeout_or_missing_evidence_never_unlocks():
    assert not classify_readiness({}).safe_to_draw
    health = ready()
    health["data"]["ready"] = False
    assert not classify_readiness(health).safe_to_draw
    health = ready()
    health["data"]["probed"] = False
    assert not classify_readiness(health).safe_to_draw
    health = ready()
    health["data"]["blocking"] = {"jobId": "job_x"}
    assert not classify_readiness(health).safe_to_draw
