#!/usr/bin/env python3
"""Checks for the bundled /testAmplitude tool (amplitude-tracking-test/): pure-logic scripts,
its runner kept apart from fastDeviceTest's, and no app-specific data in the package."""

from __future__ import annotations

import importlib.util
import json
import plistlib
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "amplitude-tracking-test"
SCRIPTS = TOOL / "scripts"


def load(name: str):
    # No __pycache__ inside the shipped tool folder.
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(f"amp_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RunnerIsolationTests(unittest.TestCase):
    """fastDeviceTest runs a different runner build on the same iPhones; sharing a cache, port,
    process name or bundle id made each tool rebuild, reuse or kill the other's runner."""

    def setUp(self) -> None:
        self.amp = (SCRIPTS / "run_flow_device.py").read_text()
        self.fast = (REPO / "scripts" / "fast_device.py").read_text()

    def test_cache_port_and_process_name_differ_from_fast_device(self) -> None:
        self.assertIn("Library/Caches/amplitude-tracking-test/device", self.amp)
        self.assertNotIn("Library/Caches/fast-device-test", self.amp)
        amp_port = re.search(r'SERVER_PORT = int\(os.environ.get\("(\w+)", "(\d+)"\)\)', self.amp)
        fast_port = re.search(r'SERVER_PORT = int\(os.environ.get\("(\w+)", "(\d+)"\)\)', self.fast)
        self.assertIsNotNone(amp_port)
        self.assertIsNotNone(fast_port)
        self.assertNotEqual(amp_port.groups(), fast_port.groups())
        # fastDeviceTest stops its runner with `pkill -f serve-<udid>.xctestrun`: a name that
        # contains that string would be killed too.
        self.assertNotIn("serve-{udid}.xctestrun", self.amp)
        self.assertIn("amp-runner-{udid}.xctestrun", self.amp)
        self.assertNotIn("serve-", "amp-runner-")

    def test_runner_bundle_id_differs(self) -> None:
        amp = (TOOL / "device-runner" / "project.yml").read_text()
        fast = (REPO / "device-runner" / "project.yml").read_text()
        ids = [re.search(r"PRODUCT_BUNDLE_IDENTIFIER: (\S+)", text).group(1) for text in (amp, fast)]
        self.assertNotEqual(*ids)
        self.assertNotIn("fastdevice.runner", self.amp)


class PrivacyTests(unittest.TestCase):
    """The package is public: no company, app, person or machine names, and no saved flows."""

    PRIVATE = re.compile(r"astraler|carwidgets|car widgets|carface|carw_|dungiosastraler|/Users/", re.I)

    def test_no_private_names_in_the_tool_skill_or_command(self) -> None:
        roots = [TOOL, REPO / "skills" / "amplitude-tracking-test", REPO / "commands" / "testAmplitude.md"]
        files = [path for root in roots for path in ([root] if root.is_file() else root.rglob("*"))
                 if path.is_file() and "__pycache__" not in path.parts]
        self.assertTrue(files)
        hits = [f"{path.relative_to(REPO)}: {match.group(0)}" for path in files
                for match in [self.PRIVATE.search(path.read_text(errors="replace"))] if match]
        self.assertEqual(hits, [])

    def test_no_flows_are_shipped(self) -> None:
        self.assertFalse((TOOL / "flows").exists())

    def test_the_suite_leaves_no_bytecode_in_the_tool(self) -> None:
        load("tracking_match")
        self.assertEqual(list(TOOL.rglob("__pycache__")), [])


class AmplitudeKeyTests(unittest.TestCase):
    def run_key(self, key: str, prod: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            app = root / "App.app"
            app.mkdir()
            (app / "Info.plist").write_bytes(plistlib.dumps({"AMPLITUDE_API_KEY": key}))
            (root / "Config-Prod.xcconfig").write_text(f"AMPLITUDE_API_KEY = {prod}\n")
            return subprocess.run([sys.executable, str(SCRIPTS / "amplitude_key.py"), str(app), "--project-root", raw],
                                  capture_output=True, text=True, timeout=30)

    def test_production_key_is_refused_and_never_printed_whole(self) -> None:
        refused = self.run_key("prodkey1234567890", "prodkey1234567890")
        self.assertEqual(refused.returncode, 2)
        self.assertNotIn("prodkey1234567890", refused.stdout)
        allowed = self.run_key("stagingkey123456", "prodkey1234567890")
        self.assertEqual(allowed.returncode, 0, allowed.stdout)
        self.assertNotIn("stagingkey123456", allowed.stdout)


PLAN = [
    {"name": "Home Viewed", "kind": "client", "properties": ["access level"]},
    {"name": "Item Saved", "kind": "client", "properties": ["item id", "source"]},
    {"name": "Never Fired", "kind": "client", "properties": []},
    {"name": "Server Billed", "kind": "backend", "properties": []},
]

SWIFT = """
enum TrackingFlowData {
    case homeViewed(level: String), itemSaved(id: String)
    case debugOnly
    var eventName: String {
        switch self {
        case .homeViewed: return "Home Viewed"
        case .itemSaved: return "Item Saved"
        case .debugOnly: return "Debug Only"
        }
    }
    var parameters: [String: Any] {
        switch self {
        case let .homeViewed(level): return ["access level": level]
        case let .itemSaved(id): return ["item id": id, "screen": "home"]
        case .debugOnly: return [:]
        }
    }
}
"""


class TrackingScriptTests(unittest.TestCase):
    def run_script(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(SCRIPTS / f"{name}.py"), *args],
                              capture_output=True, text=True, timeout=60)

    def test_static_diff_finds_missing_keys_and_unplanned_events(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "events.json").write_text(json.dumps(PLAN))
            (root / "Sources").mkdir()
            (root / "Sources" / "Tracking.swift").write_text(SWIFT)
            result = self.run_script("tracking_static", str(root / "events.json"), str(root / "Sources"),
                                     "--out", str(root / "static.json"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("in_code=2", result.stdout)
            self.assertIn("MISSING  Never Fired", result.stdout)
            self.assertIn("KEYS     Item Saved (Tracking.swift): plan-only ['source']; code-only ['screen']", result.stdout)
            self.assertIn("UNPLANNED Debug Only", result.stdout)
            # A backend event is never reported as missing from the app.
            self.assertNotIn("Server Billed", result.stdout)

    def test_match_reports_pass_fail_missing_and_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "events.json").write_text(json.dumps(PLAN))
            run = root / "runs" / "journey-1"
            run.mkdir(parents=True)
            (run / "console.log").write_text("\n".join([
                'noise line',
                '[TRACKING][Amplitude] event=Home Viewed params=["access level": "premium"]',
                '[TRACKING][Amplitude] event=Home Viewed params=["access level": "premium"]',
                '[TRACKING][Amplitude] event=Item Saved params=["item id": "42"]',
                '[TRACKING][Amplitude] event=Debug Only params=[]',
            ]))
            (root / "expect.json").write_text(json.dumps([
                {"event": "Home Viewed", "params": {"access level": "premium"}, "once": True},
                {"event": "Item Saved"},
                {"event": "Never Fired"},
            ]))
            report = root / "report.md"
            result = self.run_script("tracking_match", str(root / "events.json"), str(root / "runs"),
                                     "--expect", str(root / "expect.json"), "--out", str(report))
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("DUPLICATE Home Viewed: fired 2x", result.stdout)
            self.assertIn("FAIL      Item Saved: missing keys ['source']", result.stdout)
            self.assertIn("MISSING   Never Fired: not fired", result.stdout)
            self.assertIn("UNPLANNED Debug Only", result.stdout)
            self.assertIn("| Home Viewed | DUPLICATE |", report.read_text())

    def test_match_without_tracking_lines_says_how_to_fix_it(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "events.json").write_text(json.dumps(PLAN))
            (root / "console.log").write_text("nothing here\n")
            result = self.run_script("tracking_match", str(root / "events.json"), str(root / "console.log"),
                                     "--out", str(root / "r.md"))
            self.assertEqual(result.returncode, 1)
            self.assertIn("capture_console", result.stdout)


class TrackingPlanTests(unittest.TestCase):
    def plan_module(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            # The pure helpers do not need openpyxl; a stand-in lets the module import.
            stub = type(sys)("openpyxl")
            sys.modules["openpyxl"] = stub
            self.addCleanup(sys.modules.pop, "openpyxl", None)
        return load("tracking_plan")

    def test_source_column_decides_the_kind(self) -> None:
        plan = self.plan_module()
        self.assertEqual(plan.kind("Backend (HTTP API)"), "backend")
        self.assertEqual(plan.kind("Amplitude SDK (auto)"), "sdk")
        self.assertEqual(plan.kind("iOS client"), "client")

    def test_property_cells_become_names(self) -> None:
        plan = self.plan_module()
        cell = "1. access level (free / premium)\n2) item id - the saved item\n\nsource: where it came from"
        self.assertEqual(plan.property_names(cell), ["access level", "item id", "source"])
        self.assertEqual(plan.property_names(None), [])
        self.assertEqual(plan.property_names("sign-in method\nscreen – home or settings\nplan:monthly"),
                         ["sign-in method", "screen", "plan"])

    @unittest.skipUnless(importlib.util.find_spec("openpyxl"), "needs openpyxl")
    def test_workbook_rows_skip_struck_and_uningested_events(self) -> None:
        import openpyxl
        from openpyxl.styles import Font
        with tempfile.TemporaryDirectory() as raw:
            book = openpyxl.Workbook()
            sheet = book.active
            sheet.title = "Amplitude Events"
            sheet.append(["Category", "Event Name (Display)", "Ingested Name", "Source", "Event Properties"])
            sheet.append(["Home", "Home Viewed", "home_viewed", "iOS", "1. access level"])
            sheet.append(["Home", "Old Event", "old_event", "iOS", ""])
            sheet["B3"].font = Font(strike=True)
            sheet.append(["Home", "Draft Event", None, "iOS", ""])
            path = Path(raw) / "plan.xlsx"
            book.save(path)
            events = load("tracking_plan").load(path, "Amplitude Events")
        self.assertEqual([(e["name"], e["kind"], e["properties"]) for e in events],
                         [("Home Viewed", "client", ["access level"])])


class ScriptSmokeTests(unittest.TestCase):
    def test_every_script_compiles_and_answers_help(self) -> None:
        for script in sorted(SCRIPTS.glob("*.py")):
            compile(script.read_text(), str(script), "exec")
        for name in ("amplitude_key", "tracking_match", "tracking_static"):
            result = subprocess.run([sys.executable, str(SCRIPTS / f"{name}.py"), "--help"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_libraries_fail_with_one_line(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            for module, script in (("openpyxl", "tracking_plan"), ("PIL", "run_flow")):
                blocker = Path(raw) / module
                blocker.mkdir(exist_ok=True)
                (blocker / "__init__.py").write_text("raise ImportError('blocked for the test')\n")
                result = subprocess.run([sys.executable, str(SCRIPTS / f"{script}.py"), "--help"],
                                        capture_output=True, text=True, timeout=30,
                                        env={"PYTHONPATH": raw, "PATH": "/usr/bin:/bin"})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"FAIL {script}:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
