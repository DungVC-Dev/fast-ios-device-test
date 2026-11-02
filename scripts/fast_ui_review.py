#!/usr/bin/env python3

"""Turn recorded fastUITest runs into contact sheets the agent can judge against each case's expectation.

Per-case sheets (one per recorded run of the session):

    fast_ui_review.py --root <artifacts-root> --session <name> [--out <dir>] [--interval 1.0]
                      [--change-threshold 0.01] [--columns 6]

Frames are taken at the end of every flow step (from metrics.json `steps_seconds`) plus one
every `--interval` seconds. Interval frames that look the same as the previous kept frame are
dropped (`--change-threshold`, share of changed pixels), so a sheet shows every transition —
a popup appearing, a sheet closing — without a row of identical stills. Step frames are always
kept. The flow's `expect` text (written to metrics.json by the engine) is printed on top of the
sheet so the reviewer compares frames with the stated outcome, not from memory.

The run also writes `<out>/review-notes-<session>.json`, one entry per case with the expectation,
sheet, video, the visible accessibility labels after every step (`step_labels`, recorded by
the engine under --record) and an empty `verdict`/`note` for the reviewer to fill (existing
verdicts survive re-runs). The labels are also printed under each SHEET line, so on-screen copy
is checked from text, not by reading pixels. A case without a verdict is not reviewed.

Combined-video check (a concatenation built from a manifest of `{path, title, subtitle}` items):

    fast_ui_review.py --combined <video.mp4> --manifest <items.json> [--title-seconds 2.5] [--out <dir>]

samples the middle of every title card and the last second of every clip, writes
`combined-titles.png` / `combined-ends.png`, and compares the manifest timeline
(sum of title cards and clip durations) with the file's real duration.

Frame extraction uses AVFoundation through a small Swift helper — no ffmpeg needed.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

# bin/ holds symlinks in a git checkout but copies in the zip, so look beside scripts/ too.
sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parent.parent / "scripts")]
from fast_media import HELPER_CACHE, helper_command  # noqa: E402

SWIFT_HELPER = '''
import AVFoundation
import AppKit
let args = CommandLine.arguments
if args[1] == "duration" {
    for raw in args[2...] {
        let asset = AVURLAsset(url: URL(fileURLWithPath: raw))
        print(CMTimeGetSeconds(asset.duration))
    }
    exit(0)
}
let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
let out = args[2]
let gen = AVAssetImageGenerator(asset: asset)
gen.appliesPreferredTrackTransform = true
gen.requestedTimeToleranceBefore = .zero
gen.requestedTimeToleranceAfter = CMTime(seconds: 0.2, preferredTimescale: 600)
gen.maximumSize = CGSize(width: 402, height: 900)
for raw in args[3...] {
    guard let t = Double(raw) else { continue }
    guard let cg = try? gen.copyCGImage(at: CMTime(seconds: t, preferredTimescale: 600), actualTime: nil) else { continue }
    let rep = NSBitmapImageRep(cgImage: cg)
    try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: "\\(out)/\\(raw).png"))
}
'''

# Claude bills roughly one token per 750 image pixels; the estimate tells the reviewer what a sheet costs.
PIXELS_PER_TOKEN = 750
HEADER_HEIGHT = 96
LABEL_HEIGHT = 26
FONT_CANDIDATES = ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/SFNS.ttf")


def font(size: int) -> ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def load_runs(root: Path, session: str) -> list[dict]:
    runs: dict[str, dict] = {}
    for metrics in root.glob("*/*/metrics.json"):
        data = json.loads(metrics.read_text(encoding="utf-8"))
        if data.get("session") != session or not data.get("video"):
            continue
        # fastDeviceTest runs name their target `udid`; the sheet and notes key on `simulator`.
        data["simulator"] = str(data.get("simulator") or data.get("udid") or "device")
        key = f"{data['task']}|{data['simulator'][:8]}"
        if key not in runs or metrics.parent.name > runs[key]["_dir"]:
            runs[key] = {**data, "_dir": metrics.parent.name}
    return sorted(runs.values(), key=lambda run: run["task"])


def frame_times(run: dict, interval: float) -> list[tuple[float, str]]:
    """(time, label) pairs: one per step end, plus a regular grid so nothing between steps is lost."""
    steps = run.get("steps_seconds", {})
    start = float(steps.get("prepare", 0)) + float(steps.get("fresh_install", 0))
    times: list[tuple[float, str]] = []
    recorded = [entry for entry in run.get("step_labels", []) if "at" in entry]
    if recorded:
        # Step ends measured against the recording itself; summed step durations drift.
        times = [(round(max(float(entry["at"]), 0), 1), entry["step"]) for entry in recorded]
    else:
        clock = start
        for name, seconds in steps.items():
            if name in ("prepare", "fresh_install"):
                continue
            clock += float(seconds)
            times.append((round(max(clock - start, 0), 1), name))
    total = float(run.get("total_seconds", 0)) - start
    grid = 0.0
    while grid < total:
        times.append((round(grid, 1), ""))
        grid += interval
    merged: dict[float, str] = {}
    for time, label in sorted(times):
        merged[time] = merged.get(time) or label
    return sorted(merged.items())


def change_ratio(first: Path, second: Path, pixel_threshold: int = 24) -> float:
    """Share of pixels whose brightness moved by more than `pixel_threshold` between two frames."""
    image_a = Image.open(first).convert("L")
    image_b = Image.open(second).convert("L")
    if image_a.size != image_b.size:
        image_b = image_b.resize(image_a.size)
    mask = ImageChops.difference(image_a, image_b).point(lambda value: 255 if value > pixel_threshold else 0)
    changed = mask.histogram()[255]
    return changed / (image_a.size[0] * image_a.size[1])


def select_frames(frames: list[tuple[Path, str]], threshold: float) -> list[tuple[Path, str]]:
    """Keep every labelled (step-end) frame; keep an interval frame only when the picture changed."""
    if threshold <= 0:
        return frames
    kept: list[tuple[Path, str]] = []
    for frame, label in frames:
        if not kept or label or change_ratio(kept[-1][0], frame) >= threshold:
            kept.append((frame, label))
    return kept


def extract(video: Path, times: list[float], helper: list[str], out: Path) -> list[Path]:
    subprocess.run(
        [*helper, str(video), str(out), *[f"{t:.1f}" for t in times]],
        check=False, capture_output=True, text=True, timeout=600,
    )
    return [out / f"{t:.1f}.png" for t in times if (out / f"{t:.1f}.png").exists()]


def durations(videos: list[Path], helper: list[str]) -> list[float]:
    completed = subprocess.run(
        [*helper, "duration", *[str(video) for video in videos]],
        check=False, capture_output=True, text=True, timeout=600,
    )
    values = [float(line) for line in completed.stdout.split() if line.strip()]
    if len(values) != len(videos):
        raise RuntimeError(f"could not read durations: {completed.stderr.strip()[:300]}")
    return values


def contact_sheet(frames: list[tuple[Path, str]], columns: int, path: Path, header: str = "") -> int:
    """Write the sheet and return its rough Claude token cost."""
    images = [Image.open(frame) for frame, _ in frames]
    width, height = images[0].size
    columns = max(1, min(columns, len(images)))
    rows = (len(images) + columns - 1) // columns
    top = HEADER_HEIGHT if header else 0
    sheet = Image.new("RGB", (width * columns, top + (height + LABEL_HEIGHT) * rows), "white")
    draw = ImageDraw.Draw(sheet)
    if header:
        draw.rectangle((0, 0, sheet.width, top), fill=(24, 28, 36))
        lines = textwrap.wrap(header, width=max(20, sheet.width // 10))[:4]
        for index, line in enumerate(lines):
            draw.text((8, 6 + index * 21), line, fill="white", font=font(17))
    for index, ((frame, label), image) in enumerate(zip(frames, images)):
        x = (index % columns) * width
        y = top + (index // columns) * (height + LABEL_HEIGHT)
        sheet.paste(image, (x, y + LABEL_HEIGHT))
        draw.text((x + 4, y + 3), f"{frame.stem}s {label}".strip(), fill="black", font=font(16))
    sheet.save(path)
    return math.ceil(sheet.width * sheet.height / PIXELS_PER_TOKEN)


def label_lines(step_labels: list[dict], width: int = 160) -> list[str]:
    """One compact line per step: `01_tap @3.2s: Title · Button · …`, truncated to `width`."""
    lines = []
    for entry in step_labels:
        text = " · ".join(entry.get("labels", [])) or "(no labels)"
        line = f"{entry.get('step', '?')} @{float(entry.get('at', 0)):.1f}s: {text}"
        lines.append(line if len(line) <= width else line[: width - 1] + "…")
    return lines


def merge_notes(path: Path, entries: dict[str, dict]) -> dict[str, dict]:
    """Add new cases to the notes file without touching verdicts already written."""
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for key, entry in entries.items():
        previous = existing.get(key, {})
        existing[key] = {
            **entry,
            "verdict": previous.get("verdict"),
            "note": previous.get("note", ""),
        }
    path.write_text(json.dumps(existing, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return existing


def combined_timeline(items: list[dict], clip_seconds: list[float], title_seconds: float) -> list[dict]:
    """Where each title card and clip sits in the concatenated file."""
    clock = 0.0
    timeline = []
    for item, seconds in zip(items, clip_seconds):
        timeline.append({
            "title": item.get("title", Path(item["path"]).stem),
            "title_at": round(clock + title_seconds / 2, 2),
            "clip_start": round(clock + title_seconds, 2),
            "clip_end_at": round(clock + title_seconds + max(seconds - 0.8, 0), 2),
            "seconds": seconds,
        })
        clock += title_seconds + seconds
    return timeline


def review_session(args: argparse.Namespace, helper: list[str], raw: Path) -> int:
    root = args.root.expanduser().resolve()
    out = (args.out or root / f"review-{args.session}").expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    runs = load_runs(root, args.session)
    if not runs:
        print(f"no recorded runs for session {args.session} under {root}", file=sys.stderr)
        return 1
    entries: dict[str, dict] = {}
    for run in runs:
        video = Path(run["video"])
        if not video.exists():
            continue
        times = frame_times(run, args.interval)
        frame_dir = raw / run["task"] / run["simulator"][:8]
        frame_dir.mkdir(parents=True, exist_ok=True)
        paths = extract(video, [time for time, _ in times], helper, frame_dir)
        labels = {f"{time:.1f}": label for time, label in times}
        frames = select_frames([(path, labels.get(path.stem, "")) for path in paths], args.change_threshold)
        if not frames:
            print(f"SKIP {run['task']}: no frames extracted from {video}")
            continue
        sheet = out / f"{run['task']}-{run['simulator'][:8]}.png"
        expect = run.get("expect", "")
        header = f"{run['task']} · {run['status'].upper()} · expect: {expect or '(flow has no expect)'}"
        tokens = contact_sheet(frames, args.columns, sheet, header)
        entries[run["task"]] = {
            "simulator": run["simulator"][:8], "status": run["status"], "expect": expect,
            "sheet": str(sheet), "video": str(video),
            **({"step_labels": run["step_labels"]} if run.get("step_labels") else {}),
        }
        print(
            f"SHEET task={run['task']} sim={run['simulator'][:8]} frames={len(frames)}/{len(paths)} "
            f"tokens≈{tokens} status={run['status']} path={sheet.resolve().as_uri()}"
        )
        for line in label_lines(run.get("step_labels", [])):
            print(f"  {line}")
    notes = merge_notes(out / f"review-notes-{args.session}.json", entries)
    pending = [task for task, entry in notes.items() if not entry.get("verdict")]
    print(f"NOTES {(out / f'review-notes-{args.session}.json').resolve().as_uri()} pending={len(pending)}")
    print(f"REVIEW_DIR {out.resolve().as_uri()}")
    return 0


def review_combined(args: argparse.Namespace, helper: list[str], raw: Path) -> int:
    video = args.combined.expanduser().resolve()
    items = json.loads(args.manifest.read_text(encoding="utf-8"))
    out = (args.out or video.parent / f"review-{video.stem}").expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    clips = [Path(item["path"]) for item in items]
    clip_seconds = durations(clips, helper)
    actual = durations([video], helper)[0]
    timeline = combined_timeline(items, clip_seconds, args.title_seconds)
    expected = sum(args.title_seconds + seconds for seconds in clip_seconds)
    delta = actual - expected
    for kind, key in (("titles", "title_at"), ("ends", "clip_end_at")):
        frame_dir = raw / kind
        frame_dir.mkdir(parents=True, exist_ok=True)
        paths = extract(video, [entry[key] for entry in timeline], helper, frame_dir)
        labels = {f"{entry[key]:.1f}": f"{index + 1:02d} {entry['title']}"[:40] for index, entry in enumerate(timeline)}
        frames = [(path, labels.get(path.stem, "")) for path in paths]
        if not frames:
            print(f"SKIP {kind}: no frames extracted")
            continue
        sheet = out / f"combined-{kind}.png"
        tokens = contact_sheet(frames, args.columns, sheet, f"{video.name} · {kind} · {len(items)} items")
        print(f"SHEET kind={kind} frames={len(frames)}/{len(timeline)} tokens≈{tokens} path={Path(sheet).resolve().as_uri()}")
    (out / "combined-timeline.json").write_text(json.dumps(timeline, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    verdict = "OK" if abs(delta) <= args.tolerance else "MISMATCH"
    print(
        f"COMBINED items={len(items)} expected={expected:.2f}s actual={actual:.2f}s "
        f"delta={delta:+.2f}s {verdict}"
    )
    print(f"REVIEW_DIR {out.resolve().as_uri()}")
    return 0 if verdict == "OK" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Build contact sheets from recorded fastUITest runs.")
    parser.add_argument("--root", type=Path, help="artifacts root (the --artifacts-root of the runs)")
    parser.add_argument("--session")
    parser.add_argument("--out", type=Path, help="where to write the sheets (default <root>/review-<session>)")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between grid frames")
    parser.add_argument("--change-threshold", type=float, default=0.01,
                        help="drop an interval frame when fewer than this share of pixels changed; 0 keeps all")
    parser.add_argument("--columns", type=int, default=6)
    parser.add_argument("--combined", type=Path, help="a concatenated video to verify against --manifest")
    parser.add_argument("--manifest", type=Path, help="JSON list of {path, title, subtitle} the video was built from")
    parser.add_argument("--title-seconds", type=float, default=2.5, help="length of each title card in the combined video")
    parser.add_argument("--tolerance", type=float, default=0.5, help="allowed drift between manifest timeline and file")
    args = parser.parse_args()

    if args.combined:
        if not args.manifest:
            parser.error("--combined needs --manifest")
    elif not (args.root and args.session):
        parser.error("--root and --session are required (or use --combined)")

    helper = helper_command(SWIFT_HELPER, HELPER_CACHE)
    with tempfile.TemporaryDirectory() as raw:
        if args.combined:
            return review_combined(args, helper, Path(raw))
        return review_session(args, helper, Path(raw))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
