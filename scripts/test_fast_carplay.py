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

    def test_baguette_resolution_honours_installer_directories(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(folder))
        baguette = folder / "tools/baguette/baguette"
        wrapper = folder / "bin/baguette"
        for path in (baguette, wrapper):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
            path.chmod(0o755)
        env = {"FAST_IOS_BAGUETTE_DIR": str(baguette.parent), "FAST_IOS_BIN_DIR": str(wrapper.parent)}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(Path, "home", return_value=folder), \
             mock.patch.object(fast_carplay.shutil, "which", return_value="/path/baguette"):
            self.assertEqual(fast_carplay.baguette_path(), str(baguette.resolve()))
            baguette.unlink()
            self.assertEqual(fast_carplay.baguette_path(), str(wrapper.resolve()))

    def test_missing_baguette_names_the_exact_installer_command(self):
        with mock.patch.object(fast_carplay, "baguette_path", return_value=""):
            with self.assertRaisesRegex(fast_carplay.CarPlayError, r"\./install\.sh --install-baguette"):
                fast_carplay.baguette_screenshot("U", Path("/tmp/unused.png"))

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

    def test_input_cleanup_kills_a_process_that_ignores_terminate(self):
        session = fast_carplay.BaguetteInput("U", 800, 480)
        process = mock.Mock()
        process.stdin = mock.Mock()
        process.wait.side_effect = [
            __import__("subprocess").TimeoutExpired("baguette", 3),
            __import__("subprocess").TimeoutExpired("baguette", 3),
            None,
        ]
        session.process = process
        session._stop()
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertIsNone(session.process)

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

    def test_failed_final_phone_screenshot_is_a_flow_error(self):
        with self.assertRaisesRegex(fast_carplay.CarPlayError, "locked"):
            fast_carplay.require_phone_response({"status": "fail", "error": "iPhone is locked"}, "fallback")

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
    def test_arm_snapshot_captures_display_defaults_and_running_app(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        display = Path(folder.name) / "extended_display.plist"
        display.write_bytes(b"previous")
        domain = {
            "CarPlayConfig": {"width": 800},
            "CarPlayExtraOptions": False,
            "DevicePreferences.U.SimulatorExternalDisplay": 42,
        }
        with mock.patch.object(fast_carplay, "display_plist", return_value=display), \
             mock.patch.object(fast_carplay, "simulator_defaults", return_value=domain), \
             mock.patch.object(fast_carplay, "simulator_app_running", return_value=True):
            snapshot = fast_carplay.snapshot_carplay_arm_state("U")
        self.assertEqual(snapshot["extended_display"], b"previous")
        self.assertEqual(snapshot["defaults"]["CarPlayConfig"], (True, {"width": 800}))
        self.assertTrue(snapshot["simulator_app_running"])

    def test_restore_reinstates_display_defaults_boot_state_and_simulator_app(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        display = Path(folder.name) / "extended_display.plist"
        display.write_bytes(b"changed")
        snapshot = {
            "extended_display": b"previous",
            "defaults": {
                "CarPlayConfig": (True, {"width": 800, "height": 480}),
                "CarPlayExtraOptions": (False, None),
                "DevicePreferences.U.SimulatorExternalDisplay": (False, None),
            },
            "simulator_app_running": True,
        }
        current = {
            "CarPlayConfig": {"width": 1920, "height": 720},
            "CarPlayExtraOptions": True,
            "DevicePreferences.U.SimulatorExternalDisplay": 2714,
            "Unrelated": "preserved",
        }
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(fast_carplay, "display_plist", return_value=display), \
             mock.patch.object(fast_carplay, "simulator_defaults", return_value=current), \
             mock.patch.object(fast_carplay, "quit_simulator_app_for_rearm") as quit_app, \
             mock.patch.object(fast_carplay, "run", return_value=completed) as command:
            fast_carplay.restore_carplay_arm_state(snapshot, "U", True)
        self.assertEqual(display.read_bytes(), b"previous")
        quit_app.assert_called_once()
        import_call = next(call for call in command.call_args_list if call.args[0][:2] == ["defaults", "import"])
        restored = plistlib.loads(import_call.kwargs["input_text"].encode("utf-8"))
        self.assertEqual(restored["CarPlayConfig"], {"width": 800, "height": 480})
        self.assertEqual(restored["Unrelated"], "preserved")
        self.assertNotIn("CarPlayExtraOptions", restored)
        self.assertNotIn("DevicePreferences.U.SimulatorExternalDisplay", restored)
        self.assertIn(mock.call(["xcrun", "simctl", "boot", "U"], check=False, timeout=30),
                      command.call_args_list)
        self.assertTrue(any(call.args[0][0] == "open" for call in command.call_args_list))

    def test_open_carplay_traverses_io_submenu_before_clicking_item(self):
        completed = mock.Mock(returncode=0, stdout="false\n", stderr="")
        with mock.patch.object(fast_carplay, "run", return_value=completed) as command:
            fast_carplay.ensure_sim_carplay_window()
        script = command.call_args.args[0][-1]
        io_menu = script.index('click menu "I/O"')
        external_menu = script.index('click menu item "External Displays"')
        carplay_item = script.index('click menu item "CarPlay…"')
        self.assertLess(io_menu, external_menu)
        self.assertLess(external_menu, carplay_item)

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

    def test_rearm_can_close_its_own_extended_display_setup_dialog(self):
        completed = mock.Mock(returncode=0, stdout="not-running\n", stderr="")
        with mock.patch.object(fast_carplay, "run", return_value=completed) as command:
            fast_carplay.quit_simulator_app_for_rearm()
        script = command.call_args.args[0][-1]
        self.assertIn('windowName is not "TV Out Extended Setup"', script)

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


class SessionIsolationTests(unittest.TestCase):
    def test_carplay_restores_current_and_per_udid_session_pointers(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(folder))
        current, per_udid = folder / "current", folder / "U"
        current.write_bytes(b"previous-current")

        def pointer(udid):
            return per_udid if udid else current

        with mock.patch.object(fast_carplay.fast_ui, "session_pointer", side_effect=pointer):
            snapshot = fast_carplay.snapshot_session_pointers("U")
            current.write_bytes(b"carplay-current")
            per_udid.write_bytes(b"carplay-U")
            fast_carplay.restore_session_pointers(snapshot)
        self.assertEqual(current.read_bytes(), b"previous-current")
        self.assertFalse(per_udid.exists())


class RunFlowRegressionTests(unittest.TestCase):
    def flow(self, *, phone=False, install_path=None):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(folder))
        actions = [{"type": "launch"}] if phone else [
            {"surface": "car", "type": "car_screenshot", "name": "car"}
        ]
        path = folder / "flow.json"
        app = {"project_root": str(folder), "bundle_id": "com.example", "prebuilt": True,
               "simulator": "agent-tmp-test"}
        if install_path:
            app["install_path"] = install_path
        path.write_text(json.dumps({
            "version": 1, "name": "regression",
            "app": app,
            "actions": actions,
        }))
        return path, folder / "artifacts"

    def test_sim_record_is_rejected_before_arm_or_boot(self):
        flow, artifacts = self.flow()
        simulator = {"udid": "U", "name": "agent-tmp-test", "state": "Shutdown"}
        with mock.patch.object(fast_carplay, "resolve_simulator", return_value=simulator), \
             mock.patch.object(fast_carplay, "arm_simulator") as arm, \
             mock.patch.object(fast_carplay, "ensure_simulator_ready") as boot:
            result = fast_carplay.run_flow(flow, "sim", "U", None, True, artifacts, None)
        self.assertEqual(result, 1)
        arm.assert_not_called()
        boot.assert_not_called()
        metrics = json.loads(next(artifacts.rglob("metrics.json")).read_text())
        self.assertIn("--record is not supported for --target sim", metrics["error"])

    def test_preflight_failure_does_not_arm_or_boot(self):
        flow, artifacts = self.flow()
        simulator = {"udid": "U", "name": "agent-tmp-test", "state": "Shutdown"}
        with mock.patch.object(fast_carplay, "resolve_simulator", return_value=simulator), \
             mock.patch.object(fast_carplay, "preflight_simulator",
                               side_effect=fast_carplay.CarPlayError("baguette is missing")), \
             mock.patch.object(fast_carplay, "arm_simulator") as arm, \
             mock.patch.object(fast_carplay, "ensure_simulator_ready") as boot:
            result = fast_carplay.run_flow(flow, "sim", "U", None, False, artifacts, None)
        self.assertEqual(result, 1)
        arm.assert_not_called()
        boot.assert_not_called()

    def test_failure_closes_new_car_window_and_shuts_down_sim_booted_by_run(self):
        flow, artifacts = self.flow()
        simulator = {"udid": "U", "name": "agent-tmp-test", "state": "Shutdown"}
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(fast_carplay, "resolve_simulator", return_value=simulator), \
             mock.patch.object(fast_carplay, "preflight_simulator", return_value="/baguette"), \
             mock.patch.object(fast_carplay, "sim_carplay_window_exists", side_effect=[False, True]), \
             mock.patch.object(fast_carplay, "armed_display", return_value=(True, "1920x720@2")), \
             mock.patch.object(fast_carplay, "arm_simulator"), \
             mock.patch.object(fast_carplay, "ensure_simulator_ready"), \
             mock.patch.object(fast_carplay, "ensure_sim_carplay_window",
                               side_effect=fast_carplay.CarPlayError("window failed")), \
             mock.patch.object(fast_carplay, "close_sim_carplay_window") as close, \
             mock.patch.object(fast_carplay, "run", return_value=completed) as command:
            result = fast_carplay.run_flow(flow, "sim", "U", None, False, artifacts, None)
        self.assertEqual(result, 1)
        close.assert_called_once_with("agent-tmp-test")
        self.assertIn(mock.call(["xcrun", "simctl", "shutdown", "U"], check=False, timeout=30),
                      command.call_args_list)

    def test_failed_rearm_restores_previous_display_and_app_state(self):
        flow, artifacts = self.flow()
        simulator = {"udid": "U", "name": "agent-tmp-test", "state": "Booted"}
        snapshot = {"extended_display": b"old", "defaults": {}, "simulator_app_running": True}
        with mock.patch.object(fast_carplay, "resolve_simulator", return_value=simulator), \
             mock.patch.object(fast_carplay, "preflight_simulator", return_value="/baguette"), \
             mock.patch.object(fast_carplay, "sim_carplay_window_exists", return_value=False), \
             mock.patch.object(fast_carplay, "armed_display", return_value=(True, "800x480@2")), \
             mock.patch.object(fast_carplay, "snapshot_carplay_arm_state", return_value=snapshot), \
             mock.patch.object(fast_carplay, "arm_simulator",
                               side_effect=fast_carplay.CarPlayError("arm script failed")), \
             mock.patch.object(fast_carplay, "restore_carplay_arm_state") as restore:
            result = fast_carplay.run_flow(flow, "sim", "U", None, False, artifacts, None)
        self.assertEqual(result, 1)
        restore.assert_called_once_with(snapshot, "U", True)

    def test_hardware_install_relaunches_before_waiting_for_window(self):
        flow, artifacts = self.flow(install_path="/tmp/Test.app")
        device = {"udid": "D", "name": "Phone", "connected": True}
        order = []
        with mock.patch.object(fast_carplay, "preflight_hardware", return_value=device), \
             mock.patch.object(fast_carplay.fast_device, "install_app",
                               side_effect=lambda *_: order.append("install")), \
             mock.patch.object(fast_carplay, "relaunch_hardware_app",
                               side_effect=lambda: order.append("relaunch")), \
             mock.patch.object(fast_carplay, "wait_for_hardware_window",
                               side_effect=lambda: (order.append("window"),
                                                    (_ for _ in ()).throw(fast_carplay.CarPlayError("window failed")))[1]), \
             mock.patch.object(fast_carplay.fast_device, "start_server") as server:
            result = fast_carplay.run_flow(flow, "hardware", None, "D", False, artifacts, None)
        self.assertEqual(result, 1)
        self.assertEqual(order, ["install", "relaunch", "window"])
        server.assert_not_called()

    def test_hardware_preflight_does_not_require_an_open_window(self):
        device = {"udid": "D", "name": "Phone", "connected": True}
        with mock.patch.object(fast_carplay, "hardware_app", return_value=Path("/Applications/CarPlay Simulator.app")), \
             mock.patch.object(fast_carplay.fast_device, "resolve_device", return_value=device), \
             mock.patch.object(fast_carplay, "hardware_window") as window:
            self.assertIs(fast_carplay.preflight_hardware({}, "D"), device)
        window.assert_not_called()

    def test_hardware_final_phone_screenshot_failure_prevents_pass(self):
        flow, artifacts = self.flow(phone=True)
        device = {"udid": "D", "name": "Phone", "connected": True}
        response = {"status": "fail", "error": "iPhone is locked"}
        with mock.patch.object(fast_carplay, "preflight_hardware", return_value=device), \
             mock.patch.object(fast_carplay, "wait_for_hardware_window"), \
             mock.patch.object(fast_carplay.fast_device, "start_server"), \
             mock.patch.object(fast_carplay, "run_phone_hardware"), \
             mock.patch.object(fast_carplay.fast_device, "request", return_value=response), \
             mock.patch.object(fast_carplay.fast_device, "save_screenshots"), \
             mock.patch.object(fast_carplay, "hardware_capture") as car_capture:
            result = fast_carplay.run_flow(flow, "hardware", None, "D", False, artifacts, None)
        self.assertEqual(result, 1)
        car_capture.assert_not_called()
        metrics = json.loads(next(artifacts.rglob("metrics.json")).read_text())
        self.assertEqual(metrics["error"], "iPhone is locked")


class ReportTests(unittest.TestCase):
    def test_case_id_is_the_report_row(self):
        self.assertEqual(fast_ui_report.report_task({"task": "route-loss", "case": "CPR-01"}), "CPR-01")


if __name__ == "__main__":
    unittest.main()
