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
    assert fence["priorCompletionObserved"] is True
    assert coordinator.probe_fence is fence
