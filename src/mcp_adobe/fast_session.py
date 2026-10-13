"""Opt-in client-side Adobe Fast Path. Does not change the protected gateway.

Usage: async with AdobeFastSession(application, enabled=True) as session:
  await session.trusted_observe(identity, evidence)
  await session.read("creative.health", {"probe":False})
Writes intentionally remain disabled until a durable host journal integration exists.
"""
from __future__ import annotations
import asyncio
import os
import statistics
import time
from contextlib import asynccontextmanager
from .fast_path_v2 import Command, Coordinator, Identity, UnsafeFastPath, Phase

class AdaptiveDeadline:
    def __init__(self, initial=8.0, minimum=2.0, maximum=18.0, window=32):
        if not (0<minimum<=initial<=maximum) or window<3: raise ValueError("invalid deadline")
        self.initial,self.minimum,self.maximum,self.window=initial,minimum,maximum,window
        self.samples=[]
    @property
    def seconds(self):
        if len(self.samples)<5: return self.initial
        s=sorted(self.samples)
        p95=s[min(len(s)-1,int((len(s)-1)*.95)+1)]
        return max(self.minimum,min(self.maximum,p95*3+0.25))
    def record(self,seconds):
        if seconds>0:
            self.samples.append(seconds)
            del self.samples[:-self.window]

class AdobeFastSession:
    def __init__(self, application, *, enabled=False, client_factory=None, url="http://127.0.0.1:8787/mcp"):
        if application not in ("illustrator","xd","photoshop"): raise ValueError("unsupported app")
        self.application=application
        self.enabled=bool(enabled)
        self.url=url
        self.client_factory=client_factory
        self.coordinator=Coordinator(cache_allowlist=())
        self.deadline=AdaptiveDeadline()
        self.client=None
        self._context=None

    async def __aenter__(self):
        if not self.enabled: raise UnsafeFastPath("opt-in disabled")
        if self.client_factory is None:
            from mcp import Client
            self.client_factory=Client
        self._context=self.client_factory(self.url)
        self.client=await self._context.__aenter__()
        return self

    async def __aexit__(self,typ,value,tb):
        try:
            return await self._context.__aexit__(typ,value,tb)
        finally:
            self.client=None
            self.coordinator.invalidate("session_closed")

    def trusted_observe(self,identity: Identity,*,host_readback_verified:bool,no_unresolved_jobs:bool):
        if identity.app!=self.application: raise UnsafeFastPath("wrong application")
        self.coordinator.observe(identity,host_readback_verified,no_unresolved_jobs)

    async def event_listener(self,events):
        """Consume trusted external bridge events; invalidation never silently reconciles."""
        async for event in events:
            kind=event.get("type")
            if kind in {"process_exit","bridge_disconnect","document_changed","generation_changed","unknown_mutation"}:
                self.coordinator.invalidate(kind)

    async def read(self,capability,arguments=None):
        if self.client is None: raise UnsafeFastPath("client not connected")
        # Each health, scenegraph or doc request must be fresh; never cache.
        if capability not in ("creative.health","creative.document.info","creative.scenegraph.list"):
            raise UnsafeFastPath("opt-in fast read scope is restricted")
        timeout=self.deadline.seconds
        self.coordinator.read_timeout=timeout
        async def dispatch(command):
            result=await self.client.call_tool("creative_read",{
                "application":self.application,"capability":command.capability,"arguments":command.arguments})
            body=result.structured_content
            if result.is_error or not isinstance(body,dict) or body.get("ok") is not True:
                raise UnsafeFastPath("MCP read not verified")
            return body["result"]
        started=time.monotonic()
        result=await self.coordinator.execute(Command(capability,dict(arguments or {})),dispatch)
        self.deadline.record(time.monotonic()-started)
        return result

    async def read_batch(self,requests):
        """Sequential reads with one persistent client; not an atomic host transaction."""
        results=[]
        for capability,args in requests:
            results.append(await self.read(capability,args))
        return results

    async def write(self,*_args,**_kwargs):
        raise UnsafeFastPath("write gated until durable journal and native host verification exist")
