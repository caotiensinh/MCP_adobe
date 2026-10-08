from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any


RawToolCaller = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]

# This is intentionally the legacy tool vocabulary consumed by IllustratorAdapter.
# The compatibility client translates each supported name into the audited
# jinkeda/Illustrator_MCP 3.0.0 CEP/WebSocket surface. Capabilities whose old
# semantics cannot be preserved safely are omitted rather than falsely advertised.
SUPPORTED_LEGACY_TOOLS = frozenset(
    {
        "list_fonts",
        "get_document_info",
        "get_document_structure",
        "get_selection",
        "get_artboards",
        "get_layers",
        "get_path_items",
        "get_groups",
        "list_text_frames",
        "find_objects",
        "illustrator_job_status",
        "create_document",
        "open_document",
        "save_document",
        "export",
        "create_rectangle",
        "create_ellipse",
        "create_path",
        "create_text_frame",
        "modify_object",
        "select_objects",
        "group_objects",
        "ungroup_objects",
        "set_z_order",
        "move_to_layer",
        "delete_objects",
        "undo",
    }
)


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child)


def _find_key(value: Any, key: str) -> Any:
    for node in _walk(value):
        if isinstance(node, Mapping) and key in node:
            return node[key]
    return None


def _call(raw: RawToolCaller, tool: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
    return raw(tool, {"params": dict(params)})


def _connection_ready(status: Mapping[str, Any]) -> bool:
    layers = _find_key(status, "layers")
    if not isinstance(layers, Mapping):
        return False

    def layer_state(name: str) -> str | None:
        value = layers.get(name)
        if isinstance(value, Mapping):
            state = value.get("status")
            return str(state) if state is not None else None
        return None

    return (
        layer_state("server") == "ok"
        and layer_state("panel") in {"ok", "degraded"}
        and layer_state("illustrator") == "ok"
    )


def _query_artifacts(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for node in _walk(response):
        if not isinstance(node, Mapping):
            continue
        artifacts = node.get("artifacts")
        if isinstance(artifacts, Mapping):
            items = artifacts.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, Mapping)]
    return []


def _artboard_rect_from_response(
    response: Mapping[str, Any],
) -> tuple[float, float, float, float] | None:
    """Read active-artboard context already attached to an upstream response.

    query_items carries documentIntent/context/artboardRect.  Reusing that
    evidence avoids a second raw ExtendScript request, which can race the CEP
    job queue and turn an otherwise successful selection read into E999
    unresolved.
    """
    rect = _find_key(response, "artboardRect")
    if not isinstance(rect, list) or len(rect) != 4:
        return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in rect):
        return None
    return (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))


def _token_from_query_item(item: Mapping[str, Any]) -> str | None:
    # Persistent MCP identity is canonical when available.  Query responses may
    # also include an ephemeral handle for the very same tagged item; preferring
    # that handle makes a bounded select look like it targeted the wrong object
    # during read-back even though Illustrator selected the correct artwork.
    item_ref = item.get("itemRef")
    if isinstance(item_ref, Mapping):
        identity = item_ref.get("identity")
        if isinstance(identity, Mapping):
            item_id = identity.get("itemId")
            if isinstance(item_id, str) and item_id:
                return item_id
    handle = item.get("handle")
    if isinstance(handle, str) and handle:
        return "handle:" + handle
    return None


def _target_selector(token: str) -> dict[str, Any]:
    if token.startswith("handle:"):
        handle = token[len("handle:") :]
        if not handle:
            raise ValueError("Illustrator handle token is empty")
        return {"type": "handle", "handles": [handle]}
    return {"type": "id", "ids": [token]}


def _target_selector_many(tokens: list[str]) -> dict[str, Any]:
    if not tokens:
        raise ValueError("Illustrator operation requires at least one target")
    handle_flags = [token.startswith("handle:") for token in tokens]
    if all(handle_flags):
        handles = [token[len("handle:") :] for token in tokens]
        if any(not handle for handle in handles):
            raise ValueError("Illustrator handle token is empty")
        return {"type": "handle", "handles": handles}
    if any(handle_flags):
        raise ValueError("cannot mix Illustrator handle and persistent-id targets in one operation")
    return {"type": "id", "ids": tokens}


def _tokens_from_arguments(arguments: Mapping[str, Any]) -> list[str]:
    plural = arguments.get("uuids")
    if plural is None:
        plural = arguments.get("ids")
    if isinstance(plural, list):
        tokens = [str(value) for value in plural if isinstance(value, str) and value]
        if tokens:
            return tokens
    for key in ("uuid", "id"):
        value = arguments.get(key)
        if isinstance(value, str) and value:
            return [value]
    return []


def _task(
    raw: RawToolCaller,
    task: str,
    params: Mapping[str, Any] | None = None,
    *,
    targets: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    operation: dict[str, Any] = {"task": task, "params": dict(params or {})}
    if targets is not None:
        operation["targets"] = dict(targets)
    return _call(
        raw,
        "illustrator_execute_task",
        {"batch": {"operations": [operation], "stopOnError": True}},
    )


def _query(raw: RawToolCaller, targets: Mapping[str, Any]) -> Mapping[str, Any]:
    return _call(
        raw,
        "illustrator_query_items",
        {"targets": dict(targets), "include_handles": True},
    )


def _selection(raw: RawToolCaller) -> Mapping[str, Any]:
    response = _query(raw, {"type": "selection"})
    artifacts = _query_artifacts(response)
    artboard = _artboard_rect_from_response(response) if artifacts else None
    normalized: list[dict[str, Any]] = []
    for item in artifacts:
        token = _token_from_query_item(item)
        bounds = item.get("bounds")
        out_bounds: dict[str, Any] = {}
        if isinstance(bounds, Mapping):
            left = bounds.get("left")
            top = bounds.get("top")
            width = bounds.get("width")
            height = bounds.get("height")
            if (
                artboard is not None
                and isinstance(left, (int, float))
                and isinstance(top, (int, float))
                and not isinstance(left, bool)
                and not isinstance(top, bool)
            ):
                # query_items reports Illustrator-native Y-up coordinates. The
                # typed element_modify operation takes active-artboard Y-down.
                out_bounds["x"] = float(left) - artboard[0]
                out_bounds["y"] = artboard[1] - float(top)
            if isinstance(width, (int, float)) and not isinstance(width, bool):
                out_bounds["width"] = float(width)
            if isinstance(height, (int, float)) and not isinstance(height, bool):
                out_bounds["height"] = float(height)
        normalized.append(
            {
                "uuid": token,
                "name": item.get("name"),
                "type": item.get("type"),
                "bounds": out_bounds,
                "handle": item.get("handle"),
                "itemRef": item.get("itemRef"),
            }
        )
    return {
        "selectionCount": len(normalized),
        "coordinateSystem": "active-artboard-y-down",
        "items": normalized,
        "upstream": response,
    }


def _create_element(raw: RawToolCaller, element_type: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    params = dict(arguments)
    params.pop("coordinate_system", None)
    params["type"] = element_type
    return _task(raw, "element_create", params)


def _select_objects(raw: RawToolCaller, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    tokens = _tokens_from_arguments(arguments)
    if not tokens:
        raise ValueError("select_objects requires at least one uuid/id target")
    if len(set(tokens)) != len(tokens):
        raise ValueError("select_objects does not accept duplicate targets")

    script = r"""
var doc = app.activeDocument;
var tokens = __PARAMS__.tokens;
doc.selection = null;
var selected = [];
for (var i = 0; i < tokens.length; i++) {
    var token = tokens[i];
    var item = null;
    if (token.indexOf("handle:") === 0) {
        var resolved = mcpResolveHandle(token.substring(7), doc);
        if (!resolved || !resolved.ok || !resolved.item) {
            throw new Error("Cannot resolve Illustrator handle target: " + token);
        }
        item = resolved.item;
    } else {
        var found = findItemsByMcpId(doc, token, {limit: 100000});
        if (found.truncated) {
            throw new Error("Illustrator ID scan truncated for target: " + token);
        }
        if (!found.items || found.items.length !== 1) {
            throw new Error(
                "Illustrator target must resolve exactly once: " + token +
                " (matches=" + (found.items ? found.items.length : 0) + ")"
            );
        }
        item = found.items[0];
    }
    item.selected = true;
    selected.push(token);
}
var selectionCount = doc.selection ? doc.selection.length : 0;
if (selectionCount !== selected.length) {
    throw new Error(
        "Illustrator selection verification failed: expected " +
        selected.length + ", got " + selectionCount
    );
}
JSON.stringify({selectedCount: selectionCount, tokens: selected});
"""
    mutation = _call(
        raw,
        "illustrator_execute_script",
        {
            "script": script,
            "params": {"tokens": tokens},
            "includes": ["mcp_id", "handles"],
            "read_only": False,
            "auto_assign_ids": "off",
            "description": "Select exact Illustrator objects by MCP identity",
        },
    )
    selection = _selection(raw)
    actual = [
        item.get("uuid")
        for item in selection.get("items", [])
        if isinstance(item, Mapping) and isinstance(item.get("uuid"), str)
    ]
    if len(actual) != len(tokens) or set(actual) != set(tokens):
        raise RuntimeError(
            f"Illustrator selection read-back mismatch: requested={tokens!r}, actual={actual!r}"
        )
    return {
        "selectedCount": len(actual),
        "tokens": actual,
        "selection": selection,
        "mutation": mutation,
    }


def _modify_params(arguments: Mapping[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    properties = arguments.get("properties")
    if isinstance(properties, Mapping):
        position = properties.get("position")
        if isinstance(position, Mapping):
            if "x" in position:
                params["x"] = position["x"]
            if "y" in position:
                params["y"] = position["y"]
        for key in ("x", "y", "width", "height", "rotation", "scale", "name", "fill", "stroke", "opacity", "layer"):
            if key in properties:
                params[key] = properties[key]
    for key in ("x", "y", "width", "height", "rotation", "scale", "name", "fill", "stroke", "opacity", "layer"):
        if key in arguments:
            params[key] = arguments[key]
    return params


def call_legacy_tool(raw: RawToolCaller, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    """Translate one legacy Illustrator tool call onto the CEP/WebSocket backend.

    This function deliberately contains no process lifecycle logic; the caller
    owns the persistent stdio MCP subprocess. That keeps one persistent upstream
    server and therefore one persistent WebSocket listener for the CEP panel.
    """
    if name not in SUPPORTED_LEGACY_TOOLS:
        raise LookupError(f"Illustrator CEP backend does not safely implement legacy tool: {name}")

    args = dict(arguments)

    if name == "list_fonts":
        # creative.health is a diagnostic surface, not a readiness assertion.
        # Upstream intentionally returns a structured connection report even
        # while the panel is busy/down or an unresolved job blocks dispatch.
        # Preserve that report instead of turning "not ready" into a generic
        # tool exception that hides panelBusy/activeRequestId/recovery details.
        probe = args.get("probe", False)
        if not isinstance(probe, bool):
            raise ValueError("creative.health probe must be boolean")
        timeout = args.get("timeout", 5.0)
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError("creative.health timeout must be a positive number")
        status = _call(
            raw,
            "illustrator_connection_status",
            {"probe": probe, "timeout": float(timeout)},
        )
        return {
            "count": 1,
            "fonts": ["Illustrator CEP bridge"],
            "ready": bool(_find_key(status, "ready")),
            "connection": status,
        }

    if name == "get_document_info":
        # Upstream scope="both" composes two nested canonical calls and can
        # misclassify their CallToolResult envelopes as failures. The gateway
        # only needs document state here, so use one bounded host round-trip.
        return _call(raw, "illustrator_get_document", {"scope": "document", "max_items": 1, "max_layers": 50})
    if name == "get_document_structure":
        return _call(raw, "illustrator_get_document", {"scope": "document"})
    if name == "get_selection":
        return _selection(raw)
    if name == "get_layers":
        return _call(raw, "illustrator_get_document", {"scope": "document", "max_items": 1, "max_layers": 200})
    if name == "get_artboards":
        script = (
            "var d=app.activeDocument;var out=[];"
            "for(var i=0;i<d.artboards.length;i++){var a=d.artboards[i];var r=a.artboardRect;"
            "out.push({index:i,name:a.name,rect:[r[0],r[1],r[2],r[3]]});}"
            "JSON.stringify({artboards:out,activeIndex:d.artboards.getActiveArtboardIndex()});"
        )
        return _call(raw, "illustrator_execute_script", {"script": script, "read_only": True})
    if name in {"get_path_items", "get_groups", "list_text_frames"}:
        item_type = {
            "get_path_items": "PathItem",
            "get_groups": "GroupItem",
            "list_text_frames": "TextFrame",
        }[name]
        return _query(raw, {"type": "query", "itemType": item_type})
    if name == "illustrator_job_status":
        job_id = args.get("jobId", args.get("job_id"))
        if not isinstance(job_id, str) or not job_id.strip():
            raise ValueError("illustrator_job_status requires jobId")
        detail = args.get("detail", "full")
        if detail not in {"summary", "full"}:
            raise ValueError("illustrator_job_status detail must be summary/full")
        if args.get("finalize_export") is True:
            raise ValueError("illustrator_job_status compatibility path is inspection-only")
        return _call(
            raw,
            "illustrator_job_status",
            {"jobId": job_id.strip(), "detail": detail, "finalize_export": False},
        )

    if name == "find_objects":
        selector: dict[str, Any] = {"type": "query"}
        item_type = args.get("itemType") or args.get("item_type") or args.get("type")
        if isinstance(item_type, str) and item_type:
            selector["itemType"] = item_type
        pattern = args.get("pattern") or args.get("name")
        if isinstance(pattern, str) and pattern:
            selector["pattern"] = pattern
        contents = args.get("contents") or args.get("text")
        if isinstance(contents, str) and contents:
            selector["contents"] = contents
        return _query(raw, selector)

    if name == "create_document":
        params = {"action": "create"}
        for key in ("width", "height", "color_mode", "name"):
            if key in args:
                params[key] = args[key]
        return _call(raw, "illustrator_document", params)
    if name == "open_document":
        path = args.get("file_path") or args.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("open_document requires file_path/path")
        return _call(raw, "illustrator_document", {"action": "open", "file_path": path})
    if name == "save_document":
        path = args.get("file_path") or args.get("path")
        params: dict[str, Any] = {"action": "save"}
        if isinstance(path, str) and path:
            params["file_path"] = path
        return _call(raw, "illustrator_document", params)
    if name == "export":
        path = args.get("output_path") or args.get("file_path") or args.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("Illustrator export requires an output path")
        params: dict[str, Any] = {
            "file_path": path,
            "format": str(args.get("format", "png")).lower(),
        }
        if "scale" in args:
            params["scale"] = args["scale"]
        overwrite = args.get("overwrite")
        if isinstance(overwrite, bool):
            params["overwrite"] = "replace" if overwrite else "fail"
        elif isinstance(overwrite, str) and overwrite in {"replace", "fail", "version"}:
            params["overwrite"] = overwrite
        return _call(raw, "illustrator_export_document", params)

    if name == "create_rectangle":
        return _create_element(raw, "rect", args)
    if name == "create_ellipse":
        return _create_element(raw, "ellipse", args)
    if name == "create_path":
        return _create_element(raw, "path", args)
    if name == "create_text_frame":
        params = dict(args)
        if "text" in params and "contents" not in params:
            params["contents"] = params.pop("text")
        return _task(raw, "text_create", params)

    if name == "modify_object":
        tokens = _tokens_from_arguments(args)
        if len(tokens) != 1:
            raise ValueError("modify_object requires exactly one uuid/id target")
        return _task(raw, "element_modify", _modify_params(args), targets=_target_selector(tokens[0]))
    if name == "select_objects":
        return _select_objects(raw, args)
    if name == "group_objects":
        tokens = _tokens_from_arguments(args)
        params = {"name": args["name"]} if isinstance(args.get("name"), str) else {}
        return _task(raw, "group_create", params, targets=_target_selector_many(tokens))
    if name == "ungroup_objects":
        tokens = _tokens_from_arguments(args)
        return _task(raw, "group_ungroup", {}, targets=_target_selector_many(tokens))
    if name == "set_z_order":
        tokens = _tokens_from_arguments(args)
        action = args.get("action") or args.get("position") or args.get("z_order")
        aliases = {
            "front": "zorder_front",
            "bring_to_front": "zorder_front",
            "back": "zorder_back",
            "send_to_back": "zorder_back",
            "forward": "zorder_forward",
            "bring_forward": "zorder_forward",
            "backward": "zorder_backward",
            "send_backward": "zorder_backward",
        }
        task = aliases.get(str(action).lower())
        if task is None:
            raise ValueError("set_z_order requires front/back/forward/backward action")
        return _task(raw, task, {}, targets=_target_selector_many(tokens))
    if name == "move_to_layer":
        tokens = _tokens_from_arguments(args)
        if len(tokens) != 1:
            raise ValueError("move_to_layer requires exactly one uuid/id target")
        layer = args.get("layer") or args.get("layer_name")
        if not isinstance(layer, str) or not layer:
            raise ValueError("move_to_layer requires layer/layer_name")
        return _task(raw, "element_modify", {"layer": layer}, targets=_target_selector(tokens[0]))
    if name == "delete_objects":
        tokens = _tokens_from_arguments(args)
        return _task(raw, "element_delete", {}, targets=_target_selector_many(tokens))
    if name == "undo":
        count = args.get("count", 1)
        return _call(raw, "illustrator_history", {"action": "undo", "count": count})

    raise AssertionError(f"unreachable Illustrator CEP translation for {name}")
