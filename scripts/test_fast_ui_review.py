#!/usr/bin/env python3

"""Review-tool unit tests: python3 scripts/test_fast_ui_review.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fast_ui_review as review  # noqa: E402

from PIL import Image  # noqa: E402


def frame(path: Path, color: tuple[int, int, int]) -> Path:
    Image.new("RGB", (40, 80), color).save(path)
    return path


class FrameSelectionTests(unittest.TestCase):
    def test_static_interval_frames_are_dropped_but_step_frames_kept(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            frames = [
                (frame(tmp / "0.0.png", (255, 255, 255)), ""),
                (frame(tmp / "1.0.png", (255, 255, 255)), ""),
                (frame(tmp / "2.0.png", (255, 255, 255)), "02_tap"),
                (frame(tmp / "3.0.png", (0, 0, 0)), ""),
                (frame(tmp / "4.0.png", (0, 0, 0)), ""),
            ]
            kept = [path.stem for path, _ in review.select_frames(frames, 0.01)]
        self.assertEqual(kept, ["0.0", "2.0", "3.0"])

    def test_zero_threshold_keeps_everything(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            frames = [(frame(tmp / f"{i}.0.png", (255, 255, 255)), "") for i in range(3)]
            self.assertEqual(len(review.select_frames(frames, 0)), 3)

    def test_change_ratio_is_share_of_changed_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            base = frame(tmp / "a.png", (255, 255, 255))
            other = Image.new("RGB", (40, 80), (255, 255, 255))
            other.paste((0, 0, 0), (0, 0, 40, 20))
            other.save(tmp / "b.png")
            self.assertAlmostEqual(review.change_ratio(base, tmp / "b.png"), 0.25)


class SheetTests(unittest.TestCase):
    def test_sheet_has_header_and_reports_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            frames = [(frame(tmp / f"{i}.0.png", (200, 200, 200)), "step") for i in range(4)]
            tokens = review.contact_sheet(frames, 3, tmp / "sheet.png", "case-a · PASS · expect: popup shows")
            sheet = Image.open(tmp / "sheet.png")
        self.assertEqual(sheet.size, (40 * 3, review.HEADER_HEIGHT + (80 + review.LABEL_HEIGHT) * 2))
        self.assertEqual(sheet.getpixel((2, 2)), (24, 28, 36))
        self.assertEqual(tokens, -(-sheet.width * sheet.height // review.PIXELS_PER_TOKEN))

    def test_frame_times_marks_step_ends_and_grid(self) -> None:
        run = {"steps_seconds": {"prepare": 0.5, "fresh_install": 1.5, "01_wait": 2.0, "02_tap": 1.0}, "total_seconds": 5.0}
        self.assertEqual(review.frame_times(run, 1.0), [(0.0, ""), (1.0, ""), (2.0, "01_wait"), (3.0, "02_tap")])

    def test_frame_times_prefer_recorded_step_times(self) -> None:
        run = {
            "steps_seconds": {"prepare": 0.5, "01_wait": 2.0}, "total_seconds": 3.0,
            "step_labels": [{"step": "01_wait", "at": 2.37, "labels": []}],
        }
        self.assertEqual(review.frame_times(run, 1.0), [(0.0, ""), (1.0, ""), (2.0, ""), (2.4, "01_wait")])

    def test_label_lines_are_compact_and_truncated(self) -> None:
        lines = review.label_lines([
            {"step": "01_tap", "at": 3.21, "labels": ["Title", "Done"]},
            {"step": "02_wait", "at": 4.0, "labels": []},
            {"step": "03_dump", "at": 5.0, "labels": ["x" * 300]},
        ], width=60)
        self.assertEqual(lines[0], "01_tap @3.2s: Title · Done")
        self.assertEqual(lines[1], "02_wait @4.0s: (no labels)")
        self.assertEqual(len(lines[2]), 60)
        self.assertTrue(lines[2].endswith("…"))


class NotesTests(unittest.TestCase):
    def test_merge_keeps_existing_verdicts_and_adds_new_cases(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "notes.json"
            path.write_text(json.dumps({"a": {"expect": "old", "verdict": "OK", "note": "seen"}}))
            merged = review.merge_notes(path, {
                "a": {"expect": "new", "sheet": "a.png"},
                "b": {"expect": "popup", "sheet": "b.png"},
            })
            reloaded = json.loads(path.read_text())
        self.assertEqual(merged["a"]["verdict"], "OK")
        self.assertEqual(merged["a"]["note"], "seen")
        self.assertEqual(merged["a"]["expect"], "new")
        self.assertIsNone(reloaded["b"]["verdict"])
        self.assertEqual(reloaded["b"]["note"], "")

    def test_merge_replaces_step_labels_but_keeps_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "notes.json"
            path.write_text(json.dumps({"a": {"step_labels": [{"step": "old"}], "verdict": "OK", "note": "n"}}))
            merged = review.merge_notes(path, {"a": {"step_labels": [{"step": "01_tap", "at": 1.0, "labels": ["T"]}]}})
        self.assertEqual(merged["a"]["verdict"], "OK")
        self.assertEqual(merged["a"]["step_labels"][0]["labels"], ["T"])


class HelperTests(unittest.TestCase):
    def test_helper_is_compiled_once_and_reused(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(review.subprocess, "run") as run:
            run.return_value.returncode = 0
            cache = Path(raw)
            first = review.helper_command("print(1)", cache)
            Path(first[0]).write_text("")  # what a successful swiftc leaves behind
            second = review.helper_command("print(1)", cache)
        self.assertEqual(first, second)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][0], "swiftc")

    def test_helper_falls_back_to_the_interpreter_when_swiftc_fails(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(review.subprocess, "run") as run:
            run.return_value.returncode = 1
            command = review.helper_command("print(1)", Path(raw))
        self.assertEqual(command[0], "swift")
        self.assertTrue(command[1].endswith(".swift"))


class CombinedTests(unittest.TestCase):
    def test_timeline_places_title_mid_and_clip_end(self) -> None:
        items = [{"path": "/x/a.mp4", "title": "a"}, {"path": "/x/b.mp4", "title": "b"}]
        timeline = review.combined_timeline(items, [10.0, 4.0], 2.5)
        self.assertEqual(timeline[0]["title_at"], 1.25)
        self.assertEqual(timeline[0]["clip_start"], 2.5)
        self.assertEqual(timeline[0]["clip_end_at"], 11.7)
        self.assertEqual(timeline[1]["title_at"], 13.75)
        self.assertEqual(timeline[1]["clip_end_at"], 18.2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
