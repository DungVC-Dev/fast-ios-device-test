#!/usr/bin/env python3

"""Tests for fast_conditions (network_condition, low_power) and fast_applog (app console logs)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fast_applog  # noqa: E402
import fast_conditions  # noqa: E402


class ConditionTests(unittest.TestCase):
    def test_network_profile_names_are_matched_case_insensitively_and_off_has_aliases(self) -> None:
        self.assertEqual(fast_conditions.network_value({"profile": "very bad network"}), "Very Bad Network")
        for off in ("off", "none", "OFF"):
            self.assertEqual(fast_conditions.network_value({"profile": off}), "off")
        with self.assertRaisesRegex(ValueError, "not a Network Link Conditioner preset"):
            fast_conditions.network_value({"profile": "5G"})

    def test_network_steps_open_the_page_tolerantly_then_pick_the_cell_and_switch(self) -> None:
        steps = fast_conditions.network_steps("Edge")
        self.assertEqual(steps[0], {"type": "launch", "app": "com.apple.Preferences"})
        self.assertEqual(steps[1]["type"], "pause")
        navigation = [step for step in steps if step["type"] in ("scroll_to", "tap_label") and step.get("optional")]
        self.assertEqual([step["label"] for step in navigation],
                         ["Developer", "Developer", "Network Link Conditioner", "Network Link Conditioner"])
        self.assertEqual(steps[-3]["type"], "wait")
        self.assertEqual(steps[-2], {"type": "tap_label", "label": "Edge", "element_type": "Cell",
                                     "app": "com.apple.Preferences"})
        self.assertEqual(steps[-1]["on"], True)
        off = fast_conditions.network_steps("off")
        self.assertFalse(any(step.get("element_type") == "Cell" for step in off))
        self.assertIs(off[-1]["on"], False)

    def test_100_percent_loss_is_refused_because_it_cuts_the_runner_off(self) -> None:
        with self.assertRaisesRegex(ValueError, "cuts the USB link"):
            fast_conditions.network_value({"profile": "100% Loss"})

    def test_slowdown_grows_with_the_profile(self) -> None:
        self.assertEqual(fast_conditions.slowdown({}), 1.0)
        self.assertEqual(fast_conditions.slowdown({"low_power": True}), 1.0)
        self.assertEqual(fast_conditions.slowdown({"network": "3G"}), 5.0)
        self.assertEqual(fast_conditions.slowdown({"network": "Edge"}), 8.0)
        self.assertEqual(fast_conditions.slowdown({"network": "LTE"}), 3.0)

    def test_low_power_accepts_booleans_and_words(self) -> None:
        self.assertTrue(fast_conditions.low_power_value({"on": True}))
        self.assertFalse(fast_conditions.low_power_value({"value": "off"}))
        with self.assertRaisesRegex(ValueError, "low_power needs"):
            fast_conditions.low_power_value({})
        steps = fast_conditions.low_power_steps(True)
        self.assertEqual(steps[-1]["label"], "Low Power Mode")
        self.assertIs(steps[-1]["on"], True)

    def test_expand_keeps_other_steps_and_maps_each_step_to_its_source(self) -> None:
        actions = [{"type": "wait", "label": "A"}, {"type": "low_power", "on": True, "return_to": "com.other"},
                   {"type": "tap_label", "label": "B"}]
        expanded, origin = fast_conditions.expand(actions, "com.example.app")
        self.assertEqual(expanded[0], actions[0])
        self.assertEqual(expanded[-1], actions[2])
        self.assertEqual(expanded[-2], {"type": "activate", "app": "com.other", "via": "low_power"})
        self.assertEqual(origin[0], 1)
        self.assertEqual(origin[-1], 3)
        self.assertEqual(set(origin[1:-1]), {2})
        self.assertTrue(all(step["via"] == "low_power" for step in expanded[1:-1]))

    def test_requested_tracks_the_last_state_of_each_condition(self) -> None:
        self.assertEqual(fast_conditions.requested([{"type": "network_condition", "profile": "3G"}]), {"network": "3G"})
        both = fast_conditions.requested([
            {"type": "network_condition", "profile": "3G"}, {"type": "network_condition", "profile": "off"},
            {"type": "low_power", "on": True},
        ])
        self.assertEqual(both, {"network": None, "low_power": True})
        self.assertEqual(fast_conditions.requested([{"type": "wait"}]), {})

    def test_state_file_merges_and_disappears_when_nothing_is_on(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fast_conditions.remember(root, "U", {"network": "3G"})
            self.assertEqual(fast_conditions.remember(root, "U", {"low_power": True}), {"network": "3G", "low_power": True})
            self.assertEqual(fast_conditions.describe(fast_conditions.load(root, "U")), "network=3G,low_power=on")
            fast_conditions.remember(root, "U", {"network": None, "low_power": None})
            self.assertFalse(fast_conditions.state_path(root, "U").exists())
            self.assertEqual(fast_conditions.load(root, "U"), {})

    def test_cleanup_switches_off_only_what_is_on(self) -> None:
        steps = fast_conditions.cleanup_steps({"network": "3G"}, "com.example.app")
        self.assertIs(steps[-2]["on"], False)
        self.assertEqual(steps[-2]["label"], "Enable")
        self.assertEqual(steps[-1]["app"], "com.example.app")
        self.assertEqual(fast_conditions.cleanup_steps({}), [])


class AppLogTests(unittest.TestCase):
    def setUp(self) -> None:
        raw = tempfile.TemporaryDirectory()
        self.addCleanup(raw.cleanup)
        self.root = Path(raw.name)
        self.log = self.root / "app.log"

    def capture(self, text: str, pid: int | None = None) -> None:
        self.log.write_text(text)
        fast_applog.save(self.root, "U", {"pid": pid or os.getpid(), "bundle_id": "com.example.app",
                                         "log": str(self.log), "cursor": 0})

    def test_launch_command_attaches_the_console_and_mirrors_os_log(self) -> None:
        command = fast_applog.launch_command("U", "com.example.app")
        self.assertIn("--console", command)
        self.assertIn("--terminate-existing", command)
        self.assertEqual(json.loads(command[command.index("--environment-variables") + 1]), {"OS_ACTIVITY_DT_MODE": "YES"})
        self.assertEqual(command[-1], "com.example.app")

    def test_start_writes_state_and_stop_ends_the_process_group(self) -> None:
        sleeper = subprocess.Popen(["sleep", "30"], start_new_session=True)
        self.addCleanup(sleeper.kill)
        with mock.patch.object(fast_applog, "launch_command", return_value=["sleep", "30"]):
            state = fast_applog.start(self.root, "U", "com.example.app", popen=lambda *a, **k: sleeper)
        self.assertEqual(fast_applog.load(self.root, "U")["bundle_id"], "com.example.app")
        self.assertEqual(state["pid"], sleeper.pid)
        fast_applog.stop(self.root, "U")
        sleeper.wait(timeout=5)
        self.assertIsNone(fast_applog.load(self.root, "U"))

    def test_a_dead_capture_is_not_loaded(self) -> None:
        dead = subprocess.Popen(["true"])
        dead.wait()
        self.capture("x\n", pid=dead.pid)
        self.assertIsNone(fast_applog.load(self.root, "U"))
        with self.assertRaisesRegex(fast_applog.AppLogError, "log start"):
            fast_applog.require(self.root, "U")

    def test_wait_moves_the_cursor_so_a_line_matches_once(self) -> None:
        self.capture("boot\n[LyricFlow] song changed: A - B playing=true\nother\n")
        line = fast_applog.wait(self.root, "U", r"song changed: (.+)", timeout=1)
        self.assertEqual(line, "[LyricFlow] song changed: A - B playing=true")
        with self.assertRaisesRegex(fast_applog.AppLogError, "within 0.2s.*last lines"):
            fast_applog.wait(self.root, "U", r"song changed", timeout=0.2, poll=0.05)
        with self.log.open("a") as log:
            log.write("[LyricFlow] song changed: C - D\n")
        self.assertIn("C - D", fast_applog.wait(self.root, "U", r"song changed", timeout=1))

    def test_wait_reports_an_app_that_quit(self) -> None:
        self.capture("boot\n")
        with mock.patch.object(fast_applog, "alive", side_effect=[True, False]):
            with self.assertRaisesRegex(fast_applog.AppLogError, "console ended"):
                fast_applog.wait(self.root, "U", "never", timeout=5, poll=0)

    def test_assert_and_assert_absent_read_after_the_mark(self) -> None:
        self.capture("skip next: not_authorized\n")
        self.assertIn("not_authorized", fast_applog.check(self.root, "U", "not_authorized", present=True))
        with self.assertRaisesRegex(fast_applog.AppLogError, "matches 'not_authorized'"):
            fast_applog.check(self.root, "U", "not_authorized", present=False)
        fast_applog.mark(self.root, "U")
        self.assertEqual(fast_applog.check(self.root, "U", "not_authorized", present=False), "")
        with self.assertRaisesRegex(fast_applog.AppLogError, "nothing logged since the last mark"):
            fast_applog.check(self.root, "U", "not_authorized", present=True)

    def test_a_bad_regex_is_named(self) -> None:
        self.capture("x\n")
        with self.assertRaisesRegex(fast_applog.AppLogError, "bad regex"):
            fast_applog.check(self.root, "U", "(", present=True)

    def test_flow_expectations(self) -> None:
        text = "song changed: A\nlyrics ready\n"
        self.assertEqual(fast_applog.check_expectations(text, ["song changed", "lyrics ready"], ["not_authorized"]), [])
        problems = fast_applog.check_expectations(text, ["Failed"], ["lyrics"])
        self.assertEqual(problems, ["expect_log 'Failed' never matched", "expect_no_log 'lyrics' matched 'lyrics ready'"])


if __name__ == "__main__":
    unittest.main()
