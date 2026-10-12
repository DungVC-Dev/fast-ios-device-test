#!/usr/bin/env python3

"""Run compact, data-driven iOS Simulator UI flows."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from PIL import Image, ImageChops


BUILD_SUFFIXES = {
    ".c", ".cc", ".cpp", ".entitlements", ".gif", ".h", ".jpeg", ".jpg",
    ".json", ".m", ".mm", ".mp3", ".mp4", ".otf", ".pbxproj", ".pdf",
    ".plist", ".png", ".strings", ".swift", ".ttf", ".wav", ".xcconfig",
    ".xcprivacy", ".xcstrings", ".xib",
}


class FastUIError(RuntimeError):
    pass


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


def axe(udid: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    arguments = ["axe", *args, "--udid", udid]
    result = command(arguments, check=False)
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


def flatten(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from flatten(child)
    elif isinstance(value, list):
        for child in value:
            yield from flatten(child)


DESCRIBE_UI_ATTEMPTS = 3


def hierarchy(udid: str) -> list[dict[str, Any]]:
    # AXe occasionally fails once right after launch while the accessibility
    # server is still coming up; one failed poll must not fail the whole flow.
    last_error: Exception | None = None
    for attempt in range(DESCRIBE_UI_ATTEMPTS):
        try:
            result = axe(udid, "describe-ui")
            return list(flatten(json.loads(result.stdout)))
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


def matches(node: dict[str, Any], selector: dict[str, Any]) -> bool:
    label = selector.get("label")
    if label is not None and node.get("AXLabel") != label:
        return False
    if selector.get("label_is_empty") and node.get("AXLabel"):
        return False
    fragment = selector.get("label_contains")
    if fragment is not None and fragment not in str(node.get("AXLabel") or ""):
        return False
    expected_type = selector.get("element_type")
    if expected_type is not None and node_type(node) != expected_type:
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
) -> list[dict[str, Any]]:
    deadline = time.perf_counter() + timeout
    nodes: list[dict[str, Any]] = []
    while time.perf_counter() < deadline:
        nodes = hierarchy(udid)
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
    labels = ", ".join(visible_labels(nodes, limit=25))
    raise FastUIError(f"timed out waiting for UI selector; visible labels: [{labels}]")


def wait_selector(
    udid: str,
    selector: dict[str, Any],
    timeout: float,
    optional_prompt_labels: list[str],
) -> list[dict[str, Any]]:
    return wait_nodes(
        udid,
        lambda nodes: any(matches(node, selector) for node in nodes),
        timeout,
        optional_prompt_labels,
    )


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


def swipe_points(action: dict[str, Any], nodes: list[dict[str, Any]], index: int) -> tuple[list[float], list[float]]:
    """`from`/`to` points, or a `direction` the finger moves in ("up" scrolls content down)."""
    if "direction" not in action:
        return required(action, "from", f"action {index}"), required(action, "to", f"action {index}")
    # The application node spans the whole screen, so the largest frame is the screen.
    screen = max(
        ((node.get("frame") or {}) for node in nodes),
        key=lambda frame: float(frame.get("width", 0)) * float(frame.get("height", 0)),
        default={},
    )
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
            labels = visible_labels(hierarchy(udid))
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


def publish_video(task_dir: Path, video: Path, passed: bool, session: str = "") -> Path | None:
    """Keep exactly one final video per task (per session when tagged); failures keep only their own clip."""
    if not video.exists():
        return None
    for old in task_dir.glob("*/run.mp4"):
        if old != video:
            old.unlink(missing_ok=True)
    if not passed:
        return video
    final = task_dir / (f"final-{session}.mp4" if session else "final.mp4")
    shutil.move(str(video), final)
    return final


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


def prepare_app(app: dict[str, Any], base: Path, udid: str, reuse_app: bool) -> tuple[Path, bool]:
    ensure_booted(udid)
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


def execute_action(
    action: dict[str, Any],
    udid: str,
    artifacts: Path,
    index: int,
    optional_prompt_labels: list[str],
) -> dict[str, Any] | None:
    kind = required(action, "type", f"action {index}")
    timeout = float(action.get("timeout", 6))
    post_delay = float(action.get("post_delay", 0.15))

    if kind == "wait":
        wait_selector(udid, action, timeout, optional_prompt_labels)
    elif kind == "tap_label":
        label = required(action, "label", f"action {index}")
        selector = {"label": label, "element_type": action.get("element_type", "Button")}
        if action.get("optional", False):
            candidates = [node for node in hierarchy(udid) if matches(node, selector)]
        else:
            # One hierarchy poll resolves the control (and dismisses any
            # permission alert in the way); tapping its frame avoids a second
            # label lookup inside `axe tap --label`.
            nodes = wait_selector(udid, selector, timeout, optional_prompt_labels)
            candidates = [node for node in nodes if matches(node, selector)]
        if candidates:
            tap_point(udid, *frame_center(sort_nodes(candidates, ["y", "x"])[0]), post_delay)
    elif kind == "wait_absent":
        wait_absent(udid, action, timeout, optional_prompt_labels)
    elif kind == "assert_absent":
        assert_absent(udid, action, float(action.get("seconds", 3)), optional_prompt_labels)
    elif kind == "dump":
        nodes = wait_nodes(udid, lambda _: True, timeout, optional_prompt_labels)
        name = action.get("name", f"step-{index:02d}")
        path = artifacts / f"{name}-ui.json"
        path.write_text(json.dumps(nodes, indent=2) + "\n", encoding="utf-8")
        return {"path": str(path), "labels": visible_labels(nodes)}
    elif kind == "pause":
        time.sleep(float(action.get("seconds", 1)))
    elif kind == "tap_point":
        tap_point(udid, float(action["x"]), float(action["y"]), post_delay)
    elif kind == "swipe":
        nodes = hierarchy(udid) if "direction" in action else []
        swipe(udid, *swipe_points(action, nodes, index), float(action.get("duration", 0.3)), post_delay)
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
        nodes = wait_selector(udid, action, timeout, optional_prompt_labels)
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
            print(f"READY task={name} build={'yes' if built else 'skip'} app={file_link(app_path)} total={metrics.total:.1f}s")
            return 0
        if setup.get("fresh_install", True):
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
        for index, action in enumerate(required(spec, "actions", "flow"), start=1):
            current_step = f"{index:02d}_{action.get('type', 'unknown')}"
            with metrics.measure(current_step):
                result = execute_action(
                    action, udid, artifacts, index, optional_prompt_labels
                )
            if recorder:
                labels_per_step.append(step_labels(udid, current_step, recorder.elapsed(), result))
            if result:
                results.append({"step": index, **result})

        if recorder:
            recorder.stop()
            video = publish_video(artifacts.parent, recorder.path, passed=True, session=args.session)
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
                video = publish_video(artifacts.parent, recorder.path, passed=False, session=args.session)
            except Exception:
                video = None
        try:
            screenshot(udid, artifacts / "failure.png")
            failure_nodes = hierarchy(udid)
            (artifacts / "failure-ui.json").write_text(
                json.dumps(failure_nodes, indent=2) + "\n", encoding="utf-8"
            )
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
            reset_preferences(
                udid, bundle_id, setup.get("preferences", {}), setup.get("fresh_install", True)
            )


if __name__ == "__main__":
    raise SystemExit(main())
