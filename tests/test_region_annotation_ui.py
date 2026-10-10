from __future__ import annotations

import unittest
from html.parser import HTMLParser
from pathlib import Path


class View(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.scripts: list[str] = []
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if d.get("id"):
            self.ids.add(d["id"])
        if tag == "script":
            self.in_script = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts.append(data)


class CanvasUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = Path("ui/region_annotation.html").read_text(encoding="utf-8")
        cls.view = View()
        cls.view.feed(cls.html)

    def test_controls_present(self):
        self.assertTrue({"preview-file", "metadata-file", "preview", "canvas", "selection",
                         "meta", "detect", "candidate-list", "request",
                         "build", "payload", "copy", "clear"} <= self.view.ids)

    def test_selection_never_executes_or_fetches_remotely(self):
        js = "".join(self.view.scripts)
        for expression in ("fetch(", "XMLHttpRequest(", "WebSocket(", "eval("):
            self.assertNotIn(expression, js)
        self.assertIn("execute_automatically:false", js)
        self.assertIn("requires_live_document_identity_check:true", js)
        self.assertIn("requires_live_layer_readback:true", js)

    def test_preview_is_local_only(self):
        self.assertIn("URL.createObjectURL(file)", self.html)
        self.assertIn("URL.revokeObjectURL(url)", self.html)

    def test_preview_guard_blocks_unverified_xd_frame(self):
        js = "".join(self.view.scripts)
        self.assertIn("function validatePreviewMetadata(doc)", js)
        self.assertIn("preview_frame_verified", js)
        self.assertIn("Preview không khớp tỉ lệ", js)
        self.assertIn("requires_preview_revision_check:true", js)

    def test_metadata_edit_invalidates_selection(self):
        js = "".join(self.view.scripts)
        self.assertIn("$('meta').addEventListener('input',reset)", js)


if __name__ == "__main__":
    unittest.main()
