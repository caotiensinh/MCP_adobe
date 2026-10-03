from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class AdapterInfo:
    """Runtime capabilities advertised by one Adobe application adapter."""

    application: str
    connected: bool
    version: str | None = None
    common_capabilities: frozenset[str] = field(default_factory=frozenset)
    native_capabilities: frozenset[str] = field(default_factory=frozenset)
    writes_enabled: bool = False
    undo_supported: bool = False

    def supports(self, capability: str) -> bool:
        return capability in self.common_capabilities or capability in self.native_capabilities


class CreativeAdapter(Protocol):
    """Minimal contract implemented by Photoshop/Illustrator/XD adapters."""

    def info(self) -> AdapterInfo:
        ...

    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class CapabilityRegistry:
    """Deterministic registry and router for connected Adobe adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, CreativeAdapter] = {}

    def register(self, adapter: CreativeAdapter) -> None:
        info = adapter.info()
        application = info.application.strip().lower()
        if not application:
            raise ValueError("adapter application must be non-empty")
        if application in self._adapters:
            raise ValueError(f"adapter already registered: {application}")
        self._adapters[application] = adapter

    def applications(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def describe(self) -> tuple[AdapterInfo, ...]:
        return tuple(self._adapters[name].info() for name in self.applications())

    def resolve(self, application: str, capability: str) -> CreativeAdapter:
        key = application.strip().lower()
        try:
            adapter = self._adapters[key]
        except KeyError as exc:
            raise LookupError(f"no adapter registered for application: {key}") from exc

        info = adapter.info()
        if not info.connected:
            raise RuntimeError(f"application is not connected: {key}")
        if not info.supports(capability):
            raise LookupError(f"capability not supported by {key}: {capability}")
        return adapter

    def execute(
        self,
        application: str,
        capability: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        adapter = self.resolve(application, capability)
        return adapter.execute(capability, arguments or {})
