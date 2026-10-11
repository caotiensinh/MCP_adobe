"""Adobe XD panda Mode 1: one queued write, one Apply UI command, one receipt + scenegraph readback per shape."""
import asyncio, hashlib, json, os, subprocess, time
from collections.abc import Mapping
from pathlib import Path
from mcp import Client

ROOT=Path(os.environ["USERPROFILE"])/"Documents"/"MCPAdobe"
RUN=os.environ.get("GITHUB_RUN_ID","local")
CHECKPOINT=ROOT/f"MCP_Mode1_Panda_XD_{RUN}.json"
URL="http://127.0.0.1:8787/mcp"
def rgb(c):return "#%02X%02X%02X"%c
def rect(n,x,y,w,h,c):return (n,"creative.shape.rectangle",{"name":n,"x":x,"y":y,"width":w,"height":h,"fill":rgb(c)})
def oval(n,x,y,w,h,c):return (n,"creative.shape.ellipse",{"name":n,"x":x,"y":y,"width":w,"height":h,"fill":rgb(c)})
S=(242,249,248);G=(164,205,147);K=(39,45,49);W=(247,246,235);B=(74,153,65);H=(220,173,108)
STEPS=[
    rect("01 XD Panda Garden",0,0,880,640,S),
    rect("02 XD Bamboo Meadow",0,568,880,72,G),
    rect("03 XD Bamboo Stalk",590,242,18,302,B),
    rect("04 XD Bamboo Joint 1",584,302,31,8,(51,113,54)),
    rect("05 XD Bamboo Joint 2",584,390,31,8,(51,113,54)),
    oval("06 XD Bamboo Upper Leaf",606,265,61,28,B),
    oval("07 XD Bamboo Middle Leaf",540,350,61,28,B),
    oval("08 XD Panda Left Foot",285,500,120,71,K),
    oval("09 XD Panda Right Foot",480,500,120,71,K),
    oval("10 XD Panda Left Ear",297,166,100,114,K),
    oval("11 XD Panda Right Ear",484,166,100,114,K),
    oval("12 XD Panda Black Body",303,331,275,233,K),
    oval("13 XD Panda White Belly",353,359,185,187,W),
    oval("14 XD Panda Left Arm",258,349,95,154,K),
    oval("15 XD Panda Right Arm",538,341,97,152,K),
    oval("16 XD Panda White Head",320,189,240,218,W),
    oval("17 XD Panda Left Eye Patch",353,250,77,95,K),
    oval("18 XD Panda Right Eye Patch",453,250,77,95,K),
    oval("19 XD Panda Left Eye",389,280,22,27,W),
    oval("20 XD Panda Right Eye",480,280,22,27,W),
    oval("21 XD Panda Nose",423,337,35,24,K),
    oval("22 XD Panda Smile",417,368,46,9,(118,91,89)),
    oval("23 XD Paw Holding Bamboo",563,408,67,66,K),
    oval("24 XD Non La Wide Brim",293,182,297,34,(175,120,69)),
    rect("25 XD Non La Cone Lower",330,159,224,23,H),
    rect("26 XD Non La Cone Middle",361,134,165,25,H),
    rect("27 XD Non La Cone Upper",393,108,99,26,H),
    rect("28 XD Non La Tip",430,77,25,31,H),
    rect("29 XD Non La Highlight",441,105,10,75,(243,205,150)),
    rect("30 XD Non La Chin Strap",372,196,7,153,(157,96,51)),
    oval("31 XD Pink Flower",214,590,20,20,(241,150,174)),
    oval("32 XD Yellow Flower",689,585,20,20,(248,208,92)),
]
def walk(x):
    yield x
    if isinstance(x,Mapping):
        for a in x.values():yield from walk(a)
    elif isinstance(x,(list,tuple)):
        for a in x:yield from walk(a)
def find(x,key):
    for a in walk(x):
        if isinstance(a,Mapping) and key in a:return a[key]
    return None
def node_map(x):
    result={}
    for a in walk(x):
        if isinstance(a,Mapping) and a.get("name") in {t[0] for t in STEPS}:
            guid=a.get("id") or a.get("guid")
            if guid: result[a["name"]]=str(guid)
    return result
def apply_one():
    # Sends only the official Adobe XD plugin command shortcut; NEVER synthesizes scenegraph state.
    cmd=r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class XdMode1Native {
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
'@
$xd=Get-Process -ErrorAction SilentlyContinue | Where-Object {
 ($_.ProcessName -match '^(XD|AdobeXD)$' -or $_.MainWindowTitle -match 'Adobe XD') -and $_.MainWindowHandle -ne 0 -and $_.SessionId -eq 1
} | Select-Object -First 1
if(-not $xd){throw 'XD_INTERACTIVE_HOST_ABSENT'}
[void][XdMode1Native]::ShowWindow($xd.MainWindowHandle,9)
if(-not [XdMode1Native]::SetForegroundWindow($xd.MainWindowHandle)){throw 'XD_WINDOW_FOREGROUND_FAILED'}
Start-Sleep -Milliseconds 350
[System.Windows.Forms.SendKeys]::SendWait('^%+8')
Write-Output "XD_SINGLE_APPLY_REQUESTED PID=$($xd.Id)"
"""
    p=subprocess.run(["powershell","-NoProfile","-NonInteractive","-Command",cmd],capture_output=True,text=True,timeout=18)
    print("XD_APPLY_UI="+json.dumps({"rc":p.returncode,"stdout":p.stdout[-700:],"stderr":p.stderr[-1000:]}),flush=True)
    if p.returncode:raise RuntimeError("XD_APPLY_COMMAND_FAILED_NO_REPLAY")
async def call(c,tool,cap,args=None):
    r=await c.call_tool(tool,{"application":"xd","capability":cap,"arguments":args or {}})
    p=r.structured_content
    print("XD_MCP_RESULT="+json.dumps({"cap":cap,"error":r.is_error,"result":str(p)[:1000]},default=str),flush=True)
    if r.is_error or not isinstance(p,dict) or p.get("ok") is not True:
        raise RuntimeError("XD_MCP_OPERATION_UNKNOWN_NO_REPLAY "+cap)
    return p
async def snapshot(c):
    p=await call(c,"creative_read","creative.scenegraph.list")
    data=p.get("result") or {}
    if data.get("complete") is not True and find(p,"complete") is not True:
        raise RuntimeError("XD_SCENEGRAPH_INCOMPLETE")
    return node_map(data)
async def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    if CHECKPOINT.exists():raise RuntimeError("XD_SAME_RUN_CHECKPOINT_EXISTS_RECONCILE_BEFORE_RETRY")
    async with Client(URL) as c:
        health=await call(c,"creative_read","creative.health")
        if find(health,"bridge")!="connected" or find(health,"pending_count")!=0:
            raise RuntimeError("XD_BRIDGE_NOT_IDLE_NO_WRITE")
        initial=await snapshot(c)
        if initial:raise RuntimeError("XD_PRIOR_PANDA_NODES_PRESENT_REFUSE_DUPLICATE")
        proven=[]
        for i,(name,cap,args) in enumerate(STEPS,1):
            before=await snapshot(c)
            if len(before)!=i-1:raise RuntimeError("XD_PRE_STROKE_COUNT_MISMATCH")
            print("XD_MODE1_STROKE_START="+json.dumps({"ordinal":i,"name":name,"cap":cap}),flush=True)
            p=await call(c,"creative_write",cap,args)
            result=p.get("result") or {}
            op=result.get("operation_id")
            if result.get("status")!="queued" or not op or result.get("pending_count")!=1:
                raise RuntimeError("XD_NOT_QUEUED_AS_EXACTLY_ONE_OP_NO_REPLAY")
            apply_one()
            receipt=None
            for attempt in range(16):
                receipt=await call(c,"creative_read","xd.queue.status",{"operation_id":op})
                state=find(receipt,"status")
                if state in ("applied","failed","rejected"):break
                await asyncio.sleep(0.35)
            if state!="applied":raise RuntimeError("XD_QUEUE_NOT_APPLIED_NO_REPLAY "+str(state))
            after=await snapshot(c)
            health=await call(c,"creative_read","creative.health")
            if name not in after or len(after)!=i or find(health,"pending_count")!=0:
                raise RuntimeError("XD_SCENEGRAPH_POST_WRITE_NOT_PROVEN_NO_REPLAY")
            rec={"ordinal":i,"name":name,"guid":after[name],"operation_id":op,"status":"applied"}
            proven.append(rec)
            CHECKPOINT.write_text(json.dumps({"status":"XD_SCENEGRAPH_CHECKPOINT_NOT_NATIVE_XD_FILE","run":RUN,
              "proven":proven},indent=2),encoding="utf-8")
            digest=hashlib.sha256(CHECKPOINT.read_bytes()).hexdigest()
            print("XD_MODE1_STROKE_READBACK="+json.dumps({"ordinal":i,"nodeCount":len(after),"nameFound":True,
                "guid":after[name],"receipt":"applied","checkpointSHA256":digest}),flush=True)
        print("XD_MODE1_SCENEGRAPH_32_STROKES=PASS",flush=True)
        print("XD_NATIVE_SAVE_AND_PNG_EXPORT=NOT_IMPLEMENTED_BLOCKED_CAPABILITY",flush=True)
asyncio.run(main())
