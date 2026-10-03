from __future__ import annotations

import unittest
from typing import Any, Mapping

from mcp_adobe.core import AdapterInfo, CapabilityRegistry


class FakeAdapter:
    def __init__(self, info: AdapterInfo) -> None:
        self._info = info
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    def info(self) -> AdapterInfo:
        return self._info

    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((capability, arguments))
        return {"ok": True, "capability": capability, "arguments": dict(arguments)}


class CapabilityRegistryTests(unittest.TestCase):
    def test_register_and_discover_are_deterministic(self) -> None:
        registry = CapabilityRegistry()
        registry.register(FakeAdapter(AdapterInfo(application="Photoshop", connected=True)))
        registry.register(FakeAdapter(AdapterInfo(application="Illustrator", connected=True)))
        self.assertEqual(registry.applications(), ("illustrator", "photoshop"))

    def test_duplicate_application_is_rejected(self) -> None:
        registry = CapabilityRegistry()
        info = AdapterInfo(application="photoshop", connected=True)
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
                AdapterInfo(
                    application="photoshop",
                    connected=False,
                    common_capabilities=frozenset({"creative.document.save"}),
                )
            )
        )
        with self.assertRaises(RuntimeError):
            registry.resolve("photoshop", "creative.document.save")

    def test_unsupported_capability_is_rejected(self) -> None:
        registry = CapabilityRegistry()
        registry.register(FakeAdapter(AdapterInfo(application="photoshop", connected=True)))
        with self.assertRaises(LookupError):
            registry.resolve("photoshop", "creative.document.save")

    def test_supported_capability_routes_to_adapter(self) -> None:
        registry = CapabilityRegistry()
        adapter = FakeAdapter(
            AdapterInfo(
                application="photoshop",
                connected=True,
                common_capabilities=frozenset({"creative.document.save"}),
            )
        )
        registry.register(adapter)
        result = registry.execute(
            "Photoshop",
            "creative.document.save",
            {"path": "example.psd"},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(adapter.calls[0][0], "creative.document.save")
        self.assertEqual(adapter.calls[0][1]["path"], "example.psd")


if __name__ == "__main__":
    unittest.main()
