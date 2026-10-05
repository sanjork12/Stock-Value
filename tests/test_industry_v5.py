from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parents[1]


class IndustryPanoramaTests(unittest.TestCase):
    def test_panorama_image_exists(self):
        img = ROOT / "assets" / "ai_industry_panorama.jpg"
        self.assertTrue(img.exists(), f"missing {img}")
        self.assertGreater(img.stat().st_size, 10_000)

    def test_render_module_imports(self):
        from industry.ui import render_industry_page

        self.assertTrue(callable(render_industry_page))


if __name__ == "__main__":
    unittest.main()
