"""Photoshop panda: separate MCP primitive writes, strict per-shape readback and PSD checkpoints."""
import asyncio, hashlib, json, os, time
from pathlib import Path
from collections.abc import Mapping
from mcp import Client

ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
RUN=os.getenv("PANDA_PS_RESUME_RUN_ID") or os.getenv("GITHUB_RUN_ID","local")
TARGET=ROOT/f"MCP_Mode1_Panda_PS_{RUN}.psd"
PNG=ROOT/f"MCP_Mode1_Panda_PS_{RUN}.png"
GATEWAY="http://127.0.0.1:8787/mcp"
def rect(name,x,y,w,h,color):
    return (name,"rectangle",x,y,w,h,color)
def oval(name,x,y,w,h,color):
    return (name,"ellipse",x,y,w,h,color)
S=(242,249,248); G=(164,205,147); K=(39,45,49); W=(247,246,235)
B=(74,153,65); H=(220,173,108)
STEPS=[
    rect("01 Garden background",0,0,880,640,S),
    rect("02 Meadow",0,568,880,72,G),
    rect("03 Bamboo stalk",590,242,18,302,B),
    rect("04 Bamboo joint A",585,302,29,8,(51,113,54)),
    rect("05 Bamboo joint B",585,390,29,8,(51,113,54)),
    oval("06 Bamboo top leaf",605,271,61,26,B),
    oval("07 Bamboo middle leaf",540,352,60,27,B),
    oval("08 Panda left foot",285,500,120,71,K),
    oval("09 Panda right foot",480,500,120,71,K),
    oval("10 Panda left ear",297,166,100,114,K),
    oval("11 Panda right ear",484,166,100,114,K),
    oval("12 Panda black body",303,331,275,233,K),
    oval("13 Panda white belly",353,359,185,187,W),
    oval("14 Panda left arm",258,349,95,154,K),
    oval("15 Panda right arm",538,341,97,152,K),
    oval("16 Panda white head",320,189,240,218,W),
    oval("17 Panda left eye patch",353,250,77,95,K),
    oval("18 Panda right eye patch",453,250,77,95,K),
    oval("19 Panda left eye white",389,280,22,27,W),
    oval("20 Panda right eye white",480,280,22,27,W),
    oval("21 Panda black nose",423,337,35,24,K),
    oval("22 Panda mouth",417,365,46,9,(118,91,89)),
    oval("23 Panda hand holding bamboo",563,408,67,66,K),
    oval("24 Non la brim",293,182,297,34,(175,120,69)),
    rect("25 Non la cone base",330,160,224,22,H),
    rect("26 Non la cone middle",361,134,165,26,H),
    rect("27 Non la cone upper",393,108,99,26,H),
    rect("28 Non la cone tip",430,77,25,31,H),
    rect("29 Non la highlight",441,105,10,75,(243,205,150)),
    rect("30 Non la strap",372,196,7,153,(157,96,51)),
    oval("31 Pink flower",214,590,20,20,(241,150,174)),
    oval("32 Yellow flower",689,585,20,20,(248,208,92)),
]
def walk(v):
    yield v
    if isinstance(v,Mapping):
        for x in v.values(): yield from walk(x)
    elif isinstance(v,(list,tuple)):
        for x in v: yield from walk(x)
def decode_text(v):
    if isinstance(v,str):
        raw=v.strip()
        if raw.startswith("Layers:"): raw=raw[raw.find("{"):]
        try: return json.loads(raw)
        except (ValueError,TypeError): return v
    return v
def names_in(v):
    result=set()
    for node in walk(v):
        if isinstance(node,Mapping) and "name" in node and isinstance(node["name"],str):
            result.add(node["name"])
        if isinstance(node,Mapping) and isinstance(node.get("text"),str):
            extra=decode_text(node["text"])
            if extra is not node["text"]: result.update(names_in(extra))
    return result
async def call(c,tool,cap,args=None):
    payload={"application":"photoshop","capability":cap,"arguments":args or {}}
    if tool=="creative_authorized_write":
        if cap!="creative.style.fill":
            raise RuntimeError("PS_FORBIDDEN_HIGH_RISK_CAPABILITY "+cap)
        payload["allow_destructive"]=True
    if cap=="creative.document.save":
        if str((args or {}).get("path"))!=str(TARGET):
            raise RuntimeError("PS_FORBIDDEN_CHECKPOINT_PATH")
        payload["allow_overwrite"]=True
    r=await c.call_tool(tool,payload)
    p=r.structured_content
    print("PS_MCP_RESPONSE="+json.dumps({"tool":tool,"capability":cap,"error":r.is_error,
         "response":str(p)[:1800],"error_content":[str(v)[:900] for v in r.content] if r.is_error else []},default=str),flush=True)
    if r.is_error or not isinstance(p,dict) or p.get("ok") is not True:
        raise RuntimeError("PS_MCP_UNKNOWN_OR_FAILED_NO_REPLAY "+cap)
    execution=(p.get("result") or {}).get("execution")
    if execution in ("unknown","failed"):
        raise RuntimeError("PS_MCP_EXECUTION_UNCERTAIN_NO_REPLAY "+cap)
    return p
async def layers(c):
    p=await call(c,"creative_read","creative.layer.list")
    ns=names_in(p)
    existing=[n for n,*_ in STEPS if n in ns]
    print("PS_LAYER_READBACK="+json.dumps({"recognized":len(existing),"names":sorted(existing)}),flush=True)
    return set(existing)
async def state(c):
    p=await call(c,"creative_read","creative.document.info")
    print("PS_DOCUMENT_READBACK="+str(p)[:1700],flush=True)
    return p
async def save(c,n):
    p=await call(c,"creative_write","creative.document.save",
                 {"path":str(TARGET),"format":"PSD"})
    if not TARGET.is_file() or TARGET.stat().st_size<1000:
        raise RuntimeError("PS_CHECKPOINT_FILE_NOT_VERIFIED")
    print("PS_MODE1_CHECKPOINT="+json.dumps({"stroke":n,"bytes":TARGET.stat().st_size,
         "sha256":hashlib.sha256(TARGET.read_bytes()).hexdigest()}),flush=True)
def doc_state(payload):
    data=payload.get("result") or {}
    if not isinstance(data,Mapping):raise RuntimeError("PS_DOCUMENT_STATE_NOT_MAPPING")
    return data

def check_dimensions(doc):
    if not isinstance(doc,Mapping) or int(doc.get("width",-1))!=880 or int(doc.get("height",-1))!=640:
        raise RuntimeError("PS_DOCUMENT_DIMENSIONS_NOT_TEST_CANVAS")

def verify_painted_layer(state_payload,name,x,y,w,h):
    data=doc_state(state_payload)
    active=data.get("activeLayer") or {}
    if active.get("name")!=name:raise RuntimeError("PS_ACTIVE_LAYER_CHANGED_DURING_FILL")
    bounds=active.get("bounds") or {}
    for key,expected in (("left",x),("top",y),("right",x+w),("bottom",y+h)):
        try: error=abs(float(bounds[key])-expected)
        except (KeyError,ValueError,TypeError):raise RuntimeError("PS_FILL_BOUNDS_UNAVAILABLE "+str(bounds))
        if error>3:
            raise RuntimeError("PS_FILL_PIXEL_BOUNDS_MISMATCH "+json.dumps({"name":name,"key":key,
                "expected":expected,"actual":bounds[key]}))
    print("PS_PAINTED_PIXELS_VERIFIED="+json.dumps({"name":name,"bounds":bounds}),flush=True)

async def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    async with Client(GATEWAY) as c:
        await call(c,"creative_read","creative.health")
        original=doc_state(await state(c))
        existing=await layers(c) if original.get("hasDocument") else set()
        if TARGET.exists():
            # The previous attempt saved the initial blank document, while a
            # gateway policy rejection prevented its first fill from executing.
            # Never assume an in-memory unfinished layer was persisted.
            print("PS_PREVIOUS_CHECKPOINT_FOUND="+json.dumps({"path":str(TARGET),
                  "bytes":TARGET.stat().st_size,"sha256":hashlib.sha256(TARGET.read_bytes()).hexdigest()}),flush=True)
            doc=original.get("document") or {}
            active=original.get("activeLayer") or {}
            matches=(bool(original.get("hasDocument")) and
                     str(doc.get("name","")).startswith(TARGET.stem) and
                     int(doc.get("width",0))==880 and int(doc.get("height",0))==640)
            partial=(matches and existing=={STEPS[0][0]} and active.get("name")==STEPS[0][0]
                     and doc.get("hasSelection") is True)
            if partial:
                print("PS_PREVIOUS_IN_MEMORY_FIRST_SELECTION=VERIFIED",flush=True)
            else:
                # Inspect persistent checkpoint first: it predates the first fill.
                # Open an exact saved test PSD; no unsaved foreign document is
                # closed or overwritten. Existing partial edits remain isolated.
                opened=await call(c,"creative_write","creative.document.open",{"path":str(TARGET)})
                read=doc_state(await state(c))
                check_dimensions(read.get("document"))
                existing=await layers(c)
                if existing:
                    raise RuntimeError("PS_PERSISTENT_CHECKPOINT_NOT_BLANK_NO_REPLAY")
                partial=False
                print("PS_RESUME_FROM_PERSISTED_STROKE_ZERO=PASS",flush=True)
        else:
            if original.get("hasDocument") and existing:
                raise RuntimeError("PS_FOREIGN_PANDA_DOCUMENT_ACTIVE_NO_WRITE")
            await call(c,"creative_write","creative.document.create",
                       {"width":880,"height":640,"resolution":72,"colorMode":"RGB"})
            created=doc_state(await state(c))
            check_dimensions(created.get("document"))
            existing=await layers(c)
            if existing:raise RuntimeError("PS_NEW_DOCUMENT_CONTAINS_PANDA_PARTS")
            await save(c,0)
            partial=False

        for i,(name,shape,x,y,w,h,color) in enumerate(STEPS,1):
            print("PS_MODE1_STROKE_START="+json.dumps({"ordinal":i,"name":name,
                "shape":shape,"resume_partial_selection":partial and i==1}),flush=True)
            if i==1 and partial:
                # Directly resume at the rejected fill, do not repeat creation
                # or selection whose success was already proved by real logs.
                current=doc_state(await state(c))
                if current.get("activeLayer",{}).get("name")!=name or current.get("document",{}).get("hasSelection") is not True:
                    raise RuntimeError("PS_PREVIOUS_SELECTION_NO_LONGER_VERIFIED")
            else:
                if name in existing:raise RuntimeError("PS_DUPLICATE_LAYER_GUARD "+name)
                await call(c,"creative_write","creative.layer.create",{"name":name})
                selected=doc_state(await state(c))
                if selected.get("activeLayer",{}).get("name")!=name:
                    raise RuntimeError("PS_NEW_LAYER_NOT_ACTIVE")
                await call(c,"creative_write","creative.selection."+shape,
                           {"left":x,"top":y,"right":x+w,"bottom":y+h})
                selection_state=doc_state(await state(c))
                if selection_state.get("document",{}).get("hasSelection") is not True:
                    raise RuntimeError("PS_SELECTION_NOT_REAL_NO_FILL")
            # Fill is destructive in gateway policy, but only affects the
            # freshly named test layer's live pixel selection. No native script.
            await call(c,"creative_authorized_write","creative.style.fill",
                       {"red":color[0],"green":color[1],"blue":color[2]})
            painted=await state(c)
            verify_painted_layer(painted,name,x,y,w,h)
            await call(c,"creative_write","creative.selection.clear")
            got=await layers(c)
            if name not in got or len(got)!=i:
                raise RuntimeError("PS_STROKE_NOT_CONFIRMED_NO_REPLAY "+name)
            print("PS_MODE1_STROKE_READBACK="+json.dumps({"ordinal":i,"name":name,
                "count":len(got),"nameFound":name in got}),flush=True)
            await save(c,i)
            existing=got
            await asyncio.sleep(0.4)
        await call(c,"creative_write","creative.document.export",
                   {"path":str(PNG),"format":"PNG"})
        if not PNG.is_file() or PNG.stat().st_size<1000:
            raise RuntimeError("PS_PNG_EXPORT_UNVERIFIED")
        print("PS_MODE1_E2E=PASS "+json.dumps({"shapes":len(STEPS),
             "psd":str(TARGET),"png":str(PNG),"pngBytes":PNG.stat().st_size}),flush=True)
asyncio.run(main())
