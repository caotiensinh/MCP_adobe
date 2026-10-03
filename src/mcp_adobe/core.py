from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol


class RiskClass(str, Enum):
    READ = "read"
    WRITE_REVERSIBLE = "write_reversible"
    FILE_WRITE = "file_write"
    DESTRUCTIVE = "destructive"
    NATIVE_SCRIPT = "native_script"
    EXTERNAL_AI = "external_ai"


class PolicyError(PermissionError):
    """Raised when an operation is denied by the gateway execution policy."""


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    allow_destructive: bool = False
    allow_native_script: bool = False
    allow_external_ai: bool = False
    allow_overwrite: bool = False


@dataclass(frozen=True, slots=True)
class AdapterInfo:
    """Runtime capabilities advertised by one Adobe application adapter."""

    application: str
    connected: bool
    version: str | None = None
    common_capabilities: frozenset[str] = field(default_factory=frozenset)
    native_capabilities: frozenset[str] = field(default_factory=frozenset)
    capability_risks: Mapping[str, RiskClass] = field(default_factory=dict)
    writes_enabled: bool = False
    undo_supported: bool = False
    transport: str | None = None
    upstream_repository: str | None = None
    upstream_snapshot: str | None = None

    def supports(self, capability: str) -> bool:
        return capability in self.common_capabilities or capability in self.native_capabilities

    def risk_for(self, capability: str) -> RiskClass:
        try:
            return self.capability_risks[capability]
        except KeyError as exc:
            raise PolicyError(f"capability has no risk classification: {capability}") from exc


class CreativeAdapter(Protocol):
    """Minimal contract implemented by Photoshop/Illustrator/XD adapters."""

    def info(self) -> AdapterInfo:
        ...

    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class CapabilityRegistry:
    """Deterministic registry, policy gate, and router for Adobe adapters."""

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

    @staticmethod
    def _enforce_policy(
        info: AdapterInfo,
        capability: str,
        arguments: Mapping[str, Any],
        policy: ExecutionPolicy,
    ) -> None:
        risk = info.risk_for(capability)

        if risk is RiskClass.READ:
            return

        if not info.writes_enabled:
            raise PolicyError(f"writes are disabled for application: {info.application}")

        if risk is RiskClass.NATIVE_SCRIPT and not policy.allow_native_script:
            raise PolicyError("native script execution is denied by default")

        if risk is RiskClass.DESTRUCTIVE and not policy.allow_destructive:
            raise PolicyError("destructive operation requires explicit authorization")

        if risk is RiskClass.EXTERNAL_AI and not policy.allow_external_ai:
            raise PolicyError("external AI operation requires explicit authorization")

        if risk is RiskClass.FILE_WRITE and arguments.get("overwrite") is True and not policy.allow_overwrite:
            raise PolicyError("overwriting an existing output requires explicit authorization")

    def execute(
        self,
        application: str,
        capability: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        policy: ExecutionPolicy | None = None,
    ) -> Mapping[str, Any]:
        adapter = self.resolve(application, capability)
        args = arguments or {}
        self._enforce_policy(adapter.info(), capability, args, policy or ExecutionPolicy())
        return adapter.execute(capability, args)
