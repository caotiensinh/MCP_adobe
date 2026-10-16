"""Editable *individual* design steps for the Kung Fu Panda 4 red reference.

The reference (297x427) is used for layout only; NO poster import or SVG bundle.
Each entry is one future Adobe host MCP write+Apply+receipt+readback+checkpoint.
This is a stylized vector composition, not a claim of photorealistic similarity.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

WIDTH = 880
HEIGHT = 1265
ASPECT = WIDTH / HEIGHT
EXPECTED = 297 / 427

RED="#D60905"
DARK_RED="#BC0000"
ORANGE="#F42D08"
SHADOW="#180E13"
BLACK="#19181A"
EDGE="#343032"
WHITE="#F6F3E7"
LIT="#FFFFFF"
MID="#D7D0BD"
TAN="#C18B45"
TAN_DARK="#865526"
BAMBOO="#D5A15F"
BAMBOO_DARK="#75451F"
SKIN="#E7E0CD"
EYE="#261F1D"
PURPLE="#615253"

def shape(kind: str, name: str, x: float, y: float, **props):
    return {"kind":kind,"name":name,"x":x,"y":y,**props}

def rect(name,x,y,w,h,fill):
    return shape("rectangle",name,x,y,width=w,height=h,fill=fill)
def oval(name,x,y,w,h,fill):
    return shape("ellipse",name,x,y,width=w,height=h,fill=fill)
def vector(name,x,y,data,fill):
    return shape("path",name,x,y,pathData=data,fill=fill)
def title(name,text,x,y,size,fill=LIT):
    return shape("text",name,x,y,text=text,fontSize=size,fill=fill)

# Back to front compositing, ordered as a reproducible MCP task list.
STEPS=(
    rect("001 Deep red poster background",0,0,WIDTH,HEIGHT,DARK_RED),
    rect("002 Orange-red upper field",0,0,WIDTH,700,ORANGE),
    rect("003 Rich red lower gradient band",0,650,WIDTH,615,RED),
    vector("004 Stage light left",0,0,"M0 0 L370 0 C280 190 195 400 0 600 Z","#FF320B"),
    vector("005 Stage shadow right",640,0,"M130 0 L240 0 L240 700 L0 600 Z","#D11508"),
    oval("006 Kung fu ground shadow",195,582,640,90,"#870600"),
    # Rear legs in a low, wide fighting stance.
    vector("007 Back right trousers",500,455,"M0 0 C95 -25 165 -10 206 45 L292 165 C291 210 254 216 219 206 L87 135 L5 135 Z",TAN),
    vector("008 Right trousers fold shadow",578,532,"M0 0 L110 29 L190 117 L92 95 Z",TAN_DARK),
    oval("009 Back right foot black sole",722,593,127,77,BLACK),
    oval("010 Right toe cream highlight",790,620,48,25,WHITE),
    vector("011 Front left black leg",243,480,"M0 0 C-18 40 -12 135 12 185 L122 184 L120 90 L92 14 Z",BLACK),
    oval("012 Left shoe outer silhouette",235,592,168,75,BLACK),
    oval("013 Left shoe white toe",238,633,58,19,WHITE),
    vector("014 Left trouser sash",278,549,"M0 0 L133 10 L138 85 L0 83 Z",TAN),
    vector("015 Left trouser dark fold",278,598,"M0 0 L130 10 L130 24 L0 22 Z",TAN_DARK),
    # Bamboo staff extends diagonally from left edge, behind the raised hand.
    vector("016 Bamboo staff full shaft",14,16,"M0 228 L423 0 L432 10 L10 241 Z",BAMBOO),
    vector("017 Bamboo lower edge shade",20,26,"M0 225 L416 0 L420 4 L0 230 Z",BAMBOO_DARK),
    vector("018 Bamboo joint 1",152,147,"M0 0 L10 -5 L17 7 L7 13 Z",BAMBOO_DARK),
    vector("019 Bamboo joint 2",291,72,"M0 0 L10 -5 L17 7 L7 13 Z",BAMBOO_DARK),
    # Raised black arm gripping staff: an action silhouette, not a standing mascot.
    vector("020 Back raised sleeve",264,0,
           "M50 12 C120 -18 175 13 185 71 C184 131 153 191 123 278 L48 261 C54 191 38 138 3 100 C-17 73 -2 35 50 12 Z",BLACK),
    vector("021 Raised sleeve rim highlight",302,39,
           "M0 0 C40 -20 80 -8 98 23 L80 29 C61 2 42 0 0 18 Z",EDGE),
    oval("022 Upper fist black silhouette",340,4,128,88,BLACK),
    oval("023 Upper fist reflected knuckle",365,18,63,18,EDGE),
    # Main body and chest.
    vector("024 Rear torso martial pose",273,222,
           "M78 4 C168 -33 312 29 347 132 C372 212 323 325 245 350 C160 384 31 317 7 223 C-22 132 8 50 78 4 Z",BLACK),
    oval("025 Belly white focal volume",320,376,267,219,MID),
    oval("026 Belly bright center",335,369,235,190,WHITE),
    vector("027 Belly soft dark right contour",521,415,
           "M0 0 C49 23 60 96 12 159 L-2 170 C26 112 23 51 0 0 Z",SKIN),
    vector("028 Body left rim backlight",280,307,
           "M20 0 C-16 84 8 203 59 243 L43 247 C-10 186 -28 68 20 0 Z",EDGE),
    # Foreground sweeping arm across chest, with an open guard paw.
    vector("029 Foreground sweeping forearm",235,285,
           "M10 155 C65 56 171 44 258 94 C299 118 306 158 259 190 C193 231 72 232 0 194 Z",BLACK),
    vector("030 Forearm specular contour",275,384,
           "M0 51 C61 7 123 -5 174 8 L175 23 C118 4 48 39 0 65 Z",EDGE),
    oval("031 Guard paw black outer",230,340,104,130,BLACK),
    oval("032 Guard paw palm highlight",251,365,52,74,PURPLE),
    oval("033 Guard paw first finger",232,338,28,51,EDGE),
    oval("034 Guard paw second finger",257,337,27,54,EDGE),
    # Head, ears, distinctive angry brow and muzzle.
    oval("035 Left black panda ear",331,104,94,103,BLACK),
    oval("036 Right black panda ear",510,98,94,108,BLACK),
    oval("037 Head rear grey shadow",345,131,241,233,MID),
    oval("038 Head broad white face",353,125,222,227,WHITE),
    oval("039 Face bright upper forehead",382,130,150,91,LIT),
    vector("040 Left panda eye mask",378,208,
           "M9 17 C24 -17 72 -18 88 21 C78 68 36 82 4 55 C-6 41 -3 26 9 17 Z",BLACK),
    vector("041 Right panda eye mask",489,198,
           "M9 15 C33 -18 75 -13 83 23 C79 61 44 78 5 60 C-7 50 -7 31 9 15 Z",BLACK),
    oval("042 Left eye sclera",421,241,32,26,LIT),
    oval("043 Right eye sclera",510,232,35,29,LIT),
    oval("044 Left pupil dark",434,243,18,23,EYE),
    oval("045 Right pupil dark",510,234,18,23,EYE),
    oval("046 Left eye sparkle",442,244,7,7,LIT),
    oval("047 Right eye sparkle",514,235,7,7,LIT),
    vector("048 Left angry raised brow",391,198,"M0 8 C25 -8 56 -11 82 3 L82 15 C56 7 26 9 0 22 Z",EDGE),
    vector("049 Right angry angled brow",488,192,"M0 7 C28 -11 61 -10 85 1 L85 17 C58 10 26 12 0 22 Z",EDGE),
    oval("050 White protruding muzzle",427,279,112,70,WHITE),
    oval("051 Dark triangular nose",465,295,48,31,EYE),
    vector("052 Confident slight smile",453,325,"M0 0 C23 19 47 19 70 -2 L65 10 C41 29 21 26 0 12 Z",EDGE),
    vector("053 Chin shadow",420,346,"M0 0 C43 25 90 21 130 -7 L119 10 C81 37 38 33 0 15 Z",MID),
    oval("054 Small forehead glint",435,145,41,15,LIT),
    # Broad orange-brown sash across waist for contrasting silhouette.
    vector("055 Waist sash tan overlay",352,534,"M0 0 C88 39 169 37 240 -8 L252 30 C169 89 69 82 0 43 Z",TAN),
    vector("056 Waist sash dark edge",363,573,"M0 0 C77 33 151 20 221 -10 L221 8 C148 47 74 48 0 19 Z",TAN_DARK),
    # Sharp white layered title, poster typography remains a separate editable object.
    title("057 KUNG FU word layer","KUNG FU",156,743,115),
    title("058 PANDA word layer","PANDA",113,856,161),
    title("059 Film number 4","4",360,1030,248),
    vector("060 Number 4 ground baseline",360,1182,"M0 0 L164 0 L164 15 L0 15 Z",LIT),
)

def validate() -> None:
    if abs(ASPECT-EXPECTED) > .003:
        raise ValueError("red poster artboard must preserve supplied portrait aspect ratio")
    if len({s["name"] for s in STEPS}) != len(STEPS):
        raise ValueError("duplicate Adobe object names; readback would be ambiguous")
    for number,part in enumerate(STEPS,1):
        if not part["name"].startswith(f"{number:03d} "):
            raise ValueError("non-deterministic layer ordering")
        if part["kind"] not in {"rectangle","ellipse","path","text"}:
            raise ValueError("unsupported individual Adobe primitive")
        if not (isinstance(part["x"],(float,int)) and isinstance(part["y"],(float,int))):
            raise ValueError("invalid global position")
        if part["kind"] in {"rectangle","ellipse"}:
            if part.get("width",0) <= 0 or part.get("height",0) <= 0:
                raise ValueError("zero-size primitive")
        elif part["kind"] == "path":
            data=part.get("pathData","")
            if not 6 <= len(data) <= 8192 or not re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9.,+\-\sEe]+",data):
                raise ValueError("invalid individual path data")
        elif part["kind"] == "text":
            if not part.get("text") or part.get("fontSize",0) <= 0:
                raise ValueError("empty/invalid text layer")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}",part.get("fill","")):
            raise ValueError("invalid design fill")
    if not (STEPS[0]["kind"] == "rectangle" and STEPS[0]["width"] == WIDTH and STEPS[0]["height"] == HEIGHT):
        raise ValueError("red poster background is not full frame")
    if "Bamboo staff" not in STEPS[15]["name"]:
        raise ValueError("bamboo staff ordering regression")
    if not (STEPS[-2]["kind"] == "text" and STEPS[-2]["text"] == "4"):
        raise ValueError("missing independently editable film number")

if __name__ == "__main__":
    validate()
    print(f"PANDA_RED_SCENE_BLUEPRINT=PASS parts={len(STEPS)} size={WIDTH}x{HEIGHT}")
