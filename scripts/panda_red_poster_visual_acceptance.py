"""Conservative pixel-content checks for *native Adobe-exported* red Panda posters.

Not a similarity score and not a substitute for human visual comparison.
Caller must establish the PNG provenance from the Adobe host separately.
A blank red image or the old green garden must never be accepted.
"""
import argparse
import json
from pathlib import Path
from PIL import Image

RATIO=297/427
GATES={
  "red_poster_field":((0.0,0.0,0.10,1.0),lambda r,g,b:r>125 and r>g*1.75 and r>b*1.7,.70),
  "panda_dark_body":((.25,.05,.80,.57),lambda r,g,b:max(r,g,b)<92,.065),
  "panda_bright_face_belly":((.33,.02,.78,.55),
       lambda r,g,b:min(r,g,b)>170 and max(r,g,b)-min(r,g,b)<55,.065),
  "diagonal_bamboo":((.0,.0,.51,.28),
       lambda r,g,b:r>85 and 42<g<200 and b<g and r>g*1.10,.006),
  "lower_white_logo":((.10,.60,.94,.99),
       lambda r,g,b:min(r,g,b)>198,.065),
  "white_4":((.34,.79,.67,.99),
       lambda r,g,b:min(r,g,b)>198,.075),
  "dark_kungfu_legs":((.20,.35,.98,.57),
       lambda r,g,b:max(r,g,b)<90,.019),
}
def audit(path:Path):
    with Image.open(path) as source:
        source.load()
        if source.format!="PNG" or source.width<290 or source.height<420 or
           abs(source.width/source.height-RATIO)>.025:
            raise RuntimeError("PANDA_RED_WRONG_SIZE_OR_FORMAT")
        rgb=source.convert("RGB")
    w,h=rgb.size
    outcomes={}
    for name,(zone,predicate,min_ratio) in GATES.items():
        left,top,right,bottom=zone
        roi=rgb.crop((round(left*w),round(top*h),round(right*w),round(bottom*h)))
        samples=list(roi.getdata())
        passed_count=sum(1 for color in samples if predicate(*color))
        ratio=passed_count/len(samples) if samples else 0
        outcomes[name]={"pixels":passed_count,"sample_count":len(samples),
            "coverage":round(ratio,5),"minimum_coverage":min_ratio,"passed":ratio>=min_ratio}
    print("PANDA_RED_POSTER_VISUAL_AUDIT="+json.dumps(
       {"image_size":[w,h],"checks":outcomes},ensure_ascii=False),flush=True)
    failed=[k for k,v in outcomes.items() if not v["passed"]]
    if failed:raise RuntimeError("PANDA_RED_POSTER_VISUAL_FAIL "+",".join(failed))
    print("PANDA_RED_POSTER_VISUAL_PIXEL_GATES=PASS manual-composition-review-still-required",flush=True)
    return outcomes
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--png",required=True,type=Path)
    audit(p.parse_args().png)
