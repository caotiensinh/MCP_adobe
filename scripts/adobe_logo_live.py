from __future__ import annotations

import json
import os
from pathlib import Path

from mcp_adobe.mcp_stdio import McpSubprocessToolClient, illustrator_stdio_config
from mcp_adobe.server import GatewayRuntime

OUT = Path(os.environ.get("RUNNER_TEMP", ".")) / "mcp-adobe-brand-logo"
OUT.mkdir(parents=True, exist_ok=True)

PSD = OUT / "cao-tien-sinh-brand.psd"
PS_PNG = OUT / "cao-tien-sinh-brand-photoshop.png"
AI = OUT / "cao-tien-sinh-brand.ai"
AI_PNG = OUT / "cao-tien-sinh-brand-illustrator.png"
AI_SVG = OUT / "cao-tien-sinh-brand.svg"

for path in (PSD, PS_PNG, AI, AI_PNG, AI_SVG):
    try:
        path.unlink()
    except FileNotFoundError:
        pass

NAVY = {"type": "rgb", "r": 11, "g": 31, "b": 58}
BLUE = {"type": "rgb", "r": 21, "g": 101, "b": 255}
CYAN = {"type": "rgb", "r": 39, "g": 194, "b": 255}


def p(path: Path) -> str:
    return path.resolve().as_posix()


def assert_tool(label: str, result: dict) -> dict:
    print(f"{label}={json.dumps(result, ensure_ascii=False, default=str)}")
    if result.get("error") is True:
        raise RuntimeError(f"{label} failed: {result}")
    return result


def draw_photoshop() -> None:
    psd = p(PSD)
    png = p(PS_PNG)
    code = r'''
app.displayDialogs = DialogModes.NO;
var doc = app.documents.add(1024, 1024, 72, "Cao Tien Sinh Brand", NewDocumentMode.RGB, DocumentFill.TRANSPARENT);

function rgb(r,g,b) {
  var c = new SolidColor();
  c.rgb.red=r; c.rgb.green=g; c.rgb.blue=b;
  return c;
}
function poly(name, pts, color) {
  var layer = doc.artLayers.add();
  layer.name = name;
  doc.activeLayer = layer;
  doc.selection.select(pts);
  doc.selection.fill(color);
  doc.selection.deselect();
  return layer;
}

// Geometric CTS monogram: C = systems/network, T = engineering, S = signal/data flow.
poly("C / System", [[610,150],[330,150],[150,330],[150,650],[330,830],[610,830],[610,680],[390,680],[300,590],[300,390],[390,300],[610,300]], rgb(11,31,58));
poly("T / Engineering", [[430,245],[700,245],[700,365],[610,365],[610,720],[500,720],[500,365],[430,365]], rgb(21,101,255));
poly("S / Signal", [[610,390],[835,390],[835,500],[690,500],[650,540],[690,580],[835,580],[835,690],[620,690],[515,585],[515,505]], rgb(39,194,255));
poly("AI Node", [[765,210],[835,210],[835,280],[765,280]], rgb(39,194,255));

var title = doc.artLayers.add();
title.kind = LayerKind.TEXT;
title.name = "Brand Name";
title.textItem.contents = "CAO TIEN SINH";
title.textItem.position = [252, 930];
title.textItem.size = 54;
title.textItem.tracking = 140;
title.textItem.color = rgb(11,31,58);

var psdFile = new File("__PSD__");
var psdOpt = new PhotoshopSaveOptions();
psdOpt.layers = true;
psdOpt.embedColorProfile = true;
doc.saveAs(psdFile, psdOpt, true, Extension.LOWERCASE);

var pngFile = new File("__PNG__");
var web = new ExportOptionsSaveForWeb();
web.format = SaveDocumentType.PNG;
web.PNG8 = false;
web.transparency = true;
doc.exportDocument(pngFile, ExportType.SAVEFORWEB, web);
return "CTS_BRAND_PASS|" + app.version + "|LAYERS=" + doc.layers.length + "|PSD=" + psdFile.fsName + "|PNG=" + pngFile.fsName;
'''.replace("__PSD__", psd).replace("__PNG__", png)

    runtime = GatewayRuntime()
    try:
        payload = runtime.authorized_write(
            "photoshop",
            "photoshop.execute_script",
            {"code": code, "timeout_ms": 120000},
            allow_native_script=True,
        )
        print("PHOTOSHOP_GATEWAY=" + json.dumps(payload, ensure_ascii=False, default=str))
    finally:
        runtime.close()

    if not PSD.exists() or not PS_PNG.exists():
        raise RuntimeError("Photoshop MCP call returned but expected PSD/PNG was not created")
    if PSD.read_bytes()[:4] != b"8BPS":
        raise RuntimeError("Invalid PSD signature")
    if PS_PNG.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("Invalid Photoshop PNG signature")
    print(f"PHOTOSHOP_LOGO=PASS PSD_BYTES={PSD.stat().st_size} PNG_BYTES={PS_PNG.stat().st_size}")


def draw_illustrator() -> None:
    client = McpSubprocessToolClient(illustrator_stdio_config())
    try:
        client.start()
        print("ILLUSTRATOR_MCP_CONNECTED=true")
        print("ILLUSTRATOR_TOOL_COUNT=" + str(len(client.tool_names)))
        for required in (
            "create_document", "create_path", "create_text_frame", "save_document", "export"
        ):
            if required not in client.tool_names:
                raise RuntimeError(f"Illustrator MCP tool missing: {required}")

        assert_tool("AI_CREATE_DOCUMENT", client.call_tool("create_document", {
            "width": 1024,
            "height": 1024,
            "color_mode": "rgb",
        }))

        def path(name: str, pts: list[tuple[float, float]], fill: dict) -> None:
            assert_tool(name, client.call_tool("create_path", {
                "anchors": [{"x": x, "y": y, "point_type": "corner"} for x, y in pts],
                "closed": True,
                "fill": fill,
                "stroke": {"color": {"type": "none"}, "width": 0},
                "layer_name": "CTS Brand",
                "name": name,
                "coordinate_system": "artboard-web",
            }))

        path("C / System", [(610,150),(330,150),(150,330),(150,650),(330,830),(610,830),(610,680),(390,680),(300,590),(300,390),(390,300),(610,300)], NAVY)
        path("T / Engineering", [(430,245),(700,245),(700,365),(610,365),(610,720),(500,720),(500,365),(430,365)], BLUE)
        path("S / Signal", [(610,390),(835,390),(835,500),(690,500),(650,540),(690,580),(835,580),(835,690),(620,690),(515,585),(515,505)], CYAN)
        path("AI Node", [(765,210),(835,210),(835,280),(765,280)], CYAN)

        assert_tool("AI_WORDMARK", client.call_tool("create_text_frame", {
            "x": 250,
            "y": 935,
            "contents": "CAO TIEN SINH",
            "kind": "point",
            "font_size": 54,
            "tracking": 140,
            "fill": NAVY,
            "layer_name": "CTS Brand",
            "name": "Brand Name",
            "coordinate_system": "artboard-web",
        }))

        assert_tool("AI_SAVE", client.call_tool("save_document", {
            "mode": "save_as",
            "path": p(AI),
            "overwrite": True,
        }))
        assert_tool("AI_EXPORT_PNG", client.call_tool("export", {
            "target": "artboard:0",
            "format": "png",
            "output_path": p(AI_PNG),
            "overwrite": True,
            "raster_options": {"dpi": 144, "background": "transparent", "antialiasing": True},
        }))
        assert_tool("AI_EXPORT_SVG", client.call_tool("export", {
            "target": "artboard:0",
            "format": "svg",
            "output_path": p(AI_SVG),
            "overwrite": True,
            "svg_options": {"text_outline": False, "embed_images": True, "decimal_places": 3, "encoding": "utf8"},
        }))
    finally:
        client.close()

    if not AI.exists() or not AI_PNG.exists() or not AI_SVG.exists():
        raise RuntimeError("Illustrator MCP did not create all AI/PNG/SVG outputs")
    if AI_PNG.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("Invalid Illustrator PNG signature")
    svg_text = AI_SVG.read_text(encoding="utf-8", errors="ignore")
    if "<svg" not in svg_text.lower():
        raise RuntimeError("Invalid SVG export")
    print(f"ILLUSTRATOR_LOGO=PASS AI_BYTES={AI.stat().st_size} PNG_BYTES={AI_PNG.stat().st_size} SVG_BYTES={AI_SVG.stat().st_size}")


if __name__ == "__main__":
    draw_photoshop()
    draw_illustrator()
    print("MCP_ADOBE_BRAND_LOGO_E2E=PASS")
    print("OUTPUT_DIR=" + str(OUT))
