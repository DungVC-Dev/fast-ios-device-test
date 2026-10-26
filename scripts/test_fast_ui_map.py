#!/usr/bin/env python3

"""Screen map unit tests: python3 scripts/test_fast_ui_map.py"""

from __future__ import annotations

import contextlib
import io
import json
import multiprocessing
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fast_ui_map  # noqa: E402


def ax(label: str, kind: str, x: float = 10, y: float = 100, width: float = 100, height: float = 40, uid: str = "") -> dict:
    node = {"AXLabel": label, "type": kind, "frame": {"x": x, "y": y, "width": width, "height": height}}
    if uid:
        node["AXUniqueId"] = uid
    return node


def nodes(*labels: str, kind: str = "Button") -> list[dict]:
    return [{"label": label, "type": kind} for label in labels]


class NodeFilterTests(unittest.TestCase):
    def test_normalize_drops_noise_and_decoration(self) -> None:
        raw = [
            {"label": "12:41", "type": "StaticText"},
            {"label": "Vertical scroll bar, 2 pages", "type": "Other"},
            {"label": "q", "type": "Other"},
            {"type": "Image"},
            {"label": "General", "type": "Cell", "id": ""},
            {"type": "Other", "id": "close"},
        ]
        self.assertEqual(
            fast_ui_map.normalize_nodes(raw),
            [{"label": "General", "type": "Cell"}, {"type": "Other", "id": "close"}],
        )

    def test_long_static_text_is_dropped(self) -> None:
        self.assertEqual(fast_ui_map.normalize_nodes([{"label": "x" * 41, "type": "StaticText"}]), [])

    def test_long_interactive_label_becomes_label_contains(self) -> None:
        label = "Reply to the message about tomorrow's meeting at the office"
        self.assertEqual(
            fast_ui_map.normalize_nodes([{"label": label, "type": "Button"}]),
            [{"label_contains": label[:40], "type": "Button"}],
        )

    def test_label_contains_from_the_runner_is_kept(self) -> None:
        self.assertEqual(fast_ui_map.normalize_nodes([{"label_contains": "Reply to the message about tomorrow's m",
                                                       "type": "Button", "id": ""}]),
                         [{"label_contains": "Reply to the message about tomorrow's m", "type": "Button"}])

    def test_nodes_are_capped_interactive_first(self) -> None:
        raw = nodes(*(f"Text {index}" for index in range(200)), kind="StaticText") + nodes(*(f"Go {index}" for index in range(10)))
        kept = fast_ui_map.normalize_nodes(raw)
        self.assertEqual(len(kept), 150)
        self.assertEqual([node["label"] for node in kept[:10]], [f"Go {index}" for index in range(10)])

    def test_simulator_screen_keeps_on_screen_nodes_and_heading_title(self) -> None:
        raw = [
            ax("Settings", "Application", 0, 0, 400, 800),
            ax("General", "Heading", 150, 40, 100, 20),
            ax("About", "Heading", 16, 300, 100, 20),
            ax("Off", "Button", 500, 300),
            ax("About", "Button", 10, 340),
        ]
        app_label, title, kept = fast_ui_map.simulator_screen(raw)
        self.assertEqual((app_label, title), ("Settings", "General"))
        self.assertIn({"label": "About", "type": "Button", "id": ""}, kept)
        self.assertNotIn("Off", [node["label"] for node in kept])

    def test_tokens_ignore_types_and_fall_back_to_text(self) -> None:
        self.assertEqual(fast_ui_map.tokens([{"label": "Go", "type": "Button"}, {"id": "x", "type": "Group"}]), {"Go", "id:x"})
        self.assertEqual(fast_ui_map.tokens(nodes("Hello", "World", kind="StaticText")), {"Hello", "World"})
        self.assertEqual(fast_ui_map.tokens([]), set())


class MatchTests(unittest.TestCase):
    def screen(self, title: str, node_list: list[dict]) -> dict:
        stored = [{key: value for key, value in node.items() if key != "type"} | {"types": {"simulator": node["type"]}}
                  for node in node_list]
        return {"title": title, "nodes": stored}

    def test_match_with_title_needs_same_title(self) -> None:
        screens = {"s1": self.screen("General", nodes("A", "B", "C"))}
        self.assertEqual(fast_ui_map.match(screens, "General", nodes("A", "B", "X", "Y")), "s1")
        self.assertIsNone(fast_ui_map.match(screens, "About", nodes("A", "B", "C")))

    def test_match_by_ids_only_on_data_screens(self) -> None:
        old = [{"id": key, "type": "Button"} for key in ("compose", "search", "filter", "menu")] + nodes("Ann", "Bob")
        new = [{"id": key, "type": "Button"} for key in ("compose", "search", "filter", "edit")] + nodes("Cid", "Dee")
        self.assertEqual(fast_ui_map.match({"s1": self.screen("", old)}, "", new), "s1")

    def test_match_without_title_needs_0_6(self) -> None:
        screens = {"s1": self.screen("", nodes("A", "B", "C", "D", "E", "F", "G"))}
        self.assertIsNone(fast_ui_map.match(screens, "", nodes("A", "B", "C", "D", "X", "Y")))
        self.assertEqual(fast_ui_map.match(screens, "", nodes("A", "B", "C", "D", "E", "F", "X")), "s1")

    def test_match_crosses_engine_types(self) -> None:
        screens = {"s1": self.screen("Player", nodes("Lyrics", "Queue"))}
        self.assertEqual(fast_ui_map.match(screens, "Player", nodes("Lyrics", "Queue", kind="RadioButton")), "s1")


class GestureTests(unittest.TestCase):
    def test_kept_gesture_never_keeps_text(self) -> None:
        self.assertEqual(fast_ui_map.kept_gesture({"type": "type_text", "text": "secret"}), {"type": "type_text"})
        self.assertEqual(fast_ui_map.kept_gesture({"type": "press_button", "button": "siri", "text": "call mum"}),
                         {"type": "press_button", "button": "siri"})
        nearest = {"type": "tap_nearest", "target": {"label": "More Info"}, "anchor": {"label": "Office"}, "timeout": 3}
        self.assertEqual(fast_ui_map.kept_gesture(nearest), {k: v for k, v in nearest.items() if k != "timeout"})
        self.assertEqual(fast_ui_map.kept_gesture({"type": "launch", "launch_arguments": ["-token", "x"]}), {"type": "launch"})

    def test_kept_gesture_keeps_the_new_gestures_parameters(self) -> None:
        for action in ({"type": "edge_swipe", "edge": "top", "at": 0.9}, {"type": "pinch", "scale": 2.0, "id": "map"},
                       {"type": "rotate", "radians": 1.2}, {"type": "orientation", "value": "landscape_left"},
                       {"type": "press_key", "key": "delete", "count": 3}, {"type": "press_button", "button": "home"},
                       {"type": "set_picker", "value": "7", "index": 1}, {"type": "drag", "from": [1, 2], "to": [3, 4], "hold": 1},
                       {"type": "key_combo", "key": "a", "modifiers": ["command"]}, {"type": "two_finger_tap", "taps": 2}):
            with self.subTest(action=action["type"]):
                self.assertEqual(fast_ui_map.kept_gesture(action), action)

    def test_kept_gesture_keeps_what_makes_a_path_pasteable(self) -> None:
        link = {"type": "open_url", "url": "myapp://settings"}
        drag = {"type": "swipe", "from": [200, 600], "to": [200, 200], "duration": 0.3}
        self.assertEqual(fast_ui_map.kept_gesture(link), link)
        self.assertEqual(fast_ui_map.kept_gesture(drag), {"type": "swipe", "from": [200, 600], "to": [200, 200]})


APP = "com.apple.Preferences"
NOW = datetime(2026, 10, 26, 7, 0, tzinfo=timezone.utc)


def screen(title: str, *labels: str, app: str = APP) -> dict:
    return {"screen": {"app": app, "title": title, "nodes": nodes(*labels)}}


def gesture(kind: str, fresh: bool = True, **keys: object) -> dict:
    entry: dict = {"gesture": {"type": kind, **keys}}
    if not fresh:
        entry["from"] = None
    return entry


SETTINGS = screen("Settings", "General", "Privacy", "Wi-Fi")
GENERAL = screen("General", "About", "Software Update", "Storage")
TAP_GENERAL = gesture("tap_label", label="General")


def merged(*trail: dict, maps: dict | None = None) -> dict:
    maps = maps if maps is not None else {APP: fast_ui_map.new_map(APP)}
    fast_ui_map.merge_trail(maps, list(trail), "simulator", NOW)
    return maps[APP]


def record_in_child(directory: str, title: str) -> None:
    with mock.patch.dict(os.environ, {"FAST_UI_MAP_DIR": directory}):
        fast_ui_map.record([screen(title, f"{title} A", f"{title} B")], "simulator", NOW)


class MergeTests(unittest.TestCase):
    def test_merge_builds_screens_edges_and_entry(self) -> None:
        result = merged(gesture("launch"), SETTINGS, TAP_GENERAL, GENERAL)
        self.assertEqual(sorted(result["screens"]), ["s1", "s2"])
        self.assertTrue(result["screens"]["s1"]["entry"])
        self.assertFalse(result["screens"]["s2"].get("entry", False))
        self.assertEqual(result["screens"]["s2"]["nodes"][0], {"label": "About", "types": {"simulator": "Button"}})
        self.assertEqual(len(result["edges"]), 1)
        edge = result["edges"][0]
        self.assertEqual((edge["from"], edge["to"], edge["gesture"], edge["count"]),
                         ("s1", "s2", {"type": "tap_label", "label": "General"}, 1))

    def test_same_edge_twice_counts_and_later_landing_replaces_to(self) -> None:
        maps = {APP: fast_ui_map.new_map(APP)}
        merged(SETTINGS, TAP_GENERAL, GENERAL, maps=maps)
        merged(SETTINGS, TAP_GENERAL, GENERAL, maps=maps)
        result = merged(SETTINGS, TAP_GENERAL, screen("Sign In", "Email", "Password", "Continue"), maps=maps)
        self.assertEqual(len(result["edges"]), 1)
        self.assertEqual((result["edges"][0]["to"], result["edges"][0]["count"]), ("s3", 3))
        self.assertEqual(result["screens"]["s1"]["seen"], 3)

    def test_device_gestures_are_stored_in_one_key_order(self) -> None:
        device_tap = {"gesture": {"label": "General", "timeout": 6, "type": "tap_label"}}
        result = merged(SETTINGS, device_tap, GENERAL)
        self.assertEqual(list(result["edges"][0]["gesture"].items()), [("type", "tap_label"), ("label", "General")])

    def test_long_titles_are_cut_like_labels(self) -> None:
        title = "Dinner plans with the whole family next Saturday evening at home"
        maps = {APP: fast_ui_map.new_map(APP)}
        merged(screen(title, "Reply", "Call"), maps=maps)
        result = merged(screen(title, "Reply", "Video"), maps=maps)
        self.assertEqual(list(result["screens"]), ["s1"])
        self.assertEqual(result["screens"]["s1"]["title"], title[:40])

    def test_merging_into_a_full_map_stays_fast(self) -> None:
        import time as clock
        big = fast_ui_map.new_map(APP)
        for index in range(400):
            big["screens"][f"s{index}"] = {
                "title": "", "first_seen": "2026-10-26T07:00:00Z", "last_seen": "2026-10-26T07:00:00Z",
                "seen": 1, "nodes": [{"label": f"Item {index}-{n}", "types": {"simulator": "Button"}} for n in range(150)]}
            big["edges"].append({"from": f"s{index}", "gesture": {"type": "tap_label", "label": f"Item {index}-0"},
                                 "to": f"s{(index + 1) % 400}", "last_seen": "2026-10-26T07:00:00Z", "count": 1})
        big["next_key"] = 400
        trail = []
        for index in range(25):
            trail += [screen("", *(f"New {index}-{n}" for n in range(150))),
                      gesture("tap_label", label=f"New {index}-0")]
        started = clock.perf_counter()
        fast_ui_map.merge_trail({APP: big}, trail, "simulator", NOW)
        self.assertLess(clock.perf_counter() - started, 0.1)
        self.assertEqual(len(big["screens"]), 425)

    def test_gesture_without_fresh_read_makes_no_edge(self) -> None:
        result = merged(SETTINGS, gesture("tap_point", fresh=False, x=10, y=20), GENERAL)
        self.assertEqual(len(result["screens"]), 2)
        self.assertEqual(result["edges"], [])

    def test_scroll_merges_into_origin(self) -> None:
        result = merged(screen("Settings", *"ABCDEF"), gesture("swipe", direction="up"), screen("Settings", *"GHIJKL"))
        self.assertEqual(list(result["screens"]), ["s1"])
        self.assertEqual(len(result["screens"]["s1"]["nodes"]), 12)
        self.assertEqual(result["edges"], [])

    def test_break_and_screen_without_tokens_cut_edges(self) -> None:
        self.assertEqual(merged(SETTINGS, TAP_GENERAL, {"break": True}, GENERAL)["edges"], [])
        empty = {"screen": {"app": APP, "title": "", "nodes": []}}
        self.assertEqual(merged(SETTINGS, TAP_GENERAL, empty, gesture("tap_label", label="About"), GENERAL)["edges"], [])

    def test_other_app_screen_is_not_written_and_cuts_edge(self) -> None:
        maps = {APP: fast_ui_map.new_map(APP)}
        home = screen("", "Safari", "Mail", app="com.apple.springboard")
        merged(SETTINGS, TAP_GENERAL, home, gesture("tap_label", label="Settings"), GENERAL, maps=maps)
        self.assertEqual(list(maps), [APP])
        self.assertEqual(maps[APP]["edges"], [])

    def test_prune_drops_old_screens_and_their_edges(self) -> None:
        result = merged(SETTINGS, TAP_GENERAL, GENERAL)
        result["screens"]["s1"]["last_seen"] = fast_ui_map.timestamp(NOW - timedelta(days=61))
        fast_ui_map.prune(result, NOW)
        self.assertEqual(list(result["screens"]), ["s2"])
        self.assertEqual(result["edges"], [])

    def test_prune_keeps_400_most_recent(self) -> None:
        result = fast_ui_map.new_map(APP)
        for index in range(405):
            result["screens"][f"s{index}"] = {"title": "", "nodes": [], "seen": 1,
                                              "last_seen": fast_ui_map.timestamp(NOW - timedelta(minutes=index))}
        fast_ui_map.prune(result, NOW)
        self.assertEqual(len(result["screens"]), 400)
        self.assertNotIn("s404", result["screens"])


class MapDirTestCase(unittest.TestCase):
    """Each test gets its own empty map folder through FAST_UI_MAP_DIR."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {"FAST_UI_MAP_DIR": self.directory.name}, clear=False)
        patcher.start()
        os.environ.pop("FAST_UI_MAP", None)
        self.addCleanup(patcher.stop)
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / f"{APP}.json"


class RecordTests(MapDirTestCase):
    def test_record_writes_atomically_under_lock(self) -> None:
        fast_ui_map.record([SETTINGS, TAP_GENERAL, GENERAL], "device", NOW)
        stored = json.loads(self.path.read_text())
        self.assertEqual((stored["app"], len(stored["screens"]), len(stored["edges"])), (APP, 2, 1))
        self.assertEqual(stored["screens"]["s1"]["nodes"][0]["types"], {"device": "Button"})
        self.assertTrue(self.path.with_name(f"{APP}.json.lock").exists())
        self.assertEqual(sorted(p.name for p in Path(self.directory.name).iterdir()), [f"{APP}.json", f"{APP}.json.lock"])

    def test_two_records_on_one_app_keep_both_screens(self) -> None:
        context = multiprocessing.get_context("fork")
        children = [context.Process(target=record_in_child, args=(self.directory.name, title)) for title in ("One", "Two")]
        for child in children:
            child.start()
        for child in children:
            child.join(30)
        titles = {item["title"] for item in json.loads(self.path.read_text())["screens"].values()}
        self.assertEqual(titles, {"One", "Two"})

    def test_corrupt_map_is_renamed_bad_and_restarted(self) -> None:
        self.path.write_text("{not json")
        fast_ui_map.record([SETTINGS], "simulator", NOW)
        self.assertEqual(self.path.with_name(f"{APP}.json.bad").read_text(), "{not json")
        self.assertEqual(len(json.loads(self.path.read_text())["screens"]), 1)

    def test_record_is_off_with_fast_ui_map_0(self) -> None:
        with mock.patch.dict(os.environ, {"FAST_UI_MAP": "0"}):
            fast_ui_map.record([SETTINGS], "simulator", NOW)
        self.assertFalse(self.path.exists())


class CommandTests(MapDirTestCase):
    ABOUT = screen("About", "Name", "Model Name")
    BACK = gesture("tap_label", label="Settings")
    TAP_ABOUT = gesture("tap_label", label="About")

    def run_main(self, *argv: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = fast_ui_map.main(list(argv))
        return code, output.getvalue()

    def walk(self) -> None:
        trail = [gesture("launch"), SETTINGS, TAP_GENERAL, GENERAL, self.BACK, SETTINGS, TAP_GENERAL, GENERAL,
                 self.TAP_ABOUT, self.ABOUT]
        fast_ui_map.record(trail, "simulator", NOW)

    def test_cli_lists_maps(self) -> None:
        self.assertEqual(self.run_main(), (0, f"MAP none dir={Path(self.directory.name).resolve().as_uri()}\n"))
        self.walk()
        code, output = self.run_main()
        self.assertEqual(code, 0)
        self.assertRegex(output, rf"^MAP app={APP} screens=3 size=1K updated=2026-10-26 path=file://.*{APP}.json\n$")

    def test_cli_index_shows_paths_from_entry(self) -> None:
        self.walk()
        unlabeled = {"screen": {"app": APP, "title": "Orphan", "nodes": [{"label": "Lonely", "type": "Button"},
                                                                       {"label": "", "type": "Button", "id": "info"}]}}
        fast_ui_map.record([unlabeled], "simulator", NOW)
        code, output = self.run_main(APP)
        lines = output.splitlines()
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith(f"MAP app={APP} screens=4 edges=3 updated=2026-10-26 path=file://"))
        self.assertIn('s1 "Settings" seen=2 last=2026-10-26 labels=["General","Privacy","Wi-Fi"] path=entry', lines)
        self.assertIn('s3 "About" seen=1 last=2026-10-26 labels=["Name","Model Name"] '
                      'path=[{"type":"tap_label","label":"General"},{"type":"tap_label","label":"About"}]', lines)
        self.assertIn('s4 "Orphan" seen=1 last=2026-10-26 labels=["Lonely"] path=unknown', lines)

    def test_cli_find_prints_selector_types_and_path(self) -> None:
        self.walk()
        fast_ui_map.record([GENERAL], "device", NOW)
        code, output = self.run_main(APP, "--find", "abou")
        self.assertEqual(code, 0)
        self.assertEqual(output, 's2 "General" select={"label":"About"} types=simulator:Button,device:Button '
                                 'path=[{"type":"tap_label","label":"General"}]\n')
        self.assertEqual(self.run_main(APP, "--find", "nothing"), (0, "FIND none text=nothing\n"))

    def test_cli_screen_lists_nodes(self) -> None:
        self.walk()
        code, output = self.run_main(APP, "--screen", "s2")
        self.assertEqual(code, 0)
        self.assertEqual(output.splitlines()[1:], ["label=About types=simulator:Button",
                                                   "label=Software Update types=simulator:Button",
                                                   "label=Storage types=simulator:Button"])
        self.assertEqual(self.run_main(APP, "--screen", "s9")[0], 1)

    def test_cli_clear_one_and_all(self) -> None:
        self.walk()
        fast_ui_map.record([screen("Home", "Safari", app="com.apple.springboard")], "device", NOW)
        self.path.with_name(f"{APP}.json.bad").write_text("{old")
        self.assertEqual(self.run_main("clear", APP), (0, f"CLEARED app={APP}\n"))
        self.assertFalse(self.path.exists())
        self.assertFalse(self.path.with_name(f"{APP}.json.bad").exists())
        self.assertEqual(self.run_main("clear", "--all"), (0, "CLEARED apps=1\n"))
        # A run may hold a lock while clear runs; deleting it would let a second writer in.
        self.assertEqual(sorted(path.name for path in Path(self.directory.name).iterdir()),
                         [f"{APP}.json.lock", "com.apple.springboard.json.lock"])

    def test_cli_reports_a_bad_map_without_touching_it(self) -> None:
        self.path.write_text("{not json")
        code, output = self.run_main()
        self.assertEqual((code, output), (0, f"MAP bad app={APP} path={self.path.resolve().as_uri()}\n"))
        self.assertEqual(self.run_main(APP), (1, f"MAP bad app={APP} path={self.path.resolve().as_uri()}\n"))
        self.assertEqual(self.path.read_text(), "{not json")
        self.assertFalse(self.path.with_name(f"{APP}.json.bad").exists())

    def test_a_map_missing_its_keys_is_bad(self) -> None:
        self.path.write_text('{"screens": {}, "edges": []}')
        self.assertEqual(self.run_main()[1], f"MAP bad app={APP} path={self.path.resolve().as_uri()}\n")
        fast_ui_map.record([SETTINGS], "simulator", NOW)
        self.assertTrue(self.path.with_name(f"{APP}.json.bad").exists())
        self.assertEqual(len(json.loads(self.path.read_text())["screens"]), 1)

    def test_cli_path_to_prints_a_guarded_request(self) -> None:
        self.walk()
        code, output = self.run_main(APP, "--path-to", "about")
        header, request = output.splitlines()
        self.assertEqual(code, 0)
        self.assertEqual(header, 'PATH app=com.apple.Preferences to=s3 "About" from=s1 "Settings" steps=2')
        # Each expect names something the screen before does not show: Settings has a General row,
        # so "General" would match before the tap; General has an About row.
        self.assertEqual(json.loads(request), [
            {"type": "tap_label", "label": "General", "expect": {"label": "About"}},
            {"type": "tap_label", "label": "About", "expect": {"label": "Name"}},
        ])

    def test_expect_skips_screen_chrome_and_prefers_labels(self) -> None:
        before = {"title": "Settings", "nodes": [{"label": "General", "types": {"device": "Cell"}}]}
        target = {"title": "General", "nodes": [{"id": "BackButton", "label": "Settings", "types": {"device": "Button"}},
                                                {"label": "chevron", "types": {"device": "Button"}},
                                                {"id": "ABOUT_ID", "label": "About", "types": {"device": "Cell"}}]}
        # Every pushed screen has a back button; a row only this screen shows is the proof.
        self.assertEqual(fast_ui_map.expect_for(target, before), {"label": "About"})

    def test_expect_prefers_text_without_numbers(self) -> None:
        before = {"title": "General", "nodes": [{"label": "About", "types": {"simulator": "Button"}}]}
        target = {"title": "General", "nodes": [{"label": "iOS Version, 26.5", "types": {"simulator": "Button"}},
                                                {"label": "Legal & Regulatory", "types": {"simulator": "Button"}}]}
        # A version, a count or a date differs on the next iPhone; a fixed caption does not.
        self.assertEqual(fast_ui_map.expect_for(target, before), {"label": "Legal & Regulatory"})

    def test_cli_path_to_a_node_ends_on_its_screen_and_names_it(self) -> None:
        self.walk()
        code, output = self.run_main(APP, "--path-to", "storage")
        header, request = output.splitlines()
        self.assertEqual(header, 'PATH app=com.apple.Preferences to=s2 "General" from=s1 "Settings" steps=1 select={"label":"Storage"}')
        self.assertEqual(json.loads(request), [{"type": "tap_label", "label": "General", "expect": {"label": "About"}}])

    def test_cli_path_to_an_entry_unknown_or_unreachable_screen(self) -> None:
        self.walk()
        fast_ui_map.record([screen("Orphan", "Lonely")], "simulator", NOW)
        self.assertEqual(self.run_main(APP, "--path-to", "Settings")[1].splitlines()[0],
                         'PATH app=com.apple.Preferences to=s1 "Settings" from=s1 "Settings" steps=0')
        self.assertEqual(self.run_main(APP, "--path-to", "lonely"),
                         (0, 'PATH none text=lonely seen=s4 "Orphan" (no recorded way there)\n'))
        self.assertEqual(self.run_main(APP, "--path-to", "nowhere"), (0, "PATH none text=nowhere\n"))

    def test_cli_missing_map_is_not_an_error(self) -> None:
        self.assertEqual(self.run_main("com.example.none"), (0, "MAP none app=com.example.none\n"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
