"""Static, dependency-free validation of GitHub social-preview image assets."""
import struct
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "assets" / "branding"
MAX_BYTES = 1_000_000
PNG_SIG = b"\x89PNG\r\n\x1a\n"

class SocialPreviewTests(unittest.TestCase):
    def test_github_social_preview_pngs(self):
        for theme in ("dark", "light"):
            with self.subTest(theme=theme):
                f = BRAND / f"tuckbit-social-preview-{theme}.png"
                data = f.read_bytes()
                self.assertLess(len(data), MAX_BYTES)
                self.assertTrue(data.startswith(PNG_SIG), f)
                self.assertEqual(data[12:16], b"IHDR")
                width, height, depth, mode = struct.unpack(">IIBB", data[16:26])
                self.assertEqual((width, height), (1280, 640))
                self.assertEqual(depth, 8)
                self.assertIn(mode, (2, 6))  # RGB or RGBA
                self.assertGreater(len(data), 10_000)

    def test_docs_make_manual_upload_explicit(self):
        doc = (ROOT / "docs" / "SOCIAL_PREVIEW.md").read_text(encoding="utf-8")
        for item in ("Social preview", "Upload an image", "does not change the live preview",
                     "tuckbit-social-preview-dark.png", "tuckbit-social-preview-light.png"):
            self.assertIn(item, doc)

    def test_canonical_logo_files_exist(self):
        for theme in ("dark", "light"):
            logo = BRAND / f"tuckbit-logo-{theme}.png"
            self.assertTrue(logo.is_file())
            self.assertTrue(logo.read_bytes().startswith(PNG_SIG))

if __name__ == "__main__":
    unittest.main()
