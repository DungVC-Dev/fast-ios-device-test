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
            # Never the menu, even when the tests run in a terminal.
            mock.patch.object(fast_ui_clean.sys.stdin, "isatty", return_value=False),
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

    def make_run(self, project: Path, root: str, task: str, run: str, age: float) -> Path:
        folder = project / root / task / run
        folder.mkdir(parents=True)
        (folder / "metrics.json").write_text("{}")
        stamp = 1_700_000_000 + age
        fast_ui_clean.os.utime(folder, (stamp, stamp))
        return folder

    def test_scopes_pick_the_current_task_or_the_others(self) -> None:
        project = self.root / "App"
        home = self.make_run(project, "build/fast-ui", "home", "r1", 10)
        dark = self.make_run(project, "build/fast-ui", "home@dark", "r1", 20)
        login = self.make_run(project, "build/fast-device", "login", "r1", 30)  # the latest run
        build = project / "build/fast-ui-dd/a"
        build.mkdir(parents=True)
        out = self.run_clean("--project", str(project), "--scope", "others", "--yes")
        self.assertIn("TASK current=login", out)
        self.assertFalse(home.exists())
        self.assertFalse(dark.exists())
        self.assertTrue(login.exists())
        self.assertTrue(build.exists())
        self.run_clean("--project", str(project), "--scope", "current", "--yes")
        self.assertFalse(login.exists())
        self.assertTrue(build.exists())

    def test_named_task_and_variants(self) -> None:
        project = self.root / "App"
        home = self.make_run(project, "build/fast-ui", "home", "r1", 10)
        dark = self.make_run(project, "build/fast-ui", "home@dark", "r1", 20)
        login = self.make_run(project, "build/fast-ui", "login", "r1", 30)
        self.run_clean("--project", str(project), "--scope", "current", "--task", "home", "--yes")
        self.assertFalse(home.exists())
        self.assertFalse(dark.exists())
        self.assertTrue(login.exists())

    def test_device_runs_go_with_scope_all(self) -> None:
        project = self.root / "App"
        run = self.make_run(project, "build/fast-device", "login", "r1", 10)
        self.run_clean("--project", str(project), "--yes")
        self.assertFalse(run.exists())


if __name__ == "__main__":
    unittest.main()
