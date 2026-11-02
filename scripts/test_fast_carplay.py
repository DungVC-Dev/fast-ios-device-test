import io
import json
import os
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fast_carplay
import fast_ui_report


class DisplayTests(unittest.TestCase):
    def test_armed_display_normalizes_plist_real_scale(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "display.plist"
        path.write_bytes(plistlib.dumps({"stark": True, "width": 1920, "height": 720, "scale": 2.0}))
        with mock.patch.object(fast_carplay, "display_plist", return_value=path):
            self.assertEqual(fast_carplay.armed_display("U"), (True, "1920x720@2"))

    def test_presets_match_the_runbook(self):
        self.assertEqual(fast_carplay.parse_display("widescreen"), ("widescreen", 1920, 720, 2.0))
        self.assertEqual(fast_carplay.parse_display("standard"), ("standard", 800, 480, 2.0))
        self.assertEqual(fast_carplay.parse_display("hd"), ("hd", 1280, 720, 2.0))

    def test_custom_display(self):
        self.assertEqual(fast_carplay.parse_display("720x480@1"), ("720x480@1", 720, 480, 1.0))
        self.assertEqual(fast_carplay.parse_display("1920x720@1.5"), ("1920x720@1.5", 1920, 720, 1.5))

    def test_bad_display_is_rejected(self):
        for value in ("small", "1920*720", "100x100@2", "800x480@0"):
            with self.subTest(value=value), self.assertRaises(fast_carplay.CarPlayError):
                fast_carplay.parse_display(value)

    def test_flow_default_and_override(self):
        self.assertEqual(fast_carplay.flow_display({"setup": {}}, None)[0], "widescreen")
        self.assertEqual(fast_carplay.flow_display({"setup": {"carplay_display": "standard"}}, None)[0], "standard")
        self.assertEqual(fast_carplay.flow_display({"setup": {"carplay_display": "standard"}}, "hd")[0], "hd")


class FlowValidationTests(unittest.TestCase):
    def write(self, value):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "flow.json"
        path.write_text(json.dumps(value))
        return path

    def test_phone_steps_are_sent_through_shared_guard(self):
        path = self.write({"version": 1, "name": "x", "actions": [{"type": "launch"}]})
        with mock.patch.object(fast_carplay.fast_guard, "check_actions") as guard:
            fast_carplay.load_flow(path)
        guard.assert_called_once_with([{"type": "launch"}])

    def test_car_step_needs_a_name_or_comment(self):
        path = self.write({"version": 1, "name": "x", "actions": [
            {"surface": "car", "type": "car_tap", "x": 1, "y": 1}
        ]})
        with self.assertRaisesRegex(fast_carplay.CarPlayError, "needs name or comment"):
            fast_carplay.load_flow(path)

    def test_unknown_car_action_is_rejected(self):
        path = self.write({"version": 1, "name": "x", "actions": [
            {"surface": "car", "type": "tap_label", "name": "bad"}
        ]})
        with self.assertRaisesRegex(fast_carplay.CarPlayError, "unsupported car action"):
            fast_carplay.load_flow(path)


class InputTests(unittest.TestCase):
    def test_baguette_resolution_prefers_env_then_pinned_locations(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(folder))
        explicit = folder / "explicit"
        explicit.write_text("")
        explicit.chmod(0o755)
        with mock.patch.dict(os.environ, {"FAST_IOS_BAGUETTE": str(explicit)}):
            self.assertEqual(fast_carplay.baguette_path(), str(explicit.resolve()))
        pinned = folder / ".local/share/baguette/baguette"
        pinned.parent.mkdir(parents=True)
        pinned.write_text("")
        pinned.chmod(0o755)
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(Path, "home", return_value=folder), \
             mock.patch.object(fast_carplay.shutil, "which", return_value="/path/baguette"):
            self.assertEqual(fast_carplay.baguette_path(), str(pinned.resolve()))

    def test_connected_iphones_reuses_physical_device_engine(self):
        devices = [{"name": "A", "connected": True}, {"name": "B", "connected": False}]
        with mock.patch.object(fast_carplay.fast_device, "physical_devices", return_value=devices):
            self.assertEqual(fast_carplay.connected_iphones(), [devices[0]])

    def test_coordinates_accept_pixels_and_normalized_values(self):
        self.assertEqual(fast_carplay.coordinate(960, 1920, "x"), 960)
        self.assertEqual(fast_carplay.coordinate(0.5, 1920, "x"), 960)
        with self.assertRaises(fast_carplay.CarPlayError):
            fast_carplay.coordinate(1921, 1920, "x")

    def test_input_waits_for_ack_after_startup_diagnostic(self):
        session = fast_carplay.BaguetteInput("U", 800, 480)
        process = mock.Mock()
        process.poll.return_value = None
        process.stdin = io.StringIO()
        process.stdout = io.StringIO('{"ok":true}\n')
        process.stderr = io.StringIO("[baguette] Input session started, reading from stdin\n")
        session.process = process
        with mock.patch.object(
            fast_carplay.select, "select",
            side_effect=[([process.stderr], [], []), ([process.stdout], [], [])],
        ):
            session._write({"type": "tap"})

    def test_input_heals_reattaches_and_restarts_once(self):
        session = fast_carplay.BaguetteInput("U", 800, 480)
        session.binary = "/baguette"
        event = {"type": "tap"}
        with mock.patch.object(
            session, "_write", side_effect=[fast_carplay.CarPlayError("stopped"), None]
        ) as write, mock.patch.object(session, "_stop") as stop, \
             mock.patch.object(session, "_start") as start, \
             mock.patch.object(fast_carplay, "run") as command, \
             mock.patch.object(fast_carplay, "reattach_sim_carplay_window") as reattach:
            session.send(event)
        self.assertEqual(write.call_count, 2)
        command.assert_called_once_with(["/baguette", "heal", "--udid", "U"], check=False, timeout=30)
        reattach.assert_called_once()
        stop.assert_called_once()
        start.assert_called_once()

    def test_sim_tap_includes_display_pixels(self):
        baguette = mock.Mock()
        fast_carplay.car_action_sim(
            {"surface": "car", "type": "car_tap", "name": "card", "x": 0.5, "y": 0.5},
            baguette, "U", 800, 480, Path("/tmp"), 1,
        )
        baguette.send.assert_called_once_with(
            {"type": "tap", "x": 400, "y": 240, "width": 800, "height": 480}
        )

    def test_sim_swipe_translates_flow_coordinates_to_baguette_envelope(self):
        baguette = mock.Mock()
        fast_carplay.car_action_sim(
            {"surface": "car", "type": "car_swipe", "name": "next", "x1": 0.9, "y1": 240,
             "x2": 0.1, "y2": 240, "duration": 0.5},
            baguette, "U", 800, 480, Path("/tmp"), 1,
        )
        baguette.send.assert_called_once_with({
            "type": "swipe", "startX": 720, "startY": 240, "endX": 80, "endY": 240,
            "width": 800, "height": 480, "duration": 0.5,
        })

    def test_hardware_automaker_ui_is_void(self):
        with mock.patch.object(fast_carplay, "hardware_tap"), \
             mock.patch.object(fast_carplay, "hardware_disconnected", return_value=True):
            with self.assertRaisesRegex(fast_carplay.VoidResult, "Automaker UI"):
                fast_carplay.car_action_hardware(
                    {"type": "car_tap", "name": "app", "x": 20, "y": 20}, Path("/tmp"), 1
                )

    def test_hardware_window_helper_excludes_xcode_simulator_carplay(self):
        self.assertIn('owner == "CarPlay Simulator"', fast_carplay.WINDOW_HELPER)
        self.assertNotIn('owner == "Simulator"', fast_carplay.WINDOW_HELPER)

    def test_wait_stable_requires_two_identical_captures(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(folder))
        frames = iter((b"one", b"two", b"two"))

        def capture(path):
            path.write_bytes(next(frames))

        with mock.patch.object(fast_carplay.time, "sleep"):
            result = fast_carplay.stable_screenshot(capture, folder, "stable", 5)
        self.assertEqual(result.read_bytes(), b"two")


class ArmingTests(unittest.TestCase):
    def test_simulator_menu_is_not_clicked_when_carplay_window_exists(self):
        completed = mock.Mock(returncode=0, stdout="true\n", stderr="")
        with mock.patch.object(fast_carplay, "run", return_value=completed) as command:
            fast_carplay.ensure_sim_carplay_window()
        script = command.call_args.args[0][-1]
        self.assertIn("if not hasCarPlay", script)
        self.assertIn('menu item "CarPlay…"', script)

    def test_matching_display_boots_without_rearming(self):
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(fast_carplay.fast_ui, "ensure_booted") as boot, \
             mock.patch.object(fast_carplay, "run", return_value=completed), \
             mock.patch.object(fast_carplay.time, "sleep"):
            fast_carplay.ensure_simulator_ready("UDID")
        boot.assert_called_once_with("UDID")

    def test_missing_framebuffer_heals_reattaches_and_retries_screenshot_once(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        output = Path(folder.name) / "shot.png"
        missing = mock.Mock(returncode=1, stdout="", stderr="no CarPlay framebuffer is attached")
        ok = mock.Mock(returncode=0, stdout="", stderr="")

        def command(args, **kwargs):
            if "screenshot" in args:
                result = missing if command.calls == 0 else ok
                command.calls += 1
                if result is ok:
                    output.write_bytes(b"png")
                return result
            return ok
        command.calls = 0
        with mock.patch.object(fast_carplay, "baguette_path", return_value="/baguette"), \
             mock.patch.object(fast_carplay, "run", side_effect=command), \
             mock.patch.object(fast_carplay, "reattach_sim_carplay_window") as reattach:
            fast_carplay.baguette_screenshot("U", output)
        self.assertEqual(command.calls, 2)
        reattach.assert_called_once()

    def test_screenshot_rejects_a_framebuffer_with_the_wrong_size(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        output = Path(folder.name) / "shot.png"
        output.write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
            + (1920).to_bytes(4, "big") + (720).to_bytes(4, "big")
        )
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(fast_carplay, "baguette_path", return_value="/baguette"), \
             mock.patch.object(fast_carplay, "run", return_value=completed):
            with self.assertRaisesRegex(fast_carplay.CarPlayError, "1920x720, requested 800x480"):
                fast_carplay.baguette_screenshot("U", output, (800, 480))

    def test_matching_armed_display_skips_rebooting_arm_script(self):
        with mock.patch.object(fast_carplay, "armed_display", return_value=(True, "800x480@2")), \
             mock.patch.object(fast_carplay, "run") as command:
            fast_carplay.arm_simulator(
                {"setup": {"carplay_arm_script": "/not/needed"}}, "UDID", ("standard", 800, 480, 2.0)
            )
        command.assert_not_called()

    def test_arm_script_receives_selected_size(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        script = Path(folder.name) / "arm.sh"
        script.write_text("#!/bin/sh\n")
        with mock.patch.object(fast_carplay, "armed_display", return_value=(True, "1920x720@2")), \
             mock.patch.object(fast_carplay, "quit_simulator_app_for_rearm") as close, \
             mock.patch.object(fast_carplay, "run") as command:
            fast_carplay.arm_simulator(
                {"setup": {"carplay_arm_script": str(script)}}, "UDID",
                ("standard", 800, 480, 2.0),
            )
        close.assert_called_once()
        command.assert_called_once_with([str(script.resolve()), "UDID", "800", "480", "2"], timeout=180)

    def test_rearm_refuses_to_close_a_non_agent_simulator_window(self):
        completed = mock.Mock(returncode=0, stdout="unsafe:iPhone 17 Pro\n", stderr="")
        with mock.patch.object(fast_carplay, "run", return_value=completed):
            with self.assertRaisesRegex(fast_carplay.CarPlayError, "non-agent Simulator window"):
                fast_carplay.quit_simulator_app_for_rearm()

    def test_opened_display_must_match_the_requested_size(self):
        with mock.patch.object(fast_carplay, "armed_display", return_value=(True, "1920x720@2")), \
             mock.patch.object(fast_carplay.time, "monotonic", side_effect=[0, 11]), \
             mock.patch.object(fast_carplay.time, "sleep"):
            with self.assertRaisesRegex(fast_carplay.CarPlayError, "requested 800x480@2"):
                fast_carplay.require_armed_display("U", ("standard", 800, 480, 2.0))

    def test_missing_arm_script_requires_an_already_armed_display(self):
        with mock.patch.object(fast_carplay, "armed_display", return_value=(False, "missing")):
            with self.assertRaisesRegex(fast_carplay.CarPlayError, "not armed"):
                fast_carplay.arm_simulator({"setup": {}}, "UDID", ("widescreen", 1920, 720, 2.0))


class ReportTests(unittest.TestCase):
    def test_case_id_is_the_report_row(self):
        self.assertEqual(fast_ui_report.report_task({"task": "route-loss", "case": "CPR-01"}), "CPR-01")


if __name__ == "__main__":
    unittest.main()
