"""Reject a visually blank XD panda despite 32 GUIDs by checking native AGC geometry."""
import argparse,hashlib,json,zipfile
from pathlib import Path
from panda_xd_mode1_e2e import STEPS
def audit(xd:Path,receipt:Path):
    if not xd.is_file() or not receipt.is_file():raise RuntimeError("XD_GEOMETRY_AUDIT_MISSING_FILES")
    saved=json.loads(receipt.read_text(encoding="utf-8"))
    guids={x["name"]:x["guid"] for x in saved["proven"]}
    if len(guids)!=32 or len(set(guids.values()))!=32:
        raise RuntimeError("XD_GEOMETRY_AUDIT_ORIGINAL_CHECKPOINT_WRONG")
    with zipfile.ZipFile(xd) as z:
        if z.testzip() is not None:raise RuntimeError("XD_GEOMETRY_AUDIT_CORRUPT_ZIP")
        files=[n for n in z.namelist() if n.startswith("artwork/artboard-") and n.endswith("/graphics/graphicContent.agc")]
        if len(files)!=1:raise RuntimeError("XD_GEOMETRY_AUDIT_AMBIGUOUS_ARTBOARD")
        graphics=json.loads(z.read(files[0]))
        parts=graphics["children"][0]["artboard"]["children"]
    if len(parts)!=32:raise RuntimeError("XD_GEOMETRY_AUDIT_SHAPE_COUNT_NOT_32")
    got={v.get("name"):v for v in parts}
    if set(got)!={s[0] for s in STEPS}:raise RuntimeError("XD_GEOMETRY_AUDIT_OBJECT_NAMES_CHANGED")
    errors=[]
    for name,cap,params in STEPS:
        node=got[name]
        if node.get("id")!=guids[name]:
            errors.append(name+" GUID changed")
        geom=node.get("shape") or {}
        if cap=="creative.shape.ellipse":
            typ=geom.get("type")
            if typ=="circle":
                if not isinstance(geom.get("r"),(int,float)) or geom["r"]<=0:
                    errors.append(name+" ZERO_RADIUS")
            elif typ=="ellipse":
                x=geom.get("rx",geom.get("radiusX"))
                y=geom.get("ry",geom.get("radiusY"))
                if not isinstance(x,(int,float)) or not isinstance(y,(int,float)) or x<=0 or y<=0:
                    errors.append(name+" ZERO_ELLIPSE_RADII")
            else:
                errors.append(name+" UNKNOWN_ELLIPSE_GEOMETRY "+repr(geom)[:120])
        elif geom.get("type")=="rect":
            if geom.get("width",0)<1 or geom.get("height",0)<1:
                errors.append(name+" ZERO_RECT")
        else:errors.append(name+" WRONG_RECT_TYPE "+str(geom.get("type")))
    print("XD_NATIVE_GEOMETRY_AUDIT="+json.dumps({"objects":len(parts),"zero_or_invalid":len(errors),
      "errors":errors[:25],"xd_sha256":hashlib.sha256(xd.read_bytes()).hexdigest()}),flush=True)
    if errors:raise RuntimeError("XD_NATIVE_GEOMETRY_IS_NOT_VISIBLE_FAIL")
    print("XD_NATIVE_ALL_32_GEOMETRIES_VISIBLE=PASS",flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--xd",type=Path,default=Path.home()/"Documents"/"MCPAdobe"/"MCP_Mode1_Panda_XD_38136531800.xd")
    ap.add_argument("--receipt",type=Path,default=Path.home()/"Documents"/"MCPAdobe"/"MCP_Mode1_Panda_XD_38136531800.json")
    args=ap.parse_args()
    audit(args.xd,args.receipt)
