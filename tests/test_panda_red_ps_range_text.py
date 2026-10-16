"""Validate Photoshop native Type layer flow and fail-closed readback."""
import asyncio
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0,str(SCRIPTS))
os.environ.setdefault("USERPROFILE",str(Path.home()))
os.environ.setdefault("GITHUB_RUN_ID","123456789012")
os.environ.setdefault("RED_PS_SOURCE_NAME","MCP_KFP4_Red_PS_123456789012_40shapes.psd")
os.environ.setdefault("RED_PS_SOURCE_SHA","0"*64)
os.environ.setdefault("RED_PS_START","41")
os.environ.setdefault("RED_PS_END","60")

import panda_red_photoshop_resume_range as pipeline
from panda_red_poster_blueprint import STEPS


class PhotoshopTextLayerContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.target=Path(self.tmp.name)/"new.psd"
        self.target.write_bytes(b"original-native-source")
        self.part=STEPS[56]
        self.ordinal=57
        self.names=["Background"]+[p["name"] for p in STEPS[:self.ordinal]]
        self.layer_name=self.part["text"]
        self.layer_kind="LayerKind.TEXT"
        self.bounds={"left":160,"top":735,"right":580,"bottom":852}
        self.calls=[]

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def fake_call(self,client,tool,cap,args=None,authorized=False):
        self.calls.append((tool,cap,args or {}))
        if cap=="creative.layer.rename":
            self.layer_name=(args or {}).get("name")
        if cap=="creative.document.save":
            self.target.write_bytes(b"native-source-with-new-type-layer")
        return {}

    async def fake_state(self,client):
        return {"activeLayer":{"name":self.layer_name,
                "kind":self.layer_kind,"bounds":self.bounds},
                "document":{"hasSelection":False}}

    async def fake_names(self,client):
        return self.names

    def fake_sha(self,path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    async def invoke(self):
        with patch.object(pipeline,"TARGET",self.target), \
             patch.object(pipeline,"call",self.fake_call), \
             patch.object(pipeline,"state",self.fake_state), \
             patch.object(pipeline,"layer_names",self.fake_names), \
             patch.object(pipeline,"sha",self.fake_sha):
            await pipeline.paint_text(None,self.part,self.ordinal)

    async def test_type_layer_is_created_renamed_and_saved_with_readback(self):
        await self.invoke()
        capabilities=[c[1] for c in self.calls]
        self.assertEqual(capabilities,["creative.text.create","creative.layer.rename","creative.document.save"])
        self.assertEqual(self.calls[0][2]["text"],"KUNG FU")
        self.assertEqual(self.calls[0][2]["red"],255)
        self.assertEqual(self.layer_name,self.part["name"])
        self.assertGreater(self.target.stat().st_size,len(b"original-native-source"))

    async def test_raster_layer_instead_of_type_layer_rejects_save(self):
        self.layer_kind="LayerKind.NORMAL"
        with self.assertRaisesRegex(RuntimeError,"TEXT_LAYER_KIND_UNVERIFIED"):
            await self.invoke()
        self.assertEqual([x[1] for x in self.calls],["creative.text.create"])

    async def test_zero_size_glyph_fails_before_any_file_write(self):
        self.bounds={"left":150,"right":150,"top":700,"bottom":702}
        with self.assertRaisesRegex(RuntimeError,"GLYPH_BOUNDS_DEGENERATE"):
            await self.invoke()
        self.assertEqual([x[1] for x in self.calls],["creative.text.create","creative.layer.rename"])


if __name__=="__main__":
    unittest.main()
