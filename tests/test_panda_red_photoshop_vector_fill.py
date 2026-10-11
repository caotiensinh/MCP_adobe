"""Contract executes generated actual JSX body on Node mocked Photoshop DOM."""
import json
import shutil
import subprocess
import unittest

from scripts.panda_red_poster_blueprint import STEPS
from scripts.panda_red_photoshop_vector_fill import compile_path_fill

NATIVE="MCP_KFP4_Red_PS_38147544140_5shapes.psd"

def execute_mock(code, *,doc_name=NATIVE, layer=None):
    layer=layer or STEPS[3]["name"]
    harness=r"""
const fs=require('node:fs');
const data=JSON.parse(fs.readFileSync(0,'utf8'));
let sideEffects=0, selected=false, bound=null;
let document={
 name:data.docName,activeLayer:{name:data.layerName},
 width:{as(){return 880;}}, height:{as(){return 1265;}},
 selection:{
  select(pts,type){selected=true;sideEffects++;const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);bound={left:Math.min(...xs),top:Math.min(...ys),right:Math.max(...xs),bottom:Math.max(...ys)};},
  fill(c,blend){if(!selected)throw Error('must select before filling');sideEffects++;},
  deselect(){selected=false;sideEffects++;}
 }};
function SolidColor(){this.rgb={};}
let result;
try{result=Function('app','SolidColor','SelectionType','ColorBlendMode',data.code)(
  {activeDocument:document},SolidColor,{REPLACE:1},{NORMAL:2});}
catch(e){result={error:e.message};}
process.stdout.write(JSON.stringify({result,sideEffects,selected,bounds:bound}));
"""
    process=subprocess.run(["node","-e",harness],input=json.dumps({"code":code,"docName":doc_name,"layerName":layer}),text=True,capture_output=True,check=True,timeout=5)
    return json.loads(process.stdout)

@unittest.skipUnless(shutil.which("node"),"Node available on CI")
class PhotoshopRedVectorTests(unittest.TestCase):
    def test_real_generated_jsx_selects_fills_deselects_once(self):
        s,b=compile_path_fill(STEPS[3],expected_doc=NATIVE)
        actual=execute_mock(s)
        self.assertEqual(actual["result"]["shape"],STEPS[3]["name"])
        self.assertGreater(actual["result"]["vertices"],30)
        self.assertEqual(actual["sideEffects"],3)
        self.assertFalse(actual["selected"])
        for key,value in b.items():
            self.assertAlmostEqual(actual["bounds"][key],value,places=2)

    def test_wrong_document_never_mutates(self):
        source,_=compile_path_fill(STEPS[3],expected_doc=NATIVE)
        actual=execute_mock(source,doc_name="Foreign Document.psd")
        self.assertIn("WRONG_DOCUMENT",actual["result"]["error"])
        self.assertEqual(actual["sideEffects"],0)

    def test_wrong_active_layer_never_mutates(self):
        source,_=compile_path_fill(STEPS[3],expected_doc=NATIVE)
        actual=execute_mock(source,layer="Unrelated Design")
        self.assertIn("WRONG_ACTIVE_LAYER",actual["result"]["error"])
        self.assertEqual(actual["sideEffects"],0)

    def test_reject_imports_and_malformed_or_out_of_bounds_paths(self):
        original=dict(STEPS[3])
        for path in ('<svg onload=alert(1)>','M0 0 L10 0 Z','M0 0 L50000 0 L50000 100 Z'):
            bad=dict(original,pathData=path)
            with self.assertRaises(ValueError):
                compile_path_fill(bad,expected_doc=NATIVE)
        with self.assertRaises(ValueError):
            compile_path_fill(original,expected_doc="Foreign.psd")

if __name__=="__main__":
    unittest.main()
