"""Pixel-content acceptance for a PNG exported by the running Adobe XD host.

A successful MCP receipt without visible panda features MUST fail this gate.
This never draws, modifies or imports an image.
"""
import argparse,json
from pathlib import Path
from PIL import Image

# Each zone deliberately samples a distinctive object in the required scene.
# Thresholds are conservative, not a visual similarity score.
REGIONS={
  "dark_panda_body": ((260,185,620,575),lambda r,g,b:r<70 and g<75 and b<80,9000),
  "cream_face_belly": ((320,205,575,560),lambda r,g,b:abs(r-247)<10 and abs(g-246)<10 and abs(b-235)<10,6000),
  "bamboo_leaf": ((540,350,582,382),lambda r,g,b:g>120 and r<125 and b<115,150),
  "nonla_tan_cone": ((315,65,565,190),lambda r,g,b:r>170 and 115<g<215 and 65<b<170,2500),
}
def audit(path:Path):
    with Image.open(path) as source:
        source.load()
        if source.format!="PNG" or source.size!=(1920,1080):
            raise RuntimeError("XD_PANDA_VISUAL_WRONG_REAL_EXPORT_FORMAT_OR_SIZE")
        img=source.convert("RGB")
    outcomes={}
    for name,(bounds,predicate,minimum) in REGIONS.items():
        count=sum(1 for rgb in img.crop(bounds).getdata() if predicate(*rgb))
        outcomes[name]={"actual_pixels":count,"minimum":minimum,"passed":count>=minimum}
    print("XD_PANDA_VISUAL_PIXEL_AUDIT="+json.dumps(outcomes),flush=True)
    bad=[name for name,v in outcomes.items() if not v["passed"]]
    if bad:raise RuntimeError("XD_PANDA_VISUAL_CONTENT_FAIL "+",".join(bad))
    print("XD_PANDA_VISUAL_CONTENT=PASS",flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--png",type=Path,required=True)
    audit(p.parse_args().png)
