from __future__ import annotations

import contextlib
import fcntl
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fast_ui_clean  # noqa: E402


class CleanTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.caches = self.root / "Caches"
        self.tmp = self.root / "tmp"
        self.tmp.mkdir()
        patches = [
            mock.patch.object(fast_ui_clean, "CACHES", self.caches),
            mock.patch.object(fast_ui_clean.tempfile, "gettempdir", return_value=str(self.tmp)),
            mock.patch.object(fast_ui_clean, "runner_serving", return_value=False),
            mock.patch.dict(fast_ui_clean.os.environ, {}, clear=False),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        for key in ("FAST_UI_LOCK_DIR", "FAST_UI_MAP_DIR", "FAST_DEVICE_CACHE"):
            fast_ui_clean.os.environ.pop(key, None)

    def make(self, relative: str, text: str = "x") -> Path:
        path = self.caches / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def run_clean(self, *argv: str) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(fast_ui_clean.main(list(argv)), 0)
        return out.getvalue()

    def test_lists_without_deleting_until_yes(self) -> None:
        runner = self.make("fast-device-test/abc/signed")
        session = self.tmp / "fast-ui-session-SIM"
        session.write_text("p")
        listed = self.run_clean()
        self.assertIn("WOULD-DELETE", listed)
        self.assertIn("add --yes", listed)
        self.assertTrue(runner.exists())
        self.run_clean("--yes")
        self.assertFalse(runner.exists())
        self.assertFalse(session.exists())

    def test_maps_only_with_the_flag(self) -> None:
        map_ = self.make("fast-ui-map/com.x.json", "{}")
        self.run_clean("--yes")
        self.assertTrue(map_.exists())
        self.run_clean("--yes", "--maps")
        self.assertFalse(map_.exists())

    def test_held_and_dirty_locks_stay(self) -> None:
        idle = self.make("fast-ui/locks/IDLE.lock", json.dumps({"dirty": 0}) + "\n")
        dirty = self.make("fast-ui/locks/DIRTY.lock", json.dumps({"dirty": 1, "ui": {"appearance": "light"}}) + "\n")
        busy = self.make("fast-ui/locks/BUSY.lock", "")
        with busy.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            out = self.run_clean("--yes")
        self.assertFalse(idle.exists())
        self.assertTrue(dirty.exists())
        self.assertTrue(busy.exists())
        self.assertIn("a flow is running on BUSY", out)
        self.assertIn("killed run left DIRTY", out)

    def test_serving_runner_keeps_the_device_cache(self) -> None:
        runner = self.make("fast-device-test/server-U.json", "{}")
        with mock.patch.object(fast_ui_clean, "runner_serving", return_value=True):
            out = self.run_clean("--yes")
        self.assertTrue(runner.exists())
        self.assertIn("fastDeviceTest stop", out)

    def test_project_build_folders_and_never_the_rest(self) -> None:
        project = self.root / "App"
        runs = project / "build/fast-ui/home/run/metrics.json"
        device = project / "build/fast-device-tests/x/DerivedData/a"
        app_build = project / "build/fast-ui-dd/Build/Products/a"
        keep = project / "build/Other/a"
        for path in (runs, device, app_build, keep):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x")
        self.run_clean("--yes", "--project", str(project))
        self.assertFalse(runs.exists())
        self.assertFalse(device.exists())
        self.assertFalse(app_build.exists())
        self.assertTrue(keep.exists())


if __name__ == "__main__":
    unittest.main()
