from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from mcp_adobe import CapabilityRegistry, McpSubprocessToolClient, PhotoshopAdapter, photoshop_stdio_config


OUT_DIR = Path(os.environ.get("RUNNER_TEMP", ".")) / "mcp-adobe-photoshop-active-selection"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _state(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise RuntimeError(f"Photoshop context result is not a mapping: {type(result).__name__}")
    return result


def _active_layer(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    state = _state(payload)
    if state.get("hasDocument") is not True:
        raise RuntimeError("Photoshop has no active document")
    layer = state.get("activeLayer")
    if not isinstance(layer, Mapping):
        raise RuntimeError("Photoshop has no active layer")
    return layer


def _bounds(layer: Mapping[str, Any]) -> dict[str, float]:
    raw = layer.get("bounds")
    if not isinstance(raw, Mapping):
        raise RuntimeError("Active Photoshop layer has no readable bounds")
    try:
        return {key: float(raw[key]) for key in ("left", "top", "right", "bottom")}
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid active-layer bounds: {raw!r}") from exc


def _near(actual: float, expected: float, tolerance: float = 0.75) -> bool:
    return abs(actual - expected) <= tolerance


def _require_restored(actual: Mapping[str, float], expected: Mapping[str, float], label: str) -> None:
    for key in ("left", "top", "right", "bottom"):
        if not _near(float(actual[key]), float(expected[key])):
            raise RuntimeError(
                f"{label}: {key} was not restored; expected={expected[key]} actual={actual[key]}"
            )


def main() -> None:
    evidence: dict[str, Any] = {}
    undo_debt = 0
    config = replace(photoshop_stdio_config(), startup_timeout_seconds=180.0)

    with McpSubprocessToolClient(config) as client:
        # The upstream Photoshop MCP intentionally defers host detection until
        # photoshop_ping. get_state before a successful ping is invalid on a
        # cold server and returns "Photoshop info not available".
        ping = client.call_tool("photoshop_ping", {})
        evidence["ping"] = dict(ping)
        ping_text = " ".join(str(ping.get(key, "")) for key in ("text", "message", "value"))
        if ping.get("connected") is not True and "successfully connected to photoshop" not in ping_text.lower():
            raise RuntimeError(f"Photoshop ping did not establish a live host connection: {ping!r}")
        print("PHOTOSHOP_PING=PASS " + json.dumps(ping, ensure_ascii=False, sort_keys=True), flush=True)

        registry = CapabilityRegistry()
        registry.register(PhotoshopAdapter(client, writes_enabled=True))

        before_payload = registry.execute("photoshop", "creative.context.get", {})
        before_layer = _active_layer(before_payload)
        before_bounds = _bounds(before_layer)
        original_opacity = float(before_layer.get("opacity", 100))
        selected_name = str(before_layer.get("name", ""))

        evidence["before"] = {
            "document": _state(before_payload).get("document"),
            "activeLayer": dict(before_layer),
        }
        print(
            "PHOTOSHOP_ACTIVE_SELECTION_BEFORE="
            + json.dumps(evidence["before"], ensure_ascii=False, sort_keys=True),
            flush=True,
        )

        try:
            move_result = registry.execute(
                "photoshop",
                "creative.selection.move",
                {"deltaX": 12, "deltaY": 0},
            )
            undo_debt += 1
            evidence["move_result"] = dict(move_result)
            if move_result.get("outcome") != "verified":
                raise RuntimeError(f"Gateway did not verify live active-layer move: {move_result!r}")
            if move_result.get("selection_source") != "live-photoshop-active-layer":
                raise RuntimeError(f"Unexpected selection source: {move_result!r}")
            if move_result.get("selected_layer_name") != selected_name:
                raise RuntimeError(
                    "Gateway targeted a different layer than the one Photoshop reported immediately before mutation"
                )

            moved_payload = registry.execute("photoshop", "creative.context.get", {})
            moved_layer = _active_layer(moved_payload)
            moved_bounds = _bounds(moved_layer)
            observed_dx = moved_bounds["left"] - before_bounds["left"]
            observed_dy = moved_bounds["top"] - before_bounds["top"]
            if not _near(observed_dx, 12.0) or not _near(observed_dy, 0.0):
                raise RuntimeError(
                    f"Live Photoshop bounds did not move by requested delta: dx={observed_dx} dy={observed_dy}"
                )
            evidence["after_move"] = {
                "activeLayer": dict(moved_layer),
                "observedDelta": {"x": observed_dx, "y": observed_dy},
            }
            print(
                f"PHOTOSHOP_ACTIVE_SELECTION_MOVE=PASS layer={selected_name!r} dx={observed_dx} dy={observed_dy}",
                flush=True,
            )

            registry.execute("photoshop", "creative.undo", {})
            undo_debt -= 1
            restored_payload = registry.execute("photoshop", "creative.context.get", {})
            restored_layer = _active_layer(restored_payload)
            restored_bounds = _bounds(restored_layer)
            _require_restored(restored_bounds, before_bounds, "move undo")
            evidence["after_move_undo"] = {"activeLayer": dict(restored_layer)}
            print("PHOTOSHOP_ACTIVE_SELECTION_MOVE_UNDO=PASS", flush=True)

            target_opacity = 60.0 if not _near(original_opacity, 60.0, 0.01) else 55.0
            update_result = registry.execute(
                "photoshop",
                "creative.selection.update",
                {"properties": {"opacity": target_opacity}},
            )
            undo_debt += 1
            evidence["update_result"] = dict(update_result)
            if update_result.get("outcome") != "verified":
                raise RuntimeError(f"Gateway did not verify live opacity update: {update_result!r}")
            if update_result.get("selected_layer_name") != selected_name:
                raise RuntimeError(
                    "Gateway opacity update targeted a different layer than the live active layer"
                )

            updated_payload = registry.execute("photoshop", "creative.context.get", {})
            updated_layer = _active_layer(updated_payload)
            actual_opacity = float(updated_layer.get("opacity"))
            if not _near(actual_opacity, target_opacity, 0.01):
                raise RuntimeError(
                    f"Live Photoshop opacity read-back mismatch: expected={target_opacity} actual={actual_opacity}"
                )
            evidence["after_opacity"] = {"activeLayer": dict(updated_layer)}
            print(
                f"PHOTOSHOP_ACTIVE_SELECTION_OPACITY=PASS layer={selected_name!r} opacity={actual_opacity}",
                flush=True,
            )

            registry.execute("photoshop", "creative.undo", {})
            undo_debt -= 1
            final_payload = registry.execute("photoshop", "creative.context.get", {})
            final_layer = _active_layer(final_payload)
            final_opacity = float(final_layer.get("opacity"))
            final_bounds = _bounds(final_layer)
            if not _near(final_opacity, original_opacity, 0.01):
                raise RuntimeError(
                    f"opacity undo did not restore original value: expected={original_opacity} actual={final_opacity}"
                )
            _require_restored(final_bounds, before_bounds, "final bounds")
            if str(final_layer.get("name", "")) != selected_name:
                raise RuntimeError("Final active layer changed unexpectedly")
            evidence["final"] = {"activeLayer": dict(final_layer)}
            print("PHOTOSHOP_ACTIVE_SELECTION_OPACITY_UNDO=PASS", flush=True)
            print("PHOTOSHOP_ACTIVE_SELECTION_E2E=PASS", flush=True)
        finally:
            while undo_debt > 0:
                try:
                    registry.execute("photoshop", "creative.undo", {})
                    print("PHOTOSHOP_ACTIVE_SELECTION_CLEANUP_UNDO=PASS", flush=True)
                except Exception as exc:
                    print(f"PHOTOSHOP_ACTIVE_SELECTION_CLEANUP_UNDO=FAIL {exc}", flush=True)
                    break
                undo_debt -= 1

    (OUT_DIR / "photoshop-active-selection-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
