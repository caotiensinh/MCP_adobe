import asyncio
from types import SimpleNamespace
from mcp_adobe.illustrator_upstream_trace import install_trace

def test_trace_preserves_result_and_fence(monkeypatch):
    import sys
    mod = SimpleNamespace(get_coordinator=lambda: SimpleNamespace(
        probe_fence={"priorCompletionObserved": True}, connection_generation=4))
    monkeypatch.setitem(sys.modules, "illustrator_mcp", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "illustrator_mcp.execution", mod)

    class Bridge:
        async def execute_script_async(self):
            return {"error": "PROBE_FENCE_UNSUPPORTED", "dispatched": False}

    original = Bridge.execute_script_async
    install_trace(Bridge)
    install_trace(Bridge)
    assert asyncio.run(Bridge().execute_script_async()) == {
        "error": "PROBE_FENCE_UNSUPPORTED", "dispatched": False}
    assert Bridge.execute_script_async is not original
    assert Bridge.execute_script_async.__wrapped__ if hasattr(Bridge.execute_script_async,"__wrapped__") else True

def test_trace_never_swallows_exception(monkeypatch):
    import sys
    mod = SimpleNamespace(get_coordinator=lambda: SimpleNamespace(
        probe_fence=None, connection_generation=0))
    monkeypatch.setitem(sys.modules, "illustrator_mcp", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "illustrator_mcp.execution", mod)
    class Bridge:
        async def execute_script_async(self):
            raise RuntimeError("intentional")
    install_trace(Bridge)
    try:
        asyncio.run(Bridge().execute_script_async())
    except RuntimeError as exc:
        assert str(exc) == "intentional"
    else:
        raise AssertionError("missing error")

def test_late_completion_only_marks_matching_fence(monkeypatch):
    import sys, json
    fence={"requestId":12,"requestToken":"correct-token","priorCompletionObserved":False,
           "connectionGeneration":2}
    coordinator=SimpleNamespace(probe_fence=fence,connection_generation=2)
    mod=SimpleNamespace(get_coordinator=lambda:coordinator)
    monkeypatch.setitem(sys.modules,"illustrator_mcp",SimpleNamespace())
    monkeypatch.setitem(sys.modules,"illustrator_mcp.execution",mod)

    class Registry:
        def get_pending(self,request_id): return None
    class Bridge:
        def __init__(self):
            self.registry=Registry()
            self._panel_busy=False
            self._panel_active_request=None
        async def execute_script_async(self): return {}
        async def _handle_message(self,message): return None
    install_trace(Bridge)
    bridge=Bridge()
    asyncio.run(bridge._handle_message(json.dumps({"type":"complete","id":12,"requestToken":"incorrect"})))
    assert fence["priorCompletionObserved"] is False
    asyncio.run(bridge._handle_message(json.dumps({"type":"progress","id":12,"requestToken":"correct-token"})))
    assert fence["priorCompletionObserved"] is False
    asyncio.run(bridge._handle_message(json.dumps({"type":"complete","id":99,"requestToken":"correct-token"})))
    assert fence["priorCompletionObserved"] is False
    asyncio.run(bridge._handle_message(json.dumps({"type":"complete","id":12,"requestToken":"correct-token"})))
    # Orphan completion without a verified payload must not promote the fence.
    assert fence["priorCompletionObserved"] is False
    assert coordinator.probe_fence is fence

def test_late_completion_from_stale_generation_never_marks_current_fence(monkeypatch):
    import sys, json
    fence = {"requestId": 12, "requestToken": "same-token",
             "priorCompletionObserved": False, "connectionGeneration": 2}
    coordinator = SimpleNamespace(probe_fence=fence, connection_generation=3)
    monkeypatch.setitem(sys.modules, "illustrator_mcp", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "illustrator_mcp.execution",
                        SimpleNamespace(get_coordinator=lambda: coordinator))

    class Registry:
        def get_pending(self, request_id):
            return None

    class Bridge:
        def __init__(self):
            self.registry = Registry()
            self._panel_busy = False
            self._panel_active_request = None

        async def execute_script_async(self):
            return {}

        async def _handle_message(self, message):
            # Model the installed upstream handler: it marks the matching
            # fence without checking the coordinator's current generation.
            payload = json.loads(message)
            active_fence = coordinator.probe_fence
            if (payload.get("type") == "complete"
                    and payload.get("id") == active_fence.get("requestId")
                    and payload.get("requestToken") == active_fence.get("requestToken")):
                active_fence["priorCompletionObserved"] = True
            return None

    install_trace(Bridge)
    bridge = Bridge()
    asyncio.run(bridge._handle_message(json.dumps({
        "type": "complete", "id": 12, "requestToken": "same-token"
    })))
    assert fence["priorCompletionObserved"] is False
    assert coordinator.probe_fence is fence

def test_disconnected_cep_invalidates_host_payload_epoch(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "illustrator_mcp", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "illustrator_mcp.execution",
                        SimpleNamespace(get_coordinator=lambda: SimpleNamespace(
                            probe_fence=None, connection_generation=1)))

    class Bridge:
        def __init__(self):
            self._host_payload_session = "old-jsx-epoch"
            self.disconnect_count = 0

        async def execute_script_async(self):
            return {}

        async def _handle_disconnect(self):
            self.disconnect_count += 1

    install_trace(Bridge)
    install_trace(Bridge)
    bridge = Bridge()
    asyncio.run(bridge._handle_disconnect())
    assert bridge.disconnect_count == 1
    assert bridge._host_payload_session is None


def test_c013_invalidates_epoch_cache_without_replaying_request(monkeypatch):
    import sys, json
    monkeypatch.setitem(sys.modules, "illustrator_mcp", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "illustrator_mcp.execution",
                        SimpleNamespace(get_coordinator=lambda: SimpleNamespace(
                            probe_fence=None, connection_generation=1)))

    class Registry:
        def get_pending(self, request_id):
            return None

    class Bridge:
        def __init__(self):
            self.registry = Registry()
            self._panel_busy = False
            self._panel_active_request = None
            self._host_payload_session = "stale-jsx-epoch"
            self.handled = 0

        async def execute_script_async(self):
            return {}

        async def _handle_message(self, message):
            self.handled += 1
            return {"execution": "unknown", "error": "C013"}

    install_trace(Bridge)
    bridge = Bridge()
    result = asyncio.run(bridge._handle_message(json.dumps({
        "type": "complete", "id": 8, "requestToken": "old-token",
        "payloadError": "stale_host_session"
    })))
    assert bridge.handled == 1
    assert result == {"execution": "unknown", "error": "C013"}
    assert bridge._host_payload_session is None


def test_c014_missing_descriptor_and_payload_error_restore_upstream_fence(monkeypatch):
    import sys, json
    fence = {"requestId": 18, "requestToken": "valid-token",
             "connectionGeneration": 5, "priorCompletionObserved": False}
    coordinator = SimpleNamespace(probe_fence=fence, connection_generation=5)
    monkeypatch.setitem(sys.modules, "illustrator_mcp", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "illustrator_mcp.execution",
                        SimpleNamespace(get_coordinator=lambda: coordinator))

    receiver = SimpleNamespace(descriptor=None, failure=RuntimeError("C014 missing_descriptor"))
    pending = SimpleNamespace(request_token="valid-token", payload=receiver)

    class Registry:
        def get_pending(self, request_id):
            return pending if request_id == 18 else None

    class Bridge:
        def __init__(self):
            self.registry = Registry()
            self._panel_busy = False
            self._panel_active_request = None

        async def execute_script_async(self):
            return {}

        async def _handle_message(self, message):
            data = json.loads(message)
            # Reproduce upstream's optimistic completed-token fence promotion.
            if data.get("type") == "complete":
                fence["priorCompletionObserved"] = True
            return {"result": "unknown"}

    install_trace(Bridge)
    bridge = Bridge()
    msg = {"type": "complete", "id": 18, "requestToken": "valid-token"}
    asyncio.run(bridge._handle_message(json.dumps(msg)))
    assert fence["priorCompletionObserved"] is False
    assert coordinator.probe_fence is fence

    # An error remains unverified even if a descriptor was previously observed.
    receiver.descriptor = {"hostSession": "epoch"}
    receiver.failure = None
    asyncio.run(bridge._handle_message(json.dumps({**msg, "payloadError": "stale_host_session"})))
    assert fence["priorCompletionObserved"] is False

    # A valid descriptor without an upstream registry completion is not enough.
    async def no_upstream_acceptance(self, message):
        return None
    # The installed trace wraps the current Bridge method, so test a new
    # class rather than mutating the wrapped implementation.
    class BridgeNoAcceptance(Bridge):
        _handle_message = no_upstream_acceptance
    install_trace(BridgeNoAcceptance)
    asyncio.run(BridgeNoAcceptance()._handle_message(json.dumps(msg)))
    assert fence["priorCompletionObserved"] is False


def test_only_verified_payload_and_upstream_acceptance_mark_fence(monkeypatch):
    import sys, json
    fence = {"requestId": 9, "requestToken": "correct",
             "connectionGeneration": 3, "priorCompletionObserved": False}
    coordinator = SimpleNamespace(probe_fence=fence, connection_generation=3)
    monkeypatch.setitem(sys.modules, "illustrator_mcp", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "illustrator_mcp.execution",
                        SimpleNamespace(get_coordinator=lambda: coordinator))

    receiver = SimpleNamespace(descriptor={"hostSession": "epoch"}, failure=None)
    pending = SimpleNamespace(request_token="correct", payload=receiver)

    class Registry:
        def get_pending(self, request_id):
            return pending if request_id == 9 else None

    class Bridge:
        def __init__(self):
            self.registry = Registry()
            self._panel_busy = False
            self._panel_active_request = None

        async def execute_script_async(self):
            return {}

        async def _handle_message(self, message):
            data = json.loads(message)
            if data.get("type") == "complete":
                fence["priorCompletionObserved"] = True
            return {"ok": True}

    install_trace(Bridge)
    bridge = Bridge()
    msg = {"type": "complete", "id": 9, "requestToken": "correct"}
    assert asyncio.run(bridge._handle_message(json.dumps(msg))) == {"ok": True}
    assert fence["priorCompletionObserved"] is True

    fence["priorCompletionObserved"] = False
    # A failed payload integrity check must undo any optimistic promotion.
    receiver.failure = RuntimeError("C012 digest_mismatch")
    asyncio.run(bridge._handle_message(json.dumps(msg)))
    assert fence["priorCompletionObserved"] is False
