"""Execute bounded Photoshop one-call fast shape commands against a DOM fixture."""
import json
import shutil
import subprocess
import unittest

from scripts.panda_red_poster_blueprint import STEPS
from scripts.panda_red_photoshop_fast_native import compile_native_shape

DOCUMENT="MCP_KFP4_Red_PS_123456789012_41shapes.psd"
HARNESS=r"""
const fs=require('node:fs'),data=JSON.parse(fs.readFileSync(0,'utf8'));
let effects=0, selected=false, box=null;
let names=Array.from({length:data.ordinal},(_,i)=>({name:i===0?'Background':'Existing '+i}));
if(data.duplicate)names[0].name=data.newName;
let doc={
 name:data.docName,
 width:{as:()=>880},height:{as:()=>1265},
 layers:names,
 activeLayer:{name:'Existing 1'},
 artLayers:{add(){
  effects++;const node={name:'New Layer'};doc.layers.unshift(node);doc.activeLayer=node;return node;
 }},
 selection:{
  select(pts){effects++; selected=true;const xx=pts.map(q=>q[0]),yy=pts.map(q=>q[1]);box=[Math.min(...xx),Math.min(...yy),Math.max(...xx),Math.max(...yy)];},
  fill(){if(!selected)throw Error('no selection');effects++;},
  deselect(){effects++;selected=false}
 }
};
function ActionDescriptor(){this.values={};this.object=null;this.putUnitDouble=(key,u,val)=>this.values[key]=val;this.putObject=(key,type,obj)=>this.object=obj;this.putBoolean=()=>{};this.putReference=()=>{};}
function ActionReference(){this.putProperty=()=>{}}
function charIDToTypeID(v){return v;}
function executeAction(op,desc){effects++;const vals=desc.object.values;box=[vals['Left'],vals['Top '],vals['Rght'],vals['Btom']];selected=true;}
function SolidColor(){this.rgb={}}
let result;
try{result=Function('app','SolidColor','SelectionType','ColorBlendMode','ActionDescriptor','ActionReference','charIDToTypeID','executeAction','DialogModes',data.source)(
 {activeDocument:doc},SolidColor,{REPLACE:1},{NORMAL:1},ActionDescriptor,ActionReference,charIDToTypeID,executeAction,{NO:0});}
catch(e){result={error:e.message};}
process.stdout.write(JSON.stringify({result,effects,bounds:box,selected,layerNames:doc.layers.map(x=>x.name)}));
"""

def run_script(code,part,ordinal,*,doc_name=DOCUMENT,duplicate=False):
    if not shutil.which("node"):
        raise RuntimeError("node required for JSX regression")
    payload=json.dumps({"source":code,"ordinal":ordinal,"docName":doc_name,"duplicate":duplicate,"newName":part["name"]})
    p=subprocess.run(["node","-e",HARNESS],input=payload,text=True,capture_output=True,check=True,timeout=8)
    return json.loads(p.stdout)

@unittest.skipUnless(shutil.which("node"),"Node is required")
class NativeFastShapeTests(unittest.TestCase):
    def test_path_creates_exact_one_layer_and_one_fill(self):
        component=STEPS[40]
        source,bounds=compile_native_shape(component,document=DOCUMENT,ordinal=41)
        out=run_script(source,component,41)
        self.assertEqual(out["result"]["layer"],component["name"])
        self.assertEqual(out["result"]["afterCount"],42)
        self.assertEqual(out["effects"],4)
        self.assertFalse(out["selected"])
        self.assertEqual(out["layerNames"][0],component["name"])
        for k,v in zip(("left","top","right","bottom"),out["bounds"]):
            self.assertAlmostEqual(v,bounds[k],places=2)

    def test_true_ellipse_marquee_uses_action_manager(self):
        comp=STEPS[41]
        source,bounds=compile_native_shape(comp,document=DOCUMENT,ordinal=42)
        self.assertIn("putObject(charIDToTypeID('T   ')",source)
        out=run_script(source,comp,42)
        self.assertEqual(out["effects"],4)
        self.assertEqual(out["bounds"],[bounds[k] for k in ("left","top","right","bottom")])

    def test_wrong_document_and_duplicate_refuse_any_creation(self):
        comp=STEPS[40]
        code,_=compile_native_shape(comp,document=DOCUMENT,ordinal=41)
        foreign=run_script(code,comp,41,doc_name="Foreign.psd")
        self.assertIn("WRONG_ACTIVE_DOC",foreign["result"]["error"])
        self.assertEqual(foreign["effects"],0)
        duplicate=run_script(code,comp,41,duplicate=True)
        self.assertIn("DUPLICATE_LAYER",duplicate["result"]["error"])
        self.assertEqual(duplicate["effects"],0)

    def test_numeric_limits_and_identity_checks(self):
        comp=STEPS[40]
        for bad_ordinal in (0,61):
            with self.assertRaises(ValueError):
                compile_native_shape(comp,document=DOCUMENT,ordinal=bad_ordinal)
        with self.assertRaises(ValueError):
            compile_native_shape(comp,document="Unrelated.psd",ordinal=41)
        bad=dict(comp,pathData="<script>")
        with self.assertRaises(ValueError):
            compile_native_shape(bad,document=DOCUMENT,ordinal=41)

if __name__=="__main__":
    unittest.main()
