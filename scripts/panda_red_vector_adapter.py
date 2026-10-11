"""Translate one red poster design component into ONE native Adobe MCP write.

No SVG import, JSX bundle, or multi-part script. Bézier paths become editable
Illustrator paths (with bounded sampled anchors); Adobe XD retains one native
Path node with pathData. Unsupported Photoshop paths fail closed, never turn
into silent rectangles or claim equivalence.
"""
from __future__ import annotations

import math
import re
from typing import Any, Mapping

TOKEN = re.compile(r"[MmLlCcZz]|[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][-+]?[0-9]+)?")
SEP = re.compile(r"[\s,]*")
SAMPLES_PER_CUBIC = 20
MAX_POINTS = 512


def rgb(hex_color: str) -> dict[str, int]:
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", hex_color):
        raise ValueError("invalid RGB fill")
    return {key:int(hex_color[i:i+2],16) for key,i in (("r",1),("g",3),("b",5))}


def sample_path(path_data: str, *, count: int = SAMPLES_PER_CUBIC) -> list[tuple[float,float]]:
    if not isinstance(path_data,str) or len(path_data) > 8192 or len(path_data) < 6:
        raise ValueError("bad path data size")
    tokens=TOKEN.findall(path_data)
    if not tokens or not re.fullmatch(r"[MmLlCcZz0-9eE.,+\-\s]+",path_data):
        raise ValueError("unsupported or malformed SVG path syntax")
    if ''.join(TOKEN.findall(path_data)) != re.sub(r"[\s,]","",path_data):
        raise ValueError("unparsed path data")
    pos=0
    points: list[tuple[float,float]]=[]
    cursor=(0.0,0.0)
    start=None
    def take_number():
        nonlocal pos
        if pos>=len(tokens) or tokens[pos] in "MLCZmlcz":
            raise ValueError("SVG command has missing numeric operand")
        n=float(tokens[pos])
        pos+=1
        if not math.isfinite(n) or abs(n)>20000:raise ValueError("SVG numeric operand out of bounds")
        return n
    while pos<len(tokens):
        cmd=tokens[pos];pos+=1
        if cmd not in {"M","L","C","Z"}:
            raise ValueError("only absolute M/L/C/Z vector commands are permitted")
        if cmd=="M":
            if start is not None:raise ValueError("one independently editable contour per operation")
            cursor=(take_number(),take_number())
            start=cursor
            points.append(cursor)
        elif cmd=="L":
            if start is None:raise ValueError("path missing M start")
            cursor=(take_number(),take_number())
            points.append(cursor)
        elif cmd=="C":
            if start is None:raise ValueError("curve missing start")
            c1=(take_number(),take_number())
            c2=(take_number(),take_number())
            end=(take_number(),take_number())
            a=cursor
            for k in range(1,count+1):
                t=k/count
                u=1-t
                bx=u*u*u*a[0]+3*u*u*t*c1[0]+3*u*t*t*c2[0]+t*t*t*end[0]
                by=u*u*u*a[1]+3*u*u*t*c1[1]+3*u*t*t*c2[1]+t*t*t*end[1]
                points.append((bx,by))
            cursor=end
        else:
            if start is None or len(points)<3:raise ValueError("closed vector path has too few points")
            if pos!=len(tokens):raise ValueError("commands after final Z are not permitted")
            if points[-1]!=start:points.append(start)
        if len(points)>MAX_POINTS:raise ValueError("individual vector path exceeds bounded complexity")
    if not path_data.rstrip().endswith("Z") or len(points)<4 or points[-1]!=points[0]:
        raise ValueError("Adobe filled vector path must be closed")
    if (max(x for x,y in points)-min(x for x,y in points))<1 or (
        max(y for x,y in points)-min(y for x,y in points))<1:
        raise ValueError("vector contour degenerate")
    return points


def translate(application: str, component: Mapping[str,Any]) -> tuple[str,dict[str,Any]]:
    kind=component["kind"]
    x=float(component["x"]); y=float(component["y"])
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("nonfinite global canvas position")
    name=str(component["name"])
    if not name or len(name)>160:raise ValueError("ambiguous layer identity")
    application=application.lower()
    if application not in ("xd","illustrator","photoshop"):
        raise ValueError("unknown Adobe application")
    fill=component["fill"]
    color=fill if application=="xd" else rgb(fill)
    args={"name":name,"x":x,"y":y,"fill":color}
    if kind in ("rectangle","ellipse"):
        w=float(component["width"]); h=float(component["height"])
        if not all(math.isfinite(v) and v>0 for v in (w,h)):
            raise ValueError("degenerate primitive")
        args.update(width=w,height=h)
        return ("creative.shape.rectangle" if kind=="rectangle" else "creative.shape.ellipse"),args
    if kind=="path":
        sampled=sample_path(component["pathData"])
        if application=="photoshop":
            raise ValueError("Photoshop path capability unavailable; do not import image or rasterize silently")
        if application=="xd":
            args["pathData"]=component["pathData"]
        else:
            minx=min(p[0] for p in sampled); miny=min(p[1] for p in sampled)
            args={"name":name,"points":[[round(x+px-minx,3),round(y+py-miny,3)]
                  for px,py in sampled[:-1]],"closed":True,"fill":color}
        return "creative.path.create",args
    if kind=="text":
        if application=="photoshop":
            # Native Photoshop text capability exists but its font parameters
            # must be confirmed against the installed host before live writes.
            raise ValueError("Photoshop text schema not live-verified; cannot silently substitute raster logo")
        args.update(text=str(component["text"]),fontSize=float(component["fontSize"]))
        return "creative.text.create",args
    raise ValueError("unknown component geometry")
