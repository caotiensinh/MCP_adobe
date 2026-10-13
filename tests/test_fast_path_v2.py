"""Safety regression for opt-in Adobe fast path. No host required."""
import asyncio
import unittest
from mcp_adobe.fast_path_v2 import Coordinator, Identity, Command, IntentCompiler, Phase, UnsafeFastPath

I=Identity("illustrator",123,"bridge-1","doc-1")

class FastPathTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.co=Coordinator(ttl=10)
        self.co.observe(I,True,True)

    async def test_rectangle_compiler(self):
        cmd=IntentCompiler.rectangle("r",100,100,200,120,"#D73034","op-1")
        self.assertEqual(cmd.arguments["fill"],{"r":215,"g":48,"b":52})
        with self.assertRaises(ValueError):
            IntentCompiler.rectangle("r",0,0,-1,100,"#D73034","op-2")

    async def test_cache_and_event_invalidation(self):
        calls=0
        async def send(c):
            nonlocal calls
            calls+=1
            return calls
        c=Command("creative.health",{})
        self.assertEqual(await self.co.execute(c,send),1)
        self.assertEqual(await self.co.execute(c,send),1)
        self.assertEqual(calls,1)
        self.co.invalidate("document_changed")
        self.assertEqual(await self.co.next_event(),"document_changed")
        with self.assertRaises(UnsafeFastPath):
            await self.co.execute(c,send)

    async def test_single_writer(self):
        active=peak=0
        async def send(c):
            nonlocal active,peak
            active+=1
            peak=max(peak,active)
            await asyncio.sleep(.01)
            active-=1
            return 1
        await asyncio.gather(*(self.co.execute(Command("read",{"n":n}),send) for n in range(5)))
        self.assertEqual(peak,1)

    async def test_unknown_write_no_replay(self):
        self.co.write_timeout=.01
        calls=0
        async def send(c):
            nonlocal calls
            calls+=1
            await asyncio.sleep(.1)
        async def verify(c,r): return True
        cmd=IntentCompiler.rectangle("r",1,1,2,3,"#D73034","op-1")
        with self.assertRaises(TimeoutError):
            await self.co.execute(cmd,send,verify)
        self.assertEqual(self.co.phase,Phase.UNCERTAIN)
        with self.assertRaises(UnsafeFastPath):
            await self.co.execute(cmd,send,verify)
        self.assertEqual(calls,1)

    async def test_verified_write_requires_new_host_observation(self):
        async def send(c): return True
        async def verify(c,r): return True
        cmd=IntentCompiler.rectangle("r",1,1,2,3,"#D73034","op-1")
        await self.co.execute(cmd,send,verify)
        self.assertEqual(self.co.phase,Phase.COLD)
        with self.assertRaises(UnsafeFastPath):
            await self.co.execute(cmd,send,verify)

    async def test_uncertain_reconciliation_requires_trusted_evidence(self):
        self.co.invalidate("unknown_mutation")
        with self.assertRaises(UnsafeFastPath):
            self.co.reconcile(I,False,True,True)
        self.co.reconcile(I,True,True,True)
        self.assertEqual(self.co.phase,Phase.WARM)

    async def test_failed_host_readback_is_uncertain(self):
        async def send(c): return {"ack":True}
        async def verify(c,r): return False
        cmd=IntentCompiler.rectangle("r",1,1,2,3,"#D73034","op-1")
        with self.assertRaises(UnsafeFastPath):
            await self.co.execute(cmd,send,verify)
        self.assertEqual(self.co.phase,Phase.UNCERTAIN)

if __name__=="__main__":
    unittest.main()
