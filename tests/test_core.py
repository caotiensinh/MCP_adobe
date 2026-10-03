from __future__ import annotations

import unittest
from typing import Any, Mapping

from mcp_adobe.core import (
    AdapterInfo,
    CapabilityRegistry,
    ExecutionPolicy,
    PolicyError,
    RiskClass,
)


class FakeAdapter:
    def __init__(self, info: AdapterInfo) -> None:
        self._info = info
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    def info(self) -> AdapterInfo:
        return self._info

    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((capability, arguments))
        return {"ok": True, "capability": capability, "arguments": dict(arguments)}


def adapter_info(
    *,
    application: str = "photoshop",
    connected: bool = True,
    capabilities: Mapping[str, RiskClass] | None = None,
    writes_enabled: bool = True,
) -> AdapterInfo:
    capabilities = capabilities or {}
    return AdapterInfo(
        application=application,
        connected=connected,
        common_capabilities=frozenset(capabilities),
        capability_risks=capabilities,
        writes_enabled=writes_enabled,
        upstream_repository="example/upstream",
        upstream_snapshot="deadbeef",
    )


class CapabilityRegistryTests(unittest.TestCase):
    def test_register_and_discover_are_deterministic(self) -> None:
        registry = CapabilityRegistry()
        registry.register(FakeAdapter(adapter_info(application="Photoshop")))
        registry.register(FakeAdapter(adapter_info(application="Illustrator")))
        self.assertEqual(registry.applications(), ("illustrator", "photoshop"))

    def test_duplicate_application_is_rejected(self) -> None:
        registry = CapabilityRegistry()
        info = adapter_info()
        registry.register(FakeAdapter(info))
        with self.assertRaises(ValueError):
            registry.register(FakeAdapter(info))

    def test_unknown_application_is_rejected(self) -> None:
        registry = CapabilityRegistry()
        with self.assertRaises(LookupError):
            registry.resolve("photoshop", "creative.document.save")

    def test_disconnected_application_is_rejected(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            FakeAdapter(
                adapter_info(
                    connected=False,
                    capabilities={"creative.document.save": RiskClass.FILE_WRITE},
                )
            )
        )
        with self.assertRaises(RuntimeError):
            registry.resolve("photoshop", "creative.document.save")

    def test_unsupported_capability_is_rejected(self) -> None:
        registry = CapabilityRegistry()
        registry.register(FakeAdapter(adapter_info()))
        with self.assertRaises(LookupError):
            registry.resolve("photoshop", "creative.document.save")

    def test_read_capability_is_allowed_when_writes_disabled(self) -> None:
        registry = CapabilityRegistry()
        adapter = FakeAdapter(
            adapter_info(
                capabilities={"creative.document.info": RiskClass.READ},
                writes_enabled=False,
            )
        )
        registry.register(adapter)
        result = registry.execute("photoshop", "creative.document.info")
        self.assertTrue(result["ok"])

    def test_write_is_denied_when_adapter_writes_disabled(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            FakeAdapter(
                adapter_info(
                    capabilities={"creative.object.update": RiskClass.WRITE_REVERSIBLE},
                    writes_enabled=False,
                )
            )
        )
        with self.assertRaises(PolicyError):
            registry.execute("photoshop", "creative.object.update")

    def test_unclassified_capability_fails_closed(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            FakeAdapter(
                AdapterInfo(
                    application="photoshop",
                    connected=True,
                    common_capabilities=frozenset({"creative.object.update"}),
                    writes_enabled=True,
                )
            )
        )
        with self.assertRaises(PolicyError):
            registry.execute("photoshop", "creative.object.update")

    def test_native_script_is_default_deny(self) -> None:
        registry = CapabilityRegistry()
        adapter = FakeAdapter(
            adapter_info(capabilities={"photoshop.execute_script": RiskClass.NATIVE_SCRIPT})
        )
        registry.register(adapter)
        with self.assertRaises(PolicyError):
            registry.execute("photoshop", "photoshop.execute_script", {"code": "alert('x')"})

        result = registry.execute(
            "photoshop",
            "photoshop.execute_script",
            {"code": "alert('x')"},
            policy=ExecutionPolicy(allow_native_script=True),
        )
        self.assertTrue(result["ok"])

    def test_destructive_requires_explicit_authorization(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            FakeAdapter(adapter_info(capabilities={"creative.document.flatten": RiskClass.DESTRUCTIVE}))
        )
        with self.assertRaises(PolicyError):
            registry.execute("photoshop", "creative.document.flatten")
        self.assertTrue(
            registry.execute(
                "photoshop",
                "creative.document.flatten",
                policy=ExecutionPolicy(allow_destructive=True),
            )["ok"]
        )

    def test_file_overwrite_is_default_deny(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            FakeAdapter(adapter_info(capabilities={"creative.document.export": RiskClass.FILE_WRITE}))
        )
        self.assertTrue(
            registry.execute(
                "photoshop",
                "creative.document.export",
                {"path": "new.png", "overwrite": False},
            )["ok"]
        )
        with self.assertRaises(PolicyError):
            registry.execute(
                "photoshop",
                "creative.document.export",
                {"path": "existing.png", "overwrite": True},
            )
        self.assertTrue(
            registry.execute(
                "photoshop",
                "creative.document.export",
                {"path": "existing.png", "overwrite": True},
                policy=ExecutionPolicy(allow_overwrite=True),
            )["ok"]
        )

    def test_external_ai_requires_explicit_authorization(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            FakeAdapter(adapter_info(capabilities={"photoshop.generative_fill": RiskClass.EXTERNAL_AI}))
        )
        with self.assertRaises(PolicyError):
            registry.execute("photoshop", "photoshop.generative_fill")
        self.assertTrue(
            registry.execute(
                "photoshop",
                "photoshop.generative_fill",
                policy=ExecutionPolicy(allow_external_ai=True),
            )["ok"]
        )


if __name__ == "__main__":
    unittest.main()
