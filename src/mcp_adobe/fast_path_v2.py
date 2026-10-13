"""Opt-in Adobe MCP fast-path core: no Adobe/transport side effects.

Integrators must persist their host-side mutation journal and verify native readback.
UNKNOWN mutations must never be replayed.
"""
import asyncio
import time
from dataclasses import dataclass
from enum import Enum

class Phase(str, Enum):
    COLD="cold"
    WARM="warm"
    UNCERTAIN="uncertain"

class UnsafeFastPath(RuntimeError):
    pass

@dataclass(frozen=True)
class Identity:
    app: str
    pid: int
    bridge_generation: str
    document_generation: str

@dataclass(frozen=True)
class Command:
    capability: str
    arguments: dict
    mutation: bool = False
    operation_id: str = ""

class IntentCompiler:
    @staticmethod
    def rectangle(name, x, y, width, height, fill, operation_id):
        geometry=(x,y,width,height)
        if not name or not operation_id or any(type(n) is not int for n in geometry) or x<0 or y<0 or width<=0 or height<=0:
            raise ValueError("invalid rectangle geometry/identity")
        if len(fill)!=7 or fill[0]!="#" or any(c not in "0123456789abcdefABCDEF" for c in fill[1:]):
            raise ValueError("fill must be hex RGB")
        return Command("creative.shape.rectangle", dict(name=name,x=x,y=y,width=width,height=height,
            fill=dict(zip(("r","g","b"), (int(fill[i:i+2],16) for i in (1,3,5))))), True, operation_id)

class Coordinator:
    """Persistent-dispatch compatible, event-driven, single-writer coordinator."""
    def __init__(self, ttl=2.0, read_timeout=8.0, write_timeout=35.0):
        if min(ttl,read_timeout,write_timeout)<=0: raise ValueError("timeouts must be positive")
        self.ttl,self.read_timeout,self.write_timeout=ttl,read_timeout,write_timeout
        self.phase=Phase.COLD
        self.identity=None
        self.verified_at=0.0
        self.pending=None
        self.cache={}
        self.events=asyncio.Queue()
        self.lock=asyncio.Lock()
        self.trace=[]

    def observe(self, identity, verified, no_unresolved_jobs):
        if self.phase==Phase.UNCERTAIN: raise UnsafeFastPath("reconciliation required")
        if identity!=self.identity: self.cache.clear()
        self.identity=identity
        self.verified_at=time.monotonic()
        self.phase=Phase.WARM if verified and no_unresolved_jobs and not self.pending else Phase.COLD

    def invalidate(self, reason):
        self.cache.clear()
        self.phase=Phase.UNCERTAIN if self.pending or reason=="unknown_mutation" else Phase.COLD
        self.events.put_nowait(reason)

    async def next_event(self):
        return await self.events.get()

    def reconcile(self, identity, trusted_host_readback, no_unresolved_jobs, no_inflight_mutation):
        if not (trusted_host_readback and no_unresolved_jobs and no_inflight_mutation):
            raise UnsafeFastPath("unverified host outcome")
        self.pending=None
        self.identity=identity
        self.cache.clear()
        self.verified_at=time.monotonic()
        self.phase=Phase.WARM

    async def execute(self, command, dispatch, verify=None):
        async with self.lock:
            if self.phase!=Phase.WARM or not self.identity:
                raise UnsafeFastPath("host not verified warm")
            if time.monotonic()-self.verified_at>self.ttl:
                self.phase=Phase.COLD
                raise UnsafeFastPath("readiness expired")
            if command.mutation and (not command.operation_id or verify is None):
                raise UnsafeFastPath("write requires op ID and host readback")
            key=(self.identity,command.capability,repr(sorted(command.arguments.items())))
            if not command.mutation and key in self.cache:
                ts,value=self.cache[key]
                if time.monotonic()-ts<self.ttl: return value
            started=time.monotonic()
            if command.mutation: self.pending=command.operation_id
            try:
                result=await asyncio.wait_for(dispatch(command),
                    self.write_timeout if command.mutation else self.read_timeout)
                if command.mutation:
                    if not await asyncio.wait_for(verify(command,result),self.read_timeout):
                        raise UnsafeFastPath("readback unverified")
                    self.pending=None
                    self.cache.clear()
                    self.phase=Phase.COLD
                else:
                    self.cache[key]=(time.monotonic(),result)
                return result
            except BaseException:
                if command.mutation:
                    self.phase=Phase.UNCERTAIN
                    self.cache.clear()
                raise
            finally:
                self.trace.append(dict(capability=command.capability, mutation=command.mutation,
                  elapsed_ms=round((time.monotonic()-started)*1000,3), phase=self.phase.value))

    async def ordered_verified(self, commands, dispatch, verify):
        """Ordered non-atomic commands; fresh readiness required after any write."""
        results=[]
        for command in commands:
            results.append(await self.execute(command,dispatch,verify if command.mutation else None))
        return results
