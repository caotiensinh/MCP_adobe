import asyncio
import unittest
from mcp_adobe.fast_session import AdobeFastSession, AdaptiveDeadline
from mcp_adobe.fast_path_v2 import Identity, UnsafeFastPath, Phase

class FakeReply:
    is_error=False
    structured_content={"ok":True,"result":{"status":"ok"}}
class FakeClient:
    def __init__(self,url): self.calls=[];self.url=url
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    async def call_tool(self,tool,payload):
        self.calls.append((tool,payload))
        return FakeReply()

I=Identity("xd",100,"bridge-a","doc-a")
class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_opt_in_disabled(self):
        with self.assertRaises(UnsafeFastPath):
            async with AdobeFastSession("xd",client_factory=FakeClient): pass

    async def test_persistent_batch_fresh_health(self):
        async with AdobeFastSession("xd",enabled=True,client_factory=FakeClient) as s:
            s.trusted_observe(I,host_readback_verified=True,no_unresolved_jobs=True)
            r=await s.read_batch([("creative.health",{}),("creative.health",{})])
            self.assertEqual(len(r),2)
            self.assertEqual(len(s.client.calls),2)
            self.assertEqual(s.coordinator.phase,Phase.WARM)
        self.assertEqual(s.coordinator.phase,Phase.COLD)

    async def test_event_invalidation(self):
        async def events():
            yield {"type":"document_changed"}
        async with AdobeFastSession("xd",enabled=True,client_factory=FakeClient) as s:
            s.trusted_observe(I,host_readback_verified=True,no_unresolved_jobs=True)
            await s.event_listener(events())
            with self.assertRaises(UnsafeFastPath): await s.read("creative.health",{})

    async def test_invalid_host_identity(self):
        async with AdobeFastSession("xd",enabled=True,client_factory=FakeClient) as s:
            with self.assertRaises(UnsafeFastPath):
                s.trusted_observe(Identity("photoshop",1,"b","d"),host_readback_verified=True,no_unresolved_jobs=True)

    async def test_write_disabled(self):
        async with AdobeFastSession("xd",enabled=True,client_factory=FakeClient) as s:
            s.trusted_observe(I,host_readback_verified=True,no_unresolved_jobs=True)
            with self.assertRaises(UnsafeFastPath): await s.write("creative.shape.rectangle")

    async def test_adaptive_deadline_boundaries(self):
        d=AdaptiveDeadline()
        self.assertEqual(d.seconds,8.0)
        for _ in range(6):d.record(.01)
        self.assertEqual(d.seconds,2.0)
        for _ in range(32):d.record(100.0)
        self.assertEqual(d.seconds,18.0)

    async def test_nonallowlisted_read_fails(self):
        async with AdobeFastSession("xd",enabled=True,client_factory=FakeClient) as s:
            s.trusted_observe(I,host_readback_verified=True,no_unresolved_jobs=True)
            with self.assertRaises(UnsafeFastPath):await s.read("creative.shape.rectangle",{})
if __name__=="__main__":unittest.main()
