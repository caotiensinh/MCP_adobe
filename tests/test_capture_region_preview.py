from __future__ import annotations
import base64
import unittest
from types import SimpleNamespace
from scripts.capture_region_preview import decode_preview


def response(content, error=False):
    return SimpleNamespace(content=content, is_error=error)


def image(data, mime="image/png"):
    return SimpleNamespace(type="image", mimeType=mime, data=base64.b64encode(data).decode())


class PreviewCaptureTests(unittest.TestCase):
    def test_png_mcp_image_block(self):
        png = bytes.fromhex("89504e470d0a1a0a") + b"test"
        self.assertEqual(decode_preview(response([image(png)])), (png, ".png"))

    def test_jpeg_mcp_image_block(self):
        jpg = bytes.fromhex("ffd8ff") + b"test"
        self.assertEqual(decode_preview(response([image(jpg, "image/jpeg")])), (jpg, ".jpg"))

    def test_text_tool_success_cannot_fake_preview(self):
        with self.assertRaisesRegex(ValueError, "No MCP image"):
            decode_preview(response([SimpleNamespace(type="text", text="preview success")]))

    def test_reject_signature_mismatch(self):
        with self.assertRaisesRegex(ValueError, "signature"):
            decode_preview(response([image(b"not png")]))

    def test_reject_mcp_error(self):
        with self.assertRaisesRegex(ValueError, "failed"):
            decode_preview(response([image(b"whatever")], True))


if __name__ == "__main__":
    unittest.main()
