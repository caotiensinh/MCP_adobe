"""Strictly bounded one-component Photoshop ExtendScript, no import or bulk art.

Native script is high-risk and MUST be invoked only with allow_native_script=True,
after exact target PSD, active layer and reference geometry have been verified.
"""
from __future__ import annotations
import json,math
from typing import Any,Mapping
from panda_red_vector_adapter import sample_path

def compile_path_fill(component:Mapping[str,Any],*,expected_doc:str) -> tuple[str,dict[str,float]]:
    if component.get("kind")!="path":
        raise ValueError("Only blueprint vector paths may be compiled")
    if not isinstance(expected_doc,str) or not expected_doc.startswith("MCP_KFP4_Red_PS_") or not expected_doc.endswith(".psd") or len(expected_doc)>160:
        raise ValueError("Unexpected native Photoshop checkpoint title")
    name=component["name"]
    if not isinstance(name,str) or len(name)>160 or not name[:3].isdigit():
        raise ValueError("Invalid exact layer identity")
    points=sample_path(component["pathData"],count=16)
    x=float(component["x"]); y=float(component["y"])
    coords=[[round(x+px-min(px0 for px0,py0 in points),3),round(y+py-min(py0 for px0,py0 in points),3)] for px,py in points[:-1]]
    if not (3<=len(coords)<=512) or any(not math.isfinite(v) or abs(v)>20000 for pt in coords for v in pt):
        raise ValueError("Unsafe vector point bounds")
    fill=component["fill"]
    if not isinstance(fill,str) or len(fill)!=7 or fill[0]!="#":
        raise ValueError("Invalid color")
    try:r,g,b=bytes.fromhex(fill[1:])
    except ValueError as e:raise ValueError("Invalid RGB components") from e
    xs=[p[0] for p in coords];ys=[p[1] for p in coords]
    bounds={"left":min(xs),"top":min(ys),"right":max(xs),"bottom":max(ys)}
    if bounds["right"]-bounds["left"]<1 or bounds["bottom"]-bounds["top"]<1:
        raise ValueError("Degenerate vector contour")
    # The upstream wraps this code in its own IIFE. Only literal numeric
    # coordinates and validated JSON strings are interpolated.
    source=(
        "var d=app.activeDocument;"
        "if(d.name!=="+json.dumps(expected_doc)+" && d.name!=="+json.dumps(expected_doc[:-4])+")"
        "{throw new Error('RED_PS_WRONG_DOCUMENT_NO_WRITE');}"
        "if(d.activeLayer.name!=="+json.dumps(name)+")"
        "{throw new Error('RED_PS_WRONG_ACTIVE_LAYER_NO_WRITE');}"
        "if(Math.round(d.width.as('px'))!==880||Math.round(d.height.as('px'))!==1265)"
        "{throw new Error('RED_PS_WRONG_CANVAS_NO_WRITE');}"
        "var pts="+json.dumps(coords,separators=(",",":"))+";"
        "var c=new SolidColor();"
        "c.rgb.red="+str(r)+";c.rgb.green="+str(g)+";c.rgb.blue="+str(b)+";"
        "d.selection.select(pts,SelectionType.REPLACE,0,true);"
        "d.selection.fill(c,ColorBlendMode.NORMAL,100,false);"
        "d.selection.deselect();"
        "return {ok:true,shape:"+json.dumps(name)+",vertices:pts.length};"
    )
    if len(source)>18000:raise ValueError("JSX code exceeds bounded single-component limit")
    return source,bounds
