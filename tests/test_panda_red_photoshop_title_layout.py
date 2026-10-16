"""Bounded native editable Type-layer polishing with no foreign-layer mutation."""
import asyncio, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0,str(ROOT))
os.environ.setdefault("USERPROFILE",str(Path.home()))
os.environ.setdefault("GITHUB_RUN_ID","123456789012")
import panda_red_photoshop_title_layout as layout

class TitleLayoutTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.psd=Path(self.tmp.name)/"copy.psd"
        self.psd.write_bytes(b"base-psd")
        self.original={"left":125.0,"top":746.0,"right":590.0,"bottom":857.0}
        self.big={"left":0.0,"top":700.0,"right":767.0,"bottom":883.0}
        self.final={"left":56.0,"top":866.0,"right":823.0,"bottom":1049.0}
        self.calls=[]
        self.index=0
        self.kind="LayerKind.TEXT"
        self.name=layout.STEPS[57]["name"]

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def mock_call(self,c,tool,cap,args=None):
        self.calls.append((cap,args))
        if cap=="creative.document.save":
            self.psd.write_bytes(b"base-psd-and-title-update")
        return {}

    async def mock_state(self,c):
        states=(self.original,self.big,self.final)
        idx=min(self.index,2)
        self.index+=1
        return {"activeLayer":{"name":self.name,"kind":self.kind,"bounds":states[idx]}}

    async def mock_names(self,c):
        return ["Background"]+[p["name"] for p in layout.STEPS]

    async def invoke(self):
        with patch.object(layout,"TARGET",self.psd),              patch.object(layout,"call",self.mock_call),              patch.object(layout,"state",self.mock_state),              patch.object(layout,"layer_names",self.mock_names):
            await layout.move_text(None,58,165,56,866)

    async def test_positive_scales_moves_saves_correct_type_layer(self):
        await self.invoke()
        self.assertEqual([k for k,v in self.calls],[
          "creative.layer.select","creative.object.scale","creative.object.move","creative.document.save"])
        self.assertEqual(self.calls[0][1],{"name":self.name})
        self.assertEqual(self.calls[1][1]["scalePercent"],165)
        self.assertEqual(self.calls[2][1],{"deltaX":56.0,"deltaY":166.0})
        self.assertEqual(self.psd.read_bytes(),b"base-psd-and-title-update")

    async def test_wrong_selected_layer_rejects_transform(self):
        self.name="Unrelated"
        with self.assertRaisesRegex(RuntimeError,"SELECTED_WRONG_LAYER"):
            await self.invoke()
        self.assertEqual(len(self.calls),1)

    async def test_wrong_layer_kind_rejects_scale(self):
        self.kind="LayerKind.NORMAL"
        with self.assertRaisesRegex(RuntimeError,"SELECTED_WRONG_LAYER"):
            await self.invoke()
        self.assertEqual(len(self.calls),1)

    async def test_out_of_bound_translation_rejects_move_and_save(self):
        self.big={"left":-2000,"top":-2000,"right":-1200,"bottom":-1800}
        with self.assertRaisesRegex(RuntimeError,"UNSAFE_TRANSLATION"):
            await self.invoke()
        self.assertEqual([c for c,a in self.calls],["creative.layer.select","creative.object.scale"])

if __name__=="__main__":
    unittest.main()
