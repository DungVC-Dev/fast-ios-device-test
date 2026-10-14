#!/usr/bin/env python3

"""Run compact, data-driven iOS Simulator UI flows."""

from __future__ import annotations

import argparse
import difflib
import fcntl
import hashlib
import json
import os
import plistlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

# bin/ holds symlinks in a git checkout but copies in the zip, so look beside scripts/ too.
sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parent.parent / "scripts")]
from fast_media import publish_video, shrink_video  # noqa: E402


BUILD_SUFFIXES = {
    ".c", ".cc", ".cpp", ".entitlements", ".gif", ".h", ".jpeg", ".jpg",
    ".json", ".m", ".mm", ".mp3", ".mp4", ".otf", ".pbxproj", ".pdf",
    ".plist", ".png", ".strings", ".swift", ".ttf", ".wav", ".xcconfig",
    ".xcprivacy", ".xcstrings", ".xib",
}


class FastUIError(RuntimeError):
    # The hierarchy seen when a wait gave up, so callers can explain the miss.
    nodes: list[dict[str, Any]] = []


class Metrics:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.steps: dict[str, float] = {}

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.steps[name] = round(time.perf_counter() - started, 3)

    @property
    def total(self) -> float:
        return round(time.perf_counter() - self.started, 3)


def command(
    args: list[str], *, check: bool = True, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise FastUIError(f"command failed ({result.returncode}) {' '.join(args)}{suffix}")
    return result


def required(mapping: dict[str, Any], key: str, context: str) -> Any:
    if key not in mapping:
        raise FastUIError(f"missing '{key}' in {context}")
    return mapping[key]


def resolved_path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


# AXe links SimulatorKit from the selected Xcode; AXe older than 1.8.0 cannot
# find it under Xcode 27 (getsentry/XcodeBuildMCP#453), which surfaces as these strings.
AXE_XCODE_MARKERS = ("simulatorkit", "privateframeworks", "developer dir", "xcode-select")
AXE_XCODE_HINT = (
    "AXe could not load the simulator frameworks of the selected Xcode; Xcode 27 needs AXe 1.8.0 or newer "
    "(check `axe --version`), or rerun with DEVELOPER_DIR pointing at an Xcode 26 install"
)


# Right after a boot AXe's remote automation session sometimes fails to come up once;
# the next attempt a second later succeeds, so one retry turns a flaky FAIL into a pass.
AXE_SESSION_MARKER = "automation session"
AXE_SESSION_RETRIES = 1


def axe(udid: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    arguments = ["axe", *args, "--udid", udid]
    for attempt in range(AXE_SESSION_RETRIES + 1):
        result = command(arguments, check=False)
        transient = result.returncode != 0 and AXE_SESSION_MARKER in f"{result.stderr}\n{result.stdout}".lower()
        if not transient or attempt == AXE_SESSION_RETRIES:
            break
        time.sleep(1.0)
    if check and result.returncode != 0:
        output = f"{result.stderr}\n{result.stdout}"
        detail = (result.stderr or result.stdout).strip().splitlines()
        message = f"command failed ({result.returncode}) {' '.join(arguments)}"
        message += f": {detail[-1]}" if detail else ""
        if any(marker in output.lower() for marker in AXE_XCODE_MARKERS):
            message += f" — {AXE_XCODE_HINT}"
        raise FastUIError(message)
    return result


def file_link(path: Path | str) -> str:
    """Absolute `file://` URL: terminals open it on click, a bare or relative path they do not."""
    return Path(path).expanduser().resolve().as_uri()


NODE_KEYS = ("type", "AXLabel", "children")


def flatten(value: Any) -> Iterator[dict[str, Any]]:
    """Accessibility nodes of a describe-ui tree, parents first. Only `children`
    is descended into: an AXe node's other dict values (`frame`, …) are attributes."""
    if isinstance(value, dict):
        if any(key in value for key in NODE_KEYS):
            yield value
        yield from flatten(value.get("children") or [])
    elif isinstance(value, list):
        for child in value:
            yield from flatten(child)


def compact_node(node: dict[str, Any]) -> dict[str, Any]:
    """Label, type, id, value, frame and tap centre only: what a flow author needs,
    without the nested children that made a dump grow with the depth of the tree."""
    compact: dict[str, Any] = {}
    for key, source in (("label", "AXLabel"), ("type", "type"), ("id", "AXUniqueId"), ("value", "AXValue")):
        value = node.get(source)
        if value not in (None, ""):
            compact[key] = str(value) if key != "type" else value
    if node.get("enabled") is False:
        compact["enabled"] = False
    frame = node.get("frame") or {}
    try:
        box = {name: round(float(frame[name]), 1) for name in ("x", "y", "width", "height")}
    except (KeyError, TypeError, ValueError):
        return compact
    compact["frame"] = box
    compact["center"] = [round(box["x"] + box["width"] / 2, 1), round(box["y"] + box["height"] / 2, 1)]
    return compact


def write_dump(path: Path, nodes: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps([compact_node(node) for node in nodes], indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


DESCRIBE_UI_ATTEMPTS = 3
# A describe-ui call costs about a second of AXe session setup; a tree younger than
# this, taken by the wait that just succeeded, is still the screen the tap lands on.
HIERARCHY_REUSE = 0.3
_HIERARCHY_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def invalidate_hierarchy(udid: str) -> None:
    _HIERARCHY_CACHE.pop(udid, None)


def hierarchy(udid: str, max_age: float = 0.0) -> list[dict[str, Any]]:
    cached = _HIERARCHY_CACHE.get(udid)
    if cached is not None and max_age > 0 and time.perf_counter() - cached[0] <= max_age:
        return cached[1]
    # AXe occasionally fails once right after launch while the accessibility
    # server is still coming up; one failed poll must not fail the whole flow.
    last_error: Exception | None = None
    for attempt in range(DESCRIBE_UI_ATTEMPTS):
        try:
            result = axe(udid, "describe-ui")
            nodes = list(flatten(json.loads(result.stdout)))
            _HIERARCHY_CACHE[udid] = (time.perf_counter(), nodes)
            return nodes
        except (FastUIError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(0.4 * (attempt + 1))
    raise FastUIError(f"describe-ui failed {DESCRIBE_UI_ATTEMPTS} times: {last_error}")


NOISE_LABEL = re.compile(r"^[\d:.,%\s]*$")
SCROLL_BAR_LABEL = re.compile(r"^(Vertical|Horizontal) scroll bar, \d+ pages?$")


def visible_labels(nodes: list[dict[str, Any]], limit: int = 40) -> list[str]:
    # Screen order (top-left first), without clock/battery/widget digits that
    # otherwise crowd out the labels a flow author actually needs.
    labels: list[str] = []
    for node in sort_nodes(nodes, ["y", "x"]):
        label = str(node.get("AXLabel") or "").strip()
        if (
            label and label not in labels
            and not NOISE_LABEL.match(label) and not SCROLL_BAR_LABEL.match(label)
        ):
            labels.append(label)
    return labels[:limit]


def node_type(node: dict[str, Any]) -> str | None:
    return node.get("type") or node.get("AXRole")


def typed_labels(nodes: list[dict[str, Any]], limit: int = 25) -> list[str]:
    """`visible_labels` with the element type beside each label: a flow author sees at
    once that "Add Widget" is a StaticText, which `tap_label` (Button) never matches."""
    by_label: dict[str, str | None] = {}
    for node in sort_nodes(nodes, ["y", "x"]):
        label = str(node.get("AXLabel") or "").strip()
        if label and label not in by_label:
            by_label[label] = node_type(node)
    return [
        f"{label} ({by_label.get(label)})" if by_label.get(label) else label
        for label in visible_labels(nodes, limit=limit)
    ]


def selector_hints(selector: dict[str, Any], nodes: list[dict[str, Any]]) -> str:
    """Why a selector may have missed: same label under another type, or a near-miss label."""
    wanted = selector.get("label") or selector.get("label_contains")
    if not wanted:
        return ""
    expected_type = selector.get("element_type")
    if selector.get("label") is not None:
        other_types = sorted({
            str(node_type(node)) for node in nodes
            if node.get("AXLabel") == wanted and node_type(node) and node_type(node) != expected_type
        })
        if other_types and expected_type:
            return (
                f"; '{wanted}' exists as {', '.join(other_types)}, not {expected_type}: "
                "add element_type or use tap_first"
            )
    labels = visible_labels(nodes, limit=200)
    close = difflib.get_close_matches(str(wanted), labels, n=3, cutoff=0.6)
    close += [label for label in labels if str(wanted).lower() in label.lower() and label not in close]
    return f"; closest labels: [{', '.join(close[:3])}]" if close else ""


SELECTOR_KEYS = ("label", "label_contains", "label_is_empty", "id", "value", "element_type", "enabled", "frame")


def selector_of(action: dict[str, Any], default_type: str | None = None) -> dict[str, Any]:
    """The selector keys an action carries; `default_type` fills in `element_type` when absent."""
    selector = {key: action[key] for key in SELECTOR_KEYS if key in action}
    if default_type is not None and "element_type" not in selector:
        selector["element_type"] = default_type
    return selector


def matches(node: dict[str, Any], selector: dict[str, Any]) -> bool:
    label = selector.get("label")
    if label is not None and node.get("AXLabel") != label:
        return False
    identifier = selector.get("id")
    if identifier is not None and node.get("AXUniqueId") != identifier:
        return False
    value = selector.get("value")
    if value is not None and str(node.get("AXValue")) != str(value):
        return False
    if selector.get("label_is_empty") and node.get("AXLabel"):
        return False
    fragment = selector.get("label_contains")
    if fragment is not None and fragment not in str(node.get("AXLabel") or ""):
        return False
    expected_type = selector.get("element_type")
    if expected_type is not None and node_type(node) != expected_type:
        return False
    enabled = selector.get("enabled")
    if enabled is not None and bool(node.get("enabled", True)) != bool(enabled):
        return False
    frame = node.get("frame") or {}
    limits = selector.get("frame") or {}
    properties = {
        "x": float(frame.get("x", -1)),
        "y": float(frame.get("y", -1)),
        "width": float(frame.get("width", 0)),
        "height": float(frame.get("height", 0)),
    }
    for property_name, actual in properties.items():
        minimum = limits.get(f"min_{property_name}")
        maximum = limits.get(f"max_{property_name}")
        if minimum is not None and actual < float(minimum):
            return False
        if maximum is not None and actual > float(maximum):
            return False
    return True


def wait_nodes(
    udid: str,
    predicate: Callable[[list[dict[str, Any]]], bool],
    timeout: float,
    optional_prompt_labels: list[str] | None = None,
    first_poll_max_age: float = 0.0,
) -> list[dict[str, Any]]:
    deadline = time.perf_counter() + timeout
    nodes: list[dict[str, Any]] = []
    max_age = first_poll_max_age
    while time.perf_counter() < deadline:
        nodes = hierarchy(udid, max_age)
        max_age = 0.0
        prompt = next(
            (
                node
                for node in nodes
                if node.get("AXLabel") in (optional_prompt_labels or [])
                and node_type(node) == "Button"
            ),
            None,
        )
        if prompt is not None:
            tap_point(udid, *frame_center(prompt), 0.08)
            continue
        if predicate(nodes):
            return nodes
        time.sleep(0.12)
    labels = ", ".join(typed_labels(nodes, limit=25))
    error = FastUIError(f"timed out waiting for UI selector; visible labels: [{labels}]")
    error.nodes = nodes
    raise error


CONTAINER_TYPES = ("Application", "Window")


def tappable(node: dict[str, Any]) -> bool:
    frame = node.get("frame") or {}
    try:
        return float(frame["width"]) > 0 and float(frame["height"]) > 0
    except (KeyError, TypeError, ValueError):
        return False


def resolve_tap_target(
    nodes: list[dict[str, Any]], selector: dict[str, Any], explicit_type: bool
) -> dict[str, Any] | None:
    """The node `tap_label` taps: the first match of the full selector; else, when the
    flow did not pin `element_type`, the one node of any type with that label (a SwiftUI
    text or image that is tappable but not exposed as a Button)."""
    typed = sort_nodes([node for node in nodes if matches(node, selector)], ["y", "x"])
    if typed:
        return typed[0]
    if explicit_type:
        return None
    loose = {key: value for key, value in selector.items() if key != "element_type"}
    # The app's root node carries the app name as its label; "tapping" it would hit the screen centre.
    candidates = [
        node for node in nodes
        if matches(node, loose) and tappable(node) and node_type(node) not in CONTAINER_TYPES
    ]
    return candidates[0] if len(candidates) == 1 else None


def wait_selector(
    udid: str,
    selector: dict[str, Any],
    timeout: float,
    optional_prompt_labels: list[str],
    predicate: Callable[[list[dict[str, Any]]], bool] | None = None,
    first_poll_max_age: float = 0.0,
) -> list[dict[str, Any]]:
    """Wait until `selector` matches (or `predicate` holds); a timeout explains the miss."""
    try:
        return wait_nodes(
            udid,
            predicate or (lambda nodes: any(matches(node, selector) for node in nodes)),
            timeout,
            optional_prompt_labels,
            first_poll_max_age,
        )
    except FastUIError as error:
        explained = FastUIError(f"{error}{selector_hints(selector, error.nodes)}")
        explained.nodes = error.nodes
        raise explained from None


def wait_absent(
    udid: str,
    selector: dict[str, Any],
    timeout: float,
    optional_prompt_labels: list[str],
) -> None:
    """Succeed as soon as nothing matches the selector; fail if it is still there at the deadline."""
    try:
        wait_nodes(
            udid,
            lambda nodes: not any(matches(node, selector) for node in nodes),
            timeout,
            optional_prompt_labels,
        )
    except FastUIError as error:
        labels = str(error).split("visible labels:")[-1].strip()
        raise FastUIError(
            f"'{selector.get('label')}' is still on screen after {timeout:g}s; visible labels: {labels}"
        ) from None


def assert_absent(
    udid: str,
    selector: dict[str, Any],
    seconds: float,
    optional_prompt_labels: list[str],
) -> None:
    """Fail the moment the selector appears during the whole window; used to prove a gate held."""
    deadline = time.perf_counter() + seconds
    while True:
        nodes = wait_nodes(udid, lambda _: True, seconds, optional_prompt_labels)
        if any(matches(node, selector) for node in nodes):
            labels = ", ".join(visible_labels(nodes, limit=25))
            raise FastUIError(
                f"'{selector.get('label')}' appeared while asserting absence; visible labels: [{labels}]"
            )
        if time.perf_counter() >= deadline:
            return
        time.sleep(0.3)


SETTLE_TIMEOUT = 2.5


def tree_signature(nodes: list[dict[str, Any]]) -> str:
    """Labels, types and whole-point frames in screen order: equal signatures mean nothing moved."""
    parts = []
    for node in sort_nodes(nodes, ["y", "x"]):
        frame = node.get("frame") or {}
        box = ",".join(f"{float(frame.get(key, 0) or 0):.0f}" for key in ("x", "y", "width", "height"))
        parts.append(f"{node.get('AXLabel') or ''}/{node_type(node) or ''}/{box}")
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def wait_settled(
    udid: str, timeout: float = SETTLE_TIMEOUT, interval: float = 0.1, stable_for: float = 0.1
) -> bool:
    """Poll until two consecutive trees match and have for `stable_for`; False after `timeout`.
    Opt-in per action: a screen that animates forever would otherwise pay the whole timeout."""
    deadline = time.perf_counter() + timeout
    previous: str | None = None
    stable_since = 0.0
    while True:
        try:
            signature = tree_signature(hierarchy(udid))
        except FastUIError:
            return False
        now = time.perf_counter()
        if signature == previous:
            if now - stable_since >= stable_for:
                return True
        else:
            previous, stable_since = signature, now
        if now >= deadline:
            return False
        time.sleep(interval)


def swipe_points(
    action: dict[str, Any], nodes: list[dict[str, Any]], index: int, area: dict[str, Any] | None = None,
) -> tuple[list[float], list[float]]:
    """`from`/`to` points, or a `direction` the finger moves in ("up" scrolls content down)
    across `area` (an element's frame, e.g. a row to swipe-delete) or else the whole screen."""
    if "direction" not in action:
        return required(action, "from", f"action {index}"), required(action, "to", f"action {index}")
    screen = area or screen_frame(nodes)
    x0, y0 = float(screen.get("x", 0)), float(screen.get("y", 0))
    width, height = float(screen.get("width", 0)), float(screen.get("height", 0))
    mid_x, mid_y = x0 + width / 2, y0 + height / 2
    top, bottom = y0 + height * 0.3, y0 + height * 0.7
    left, right = x0 + width * 0.2, x0 + width * 0.8
    points = {
        "up": ([mid_x, bottom], [mid_x, top]),
        "down": ([mid_x, top], [mid_x, bottom]),
        "left": ([right, mid_y], [left, mid_y]),
        "right": ([left, mid_y], [right, mid_y]),
    }
    if action["direction"] not in points or not width or not height:
        raise FastUIError(f"action {index}: swipe needs from/to or direction up|down|left|right")
    return points[action["direction"]]


def swipe(udid: str, start: list[float], end: list[float], duration: float, post_delay: float) -> None:
    invalidate_hierarchy(udid)
    axe(
        udid, "swipe", "--start-x", str(start[0]), "--start-y", str(start[1]),
        "--end-x", str(end[0]), "--end-y", str(end[1]),
        "--duration", str(duration),
        "--post-delay", str(post_delay),
    )


def frame_center(node: dict[str, Any]) -> tuple[float, float]:
    frame = node.get("frame") or {}
    try:
        return (
            float(frame["x"]) + float(frame["width"]) / 2,
            float(frame["y"]) + float(frame["height"]) / 2,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise FastUIError("selected node has no tappable frame") from error


AXE_MAX_POST_DELAY = 10.0


def split_post_delay(post_delay: float) -> tuple[float, float]:
    capped = min(float(post_delay), AXE_MAX_POST_DELAY)
    return capped, max(0.0, float(post_delay) - capped)


def tap_point(udid: str, x: float, y: float, post_delay: float) -> None:
    invalidate_hierarchy(udid)
    capped, remainder = split_post_delay(max(post_delay, TAP_SETTLE))
    axe(
        udid, "tap", "-x", f"{x:.2f}", "-y", f"{y:.2f}",
        "--post-delay", str(capped),
    )
    if remainder:
        time.sleep(remainder)


def screenshot(udid: str, path: Path) -> None:
    image_type = path.suffix.removeprefix(".").lower() or "png"
    if image_type == "jpg":
        image_type = "jpeg"
    command(["xcrun", "simctl", "io", udid, "screenshot", f"--type={image_type}", str(path)])


UI_SETTINGS: dict[str, dict[str, str]] = {
    # simctl value -> short tag used in the task name of a matrix variant
    "appearance": {"light": "light", "dark": "dark"},
    "content_size": {
        "extra-small": "xs", "small": "s", "medium": "m", "large": "l",
        "extra-large": "xl", "extra-extra-large": "xxl", "extra-extra-extra-large": "xxxl",
        "accessibility-medium": "ax-m", "accessibility-large": "ax-l",
        "accessibility-extra-large": "ax-xl", "accessibility-extra-extra-large": "ax-xxl",
        "accessibility-extra-extra-extra-large": "ax-xxxl",
    },
}


def ui_variant(setup: dict[str, Any], appearance: str | None, content_size: str | None) -> dict[str, str]:
    """Effective simulator UI settings: CLI overrides win over `setup`."""
    variant: dict[str, str] = {}
    for key, override in (("appearance", appearance), ("content_size", content_size)):
        value = override or setup.get(key)
        if not value:
            continue
        if value not in UI_SETTINGS[key]:
            raise FastUIError(f"unsupported {key} '{value}'; use one of {', '.join(UI_SETTINGS[key])}")
        variant[key] = value
    return variant


def variant_name(name: str, variant: dict[str, str]) -> str:
    return name + "".join(f"@{UI_SETTINGS[key][variant[key]]}" for key in UI_SETTINGS if key in variant)


def apply_ui_settings(udid: str, variant: dict[str, str], previous: dict[str, str]) -> None:
    """Set the variant, recording each replaced value in `previous` before it changes so a
    failure halfway still restores what was already switched."""
    for key, value in variant.items():
        current = command(["xcrun", "simctl", "ui", udid, key]).stdout.strip()
        if current == value:
            continue
        if current in UI_SETTINGS[key]:
            previous[key] = current
        command(["xcrun", "simctl", "ui", udid, key, value])


def restore_ui_settings(udid: str, previous: dict[str, str]) -> None:
    for key, value in previous.items():
        command(["xcrun", "simctl", "ui", udid, key, value], check=False)


def step_labels(udid: str, step: str, at: float, result: dict[str, Any] | None) -> dict[str, Any]:
    """Visible text after a step, so a reviewer checks copy without OCR on the video frames."""
    if result and "labels" in result:
        labels = result["labels"]
    else:
        try:
            labels = visible_labels(hierarchy(udid, HIERARCHY_REUSE))
        except FastUIError:
            labels = []
    return {"step": step, "at": round(at, 2), "labels": labels}


def stop_stale_recorder(udid: str) -> None:
    # A recorder left behind by an aborted run keeps the device locked and
    # makes the next start write a 0-byte file.
    command(["pkill", "-INT", "-f", f"simctl io {udid} recordVideo"], check=False)


class Recorder:
    """Records the simulator screen with `simctl io recordVideo` for one run."""

    def __init__(self, udid: str, path: Path) -> None:
        self.udid = udid
        self.path = path
        self.process: subprocess.Popen[bytes] | None = None
        self.started: float | None = None

    def elapsed(self) -> float:
        return time.perf_counter() - self.started if self.started is not None else 0.0

    def start(self) -> None:
        stop_stale_recorder(self.udid)
        self.path.unlink(missing_ok=True)
        self.started = time.perf_counter()
        self.process = subprocess.Popen(
            [
                "xcrun", "simctl", "io", self.udid, "recordVideo",
                "--codec", "hevc", "--force", str(self.path),
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1.5)

    def stop(self) -> None:
        if self.process is None:
            return
        time.sleep(1.0)
        self.process.send_signal(signal.SIGINT)
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
        for _ in range(20):
            partial = list(self.path.parent.glob(self.path.name + ".sb-*"))
            if self.path.exists() and not partial:
                break
            time.sleep(1.0)
        self.process = None


def prune_artifacts(root: Path, keep_days: float) -> int:
    """Delete run folders and final videos untouched for `keep_days`; empty task dirs go too."""
    if keep_days <= 0 or not root.is_dir():
        return 0
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for task_dir in root.iterdir():
        if not task_dir.is_dir():
            continue
        for entry in task_dir.iterdir():
            try:
                if entry.stat().st_mtime >= cutoff:
                    continue
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                removed += 1
            except OSError:
                continue
        if not any(task_dir.iterdir()):
            task_dir.rmdir()
    return removed


def build_input_files(app: dict[str, Any], base: Path) -> list[Path]:
    files: list[Path] = []
    for raw_root in app.get("build_inputs", []):
        root = resolved_path(raw_root, base)
        if not root.exists():
            continue
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if path.is_file() and path.suffix.lower() in BUILD_SUFFIXES:
                files.append(path)
    return sorted(set(files), key=lambda path: str(path))


def build_fingerprint(app: dict[str, Any], base: Path) -> str:
    digest = hashlib.sha256()
    # The simulator UDID is deliberately excluded: one simulator .app serves
    # every booted simulator, and keying on it forced a full rebuild whenever
    # flows alternated between devices.
    settings = {
        key: app.get(key)
        for key in ("project", "scheme", "configuration", "bundle_id", "app_path")
    }
    digest.update(json.dumps(settings, sort_keys=True).encode("utf-8"))
    for path in build_input_files(app, base):
        stat = path.stat()
        digest.update(str(path).encode("utf-8"))
        digest.update(f"\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode("ascii"))
    return digest.hexdigest()


def read_build_fingerprint(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("fingerprint")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def write_build_fingerprint(path: Path, fingerprint: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fingerprint": fingerprint, "updated_at": datetime.now().isoformat()}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def verify_app(path: Path, bundle_id: str) -> None:
    info = path / "Info.plist"
    if not info.exists():
        raise FastUIError(f"invalid app bundle: {path}")
    with info.open("rb") as stream:
        actual = plistlib.load(stream).get("CFBundleIdentifier")
    if actual != bundle_id:
        raise FastUIError(f"bundle mismatch: expected {bundle_id}, found {actual}")


def ensure_booted(udid: str) -> None:
    # Installing into a shut-down simulator fails only after the build has
    # already spent a minute, so boot (or confirm boot) up front.
    command(["xcrun", "simctl", "bootstatus", udid, "-b"], timeout=120)
    ensure_device_hub(udid)


DEVICE_HUB_WAIT = 30.0
# Under Device Hub a tap is dropped when `axe` exits right after sending it:
# measured on Xcode 27.0, 0 s lost every tap, 0.15 s one in three, 0.25 s none.
DEVICE_HUB_TAP_SETTLE = 0.4
TAP_SETTLE = 0.0


def ensure_device_hub(udid: str) -> None:
    # Xcode 27 replaced Simulator.app with Device Hub, and AXe's automation
    # session times out unless Device Hub is running. Older Xcodes ship no
    # Device Hub, so this does nothing there.
    developer_dir = os.environ.get("DEVELOPER_DIR") or command(["xcode-select", "-p"], check=False).stdout.strip()
    if not developer_dir:
        return
    device_hub = Path(developer_dir).parent / "Applications" / "DeviceHub.app"
    if not device_hub.exists():
        return
    global TAP_SETTLE
    TAP_SETTLE = DEVICE_HUB_TAP_SETTLE
    if command(["pgrep", "-f", str(device_hub)], check=False).returncode == 0:
        return
    command(["open", "-g", "-a", str(device_hub)])
    deadline = time.perf_counter() + DEVICE_HUB_WAIT
    while time.perf_counter() < deadline:
        if axe(udid, "describe-ui", check=False).returncode == 0:
            return
        time.sleep(1)


@contextmanager
def build_lock(derived_data: Path) -> Iterator[None]:
    # Parallel flows share one DerivedData; only one xcodebuild may run in it.
    derived_data.mkdir(parents=True, exist_ok=True)
    with (derived_data / ".fastui-build.lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def prepare_app(app: dict[str, Any], base: Path, udid: str, reuse_app: bool) -> tuple[Path | None, bool]:
    ensure_booted(udid)
    if app.get("prebuilt"):
        # Drive what is already on the simulator (a system app, a build Xcode installed):
        # nothing to build, so no project or DerivedData is needed.
        if app.get("app_path"):
            app_path = resolved_path(app["app_path"], base)
            verify_app(app_path, required(app, "bundle_id", "app"))
            return app_path, False
        return None, False
    app_path = resolved_path(required(app, "app_path", "app"), base)
    derived_data = resolved_path(required(app, "derived_data", "app"), base)
    if reuse_app:
        verify_app(app_path, required(app, "bundle_id", "app"))
        return app_path, False
    with build_lock(derived_data):
        return build_if_needed(app, base, udid, app_path, derived_data)


def build_if_needed(
    app: dict[str, Any], base: Path, udid: str, app_path: Path, derived_data: Path
) -> tuple[Path, bool]:
    state_path = derived_data / ".fastui-build-state.json"
    fingerprint_before = build_fingerprint(app, base)
    # Without build_inputs the fingerprint cannot see a source edit, so the cached
    # app would be reused forever; let xcodebuild's own incremental check decide.
    untracked = not build_input_files(app, base)
    stale = untracked or not app_path.exists() or read_build_fingerprint(state_path) != fingerprint_before
    if not stale:
        verify_app(app_path, required(app, "bundle_id", "app"))
        return app_path, False

    project = resolved_path(required(app, "project", "app"), base)
    project_flag = "-workspace" if project.suffix == ".xcworkspace" else "-project"
    build = [
        "xcodebuild", "build", project_flag, str(project),
        "-scheme", required(app, "scheme", "app"),
        "-destination", f"platform=iOS Simulator,id={udid}",
        "-derivedDataPath", str(derived_data),
        "-skipPackagePluginValidation", "-disableAutomaticPackageResolution",
        "COMPILER_INDEX_STORE_ENABLE=NO", "ONLY_ACTIVE_ARCH=YES", "-quiet",
    ]
    if app.get("configuration"):
        build[6:6] = ["-configuration", app["configuration"]]
    result = command(build, check=False, timeout=float(app.get("build_timeout", 300)))
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-8:]
        raise FastUIError("incremental build failed: " + " | ".join(tail))
    verify_app(app_path, required(app, "bundle_id", "app"))
    fingerprint_after = build_fingerprint(app, base)
    if fingerprint_after == fingerprint_before:
        write_build_fingerprint(state_path, fingerprint_after)
    return app_path, True


def write_preference(udid: str, domain: str, key: str, value: Any) -> None:
    args = ["xcrun", "simctl", "spawn", udid, "defaults", "write", domain, key]
    if isinstance(value, bool):
        args += ["-bool", "true" if value else "false"]
    elif isinstance(value, int):
        args += ["-int", str(value)]
    elif isinstance(value, float):
        args += ["-float", str(value)]
    elif isinstance(value, str):
        args += ["-string", value]
    elif isinstance(value, dict) and set(value) == {"$json_data"}:
        encoded = json.dumps(
            value["$json_data"], separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        args += ["-data", encoded.hex()]
    else:
        raise FastUIError(f"unsupported preference type for '{key}'")
    command(args)


def set_preferences(udid: str, bundle_id: str, preferences: dict[str, Any]) -> None:
    if not preferences:
        return
    for key, value in preferences.items():
        write_preference(udid, bundle_id, key, value)


def reset_preferences(udid: str, bundle_id: str, preferences: dict[str, Any], fresh_install: bool) -> None:
    # Seeded keys (e.g. isPremium to hide the paywall) live in the simulator's user
    # domain and would otherwise stay active for ordinary app runs after the test.
    if not preferences:
        return
    command(["xcrun", "simctl", "terminate", udid, bundle_id], check=False)
    if fresh_install:
        command(["xcrun", "simctl", "spawn", udid, "defaults", "delete", bundle_id], check=False)
        return
    for key in preferences:
        command(["xcrun", "simctl", "spawn", udid, "defaults", "delete", bundle_id, key], check=False)


def sort_nodes(nodes: list[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    return sorted(
        nodes,
        key=lambda node: tuple(float((node.get("frame") or {}).get(key, 0)) for key in keys),
    )


def motion_ratio(first: Path, second: Path, region: list[float], threshold: int) -> float:
    try:
        # Only `motion` needs Pillow; every other action runs on a stock python3.
        from PIL import Image, ImageChops
    except ImportError as error:
        raise FastUIError("motion needs Pillow: python3 -m pip install --user pillow") from error
    image_a = Image.open(first).convert("RGB")
    image_b = Image.open(second).convert("RGB")
    if image_a.size != image_b.size:
        raise FastUIError("motion frames have different dimensions")
    width, height = image_a.size
    box = (
        round(width * float(region[0])), round(height * float(region[1])),
        round(width * float(region[2])), round(height * float(region[3])),
    )
    difference = ImageChops.difference(image_a.crop(box), image_b.crop(box))
    # Max over channels, then a threshold mask, all in C — a Python loop over a
    # 3x screenshot took seconds per frame pair.
    red, green, blue = difference.split()
    peak = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    mask = peak.point(lambda value: 255 if value >= threshold else 0)
    changed = mask.histogram()[255]
    return changed / (difference.width * difference.height)


GESTURE_KINDS = {
    "tap_label", "tap_first", "tap_nearest", "tap_point", "swipe", "scroll_to",
    "long_press", "double_tap", "drag", "edge_swipe", "back", "pull_to_refresh",
    "set_switch", "set_slider", "set_picker", "tap_alert",
}

# Gestures AXe cannot synthesize: it sends one touch at a time.
DEVICE_ONLY = {
    "pinch": "a two-finger pinch",
    "rotate_gesture": "a two-finger rotation",
    "two_finger_tap": "a two-finger tap",
    "set_orientation": "rotating the device",
}

# USB HID usage ids AXe sends for `press_key`.
HID_KEYS = {
    "return": 40, "enter": 40, "escape": 41, "delete": 42, "backspace": 42, "tab": 43, "space": 44,
    "right": 79, "left": 80, "down": 81, "up": 82,
}
HID_COMMAND, HID_A = 227, 4

# `axe button` names; a press shorter than ~0.2 s is dropped under Device Hub.
SIMULATOR_BUTTONS = {"home": "home", "lock": "lock", "side": "side-button", "siri": "siri", "apple_pay": "apple-pay"}
BUTTON_PRESS = 0.3

# Start and end of an edge swipe as fractions of the screen. Measured on Xcode 27.0: neither
# `axe swipe` nor `axe gesture swipe-from-left-edge` triggers the back gesture; `axe drag`,
# which sends every touch move, does.
EDGE_FRACTIONS = {
    "left": ((0.005, 0.5), (0.8, 0.5)), "right": ((0.995, 0.5), (0.2, 0.5)),
    "top": ((0.5, 0.003), (0.5, 0.6)), "bottom": ((0.5, 0.997), (0.5, 0.5)),
}

STATUS_BAR_FLAGS = {
    "time": "--time", "data_network": "--dataNetwork", "wifi_mode": "--wifiMode", "wifi_bars": "--wifiBars",
    "cellular_mode": "--cellularMode", "cellular_bars": "--cellularBars", "operator_name": "--operatorName",
    "battery_state": "--batteryState", "battery_level": "--batteryLevel",
}


def ax_text(node: dict[str, Any], key: str = "AXValue") -> str:
    """An AX attribute as text. AXe sends numbers as numbers, and `value or ""` would turn
    a wheel's row 0 or a switch's 0 into an empty string."""
    value = node.get(key)
    return "" if value is None else str(value)


def has_selector(action: dict[str, Any]) -> bool:
    return any(key in action for key in SELECTOR_KEYS)


def screen_frame(nodes: list[dict[str, Any]]) -> dict[str, float]:
    """The application node's frame, which spans the screen. Only without one, the largest
    frame starting on screen: a scroll view's content can be taller than the screen and
    start far above it (y -1580 in a long Settings list)."""
    frames = [node.get("frame") or {} for node in nodes if node_type(node) == "Application"]
    frames = frames or [
        node.get("frame") or {} for node in nodes
        if float((node.get("frame") or {}).get("x", 0)) >= 0 and float((node.get("frame") or {}).get("y", 0)) >= 0
    ]
    frame = max(
        frames,
        key=lambda value: float(value.get("width", 0)) * float(value.get("height", 0)),
        default={},
    )
    return {key: float(frame.get(key, 0)) for key in ("x", "y", "width", "height")}


def resolve_node(
    udid: str, selector: dict[str, Any], timeout: float, optional_prompt_labels: list[str],
    accept: Callable[[dict[str, Any]], bool] = lambda node: True,
) -> dict[str, Any]:
    """The top-left node matching `selector` (and `accept`), waiting for it like `wait` does."""
    def found(node: dict[str, Any]) -> bool:
        return matches(node, selector) and tappable(node) and accept(node)

    nodes = wait_selector(
        udid, selector, timeout, optional_prompt_labels,
        predicate=lambda value: any(found(node) for node in value),
        first_poll_max_age=HIERARCHY_REUSE,
    )
    return sort_nodes([node for node in nodes if found(node)], ["y", "x"])[0]


# AXe reports a UISwitch as CheckBox on iOS 27 and as Switch before it.
SWITCH_TYPES = ("Switch", "CheckBox")


SWITCH_PRESS = 0.3
PICKER_TYPES = ("PickerWheel", "Picker", "Slider")


def is_picker(node: dict[str, Any]) -> bool:
    """A picker wheel; AXe reports a SwiftUI wheel as a Slider whose value is the row index."""
    return node_type(node) in PICKER_TYPES and not SCROLL_BAR_LABEL.match(str(node.get("AXLabel") or ""))
SLIDER_CORRECTIONS = 3
# A UISlider thumb is ~28 pt wide, so its centre travels inside the track by about half that.
SLIDER_THUMB_INSET = 14.0


def slider_percent(node: dict[str, Any]) -> float | None:
    """A slider's AXValue as a percentage: UIKit reports "50%", SwiftUI the fraction "0.5".
    None for anything else, such as the step number of a stepped slider."""
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(%?)\s*", ax_text(node))
    if not match:
        return None
    number = float(match.group(1))
    if match.group(2):
        return number
    return number * 100 if 0 <= number <= 1 else None


def is_switch(node: dict[str, Any]) -> bool:
    return node_type(node) in SWITCH_TYPES and str(node.get("AXValue")) in ("0", "1")


def is_slider(node: dict[str, Any]) -> bool:
    """A Slider that is not a scroll view's scroll bar, which AX also reports as Slider."""
    return node_type(node) == "Slider" and not SCROLL_BAR_LABEL.match(str(node.get("AXLabel") or ""))


def resolve_point(
    udid: str, spec: Any, timeout: float, optional_prompt_labels: list[str], context: str,
) -> tuple[float, float]:
    """A gesture target: `[x, y]`, a mapping with `x`/`y`, or a selector mapping."""
    if isinstance(spec, (list, tuple)) and len(spec) == 2:
        return float(spec[0]), float(spec[1])
    if isinstance(spec, dict):
        if "x" in spec and "y" in spec:
            return float(spec["x"]), float(spec["y"])
        if has_selector(spec):
            return frame_center(resolve_node(udid, selector_of(spec), timeout, optional_prompt_labels))
    raise FastUIError(f"{context} needs x/y, an [x, y] point or a selector (label, id, …)")


def deduped(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One node per on-screen box: AX trees nest a text in containers with the same frame."""
    seen: set[tuple[Any, ...]] = set()
    unique = []
    for node in nodes:
        frame = node.get("frame") or {}
        key = tuple(round(float(frame.get(name, 0) or 0)) for name in ("x", "y", "width", "height"))
        if key not in seen:
            seen.add(key)
            unique.append(node)
    return unique


def check_text(actual: str, action: dict[str, Any], context: str) -> str | None:
    """Why `actual` fails the action's `equals`/`not_equals`/`contains`/`matches`; None when it passes."""
    checks = [key for key in ("equals", "not_equals", "contains", "matches") if key in action]
    if not checks:
        raise FastUIError(f"{context} needs equals, not_equals, contains or matches")
    for key in checks:
        expected = str(action[key])
        if key == "equals" and actual != expected:
            return f"is '{actual}', expected '{expected}'"
        if key == "not_equals" and actual == expected:
            return f"is still '{actual}'"
        if key == "contains" and expected not in actual:
            return f"is '{actual}', expected it to contain '{expected}'"
        if key == "matches" and not re.search(expected, actual):
            return f"is '{actual}', expected it to match /{expected}/"
    return None


def count_failure(count: int, action: dict[str, Any]) -> str | None:
    if "count" in action and count != int(action["count"]):
        return f"expected {int(action['count'])}"
    if "min" in action and count < int(action["min"]):
        return f"expected at least {int(action['min'])}"
    if "max" in action and count > int(action["max"]):
        return f"expected at most {int(action['max'])}"
    return None


def poll_until(udid: str, check: Callable[[list[dict[str, Any]]], str | None], timeout: float,
               optional_prompt_labels: list[str]) -> None:
    """Re-read the tree until `check` returns None; its last complaint becomes the failure."""
    complaint: list[str | None] = [None]

    def passes(nodes: list[dict[str, Any]]) -> bool:
        complaint[0] = check(nodes)
        return complaint[0] is None

    try:
        wait_nodes(udid, passes, timeout, optional_prompt_labels)
    except FastUIError as error:
        labels = str(error).split("visible labels:")[-1].strip()
        reason = complaint[0] or "a declared permission prompt kept covering the screen"
        raise FastUIError(f"{reason} after {timeout:g}s; visible labels: {labels}") from None


def settle_tap(post_delay: float) -> None:
    capped, remainder = split_post_delay(max(post_delay, TAP_SETTLE))
    time.sleep(capped + remainder)


def long_press(udid: str, x: float, y: float, duration: float, post_delay: float) -> None:
    invalidate_hierarchy(udid)
    axe(udid, "touch", "-x", f"{x:.2f}", "-y", f"{y:.2f}", "--down", "--up", "--delay", str(duration))
    settle_tap(post_delay)


def double_tap(udid: str, x: float, y: float, post_delay: float) -> None:
    # One AXe session for both taps: two `axe tap` processes land too far apart to be a double tap.
    invalidate_hierarchy(udid)
    point = f"tap -x {x:.2f} -y {y:.2f}"
    axe(udid, "batch", *KEY_LEAD, "--step", point, "--step", "sleep 0.08", "--step", point, "--step", f"sleep {KEY_SETTLE}")
    settle_tap(post_delay)


def hold_and_drag(
    udid: str, start: tuple[float, float], end: tuple[float, float], hold: float, duration: float, post_delay: float,
) -> None:
    """Press, stay still for `hold` (long enough for a reorder or drag-and-drop to pick the item
    up), then move: a touch-down followed by a swipe from the same point in one AXe session
    keeps the finger down throughout."""
    invalidate_hierarchy(udid)
    (x0, y0), (x1, y1) = start, end
    axe(
        udid, "batch",
        "--step", f"touch -x {x0:.2f} -y {y0:.2f} --down",
        "--step", f"sleep {hold}",
        "--step", f"swipe --start-x {x0:.2f} --start-y {y0:.2f} --end-x {x1:.2f} --end-y {y1:.2f} --duration {duration}",
    )
    settle_tap(post_delay)


def drag(udid: str, start: tuple[float, float], end: tuple[float, float], duration: float, post_delay: float) -> None:
    """A finger moved without a fling: no momentum scroll, and edge gestures recognise it."""
    invalidate_hierarchy(udid)
    capped, remainder = split_post_delay(post_delay)
    axe(
        udid, "drag", "--start-x", f"{start[0]:.2f}", "--start-y", f"{start[1]:.2f}",
        "--end-x", f"{end[0]:.2f}", "--end-y", f"{end[1]:.2f}", "--duration", str(duration),
        "--post-delay", str(capped),
    )
    time.sleep(remainder)


# Like a tap, a key is dropped when AXe exits right after sending it, and also when it is the
# first thing a new AXe session sends after another one typed. Measured on Xcode 27.0 (two
# Backspaces after `axe type`): a lone `axe key` or `axe key-sequence` deleted nothing, a batch
# with a trailing sleep worked 2/6 times, with a leading sleep as well 5/5.
KEY_SETTLE = 0.3
KEY_LEAD = ["--step", "sleep 0.3"]


DISMISS_ATTEMPTS = 3
KEYBOARD_KEY_IDS = ("Return", "delete", "shift", "space")


def is_keyboard_key(node: dict[str, Any]) -> bool:
    return node_type(node) == "Button" and node.get("AXUniqueId") in KEYBOARD_KEY_IDS


def press_keys(udid: str, codes: list[int]) -> None:
    invalidate_hierarchy(udid)
    steps: list[str] = []
    for code in codes:
        steps += ["--step", f"key {code}", "--step", "sleep 0.05"]
    axe(udid, "batch", *KEY_LEAD, *steps, "--step", f"sleep {KEY_SETTLE}")


def clear_focused_text(udid: str) -> None:
    """Select all, then delete: works whatever the cursor position and text length."""
    invalidate_hierarchy(udid)
    axe(
        udid, "batch", *KEY_LEAD,
        "--step", f"key-combo --modifiers {HID_COMMAND} --key {HID_A}",
        "--step", "sleep 0.2",
        "--step", f"key {HID_KEYS['delete']}",
        "--step", f"sleep {KEY_SETTLE}",
    )


def verify_cleared(
    udid: str, selector: dict[str, Any], timeout: float, optional_prompt_labels: list[str],
) -> None:
    """Cmd+A is sometimes eaten by the edit menu that a tap on a focused field opens, so
    whatever value the field still reports is deleted from the end: Cmd+Down moves the
    cursor there, then one Backspace per character. AX reports an empty field's placeholder
    as its value, which cannot be told apart from text; Backspace on an empty field does nothing."""
    time.sleep(0.2)
    # A field picked by its old text no longer has it: find it again without `value`.
    selector = {key: value for key, value in selector.items() if key != "value"}
    remaining = ax_text(resolve_node(udid, selector, timeout, optional_prompt_labels))
    if not remaining:
        return
    invalidate_hierarchy(udid)
    steps = ["--step", f"key-combo --modifiers {HID_COMMAND} --key {HID_KEYS['down']}", "--step", "sleep 0.1"]
    for _ in range(len(remaining) + 2):
        steps += ["--step", f"key {HID_KEYS['delete']}", "--step", "sleep 0.03"]
    axe(udid, "batch", *KEY_LEAD, *steps, "--step", f"sleep {KEY_SETTLE}")


def focus_field(
    udid: str, action: dict[str, Any], timeout: float, optional_prompt_labels: list[str], post_delay: float,
) -> None:
    """Tap the field a typing action names, if it names one; keyboards need a moment to come up."""
    if has_selector(action):
        node = resolve_node(udid, selector_of(action), timeout, optional_prompt_labels)
        tap_point(udid, *frame_center(node), max(post_delay, 0.5))


def switch_point(node: dict[str, Any]) -> tuple[float, float]:
    """A SwiftUI Toggle spans its whole row and only flips when the switch itself is hit,
    so a wide switch is tapped near its trailing edge."""
    frame = node.get("frame") or {}
    x, y = frame_center(node)
    width = float(frame.get("width", 0))
    if width > 120:
        x = float(frame["x"]) + width - 36
    return x, y


def simctl_with_input(args: list[str], data: str) -> None:
    result = subprocess.run(args, input=data, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise FastUIError(f"command failed ({result.returncode}) {' '.join(args)}" + (f": {detail[-1]}" if detail else ""))


def execute_action(
    action: dict[str, Any],
    udid: str,
    artifacts: Path,
    index: int,
    optional_prompt_labels: list[str],
    defaults: dict[str, Any] | None = None,
    bundle_id: str = "",
) -> dict[str, Any] | None:
    """Run one action; `defaults` carries flow-wide keys such as `settle` from `setup`,
    `bundle_id` is the app under test for `launch`/`terminate` without an `app` key."""
    kind = required(action, "type", f"action {index}")
    result = run_action(action, udid, artifacts, index, optional_prompt_labels, bundle_id)
    settle = action.get("settle", (defaults or {}).get("settle"))
    if kind in GESTURE_KINDS and settle:
        timeout = SETTLE_TIMEOUT if isinstance(settle, bool) else float(settle)
        result = {**(result or {}), "settled": wait_settled(udid, timeout=timeout)}
    return result


def run_action(
    action: dict[str, Any],
    udid: str,
    artifacts: Path,
    index: int,
    optional_prompt_labels: list[str],
    bundle_id: str = "",
) -> dict[str, Any] | None:
    kind = required(action, "type", f"action {index}")
    timeout = float(action.get("timeout", 6))
    post_delay = float(action.get("post_delay", 0.15))

    if kind == "wait":
        wait_selector(udid, action, timeout, optional_prompt_labels)
    elif kind == "tap_label":
        if not any(key in action for key in ("label", "label_contains", "id")):
            raise FastUIError(f"missing 'label' or 'id' in action {index}")
        selector = selector_of(action, "Button")
        explicit_type = "element_type" in action
        if action.get("optional", False):
            target = resolve_tap_target(hierarchy(udid), selector, explicit_type)
        else:
            # One hierarchy poll resolves the control (and dismisses any
            # permission alert in the way); tapping its frame avoids a second
            # label lookup inside `axe tap --label`.
            nodes = wait_selector(
                udid, selector, timeout, optional_prompt_labels,
                predicate=lambda value: resolve_tap_target(value, selector, explicit_type) is not None,
                first_poll_max_age=HIERARCHY_REUSE,
            )
            target = resolve_tap_target(nodes, selector, explicit_type)
        if target is not None:
            tap_point(udid, *frame_center(target), post_delay)
            if node_type(target) != selector["element_type"]:
                return {"fallback_type": node_type(target)}
    elif kind == "wait_absent":
        wait_absent(udid, action, timeout, optional_prompt_labels)
    elif kind == "assert_absent":
        assert_absent(udid, action, float(action.get("seconds", 3)), optional_prompt_labels)
    elif kind == "dump":
        nodes = wait_nodes(udid, lambda _: True, timeout, optional_prompt_labels)
        name = action.get("name", f"step-{index:02d}")
        path = artifacts / f"{name}-ui.json"
        write_dump(path, nodes)
        return {"path": str(path), "labels": visible_labels(nodes)}
    elif kind == "pause":
        time.sleep(float(action.get("seconds", 1)))
    elif kind == "tap_point":
        tap_point(udid, float(action["x"]), float(action["y"]), post_delay)
    elif kind == "swipe":
        area = None
        if has_selector(action):
            area = resolve_node(udid, selector_of(action), timeout, optional_prompt_labels).get("frame")
        nodes = hierarchy(udid) if "direction" in action and area is None else []
        start, end = swipe_points(action, nodes, index, area)
        if area is None:
            swipe(udid, start, end, float(action.get("duration", 0.3)), post_delay)
        else:
            # A row's swipe actions ignore `axe swipe` (measured on Xcode 27.0); a drag reveals them.
            drag(udid, tuple(start), tuple(end), float(action.get("duration", 0.3)), max(post_delay, 0.4))
    elif kind == "scroll_to":
        limit = int(action.get("max_swipes", 6))
        for attempt in range(limit + 1):
            nodes = hierarchy(udid)
            if any(matches(node, action) for node in nodes):
                break
            if attempt == limit:
                labels = ", ".join(visible_labels(nodes, limit=25))
                target = action.get("label") or action.get("label_contains") or "selector"
                raise FastUIError(f"'{target}' not found after {limit} swipes; visible labels: [{labels}]")
            direction = {"direction": action.get("direction", "up")}
            swipe(udid, *swipe_points(direction, nodes, index), 0.3, 0.4)
    elif kind == "tap_first":
        nodes = wait_selector(udid, action, timeout, optional_prompt_labels, first_poll_max_age=HIERARCHY_REUSE)
        candidates = [node for node in nodes if matches(node, action)]
        candidates = sort_nodes(candidates, action.get("sort", ["y", "x"]))
        if not candidates:
            raise FastUIError(f"no node matched tap_first at action {index}")
        tap_point(udid, *frame_center(candidates[0]), post_delay)
    elif kind == "tap_nearest":
        target_selector = required(action, "target", f"action {index}")
        anchor_selector = required(action, "anchor", f"action {index}")
        axis = action.get("axis", "y")

        def resolve_and_tap() -> None:
            nodes = wait_nodes(
                udid,
                lambda value: any(matches(node, target_selector) for node in value)
                and any(matches(node, anchor_selector) for node in value),
                timeout,
                optional_prompt_labels,
                HIERARCHY_REUSE,
            )
            targets = [node for node in nodes if matches(node, target_selector)]
            anchors = [node for node in nodes if matches(node, anchor_selector)]
            if len(anchors) != 1 or not targets:
                raise FastUIError(
                    "tap_nearest requires one anchor and at least one target; "
                    f"got {len(anchors)}/{len(targets)}"
                )
            anchor_value = float((anchors[0].get("frame") or {})[axis])
            target = min(
                targets,
                key=lambda node: abs(
                    float((node.get("frame") or {})[axis]) - anchor_value
                ),
            )
            tap_point(udid, *frame_center(target), post_delay)

        resolve_and_tap()
        success = action.get("success")
        dismiss_selectors = action.get("dismiss", [])
        if isinstance(dismiss_selectors, dict):
            dismiss_selectors = [dismiss_selectors]
        if success:
            nodes = wait_nodes(
                udid,
                lambda value: any(matches(node, success) for node in value)
                or any(
                    matches(node, selector)
                    for selector in dismiss_selectors
                    for node in value
                ),
                timeout,
                optional_prompt_labels,
            )
            if not any(matches(node, success) for node in nodes):
                dismissals = [
                    node
                    for selector in dismiss_selectors
                    for node in nodes
                    if matches(node, selector)
                ]
                if not dismissals:
                    raise FastUIError("tap_nearest reached neither success nor dismiss selector")
                tap_point(udid, *frame_center(sort_nodes(dismissals, ["y", "x"])[0]), post_delay)
                resolve_and_tap()
                wait_selector(udid, success, timeout, optional_prompt_labels)
    elif kind == "screenshot":
        path = artifacts / action.get("name", f"step-{index:02d}.png")
        screenshot(udid, path)
        return {"path": str(path)}
    elif kind == "motion":
        frame_count = int(action.get("frames", 3))
        if frame_count < 2:
            raise FastUIError("motion action needs at least two frames")
        region = action.get("region", [0, 0, 1, 1])
        if len(region) != 4:
            raise FastUIError("motion region must be [left, top, right, bottom]")
        paths: list[Path] = []
        for frame_index in range(frame_count):
            path = artifacts / f"{action.get('name', 'motion')}-{frame_index + 1}.png"
            screenshot(udid, path)
            paths.append(path)
            if frame_index + 1 < frame_count:
                time.sleep(float(action.get("interval", 0.35)))
        ratios = [
            motion_ratio(paths[position], paths[position + 1], region, int(action.get("pixel_threshold", 12)))
            for position in range(len(paths) - 1)
        ]
        measured = min(ratios)
        threshold = float(action.get("ratio_threshold", 0.001))
        if measured < threshold:
            raise FastUIError(f"motion {measured:.6f} is below {threshold:.6f}")
        keep_frames = bool(action.get("keep_frames", False))
        if not keep_frames:
            for path in paths:
                path.unlink(missing_ok=True)
        return {
            "motion_ratio": round(measured, 6),
            "motion_ratios": [round(value, 6) for value in ratios],
            **({"frames": [str(path) for path in paths]} if keep_frames else {}),
        }
    elif kind == "type_text":
        text = required(action, "text", f"action {index}")
        focus_field(udid, action, timeout, optional_prompt_labels, post_delay)
        if action.get("clear", False):
            clear_focused_text(udid)
            if has_selector(action):
                verify_cleared(udid, selector_of(action), timeout, optional_prompt_labels)
        # A lone `axe type` lost its last character ("hello worl") when AXe exited right after
        # it, like a key; inside a batch with sleeps around it nothing was lost.
        invalidate_hierarchy(udid)
        axe(udid, "batch", *KEY_LEAD, "--step", f"type {shlex.quote(text)}", "--step", f"sleep {KEY_SETTLE}")
    elif kind == "clear_text":
        focus_field(udid, action, timeout, optional_prompt_labels, post_delay)
        clear_focused_text(udid)
        if has_selector(action):
            verify_cleared(udid, selector_of(action), timeout, optional_prompt_labels)
    elif kind == "press_key":
        key = str(required(action, "key", f"action {index}")).lower()
        if key not in HID_KEYS:
            raise FastUIError(f"action {index}: press_key key must be one of {', '.join(HID_KEYS)}")
        press_keys(udid, [HID_KEYS[key]] * int(action.get("count", 1)))
        time.sleep(post_delay)
    elif kind == "dismiss_keyboard":
        # Simulator keeps the software keyboard out of the app's AX tree, so there is no key to
        # find: tap the app's own button (a toolbar "Done") when named, else send Return.
        if "button" in action:
            node = resolve_node(udid, {"label": action["button"]}, timeout, optional_prompt_labels)
            tap_point(udid, *frame_center(node), post_delay)
        else:
            # The first Return can be spent accepting a QuickType/autocorrect suggestion; when the
            # keyboard's keys are still in the tree (an app's keyboard often is), send another.
            for _ in range(DISMISS_ATTEMPTS):
                press_keys(udid, [HID_KEYS["return"]])
                time.sleep(max(post_delay, 0.4))
                if not any(is_keyboard_key(node) for node in hierarchy(udid)):
                    break
    elif kind == "long_press":
        point = resolve_point(udid, action, timeout, optional_prompt_labels, f"action {index}: long_press")
        long_press(udid, *point, float(action.get("duration", 1.0)), post_delay)
    elif kind == "double_tap":
        point = resolve_point(udid, action, timeout, optional_prompt_labels, f"action {index}: double_tap")
        double_tap(udid, *point, post_delay)
    elif kind == "drag":
        start = resolve_point(udid, required(action, "from", f"action {index}"), timeout, optional_prompt_labels,
                              f"action {index}: drag 'from'")
        end = resolve_point(udid, required(action, "to", f"action {index}"), timeout, optional_prompt_labels,
                            f"action {index}: drag 'to'")
        hold_and_drag(udid, start, end, float(action.get("hold", 0.6)), float(action.get("duration", 0.8)), post_delay)
    elif kind in ("edge_swipe", "back"):
        edge = "left" if kind == "back" else action.get("edge", "left")
        if edge not in EDGE_FRACTIONS:
            raise FastUIError(f"action {index}: edge must be left, right, top or bottom")
        screen = screen_frame(hierarchy(udid))
        (fx0, fy0), (fx1, fy1) = EDGE_FRACTIONS[edge]
        drag(
            udid,
            (screen["x"] + screen["width"] * fx0, screen["y"] + screen["height"] * fy0),
            (screen["x"] + screen["width"] * fx1, screen["y"] + screen["height"] * fy1),
            float(action.get("duration", 0.5)), max(post_delay, 0.6),
        )
    elif kind == "pull_to_refresh":
        if has_selector(action):
            area = resolve_node(udid, selector_of(action), timeout, optional_prompt_labels).get("frame") or {}
            frame = {key: float(area.get(key, 0)) for key in ("x", "y", "width", "height")}
        else:
            frame = screen_frame(hierarchy(udid))
        x = frame["x"] + frame["width"] / 2
        drag(
            udid, (x, frame["y"] + frame["height"] * 0.25), (x, frame["y"] + frame["height"] * 0.75),
            float(action.get("duration", 0.8)), max(post_delay, 1.0),
        )
    elif kind == "set_switch":
        selector = selector_of(action)
        wanted = "1" if bool(required(action, "on", f"action {index}")) else "0"
        node = resolve_node(udid, selector, timeout, optional_prompt_labels, accept=is_switch)
        if str(node.get("AXValue")) != wanted:
            invalidate_hierarchy(udid)
            frame = node.get("frame") or {}
            x, y = switch_point(node)
            # The iOS 27 switch ignores AXe's taps, even `--tap-style physical`; measured on Xcode 27.0,
            # it flips only for a touch held about SWITCH_PRESS seconds (0.1 s did nothing).
            axe(udid, "touch", "-x", f"{x:.2f}", "-y", f"{y:.2f}", "--down", "--up", "--delay", str(SWITCH_PRESS))
            settle_tap(post_delay)
            # The same switch, found by where it was: its value is what changes.
            moved = {**{k: v for k, v in selector.items() if k != "value"}, "frame": {
                "min_x": float(frame.get("x", 0)) - 4, "max_x": float(frame.get("x", 0)) + 4,
                "min_y": float(frame.get("y", 0)) - 4, "max_y": float(frame.get("y", 0)) + 4,
            }}
            poll_until(
                udid,
                lambda nodes: None if any(matches(n, moved) and is_switch(n) and str(n.get("AXValue")) == wanted
                                          for n in nodes)
                else f"switch did not turn {'on' if wanted == '1' else 'off'}",
                timeout, optional_prompt_labels,
            )
            return {"toggled": True}
        return {"toggled": False}
    elif kind == "set_slider":
        percent = float(required(action, "percent", f"action {index}"))
        if not 0 <= percent <= 100:
            raise FastUIError(f"action {index}: percent must be 0-100")
        selector = selector_of(action)
        node = resolve_node(udid, selector, timeout, optional_prompt_labels, accept=is_slider)
        target = ["--id", node["AXUniqueId"]] if node.get("AXUniqueId") else ["--label", str(node.get("AXLabel") or "")]
        invalidate_hierarchy(udid)
        # AXe fails when a stepped slider snaps to a neighbouring step; correct by dragging the thumb.
        axe(udid, "slider", *target, "--element-type", "Slider", "--value", f"{percent:g}", check=False)
        tolerance = float(action.get("tolerance", 2))
        # Up to SLIDER_CORRECTIONS drags, each followed by a fresh read.
        for attempt in range(SLIDER_CORRECTIONS + 1):
            node = resolve_node(udid, selector, timeout, optional_prompt_labels, accept=is_slider)
            current = slider_percent(node)
            if current is None or abs(current - percent) <= tolerance or attempt == SLIDER_CORRECTIONS:
                break
            frame = node.get("frame") or {}
            left = float(frame.get("x", 0)) + SLIDER_THUMB_INSET
            travel = float(frame.get("width", 0)) - 2 * SLIDER_THUMB_INSET
            y = frame_center(node)[1]
            drag(udid, (left + travel * current / 100, y), (left + travel * percent / 100, y), 0.5, 0.4)
        if current is not None and abs(current - percent) > tolerance:
            raise FastUIError(f"slider is at {current:g}%, expected {percent:g}% (±{tolerance:g})")
        time.sleep(post_delay)
        return {"percent": current}
    elif kind == "set_picker":
        if "option" not in action and "index" not in action:
            raise FastUIError(f"action {index}: set_picker needs option (the row text) or index")
        selector = selector_of(action)
        limit = int(action.get("max_steps", 15))
        row = float(action.get("row_height", 34))
        # The wheel exposes only its current value: the row text for a UIPickerView, the row
        # index for a SwiftUI wheel (reported as a Slider). Step it one row at a time; for an
        # index the direction is known, for text search forwards, then back.
        wanted_index = int(action["index"]) if "index" in action else None
        directions = [None] * (2 * limit) if wanted_index is not None else ["up"] * limit + ["down"] * (2 * limit)
        for step, direction in enumerate([*directions, "stop"]):
            node = resolve_node(
                udid, selector, timeout, optional_prompt_labels,
                # An index wheel shows a whole number; that keeps a "0.5" slider out of the match.
                accept=lambda value: is_picker(value)
                and (wanted_index is None or ax_text(value).isdigit()),
            )
            current = ax_text(node)
            if wanted_index is not None:
                if current == str(wanted_index):
                    return {"steps": step}
                if current.isdigit() and direction != "stop":
                    direction = "up" if int(current) < wanted_index else "down"
            elif str(action["option"]) in current:
                return {"steps": step}
            if direction in (None, "stop"):
                wanted = action.get("option", action.get("index"))
                raise FastUIError(f"picker never showed '{wanted}'; it shows '{current}'")
            x, y = frame_center(node)
            drag(udid, (x, y), (x, y - row if direction == "up" else y + row), 0.4, 0.6)
    elif kind == "tap_alert":
        selector = {"label": required(action, "button", f"action {index}"), "element_type": "Button"}
        node = resolve_node(udid, selector, timeout, optional_prompt_labels)
        tap_point(udid, *frame_center(node), post_delay)
    elif kind == "assert_value":
        selector = selector_of(action)
        attribute = {"value": "AXValue", "label": "AXLabel"}.get(action.get("attribute", "value"))
        if attribute is None:
            raise FastUIError(f"action {index}: attribute must be value or label")
        check_text("", action, f"action {index}: assert_value")  # validates the keys up front

        def value_check(nodes: list[dict[str, Any]]) -> str | None:
            found = sort_nodes([node for node in nodes if matches(node, selector) and tappable(node)], ["y", "x"])
            if not found:
                return "no node matched the selector"
            failure = check_text(ax_text(found[0], attribute), action, "assert_value")
            return None if failure is None else f"{action.get('attribute', 'value')} {failure}"

        poll_until(udid, value_check, timeout, optional_prompt_labels)
    elif kind == "assert_count":
        selector = selector_of(action)
        if not any(key in action for key in ("count", "min", "max")):
            raise FastUIError(f"action {index}: assert_count needs count, min or max")
        seen: list[int] = [0]

        def count_check(nodes: list[dict[str, Any]]) -> str | None:
            seen[0] = len(deduped([node for node in nodes if matches(node, selector) and tappable(node)]))
            failure = count_failure(seen[0], action)
            return None if failure is None else f"{seen[0]} nodes matched, {failure}"

        poll_until(udid, count_check, timeout, optional_prompt_labels)
        return {"count": seen[0]}
    elif kind == "press_button":
        button = str(required(action, "button", f"action {index}"))
        if button not in SIMULATOR_BUTTONS:
            raise FastUIError(
                f"action {index}: Simulator buttons are {', '.join(SIMULATOR_BUTTONS)}"
                + ("; volume buttons need a physical iPhone" if button.startswith("volume") else "")
            )
        invalidate_hierarchy(udid)
        axe(udid, "button", SIMULATOR_BUTTONS[button], "--duration", str(action.get("duration", BUTTON_PRESS)))
        time.sleep(max(post_delay, 1.0))
    elif kind == "activate":
        app = action.get("app") or bundle_id
        if not app:
            raise FastUIError(f"action {index}: activate needs 'app'")
        # `simctl launch` brings a running app to the front without restarting it.
        command(["xcrun", "simctl", "launch", udid, app])
        invalidate_hierarchy(udid)
    elif kind == "set_appearance":
        mode = required(action, "appearance", f"action {index}")
        command(["xcrun", "simctl", "ui", udid, "appearance", mode])
        invalidate_hierarchy(udid)
    elif kind == "set_permission":
        verb = action.get("action")
        if verb not in ("grant", "revoke", "reset"):
            raise FastUIError(f"action {index}: set_permission needs action: grant, revoke or reset")
        service = required(action, "service", f"action {index}")
        app = action.get("app") or bundle_id
        command(["xcrun", "simctl", "privacy", udid, verb, service, *([app] if app else [])])
        invalidate_hierarchy(udid)
    elif kind == "set_location":
        if action.get("clear"):
            command(["xcrun", "simctl", "location", udid, "clear"])
        else:
            latitude = float(required(action, "latitude", f"action {index}"))
            longitude = float(required(action, "longitude", f"action {index}"))
            command(["xcrun", "simctl", "location", udid, "set", f"{latitude},{longitude}"])
    elif kind == "push_notification":
        app = action.get("app") or bundle_id
        if not app:
            raise FastUIError(f"action {index}: push_notification needs 'app'")
        payload = action.get("payload") or {"aps": {"alert": {
            "title": action.get("title", "Test"), "body": action.get("body", "")}}}
        try:
            simctl_with_input(["xcrun", "simctl", "push", udid, app, "-"], json.dumps(payload))
        except FastUIError as error:
            if "not authorized" not in str(error):
                raise
            raise FastUIError(
                f"{error} — the app has not been granted notification permission yet: let it ask "
                "(and add \"Allow\" to setup.optional_permission_labels) before pushing"
            ) from None
        invalidate_hierarchy(udid)
    elif kind == "status_bar":
        if action.get("clear"):
            command(["xcrun", "simctl", "status_bar", udid, "clear"])
        else:
            flags = [part for key, flag in STATUS_BAR_FLAGS.items() if key in action for part in (flag, str(action[key]))]
            if not flags:
                raise FastUIError(f"action {index}: status_bar needs clear or one of {', '.join(STATUS_BAR_FLAGS)}")
            command(["xcrun", "simctl", "status_bar", udid, "override", *flags])
    elif kind == "set_clipboard":
        text = str(required(action, "text", f"action {index}"))
        simctl_with_input(["xcrun", "simctl", "pbcopy", udid], text)
        # On Xcode 27.0 / iOS 27 `simctl pbcopy` exits 0 and the device pasteboard stays empty
        # (`pbsync host` too); say so instead of letting a later paste fail obscurely.
        deadline = time.perf_counter() + min(timeout, 3.0)
        while command(["xcrun", "simctl", "pbpaste", udid]).stdout != text:
            if time.perf_counter() >= deadline:
                raise FastUIError(
                    "simctl pbcopy did not reach the simulator's pasteboard (seen on Xcode 27.0 / iOS 27); "
                    "set_clipboard works on Xcode 26 simulators and on a physical iPhone"
                )
            time.sleep(0.3)
    elif kind == "assert_clipboard":
        # The device pasteboard syncs a moment after `pbcopy` or an in-app copy; poll it.
        deadline = time.perf_counter() + timeout
        while True:
            actual = command(["xcrun", "simctl", "pbpaste", udid]).stdout
            failure = check_text(actual, action, f"action {index}: assert_clipboard")
            if not failure:
                break
            if time.perf_counter() >= deadline:
                raise FastUIError(f"clipboard {failure} after {timeout:g}s")
            time.sleep(0.3)
    elif kind in DEVICE_ONLY:
        raise FastUIError(
            f"action {index}: {kind} needs {DEVICE_ONLY[kind]}, which Simulator cannot do through AXe; "
            "run it with fastDeviceTest on a physical iPhone"
        )
    elif kind in ("launch", "terminate"):
        app = action.get("app") or bundle_id
        if not app:
            raise FastUIError(f"action {index}: {kind} needs 'app'")
        if kind == "launch":
            arguments = [str(value) for value in action.get("launch_arguments", [])]
            command(["xcrun", "simctl", "launch", udid, app, *arguments])
        else:
            command(["xcrun", "simctl", "terminate", udid, app], check=False)
        invalidate_hierarchy(udid)
    elif kind == "open_url":
        command(["xcrun", "simctl", "openurl", udid, required(action, "url", f"action {index}")])
        invalidate_hierarchy(udid)
    else:
        raise FastUIError(f"unsupported action type '{kind}'")
    return None


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a compact JSON-driven iOS Simulator UI flow.")
    parser.add_argument("flow", type=Path, help="Path to a fastUITest JSON file")
    parser.add_argument("--reuse-app", action="store_true", help="Skip source freshness checks")
    parser.add_argument(
        "--build-only", action="store_true",
        help="Build/refresh the cached app and exit without installing or running actions",
    )
    parser.add_argument(
        "--record", action="store_true",
        help="Record the simulator screen; a PASS keeps <artifacts-root>/<task>/final[-<session>].mp4",
    )
    parser.add_argument(
        "--artifacts-root", type=Path, default=os.environ.get("FAST_UI_ROOT") or None,
        help="Where runs, screenshots and videos go (default <project_root>/build/fast-ui; env FAST_UI_ROOT)",
    )
    parser.add_argument(
        "--session", default=os.environ.get("FAST_UI_SESSION", ""),
        help="Group this run under a fan-out session; fast_ui_report.py collates by it",
    )
    parser.add_argument(
        "--keep-state", action="store_true",
        help="Leave the seeded setup.preferences in place after the run (default: remove them)",
    )
    parser.add_argument(
        "--appearance", choices=sorted(UI_SETTINGS["appearance"]),
        help="Run as a matrix variant in this appearance (overrides setup.appearance; task name gets @<value>)",
    )
    parser.add_argument(
        "--content-size", choices=list(UI_SETTINGS["content_size"]),
        help="Run as a Dynamic Type variant (overrides setup.content_size; task name gets @<short size>)",
    )
    parser.add_argument("--json", action="store_true", help="Print the complete result JSON")
    parser.add_argument("--artifacts", type=Path, help="Override the artifact directory")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    flow_path = args.flow.expanduser().resolve()
    try:
        spec = json.loads(flow_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FastUIError(f"cannot read flow {flow_path}: {error}") from error
    if spec.get("version") != 1:
        raise FastUIError("flow version must be 1")

    base = flow_path.parent
    app = required(spec, "app", "flow")
    setup = spec.get("setup", {})
    variant = ui_variant(setup, args.appearance, args.content_size)
    name = variant_name(required(spec, "name", "flow"), variant)
    udid = required(app, "simulator", "app")
    bundle_id = required(app, "bundle_id", "app")
    # A prebuilt app is driven as installed; a fresh install needs an .app to put back.
    fresh_install = bool(setup.get("fresh_install", not app.get("prebuilt")))
    if fresh_install and app.get("prebuilt") and not app.get("app_path"):
        raise FastUIError("prebuilt app without app_path cannot be fresh-installed")
    project_root = resolved_path(app.get("project_root", "."), base)
    artifacts_root = (
        Path(args.artifacts_root).expanduser().resolve()
        if args.artifacts_root
        else project_root / "build/fast-ui"
    )
    artifacts = (
        args.artifacts.expanduser().resolve()
        if args.artifacts
        else artifacts_root / name
        / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{udid[:8]}-{os.getpid()}"
    )
    prune_artifacts(artifacts_root, float(os.environ.get("FAST_UI_KEEP_DAYS", "3")))
    artifacts.mkdir(parents=True, exist_ok=True)
    metrics = Metrics()
    results: list[dict[str, Any]] = []
    built = False
    current_step = "prepare"
    recorder = Recorder(udid, artifacts / "run.mp4") if args.record else None
    video: Path | None = None
    labels_per_step: list[dict[str, Any]] = []
    previous_ui: dict[str, str] = {}

    try:
        with metrics.measure("prepare"):
            app_path, built = prepare_app(app, base, udid, args.reuse_app)
        if args.build_only:
            location = file_link(app_path) if app_path else "installed"
            print(f"READY task={name} build={'yes' if built else 'skip'} app={location} total={metrics.total:.1f}s")
            return 0
        if fresh_install:
            current_step = "fresh_install"
            with metrics.measure(current_step):
                command(["xcrun", "simctl", "uninstall", udid, bundle_id], check=False)
                # `defaults write` lands in the simulator's user domain, which an
                # uninstall leaves behind; without this wipe one flow's state leaks
                # into the next fresh install.
                command(["xcrun", "simctl", "spawn", udid, "defaults", "delete", bundle_id], check=False)
                command(["xcrun", "simctl", "install", udid, str(app_path)])
        current_step = "state_and_launch"
        with metrics.measure(current_step):
            apply_ui_settings(udid, variant, previous_ui)
            set_preferences(udid, bundle_id, setup.get("preferences", {}))
            if recorder:
                recorder.start()
            launch = ["xcrun", "simctl", "launch", udid, bundle_id]
            launch += [str(value) for value in setup.get("launch_arguments", [])]
            command(launch)

        optional_prompt_labels = setup.get("optional_permission_labels", [])
        defaults = {"settle": True} if setup.get("settle_after_actions") else {}
        for index, action in enumerate(required(spec, "actions", "flow"), start=1):
            current_step = f"{index:02d}_{action.get('type', 'unknown')}"
            with metrics.measure(current_step):
                result = execute_action(
                    action, udid, artifacts, index, optional_prompt_labels, defaults, bundle_id
                )
            if recorder:
                labels_per_step.append(step_labels(udid, current_step, recorder.elapsed(), result))
            if result:
                results.append({"step": index, **result})

        if recorder:
            recorder.stop()
            video = publish_video(artifacts.parent, shrink_video(recorder.path), passed=True, session=args.session)
        payload = {
            "status": "pass", "task": name, "simulator": udid, "session": args.session,
            **({"expect": spec["expect"]} if spec.get("expect") else {}),
            **({"variant": variant} if variant else {}),
            "built": built, "total_seconds": metrics.total,
            "steps_seconds": metrics.steps, "results": results, "artifacts": str(artifacts),
            **({"step_labels": labels_per_step} if recorder else {}),
            **({"video": str(video)} if video else {}),
        }
        (artifacts / "metrics.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            motion = next((result.get("motion_ratio") for result in reversed(results) if "motion_ratio" in result), None)
            suffix = f" motion={motion:.6f}" if motion is not None else ""
            dumps = [result for result in results if "labels" in result]
            if dumps:
                suffix += f" labels={json.dumps(dumps[-1]['labels'], ensure_ascii=False)}"
            if video:
                suffix += f" video={file_link(video)}"
            print(f"PASS task={name} total={metrics.total:.1f}s build={'yes' if built else 'skip'}{suffix} artifacts={file_link(artifacts)}")
        return 0
    except (FastUIError, OSError, subprocess.TimeoutExpired) as error:
        failed_at = recorder.elapsed() if recorder else 0.0
        if recorder:
            try:
                recorder.stop()
                video = publish_video(artifacts.parent, shrink_video(recorder.path), passed=False, session=args.session)
            except Exception:
                video = None
        try:
            screenshot(udid, artifacts / "failure.png")
            failure_nodes = hierarchy(udid)
            write_dump(artifacts / "failure-ui.json", failure_nodes)
            if recorder and recorder.started is not None:
                labels_per_step.append(
                    {"step": current_step, "at": round(failed_at, 2), "labels": visible_labels(failure_nodes)}
                )
        except Exception:
            pass
        payload = {
            "status": "fail", "task": name, "simulator": udid, "session": args.session,
            **({"expect": spec["expect"]} if spec.get("expect") else {}),
            **({"variant": variant} if variant else {}),
            "step": current_step, "error": str(error),
            "built": built, "total_seconds": metrics.total, "steps_seconds": metrics.steps,
            "results": results, "artifacts": str(artifacts),
            **({"step_labels": labels_per_step} if recorder else {}),
            **({"video": str(video)} if video else {}),
        }
        (artifacts / "metrics.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            video_suffix = f" video={file_link(video)}" if video else ""
            print(f"FAIL task={name} step={current_step} total={metrics.total:.1f}s error={error}{video_suffix} artifacts={file_link(artifacts)}", file=sys.stderr)
        return 1
    finally:
        restore_ui_settings(udid, previous_ui)
        if not args.build_only and not args.keep_state:
            reset_preferences(udid, bundle_id, setup.get("preferences", {}), fresh_install)


if __name__ == "__main__":
    raise SystemExit(main())
