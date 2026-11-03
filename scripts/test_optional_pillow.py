#!/usr/bin/env python3

"""The complete test discovery remains green when optional Pillow is absent."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class OptionalPillowTests(unittest.TestCase):
    def test_image_test_modules_skip_cleanly_without_pillow(self):
        scripts = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as raw:
            shadow = Path(raw)
            package = shadow / "PIL"
            package.mkdir()
            (package / "__init__.py").write_text(
                "raise ImportError('Pillow intentionally hidden by test')\n"
            )
            environment = dict(os.environ)
            environment["PYTHONPATH"] = os.pathsep.join(
                [str(shadow), environment.get("PYTHONPATH", "")]
            )
            for module in (
                "test_fast_evidence",
                "test_fast_evidence_sheet",
                "test_fast_ui_review",
            ):
                with self.subTest(module=module):
                    result = subprocess.run(
                        [sys.executable, "-m", "unittest", module],
                        cwd=scripts,
                        env=environment,
                        text=True,
                        capture_output=True,
                        timeout=30,
                        check=False,
                    )
                    report = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 0, report)
                    self.assertIn("skipped", report.lower())


if __name__ == "__main__":
    unittest.main()
