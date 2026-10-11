"""Fast one-shot Photoshop component creation through bounded native ExtendScript.

A single MCP operation creates exactly ONE named native Photoshop pixel layer,
draws its closed raster selection from editable plan geometry, and returns.
Persist/read back separately; unknown outcome prohibits retrying the command.
"""
from __future__ import annotations

import json
import math
from typing import Any, Mapping

if __package__:
    from .panda_red_vector_adapter import sample_path
else:
    from panda_red_vector_adapter import sample_path


def compile_native_shape(component: Mapping[str,Any], *, document: str,
                         ordinal: int) -> tuple[str,dict[str,float]]:
    if not isinstance(document,str) or not document.startswith("MCP_KFP4_Red_PS_") \
       or not document.endswith(".psd") or len(document)>155:
        raise ValueError("Unexpected native target Photoshop document")
    if not isinstance(ordinal,int) or not 1<=ordinal<=60:
        raise ValueError("Unsafe cumulative layer identity")
    name=component.get("name")
    if not isinstance(name,str) or not name.startswith(f"{ordinal:03d} ") or len(name)>160:
        raise ValueError("Wrong ordinal/name binding")
    kind=component.get("kind")
    if kind not in ("path","rectangle","ellipse"):
        raise ValueError("Only bounded non-text shape primitives supported")
    color=component.get("fill","")
    if not isinstance(color,str) or len(color)!=7 or not color.startswith("#"):
        raise ValueError("Invalid native RGB")
    try:
        r,g,b=bytes.fromhex(color[1:])
    except ValueError as exc:
        raise ValueError("Malformed native color") from exc
    x=float(component["x"]);y=float(component["y"])
    if not all(math.isfinite(z) for z in (x,y)):
        raise ValueError("Nonfinite placement")
    if kind=="path":
        points=sample_path(component["pathData"],count=16)
        minx=min(px for px,py in points);miny=min(py for px,py in points)
        coords=[[round(x+px-minx,3),round(y+py-miny,3)] for px,py in points[:-1]]
        xs=[p[0] for p in coords];ys=[p[1] for p in coords]
        bounds=dict(left=min(xs),top=min(ys),right=max(xs),bottom=max(ys))
        draw="d.selection.select("+json.dumps(coords,separators=(",",":"))+",SelectionType.REPLACE,0,true);"
    else:
        width=float(component["width"]);height=float(component["height"])
        if not all(math.isfinite(z) and 0<z<=20000 for z in (width,height)):
            raise ValueError("Degenerate native primitive")
        bounds=dict(left=x,top=y,right=x+width,bottom=y+height)
        if kind=="rectangle":
            pts=[[x,y],[x+width,y],[x+width,y+height],[x,y+height]]
            draw="d.selection.select("+json.dumps(pts,separators=(",",":"))+",SelectionType.REPLACE,0,true);"
        else:
            # Exact Action Manager ellipse constructor as used by the pinned
            # Photoshop-MCP upstream. Never approximate an ellipse by a box.
            commands=[
                "var desc=new ActionDescriptor();",
                "var ref=new ActionReference();",
                "ref.putProperty(charIDToTypeID('Chnl'),charIDToTypeID('fsel'));",
                "desc.putReference(charIDToTypeID('null'),ref);",
                "var elps=new ActionDescriptor();",
            ]
            for key,val in (("Top ",y),("Left",x),("Btom",y+height),("Rght",x+width)):
                commands.append("elps.putUnitDouble(charIDToTypeID("+json.dumps(key)+"),charIDToTypeID('#Pxl'),"+str(round(val,3))+");")
            commands.extend([
                "desc.putObject(charIDToTypeID('T   '),charIDToTypeID('Elps'),elps);",
                "desc.putBoolean(charIDToTypeID('AntA'),true);",
                "executeAction(charIDToTypeID('setd'),desc,DialogModes.NO);"
            ])
            draw="".join(commands)
    if not all(math.isfinite(v) and -20000<=v<=20000 for v in bounds.values()) or \
       bounds["right"]<=bounds["left"] or bounds["bottom"]<=bounds["top"]:
        raise ValueError("Unsafe actual graphic bounds")
    title=json.dumps(document)
    n=json.dumps(name)
    # Duplicates are rejected BEFORE creating the layer. Source SHA and
    # exact active document are independently checked by the caller.
    code=(
      "var d=app.activeDocument;"
      "if(d.name!=="+title+"&&d.name!=="+json.dumps(document[:-4])+")"
      "{throw new Error('RED_PS_FAST_WRONG_ACTIVE_DOC');}"
      "if(Math.round(d.width.as('px'))!==880||Math.round(d.height.as('px'))!==1265)"
      "{throw new Error('RED_PS_FAST_WRONG_CANVAS');}"
      "if(d.layers.length!=="+str(ordinal)+")"
      "{throw new Error('RED_PS_FAST_LAYER_COUNT_MISMATCH');}"
      "for(var i=0;i<d.layers.length;i++){if(d.layers[i].name==="+n+")"
      "{throw new Error('RED_PS_FAST_DUPLICATE_LAYER_NO_WRITE');}}"
      "var layer=d.artLayers.add();layer.name="+n+";"
      "if(d.activeLayer.name!=="+n+")"
      "{throw new Error('RED_PS_FAST_INSERTION_NOT_ACTIVE');}"
      +draw+
      "var color=new SolidColor();color.rgb.red="+str(r)+";"
      "color.rgb.green="+str(g)+";color.rgb.blue="+str(b)+";"
      "d.selection.fill(color,ColorBlendMode.NORMAL,100,false);"
      "d.selection.deselect();"
      "return {ok:true,layer:"+n+",kind:"+json.dumps(kind)+",afterCount:d.layers.length};"
    )
    if len(code)>18000:
        raise ValueError("Too many native JSX source bytes")
    return code,bounds
