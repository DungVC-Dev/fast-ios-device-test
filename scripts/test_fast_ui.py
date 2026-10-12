#!/usr/bin/env python3

"""Engine unit tests: python3 scripts/test_fast_ui.py"""

from __future__ import annotations

import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fast_ui  # noqa: E402

from PIL import Image  # noqa: E402


def app_spec(tmp: Path, simulator: str) -> dict:
    src = tmp / "Sources"
    src.mkdir(exist_ok=True)
    if not (src / "A.swift").exists():
        (src / "A.swift").write_text("let a = 1\n")
    return {
        "project": str(tmp / "App.xcodeproj"),
        "scheme": "App",
        "configuration": "Debug",
        "simulator": simulator,
        "bundle_id": "com.example.app",
        "app_path": str(tmp / "App.app"),
        "derived_data": str(tmp / "dd"),
        "build_inputs": [str(src)],
    }


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_ignores_simulator(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            first = fast_ui.build_fingerprint(app_spec(tmp, "SIM-A"), tmp)
            second = fast_ui.build_fingerprint(app_spec(tmp, "SIM-B"), tmp)
        self.assertEqual(first, second)

    def test_fingerprint_changes_with_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            spec = app_spec(tmp, "SIM-A")
            first = fast_ui.build_fingerprint(spec, tmp)
            (tmp / "Sources" / "A.swift").write_text("let a = 22\n")
            second = fast_ui.build_fingerprint(spec, tmp)
        self.assertNotEqual(first, second)


class HierarchyTests(unittest.TestCase):
    def test_describe_ui_retries_transient_failure(self) -> None:
        good = mock.Mock(stdout='[{"AXLabel": "Widgets", "type": "Button"}]', returncode=0)
        calls = [fast_ui.FastUIError("boom"), good]

        def fake_axe(udid, *args, check=True):
            value = calls.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        with mock.patch.object(fast_ui, "axe", side_effect=fake_axe), \
                mock.patch.object(fast_ui.time, "sleep"):
            nodes = fast_ui.hierarchy("SIM")
        self.assertEqual(nodes[0]["AXLabel"], "Widgets")

    def test_visible_labels_are_screen_ordered_deduped_and_denoised(self) -> None:
        nodes = [
            {"AXLabel": "B", "frame": {"x": 0, "y": 50}},
            {"AXLabel": "A", "frame": {"x": 0, "y": 10}},
            {"AXLabel": "B", "frame": {"x": 0, "y": 90}},
            {"AXLabel": "14:22", "frame": {"x": 0, "y": 0}},
            {"AXLabel": "100%", "frame": {"x": 0, "y": 0}},
            {"AXLabel": "", "frame": {"x": 0, "y": 0}},
            {"AXLabel": "Vertical scroll bar, 2 pages", "frame": {"x": 0, "y": 5}},
            {"AXLabel": "Horizontal scroll bar, 1 page", "frame": {"x": 0, "y": 6}},
        ]
        self.assertEqual(fast_ui.visible_labels(nodes), ["A", "B"])
        many = [{"AXLabel": f"L{i:03d}"} for i in range(100)]
        self.assertEqual(len(fast_ui.visible_labels(many, limit=12)), 12)

    def test_hierarchy_reuses_a_fresh_tree_until_a_gesture(self) -> None:
        good = mock.Mock(stdout='[{"AXLabel": "A", "type": "Button"}]', returncode=0)
        with mock.patch.object(fast_ui, "axe", return_value=good) as axe, mock.patch.object(fast_ui.time, "sleep"):
            fast_ui.hierarchy("SIM")
            fast_ui.hierarchy("SIM", max_age=fast_ui.HIERARCHY_REUSE)
            self.assertEqual(axe.call_count, 1)
            fast_ui.tap_point("SIM", 1, 1, 0)
            fast_ui.hierarchy("SIM", max_age=fast_ui.HIERARCHY_REUSE)
            fast_ui.hierarchy("SIM")
        self.assertEqual(axe.call_count, 4)  # describe, tap, describe, describe

    def test_flatten_skips_frame_dicts_and_recurses_children_only(self) -> None:
        tree = [{"type": "Application", "frame": {"x": 0, "y": 0, "width": 10, "height": 10},
                 "children": [{"type": "Button", "AXLabel": "Go", "frame": {"x": 1, "y": 2, "width": 4, "height": 4}}]}]
        nodes = list(fast_ui.flatten(tree))
        self.assertEqual([n.get("type") for n in nodes], ["Application", "Button"])

    def test_compact_node_drops_children_and_survives_missing_frame(self) -> None:
        node = {"type": "Button", "AXLabel": "Go", "AXUniqueId": "go", "AXValue": "1",
                "frame": {"x": 1, "y": 2, "width": 4, "height": 4}, "children": [{"type": "Image"}]}
        self.assertEqual(fast_ui.compact_node(node),
                         {"label": "Go", "type": "Button", "id": "go", "value": "1",
                          "frame": {"x": 1, "y": 2, "width": 4, "height": 4}, "center": [3.0, 4.0]})
        self.assertEqual(fast_ui.compact_node({"type": "Other"}), {"type": "Other"})

    def test_dump_file_is_flat_and_compact(self) -> None:
        nodes = [{"AXLabel": "Widgets", "type": "Button", "frame": {"x": 0, "y": 0, "width": 1, "height": 1},
                  "children": [{"type": "Image", "frame": {"x": 0, "y": 0, "width": 1, "height": 1}}]}]
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(fast_ui, "hierarchy", return_value=nodes), \
                mock.patch.object(fast_ui.time, "sleep"):
            fast_ui.execute_action({"type": "dump", "name": "home"}, "SIM", Path(raw), 3, [])
            text = (Path(raw) / "home-ui.json").read_text()
        self.assertNotIn("children", text)
        self.assertIn('"center"', text)


class ActionTests(unittest.TestCase):
    def test_tap_label_taps_matched_frame_without_axe_label_lookup(self) -> None:
        node = {"AXLabel": "Yes", "type": "Button", "frame": {"x": 10, "y": 20, "width": 100, "height": 40}}
        with mock.patch.object(fast_ui, "hierarchy", return_value=[node]), \
                mock.patch.object(fast_ui, "tap_point") as tap, \
                mock.patch.object(fast_ui, "axe") as axe:
            fast_ui.execute_action({"type": "tap_label", "label": "Yes"}, "SIM", Path("/tmp"), 1, [])
        tap.assert_called_once_with("SIM", 60.0, 40.0, 0.15)
        axe.assert_not_called()

    def test_optional_tap_label_skips_when_missing(self) -> None:
        with mock.patch.object(fast_ui, "hierarchy", return_value=[]), \
                mock.patch.object(fast_ui, "tap_point") as tap:
            result = fast_ui.execute_action(
                {"type": "tap_label", "label": "Nope", "optional": True}, "SIM", Path("/tmp"), 1, []
            )
        tap.assert_not_called()
        self.assertIsNone(result)

    def test_dump_action_writes_labels_and_hierarchy(self) -> None:
        nodes = [{"AXLabel": "Widgets", "type": "Button", "frame": {"x": 0, "y": 0, "width": 1, "height": 1}}]
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(fast_ui, "hierarchy", return_value=nodes), \
                mock.patch.object(fast_ui.time, "sleep"):
            artifacts = Path(raw)
            result = fast_ui.execute_action({"type": "dump", "name": "home"}, "SIM", artifacts, 3, [])
            self.assertEqual(result["labels"], ["Widgets"])
            self.assertTrue((artifacts / "home-ui.json").exists())

    def test_label_contains_matches_a_fragment(self) -> None:
        node = {"AXLabel": "Office, No Internet Connection", "type": "Cell", "frame": {}}
        self.assertTrue(fast_ui.matches(node, {"label_contains": "Office"}))
        self.assertFalse(fast_ui.matches(node, {"label_contains": "Office 2G"}))

    def test_matches_id_and_value(self) -> None:
        node = {"AXLabel": "Wi-Fi", "AXUniqueId": "wifiSwitch", "AXValue": "1", "type": "Switch", "frame": {}}
        self.assertTrue(fast_ui.matches(node, {"id": "wifiSwitch"}))
        self.assertTrue(fast_ui.matches(node, {"value": "1", "element_type": "Switch"}))
        self.assertFalse(fast_ui.matches(node, {"id": "other"}))

    def test_tap_label_accepts_id_and_label_contains(self) -> None:
        node = {"AXLabel": "Continue to app", "AXUniqueId": "cta", "type": "Button",
                "frame": {"x": 0, "y": 0, "width": 10, "height": 10}}
        with mock.patch.object(fast_ui, "hierarchy", return_value=[node]), \
                mock.patch.object(fast_ui, "tap_point") as tap:
            fast_ui.execute_action({"type": "tap_label", "id": "cta"}, "SIM", Path("/tmp"), 1, [])
            fast_ui.execute_action({"type": "tap_label", "label_contains": "Continue"}, "SIM", Path("/tmp"), 2, [])
        self.assertEqual(tap.call_count, 2)
        with self.assertRaisesRegex(fast_ui.FastUIError, "missing 'label' or 'id'"):
            fast_ui.execute_action({"type": "tap_label"}, "SIM", Path("/tmp"), 3, [])

    def test_wait_timeout_lists_types_and_explains_type_mismatch(self) -> None:
        nodes = [{"AXLabel": "Add Widget", "type": "StaticText", "frame": {"x": 0, "y": 10}}]
        with mock.patch.object(fast_ui, "hierarchy", return_value=nodes), mock.patch.object(fast_ui.time, "sleep"):
            with self.assertRaises(fast_ui.FastUIError) as caught:
                fast_ui.wait_selector("SIM", {"label": "Add Widget", "element_type": "Button"}, 0.01, [])
        self.assertIn("Add Widget (StaticText)", str(caught.exception))
        self.assertIn("exists as StaticText, not Button", str(caught.exception))

    def test_wait_timeout_suggests_close_labels(self) -> None:
        nodes = [{"AXLabel": "Widget Gallery", "type": "StaticText", "frame": {"x": 0, "y": 10}}]
        with mock.patch.object(fast_ui, "hierarchy", return_value=nodes), mock.patch.object(fast_ui.time, "sleep"):
            with self.assertRaises(fast_ui.FastUIError) as caught:
                fast_ui.wait_selector("SIM", {"label": "Widget gallery"}, 0.01, [])
        self.assertIn("closest labels: [Widget Gallery]", str(caught.exception))

    def test_tap_label_falls_back_to_the_only_node_with_that_label(self) -> None:
        node = {"AXLabel": "Add Widget", "type": "StaticText", "frame": {"x": 0, "y": 0, "width": 10, "height": 10}}
        with mock.patch.object(fast_ui, "hierarchy", return_value=[node]), mock.patch.object(fast_ui, "tap_point") as tap:
            result = fast_ui.execute_action({"type": "tap_label", "label": "Add Widget"}, "SIM", Path("/tmp"), 1, [])
        tap.assert_called_once_with("SIM", 5.0, 5.0, 0.15)
        self.assertEqual(result, {"fallback_type": "StaticText"})

    def test_tap_label_does_not_fall_back_when_ambiguous_or_type_explicit(self) -> None:
        a = {"AXLabel": "Add", "type": "StaticText", "frame": {"x": 0, "y": 0, "width": 10, "height": 10}}
        b = {"AXLabel": "Add", "type": "Image", "frame": {"x": 0, "y": 20, "width": 10, "height": 10}}
        with mock.patch.object(fast_ui, "hierarchy", return_value=[a, b]), mock.patch.object(fast_ui.time, "sleep"), \
                mock.patch.object(fast_ui, "tap_point") as tap:
            with self.assertRaises(fast_ui.FastUIError):
                fast_ui.execute_action({"type": "tap_label", "label": "Add", "timeout": 0.01}, "SIM", Path("/tmp"), 1, [])
            with self.assertRaises(fast_ui.FastUIError):
                fast_ui.execute_action({"type": "tap_label", "label": "Add Widget", "element_type": "Button", "timeout": 0.01},
                                       "SIM", Path("/tmp"), 2, [])
        tap.assert_not_called()

    def test_wait_settled_returns_true_when_two_polls_match(self) -> None:
        a = [{"AXLabel": "A", "type": "Button", "frame": {"x": 0, "y": 0, "width": 1, "height": 1}}]
        b = [{"AXLabel": "A", "type": "Button", "frame": {"x": 0, "y": 5, "width": 1, "height": 1}}]
        with mock.patch.object(fast_ui, "hierarchy", side_effect=[a, b, b, b]), mock.patch.object(fast_ui.time, "sleep"):
            self.assertTrue(fast_ui.wait_settled("SIM", timeout=5, stable_for=0))

    def test_wait_settled_gives_up_quietly_on_a_moving_screen(self) -> None:
        frames = itertools.count()
        moving = lambda udid, max_age=0.0: [  # noqa: E731
            {"AXLabel": "A", "type": "Image", "frame": {"x": 0, "y": next(frames), "width": 1, "height": 1}}
        ]
        with mock.patch.object(fast_ui, "hierarchy", side_effect=moving), mock.patch.object(fast_ui.time, "sleep"):
            self.assertFalse(fast_ui.wait_settled("SIM", timeout=0.01))

    def test_settle_flag_on_tap_records_result(self) -> None:
        node = {"AXLabel": "Go", "type": "Button", "frame": {"x": 0, "y": 0, "width": 2, "height": 2}}
        with mock.patch.object(fast_ui, "hierarchy", return_value=[node]), mock.patch.object(fast_ui, "tap_point"), \
                mock.patch.object(fast_ui, "wait_settled", return_value=True) as settled:
            result = fast_ui.execute_action({"type": "tap_label", "label": "Go", "settle": True}, "SIM", Path("/tmp"), 1, [])
        settled.assert_called_once()
        self.assertEqual(result, {"settled": True})

    def test_simulator_lifecycle_actions_call_simctl_and_axe(self) -> None:
        with mock.patch.object(fast_ui, "command") as cmd, mock.patch.object(fast_ui, "axe") as axe:
            fast_ui.execute_action({"type": "type_text", "text": "hello"}, "SIM", Path("/tmp"), 1, [], {}, "com.x")
            fast_ui.execute_action({"type": "launch", "launch_arguments": ["-flag"]}, "SIM", Path("/tmp"), 2, [], {}, "com.x")
            fast_ui.execute_action({"type": "terminate", "app": "com.apple.Preferences"}, "SIM", Path("/tmp"), 3, [], {}, "com.x")
            fast_ui.execute_action({"type": "open_url", "url": "myapp://home"}, "SIM", Path("/tmp"), 4, [], {}, "com.x")
        axe.assert_called_once_with("SIM", "type", "hello")
        self.assertEqual(cmd.call_args_list[0].args[0], ["xcrun", "simctl", "launch", "SIM", "com.x", "-flag"])
        self.assertEqual(cmd.call_args_list[1].args[0], ["xcrun", "simctl", "terminate", "SIM", "com.apple.Preferences"])
        self.assertEqual(cmd.call_args_list[2].args[0], ["xcrun", "simctl", "openurl", "SIM", "myapp://home"])
        with self.assertRaisesRegex(fast_ui.FastUIError, "needs 'app'"):
            fast_ui.execute_action({"type": "launch"}, "SIM", Path("/tmp"), 5, [], {}, "")

    def test_swipe_direction_uses_the_screen_frame(self) -> None:
        nodes = [
            {"AXLabel": "App", "type": "Application", "frame": {"x": 0, "y": 0, "width": 400, "height": 800}},
            {"AXLabel": "Row", "type": "Button", "frame": {"x": 0, "y": 100, "width": 400, "height": 40}},
        ]
        self.assertEqual(fast_ui.swipe_points({"direction": "up"}, nodes, 1), ([200.0, 560.0], [200.0, 240.0]))
        self.assertEqual(fast_ui.swipe_points({"direction": "left"}, nodes, 1), ([320.0, 400.0], [80.0, 400.0]))
        with self.assertRaises(fast_ui.FastUIError):
            fast_ui.swipe_points({"direction": "sideways"}, nodes, 1)

    def test_scroll_to_swipes_until_the_selector_shows(self) -> None:
        screen = {"AXLabel": "", "type": "Application", "frame": {"x": 0, "y": 0, "width": 400, "height": 800}}
        target = {"AXLabel": "Configure Proxy", "type": "Cell", "frame": {"x": 0, "y": 600, "width": 400, "height": 44}}
        with mock.patch.object(fast_ui, "hierarchy", side_effect=[[screen], [screen], [screen, target]]), \
                mock.patch.object(fast_ui, "swipe") as swipe:
            fast_ui.execute_action({"type": "scroll_to", "label": "Configure Proxy"}, "SIM", Path("/tmp"), 1, [])
        self.assertEqual(swipe.call_count, 2)

    def test_scroll_to_fails_after_max_swipes(self) -> None:
        screen = {"AXLabel": "Wi-Fi", "type": "Application", "frame": {"x": 0, "y": 0, "width": 400, "height": 800}}
        with mock.patch.object(fast_ui, "hierarchy", return_value=[screen]), \
                mock.patch.object(fast_ui, "swipe") as swipe:
            with self.assertRaisesRegex(fast_ui.FastUIError, "not found after 2 swipes"):
                fast_ui.execute_action(
                    {"type": "scroll_to", "label": "Nope", "max_swipes": 2}, "SIM", Path("/tmp"), 1, []
                )
        self.assertEqual(swipe.call_count, 2)

    def test_file_link_is_an_absolute_clickable_url(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw) / "evidence run"
            folder.mkdir()
            link = fast_ui.file_link(folder)
        self.assertTrue(link.startswith("file:///"))
        self.assertTrue(link.endswith("/evidence%20run"))

    def test_wait_timeout_error_lists_visible_labels(self) -> None:
        nodes = [{"AXLabel": "Widgets"}, {"AXLabel": "Smart"}]
        with mock.patch.object(fast_ui, "hierarchy", return_value=nodes), \
                mock.patch.object(fast_ui.time, "sleep"):
            with self.assertRaises(fast_ui.FastUIError) as caught:
                fast_ui.wait_selector("SIM", {"label": "Missing"}, 0.01, [])
        self.assertIn("Smart", str(caught.exception))
        self.assertIn("Widgets", str(caught.exception))


class AbsenceTests(unittest.TestCase):
    def test_wait_absent_returns_once_selector_is_gone(self) -> None:
        polls = [[{"AXLabel": "Popup"}], [{"AXLabel": "Popup"}], [{"AXLabel": "Home"}]]
        with mock.patch.object(fast_ui, "hierarchy", side_effect=polls), \
                mock.patch.object(fast_ui.time, "sleep"):
            fast_ui.execute_action({"type": "wait_absent", "label": "Popup", "timeout": 5}, "SIM", Path("."), 1, [])

    def test_wait_absent_fails_when_selector_stays(self) -> None:
        with mock.patch.object(fast_ui, "hierarchy", return_value=[{"AXLabel": "Popup"}]), \
                mock.patch.object(fast_ui.time, "sleep"):
            with self.assertRaises(fast_ui.FastUIError) as caught:
                fast_ui.wait_absent("SIM", {"label": "Popup"}, 0.01, [])
        self.assertIn("still on screen", str(caught.exception))

    def test_assert_absent_fails_the_moment_selector_appears(self) -> None:
        polls = [[{"AXLabel": "Home"}], [{"AXLabel": "Home"}, {"AXLabel": "Popup"}]]
        with mock.patch.object(fast_ui, "hierarchy", side_effect=polls), \
                mock.patch.object(fast_ui.time, "sleep"):
            with self.assertRaises(fast_ui.FastUIError) as caught:
                fast_ui.assert_absent("SIM", {"label": "Popup"}, 5, [])
        self.assertIn("appeared while asserting absence", str(caught.exception))
        self.assertIn("Popup", str(caught.exception))

    def test_assert_absent_passes_when_selector_never_shows(self) -> None:
        with mock.patch.object(fast_ui, "hierarchy", return_value=[{"AXLabel": "Home"}]), \
                mock.patch.object(fast_ui.time, "sleep"):
            fast_ui.assert_absent("SIM", {"label": "Popup"}, 0.01, [])


class MotionTests(unittest.TestCase):
    def test_engine_imports_without_pillow(self) -> None:
        import subprocess
        code = "import sys; sys.modules['PIL'] = None; import fast_ui; print('ok')"
        out = subprocess.run(
            [sys.executable, "-c", code], cwd=str(Path(fast_ui.__file__).parent), capture_output=True, text=True
        )
        self.assertEqual(out.stdout.strip(), "ok", out.stderr[-300:])

    def test_motion_ratio_counts_changed_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            a = Image.new("RGB", (100, 100), (0, 0, 0))
            b = a.copy()
            for x in range(50):
                for y in range(100):
                    b.putpixel((x, y), (255, 255, 255))
            a.save(tmp / "a.png")
            b.save(tmp / "b.png")
            ratio = fast_ui.motion_ratio(tmp / "a.png", tmp / "b.png", [0, 0, 1, 1], 12)
        self.assertAlmostEqual(ratio, 0.5)


class LifecycleTests(unittest.TestCase):
    def test_build_if_needed_boots_simulator_before_building(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            spec = app_spec(tmp, "SIM-A")
            order: list[str] = []
            with mock.patch.object(fast_ui, "ensure_booted", side_effect=lambda udid: order.append("boot")), \
                    mock.patch.object(fast_ui, "command", side_effect=lambda *a, **k: order.append("xcodebuild") or mock.Mock(returncode=1, stdout="", stderr="x")):
                with self.assertRaises(fast_ui.FastUIError):
                    fast_ui.prepare_app(spec, tmp, "SIM-A", reuse_app=False)
        self.assertEqual(order[:2], ["boot", "xcodebuild"])

    def prepare_with_cached_app(self, tmp: Path, spec: dict) -> tuple[bool, list[str]]:
        (tmp / "App.app").mkdir()
        fast_ui.write_build_fingerprint(tmp / "dd" / ".fastui-build-state.json", fast_ui.build_fingerprint(spec, tmp))
        calls: list[str] = []
        with mock.patch.object(fast_ui, "ensure_booted"), mock.patch.object(fast_ui, "verify_app"), \
                mock.patch.object(fast_ui, "command", side_effect=lambda args, **_: calls.append(args[0]) or mock.Mock(returncode=0, stdout="", stderr="")):
            _, built = fast_ui.prepare_app(spec, tmp, "SIM-A", reuse_app=False)
        return built, calls

    def test_unchanged_inputs_reuse_the_cached_app(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            built, calls = self.prepare_with_cached_app(tmp, app_spec(tmp, "SIM-A"))
        self.assertFalse(built)
        self.assertNotIn("xcodebuild", calls)

    def test_missing_build_inputs_never_reuse_the_cached_app(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            spec = app_spec(tmp, "SIM-A")
            del spec["build_inputs"]
            built, calls = self.prepare_with_cached_app(tmp, spec)
        self.assertTrue(built)
        self.assertIn("xcodebuild", calls)

    def device_hub_calls(self, tmp: Path, running: bool) -> list[list[str]]:
        calls: list[list[str]] = []

        def fake(args: list[str], **_: object) -> mock.Mock:
            calls.append(args)
            return mock.Mock(returncode=0 if running or args[0] != "pgrep" else 1, stdout="", stderr="")

        self.addCleanup(setattr, fast_ui, "TAP_SETTLE", 0.0)
        with mock.patch.dict(fast_ui.os.environ, {"DEVELOPER_DIR": str(tmp / "Contents" / "Developer")}), \
                mock.patch.object(fast_ui, "command", side_effect=fake):
            fast_ui.ensure_device_hub("SIM-A")
        return calls

    def test_device_hub_is_opened_when_xcode_ships_it_and_it_is_not_running(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            (tmp / "Contents" / "Applications" / "DeviceHub.app").mkdir(parents=True)
            calls = self.device_hub_calls(tmp, running=False)
        self.assertIn("open", [args[0] for args in calls])

    def test_device_hub_is_left_alone_when_running_or_absent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            self.assertEqual(self.device_hub_calls(tmp, running=False), [])
            self.assertEqual(fast_ui.TAP_SETTLE, 0.0)
            (tmp / "Contents" / "Applications" / "DeviceHub.app").mkdir(parents=True)
            calls = self.device_hub_calls(tmp, running=True)
        self.assertNotIn("open", [args[0] for args in calls])

    def test_taps_linger_under_device_hub(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            (tmp / "Contents" / "Applications" / "DeviceHub.app").mkdir(parents=True)
            self.device_hub_calls(tmp, running=True)
        with mock.patch.object(fast_ui, "axe") as axe:
            fast_ui.tap_point("SIM-A", 10, 20, 0.08)
        self.assertEqual(axe.call_args.args[-1], str(fast_ui.DEVICE_HUB_TAP_SETTLE))

    def test_prebuilt_app_skips_build_and_derived_data(self) -> None:
        with mock.patch.object(fast_ui, "ensure_booted"), mock.patch.object(fast_ui, "build_if_needed") as build:
            app_path, built = fast_ui.prepare_app(
                {"bundle_id": "com.apple.Preferences", "prebuilt": True}, Path("/tmp"), "SIM", False
            )
        build.assert_not_called()
        self.assertIsNone(app_path)
        self.assertFalse(built)

    def test_build_only_flag_parses(self) -> None:
        with mock.patch.object(sys, "argv", ["fast_ui.py", "flow.json", "--build-only"]):
            args = fast_ui.parse_arguments()
        self.assertTrue(args.build_only)


class RecordingTests(unittest.TestCase):
    def test_recorder_starts_simctl_and_finalizes_on_stop(self) -> None:
        with tempfile.TemporaryDirectory() as raw, \
                mock.patch.object(fast_ui.subprocess, "Popen") as popen, \
                mock.patch.object(fast_ui, "stop_stale_recorder"), \
                mock.patch.object(fast_ui.time, "sleep"):
            video = Path(raw) / "run.mp4"
            popen.return_value.wait.return_value = 0
            recorder = fast_ui.Recorder("SIM", video)
            recorder.start()
            video.write_bytes(b"x" * 200_000)
            recorder.stop()
        args = popen.call_args.args[0]
        self.assertEqual(args[:5], ["xcrun", "simctl", "io", "SIM", "recordVideo"])
        popen.return_value.send_signal.assert_called_once()

    def test_publish_video_keeps_only_final_on_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            task_dir = Path(raw) / "task"
            old_run = task_dir / "20260101-000000-x-1"
            old_run.mkdir(parents=True)
            (old_run / "run.mp4").write_bytes(b"old")
            (task_dir / "final.mp4").write_bytes(b"older-final")
            new_run = task_dir / "20260102-000000-x-2"
            new_run.mkdir()
            (new_run / "run.mp4").write_bytes(b"new")
            final = fast_ui.publish_video(task_dir, new_run / "run.mp4", passed=True)
            self.assertEqual(final, task_dir / "final.mp4")
            self.assertEqual(final.read_bytes(), b"new")
            self.assertFalse((old_run / "run.mp4").exists())
            self.assertFalse((new_run / "run.mp4").exists())

    def test_publish_video_names_final_after_session(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            task = Path(raw)
            run = task / "run-1"; run.mkdir()
            (run / "run.mp4").write_bytes(b"x")
            final = fast_ui.publish_video(task, run / "run.mp4", passed=True, session="qa-1")
            self.assertEqual(final, task / "final-qa-1.mp4")
            self.assertTrue(final.exists())

    def test_publish_video_keeps_failure_video_and_previous_final(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            task_dir = Path(raw) / "task"
            run = task_dir / "20260102-000000-x-2"
            run.mkdir(parents=True)
            (task_dir / "final.mp4").write_bytes(b"final")
            (run / "run.mp4").write_bytes(b"fail")
            result = fast_ui.publish_video(task_dir, run / "run.mp4", passed=False)
            self.assertEqual(result, run / "run.mp4")
            self.assertEqual((task_dir / "final.mp4").read_bytes(), b"final")

    def test_record_flag_parses(self) -> None:
        with mock.patch.object(sys, "argv", ["fast_ui.py", "flow.json", "--record"]):
            self.assertTrue(fast_ui.parse_arguments().record)


class PruneTests(unittest.TestCase):
    def test_prune_removes_runs_and_finals_older_than_keep_days(self) -> None:
        import os, time as _time
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            old_run = root / "task-a" / "20260101-000000-SIM-1"
            new_run = root / "task-a" / "20260908-000000-SIM-2"
            old_final = root / "task-b" / "final.mp4"
            for d in (old_run, new_run, old_final.parent):
                d.mkdir(parents=True, exist_ok=True)
            (old_run / "metrics.json").write_text("{}")
            (new_run / "metrics.json").write_text("{}")
            old_final.write_bytes(b"v")
            stale = _time.time() - 4 * 86400
            os.utime(old_run, (stale, stale))
            os.utime(old_final, (stale, stale))
            removed = fast_ui.prune_artifacts(root, keep_days=3)
            self.assertFalse(old_run.exists())
            self.assertFalse(old_final.exists())
            self.assertFalse(old_final.parent.exists())
            self.assertTrue(new_run.exists())
            self.assertEqual(removed, 2)


class ReportTests(unittest.TestCase):
    def test_report_uses_latest_attempt_per_cell_and_counts_attempts(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import fast_ui_report
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            def write(task, stamp, sim, status, extra=None):
                d = root / task / f"{stamp}-{sim}-1"
                d.mkdir(parents=True)
                (d / "metrics.json").write_text(json.dumps({
                    "task": task, "simulator": sim, "session": "s1",
                    "status": status, "total_seconds": 10.0, "step": "02_wait", **(extra or {}),
                }))
            write("a", "20260101-000001", "SIM1XXXX", "fail")
            write("a", "20260101-000002", "SIM1XXXX", "pass", {"video": "/v/final.mp4"})
            write("a", "20260101-000001", "SIM2XXXX", "fail", {"error": "boom"})
            runs = fast_ui_report.load_runs(root, "s1", "")
            cells = fast_ui_report.latest_per_cell(runs)
            text = fast_ui_report.render(cells, {("a", "SIM1XXXX"): 2, ("a", "SIM2XXXX"): 1})
        self.assertIn("PASS 10s ×2", text)
        self.assertIn("FAIL 10s @02_wait", text)
        self.assertIn("boom", text)
        self.assertIn("/v/final.mp4", text)
        self.assertIn("1/2 PASS", text)


class UIVariantTests(unittest.TestCase):
    def test_cli_overrides_setup_and_names_variant(self) -> None:
        setup = {"appearance": "light", "content_size": "large"}
        variant = fast_ui.ui_variant(setup, "dark", "extra-extra-large")
        self.assertEqual(variant, {"appearance": "dark", "content_size": "extra-extra-large"})
        self.assertEqual(fast_ui.variant_name("home", variant), "home@dark@xxl")
        self.assertEqual(fast_ui.variant_name("home", {}), "home")
        self.assertEqual(
            fast_ui.variant_name("home", fast_ui.ui_variant({"content_size": "accessibility-extra-large"}, None, None)),
            "home@ax-xl",
        )

    def test_unknown_setting_fails_closed(self) -> None:
        with self.assertRaises(fast_ui.FastUIError):
            fast_ui.ui_variant({"content_size": "huge"}, None, None)

    def test_apply_records_previous_and_restore_puts_it_back(self) -> None:
        current = {"appearance": "light", "content_size": "extra-extra-large"}
        calls: list[list[str]] = []

        def fake_command(args, check=True, timeout=None):
            calls.append(args)
            key = args[4]
            if len(args) == 5:
                return mock.Mock(stdout=current[key] + "\n", returncode=0)
            current[key] = args[5]
            return mock.Mock(stdout="", returncode=0)

        previous: dict[str, str] = {}
        with mock.patch.object(fast_ui, "command", side_effect=fake_command):
            fast_ui.apply_ui_settings("SIM", {"appearance": "dark", "content_size": "extra-extra-large"}, previous)
            self.assertEqual(current, {"appearance": "dark", "content_size": "extra-extra-large"})
            self.assertEqual(previous, {"appearance": "light"})
            fast_ui.restore_ui_settings("SIM", previous)
        self.assertEqual(current["appearance"], "light")
        self.assertNotIn(["xcrun", "simctl", "ui", "SIM", "content_size", "extra-extra-large"], calls)

    def test_apply_keeps_previous_when_second_setting_fails(self) -> None:
        def fake_command(args, check=True, timeout=None):
            if len(args) == 5:
                return mock.Mock(stdout="light\n" if args[4] == "appearance" else "large\n", returncode=0)
            if args[4] == "content_size":
                raise fast_ui.FastUIError("boom")
            return mock.Mock(stdout="", returncode=0)

        previous: dict[str, str] = {}
        with mock.patch.object(fast_ui, "command", side_effect=fake_command):
            with self.assertRaises(fast_ui.FastUIError):
                fast_ui.apply_ui_settings("SIM", {"appearance": "dark", "content_size": "small"}, previous)
        self.assertEqual(previous, {"appearance": "light", "content_size": "large"})

    def test_variant_flags_parse(self) -> None:
        with mock.patch.object(sys, "argv", ["fast_ui.py", "flow.json", "--appearance", "dark", "--content-size", "accessibility-large"]):
            args = fast_ui.parse_arguments()
        self.assertEqual((args.appearance, args.content_size), ("dark", "accessibility-large"))


class StepLabelTests(unittest.TestCase):
    def test_step_labels_poll_hierarchy_once(self) -> None:
        nodes = [{"AXLabel": "Title", "frame": {"x": 0, "y": 10}}, {"AXLabel": "12:00", "frame": {"x": 0, "y": 0}}]
        with mock.patch.object(fast_ui, "hierarchy", return_value=nodes) as poll:
            entry = fast_ui.step_labels("SIM", "01_tap_label", 3.456, None)
        poll.assert_called_once()
        self.assertEqual(entry, {"step": "01_tap_label", "at": 3.46, "labels": ["Title"]})

    def test_step_labels_reuse_dump_and_survive_axe_failure(self) -> None:
        with mock.patch.object(fast_ui, "hierarchy") as poll:
            entry = fast_ui.step_labels("SIM", "02_dump", 1.0, {"labels": ["A"]})
        poll.assert_not_called()
        self.assertEqual(entry["labels"], ["A"])
        with mock.patch.object(fast_ui, "hierarchy", side_effect=fast_ui.FastUIError("x")):
            self.assertEqual(fast_ui.step_labels("SIM", "03_wait", 1.0, None)["labels"], [])


class AxeErrorTests(unittest.TestCase):
    def test_automation_session_timeout_is_retried_once(self) -> None:
        timed_out = mock.Mock(returncode=1, stdout="", stderr="Error: Timed out creating the simulator remote automation session")
        good = mock.Mock(returncode=0, stdout="[]", stderr="")
        with mock.patch.object(fast_ui, "command", side_effect=[timed_out, good]) as run, \
                mock.patch.object(fast_ui.time, "sleep"):
            self.assertIs(fast_ui.axe("SIM", "tap", "-x", "1", "-y", "1"), good)
        self.assertEqual(run.call_count, 2)
        with mock.patch.object(fast_ui, "command", side_effect=[timed_out, timed_out]), \
                mock.patch.object(fast_ui.time, "sleep"):
            with self.assertRaisesRegex(fast_ui.FastUIError, "automation session"):
                fast_ui.axe("SIM", "tap", "-x", "1", "-y", "1")

    def test_simulatorkit_failure_suggests_developer_dir(self) -> None:
        failed = mock.Mock(returncode=1, stdout="", stderr="dyld: Library not loaded: /Library/Developer/PrivateFrameworks/SimulatorKit.framework")
        with mock.patch.object(fast_ui, "command", return_value=failed):
            with self.assertRaises(fast_ui.FastUIError) as caught:
                fast_ui.axe("SIM", "describe-ui")
        self.assertIn("AXe 1.8.0", str(caught.exception))

    def test_other_failure_has_no_hint(self) -> None:
        failed = mock.Mock(returncode=1, stdout="", stderr="element not found")
        with mock.patch.object(fast_ui, "command", return_value=failed):
            with self.assertRaises(fast_ui.FastUIError) as caught:
                fast_ui.axe("SIM", "tap")
        self.assertNotIn("DEVELOPER_DIR", str(caught.exception))
        self.assertIn("element not found", str(caught.exception))
        with mock.patch.object(fast_ui, "command", return_value=failed):
            self.assertIs(fast_ui.axe("SIM", "tap", check=False), failed)


class ReportVariantTests(unittest.TestCase):
    def test_variants_are_separate_rows_under_their_base_flow(self) -> None:
        import fast_ui_report
        base = {"simulator": "SIM1XXXX", "status": "pass", "total_seconds": 5.0, "_stamp": "1", "_dir": "d"}
        runs = [{**base, "task": task} for task in ("home@dark@xxl", "home-b", "home", "home@dark")]
        cells = fast_ui_report.latest_per_cell(runs)
        text = fast_ui_report.render(cells, {key: 1 for key in cells})
        rows = [line.split(" | ")[0].lstrip("| ") for line in text.splitlines()[2:6]]
        self.assertEqual(rows, ["home", "home@dark", "home@dark@xxl", "home-b"])
        self.assertIn("4/4 PASS", text)


if __name__ == "__main__":
    unittest.main(verbosity=1)


class DeviceLauncherTests(unittest.TestCase):
    def test_save_dumps_writes_nodes_and_keeps_the_report_short(self) -> None:
        import fast_device

        nodes = [{"label": "More Info", "type": "Button", "frame": {"x": 350, "y": 120, "width": 44, "height": 44}}]
        results = [{"step": 2, "name": "wifi", "labels": ["More Info"], "nodes": nodes}, {"step": 3}]
        with tempfile.TemporaryDirectory() as raw:
            saved = fast_device.save_dumps(results, Path(raw))
            self.assertEqual(saved, [str(Path(raw) / "wifi-ui.json")])
            self.assertEqual(json.loads((Path(raw) / "wifi-ui.json").read_text()), nodes)
        self.assertNotIn("nodes", results[0])
        self.assertEqual(results[0]["path"], saved[0])

    def test_resolve_device_matches_partial_name_only_when_unique(self) -> None:
        import fast_device
        devices = [{"udid": "A", "name": "iPhone - Blue - 27", "os": "27.0", "connected": True},
                   {"udid": "B", "name": "iPhone 16 - 26.2", "os": "26.2", "connected": True},
                   {"udid": "C", "name": "iPhone 16 blue 18.6.2", "os": "18.6", "connected": False}]
        with mock.patch.object(fast_device, "physical_devices", return_value=devices):
            self.assertEqual(fast_device.resolve_device("blue - 27")["udid"], "A")
            with self.assertRaisesRegex(fast_device.FastDeviceError, "matches 2 iPhones"):
                fast_device.resolve_device("iPhone 16")

    def test_prepare_flow_keeps_wait_for_idle(self) -> None:
        import fast_device
        prepared = fast_device.prepare_flow({"version": 1, "setup": {"wait_for_idle": False, "preferences": {"a": True}}})
        self.assertFalse(prepared["setup"]["wait_for_idle"])

    def test_do_passes_no_idle_wait_into_the_request(self) -> None:
        import fast_device
        reply = {"status": "pass", "results": [], "labels": []}
        with mock.patch.object(fast_device, "resolve_device", return_value={"udid": "U", "name": "X"}), \
                mock.patch.object(fast_device, "start_server"), \
                mock.patch.object(fast_device, "request", return_value=dict(reply)) as request, \
                tempfile.TemporaryDirectory() as raw:
            fast_device.run_command(["do", '[{"type":"wait","label":"A"}]', "--no-idle-wait", "--out", raw])
            fast_device.run_command(["do", '{"type":"wait","label":"A"}', "--out", raw])
        self.assertIs(request.call_args_list[0].args[1]["wait_for_idle"], False)
        self.assertNotIn("wait_for_idle", request.call_args_list[1].args[1])

    def test_build_runner_uses_committed_xcodeproj_without_xcodegen(self) -> None:
        import fast_device
        calls: list[str] = []

        def fake_run(args, **kwargs):
            calls.append(args[0])
            if args[0] == "xcodebuild":
                products = Path(kwargs["cwd"]) / "dd/Build/Products"
                products.mkdir(parents=True)
                (products / "FastDevice_iphoneos.xctestrun").write_text("")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as raw:
            src = Path(raw) / "src"
            (src / "UITests").mkdir(parents=True)
            (src / "project.yml").write_text("name: x\n")
            (src / "FastDeviceRunner.xcodeproj").mkdir()
            (src / "FastDeviceRunner.xcodeproj" / "project.pbxproj").write_text("v1")
            cache = Path(raw) / "cache"
            with mock.patch.object(fast_device, "RUNNER_SOURCE", src), mock.patch.object(fast_device, "CACHE_ROOT", cache), \
                    mock.patch.object(fast_device.shutil, "which", return_value=None), \
                    mock.patch.object(fast_device, "run", side_effect=fake_run), mock.patch.object(fast_device, "sign_runner"):
                before = fast_device.runner_fingerprint("/Xcode", {"uuid": "u"})
                xctestrun = fast_device.build_runner("/Xcode", {"uuid": "u"}, False)
                (src / "FastDeviceRunner.xcodeproj" / "project.pbxproj").write_text("v2")
                after = fast_device.runner_fingerprint("/Xcode", {"uuid": "u"})
            work = cache / xctestrun.relative_to(cache).parts[0]
            self.assertTrue((work / "FastDeviceRunner.xcodeproj" / "project.pbxproj").is_file())
        self.assertNotIn("xcodegen", calls)
        self.assertEqual(calls, ["xcodebuild"])
        self.assertNotEqual(before, after)
