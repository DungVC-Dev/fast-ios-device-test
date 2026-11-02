#!/usr/bin/env python3
"""Drive one mixed phone + CarPlay JSON flow on Simulator or a USB iPhone.

Phone actions are delegated to fast_ui / fast_device.  The CarPlay surface is deliberately
separate: Simulator.app is driven by one persistent baguette input process, while Apple's
standalone CarPlay Simulator is captured and clicked as a macOS window.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import fast_device  # noqa: E402
import fast_guard  # noqa: E402
import fast_ui  # noqa: E402


DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 720
DEFAULT_SCALE = 2
DISPLAY_PRESETS: dict[str, tuple[int, int, float]] = {
    "widescreen": (1920, 720, 2),
    "standard": (800, 480, 2),
    "hd": (1280, 720, 2),
}
CAR_TYPES = {
    "car_tap", "car_swipe", "car_screenshot", "car_wait_stable",
    "carplay_connect", "carplay_disconnect",
}
HARDWARE_APPS = (
    Path("/Volumes/Additional Tools/Hardware/CarPlay Simulator.app"),
    Path("/Applications/CarPlay Simulator.app"),
)
BAGUETTE_INSTALL_HINT = "run ./install.sh --install-baguette"


class CarPlayError(RuntimeError):
    pass


def run(command: list[str], *, check: bool = True, timeout: float = 60,
        input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, input=input_text, text=True, capture_output=True,
                              check=check, timeout=timeout)
    except FileNotFoundError as error:
        raise CarPlayError(f"command not found: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error)).strip()
        raise CarPlayError(f"{' '.join(command)}: {detail}") from error


def file_link(path: Path) -> str:
    return path.resolve().as_uri()


def load_flow(path: Path) -> dict[str, Any]:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CarPlayError(f"cannot read flow {path}: {error}") from error
    if spec.get("version") != 1:
        raise CarPlayError("flow version must be 1")
    if not spec.get("name"):
        raise CarPlayError("flow needs name")
    actions = spec.get("actions")
    if not isinstance(actions, list) or not actions:
        raise CarPlayError("flow needs a non-empty actions array")
    phone = []
    for index, action in enumerate(actions, 1):
        if not isinstance(action, dict):
            raise CarPlayError(f"step {index} must be an object")
        surface = action.get("surface", "phone")
        if surface not in ("phone", "car"):
            raise CarPlayError(f"step {index}: surface must be phone or car")
        if surface == "car":
            if action.get("type") not in CAR_TYPES:
                raise CarPlayError(f"step {index}: unsupported car action {action.get('type')!r}")
            if not (action.get("name") or action.get("comment")):
                raise CarPlayError(f"step {index}: every car action needs name or comment")
        else:
            clean = {key: value for key, value in action.items() if key != "surface"}
            phone.append(clean)
    try:
        fast_guard.check_actions(phone)
    except ValueError as error:
        raise CarPlayError(str(error)) from error
    return spec


def parse_display(value: str) -> tuple[str, int, int, float]:
    key = value.strip().lower()
    if key in DISPLAY_PRESETS:
        width, height, scale = DISPLAY_PRESETS[key]
        return key, width, height, float(scale)
    match = re.fullmatch(r"(\d+)x(\d+)@([0-9]+(?:\.[0-9]+)?)", key)
    if not match:
        raise CarPlayError("display must be widescreen, standard, hd, or WxH@S (for example 720x480@1)")
    width, height, scale = int(match.group(1)), int(match.group(2)), float(match.group(3))
    if width < 320 or height < 240 or scale <= 0:
        raise CarPlayError("custom display must be at least 320x240 with scale > 0")
    scale_text = str(int(scale)) if scale.is_integer() else str(scale)
    return f"{width}x{height}@{scale_text}", width, height, scale


def flow_display(spec: dict[str, Any], override: str | None) -> tuple[str, int, int, float]:
    if override:
        return parse_display(override)
    setup = spec.get("setup", {})
    configured = setup.get("carplay_display", "widescreen")
    if "carplay_size" in setup and "carplay_display" not in setup:
        size = setup["carplay_size"]
        if not isinstance(size, list) or len(size) != 3:
            raise CarPlayError("setup.carplay_size must be [width, height, scale]")
        configured = f"{size[0]}x{size[1]}@{size[2]}"
    return parse_display(str(configured))


def simctl_devices() -> list[dict[str, Any]]:
    payload = json.loads(run(["xcrun", "simctl", "list", "devices", "available", "--json"]).stdout)
    return [device for devices in payload.get("devices", {}).values() for device in devices]


def resolve_simulator(value: str | None) -> dict[str, Any]:
    if not value:
        raise CarPlayError("sim target needs --udid or app.simulator")
    matches = [device for device in simctl_devices()
               if device.get("udid") == value or device.get("name") == value]
    if len(matches) != 1:
        raise CarPlayError(f"simulator {value!r} matched {len(matches)} available devices")
    if not str(matches[0].get("name", "")).startswith("agent-tmp-"):
        raise CarPlayError("CarPlay runs only on disposable simulators named agent-tmp-*")
    return matches[0]


def simulator_runtime(udid: str) -> str:
    result = run(["xcrun", "simctl", "list", "devices", "available", "--json"])
    payload = json.loads(result.stdout)
    for runtime, devices in payload.get("devices", {}).items():
        if any(device.get("udid") == udid for device in devices):
            return runtime
    return ""


def display_plist(udid: str) -> Path:
    return (Path.home() / "Library/Developer/CoreSimulator/Devices" / udid / "data/Library"
            / "Application Support/Simulator/extended_display.plist")


def armed_display(udid: str) -> tuple[bool, str]:
    path = display_plist(udid)
    try:
        data = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return False, f"missing or invalid {path}"
    if not data.get("stark"):
        return False, "extended display exists but stark=false"
    try:
        scale = f"{float(data.get('scale')):g}"
    except (TypeError, ValueError):
        return False, "extended display has an invalid scale"
    size = f"{data.get('width')}x{data.get('height')}@{scale}"
    return True, size


def baguette_path() -> str:
    explicit = os.environ.get("FAST_IOS_BAGUETTE")
    if explicit:
        path = Path(explicit).expanduser()
        return str(path.resolve()) if path.is_file() and os.access(path, os.X_OK) else ""
    candidates = []
    if os.environ.get("FAST_IOS_BAGUETTE_DIR"):
        candidates.append(Path(os.environ["FAST_IOS_BAGUETTE_DIR"]).expanduser() / "baguette")
    candidates.append(Path.home() / ".local/share/baguette/baguette")
    if os.environ.get("FAST_IOS_BIN_DIR"):
        candidates.append(Path(os.environ["FAST_IOS_BIN_DIR"]).expanduser() / "baguette")
    candidates.append(Path.home() / ".local/bin/baguette")
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
    return shutil.which("baguette") or ""


def baguette_version(binary: str | None = None) -> str:
    binary = binary or baguette_path()
    if not binary:
        return ""
    result = run([binary, "--version"], check=False)
    return (result.stdout or result.stderr).strip().splitlines()[0] if result.returncode == 0 else "unknown"


class BaguetteInput:
    """One input process for the whole flow; warm it because its first event is often lost."""

    def __init__(self, udid: str, width: int, height: int) -> None:
        self.udid, self.width, self.height = udid, width, height
        self.binary = baguette_path()
        self.process: subprocess.Popen[str] | None = None

    def _start(self) -> None:
        self.process = subprocess.Popen(
            [self.binary, "input", "--udid", self.udid, "--display", "carplay", "--require-existing-display"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            bufsize=1,
        )

    def __enter__(self) -> "BaguetteInput":
        self._start()
        self.send({"type": "tap", "x": 1, "y": 1, "width": self.width, "height": self.height})
        return self

    def _write(self, event: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin or self.process.poll() is not None:
            raise CarPlayError("baguette input session stopped")
        self.process.stdin.write(json.dumps(event, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        streams = [stream for stream in (self.process.stdout, self.process.stderr) if stream]
        deadline = time.monotonic() + 3
        diagnostics: list[str] = []
        acknowledgement = ""
        while time.monotonic() < deadline:
            ready = select.select(streams, [], [], max(0, deadline - time.monotonic()))[0]
            if self.process.stdout and self.process.stdout in ready:
                acknowledgement = self.process.stdout.readline().strip()
                break
            if self.process.stderr and self.process.stderr in ready:
                diagnostic = self.process.stderr.readline().strip()
                if diagnostic:
                    diagnostics.append(diagnostic)
                continue
            break
        if not acknowledgement:
            detail = f": {'; '.join(diagnostics)}" if diagnostics else ""
            raise CarPlayError(f"baguette input produced no acknowledgement{detail}")
        try:
            payload = json.loads(acknowledgement)
        except json.JSONDecodeError:
            payload = {}
        if payload.get("ok") is False or payload.get("error"):
            raise CarPlayError(f"baguette input: {payload.get('error') or acknowledgement}")

    def send(self, event: dict[str, Any], *, retry: bool = True) -> None:
        try:
            self._write(event)
        except CarPlayError:
            if not retry:
                raise
            run([self.binary, "heal", "--udid", self.udid], check=False, timeout=30)
            reattach_sim_carplay_window()
            self._stop()
            self._start()
            self._write(event)

    def _stop(self) -> None:
        if not self.process:
            return
        if self.process.stdin:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        try:
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        pass
        except (OSError, ProcessLookupError):
            pass
        finally:
            self.process = None

    def __exit__(self, *_: object) -> None:
        self._stop()


def coordinate(value: Any, extent: int, label: str) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise CarPlayError(f"{label} must be a number") from error
    if 0 <= number <= 1:
        number *= extent
    if number < 0 or number > extent:
        raise CarPlayError(f"{label}={number:g} is outside 0..{extent}")
    return round(number)


def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise CarPlayError(f"baguette returned an invalid PNG: {path}")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def baguette_screenshot(udid: str, output: Path, expected_size: tuple[int, int] | None = None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    binary = baguette_path()
    if not binary:
        raise CarPlayError(f"baguette is missing; {BAGUETTE_INSTALL_HINT}")
    command = [binary, "screenshot", "--udid", udid, "--display", "carplay", "-o", str(output)]
    result = run(command, check=False, timeout=30)
    if result.returncode and "no CarPlay framebuffer is attached" in (result.stderr + result.stdout):
        run([binary, "heal", "--udid", udid], check=False, timeout=30)
        reattach_sim_carplay_window()
        result = run(command, check=False, timeout=30)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise CarPlayError(f"{' '.join(command)}: {detail}")
    if not output.exists() or output.stat().st_size == 0:
        raise CarPlayError("baguette returned no CarPlay screenshot")
    if expected_size:
        actual = png_size(output)
        if actual != expected_size:
            raise CarPlayError(
                f"CarPlay framebuffer is {actual[0]}x{actual[1]}, requested "
                f"{expected_size[0]}x{expected_size[1]}; close and re-arm the CarPlay display"
            )


def stable_screenshot(capture: Any, folder: Path, stem: str, timeout: float) -> Path:
    previous: bytes | None = None
    deadline = time.monotonic() + timeout
    count = 0
    while True:
        path = folder / f".{stem}-{count}.png"
        capture(path)
        current = path.read_bytes()
        path.unlink(missing_ok=True)
        if previous == current:
            final = folder / f"{stem}.png"
            final.write_bytes(current)
            return final
        if time.monotonic() >= deadline:
            raise CarPlayError(f"CarPlay screen did not stabilize in {timeout:g}s")
        previous = current
        count += 1
        time.sleep(0.5)


WINDOW_HELPER = r'''
import Cocoa
import CoreGraphics

func window() -> [String: Any]? {
  let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
  guard let rows = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] else { return nil }
  return rows.first { row in
    let owner = row[kCGWindowOwnerName as String] as? String ?? ""
    let name = row[kCGWindowName as String] as? String ?? ""
    let isCar = owner == "CarPlay Simulator"
    return isCar && !name.isEmpty && (row[kCGWindowLayer as String] as? Int ?? 1) == 0
  }
}
if CommandLine.arguments.count > 1 && CommandLine.arguments[1] == "window", let row = window(),
   let bounds = row[kCGWindowBounds as String] as? [String: Any] {
  let out: [String: Any] = ["id": row[kCGWindowNumber as String]!, "name": row[kCGWindowName as String] ?? "",
    "x": bounds["X"]!, "y": bounds["Y"]!, "width": bounds["Width"]!, "height": bounds["Height"]!]
  let data = try! JSONSerialization.data(withJSONObject: out)
  print(String(data: data, encoding: .utf8)!)
} else if CommandLine.arguments.count == 4 && CommandLine.arguments[1] == "tap" {
  let p = CGPoint(x: Double(CommandLine.arguments[2])!, y: Double(CommandLine.arguments[3])!)
  CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
  CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
  usleep(70000)
  CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
} else { exit(2) }
'''


def window_helper() -> Path:
    cache = Path.home() / "Library/Caches/fast-ios-device-test/carplay"
    cache.mkdir(parents=True, exist_ok=True)
    source, binary = cache / "window.swift", cache / "window-helper"
    current = source.read_text(encoding="utf-8") if source.exists() else ""
    if not binary.exists() or current != WINDOW_HELPER:
        source.write_text(WINDOW_HELPER, encoding="utf-8")
        run(["xcrun", "swiftc", "-framework", "Cocoa", "-framework", "CoreGraphics",
             str(source), "-o", str(binary)], timeout=120)
    return binary


def hardware_window() -> dict[str, Any]:
    result = run([str(window_helper()), "window"], check=False)
    if result.returncode or not result.stdout.strip():
        raise CarPlayError("CarPlay Simulator window not found; open a session first")
    return json.loads(result.stdout)


def hardware_capture(output: Path) -> None:
    info = hardware_window()
    output.parent.mkdir(parents=True, exist_ok=True)
    run(["screencapture", "-x", "-l", str(info["id"]), str(output)], timeout=30)
    if not output.exists() or output.stat().st_size == 0:
        raise CarPlayError("CarPlay Simulator window capture failed")


def hardware_tap(x: float, y: float, *, normalized: bool = False) -> None:
    info = hardware_window()
    width, height = float(info["width"]), float(info["height"])
    px = x * width if normalized or 0 <= x <= 1 else x
    py = y * height if normalized or 0 <= y <= 1 else y
    if not (0 <= px <= width and 0 <= py <= height):
        raise CarPlayError("car tap is outside the CarPlay Simulator window")
    run([str(window_helper()), "tap", str(float(info["x"]) + px), str(float(info["y"]) + py)])


def carplay_ui_text() -> str:
    script = r'''tell application "System Events" to tell process "CarPlay Simulator"
if not (exists window 1) then return ""
set frontmost to true
set xs to entire contents of window 1
set out to ""
repeat with x in xs
try
set out to out & " " & (name of x as text) & " " & (description of x as text) & " " & (value of x as text)
end try
end repeat
return out
end tell'''
    result = run(["osascript", "-e", script], check=False, timeout=30)
    return (result.stdout + " " + result.stderr).strip()


def hardware_disconnected() -> bool:
    text = carplay_ui_text().lower()
    return "automaker ui" in text or ("disconnected" in text and "connected" not in text.replace("disconnected", ""))


def toggle_connection(want_connected: bool) -> None:
    wanted = "Disconnected" if want_connected else "Connected"
    script = f'''tell application "System Events" to tell process "CarPlay Simulator"
set frontmost to true
set xs to entire contents of window 1
repeat with x in xs
try
set blob to (name of x as text) & " " & (description of x as text) & " " & (value of x as text)
if blob contains "{wanted}" then click x
end try
end repeat
end tell'''
    result = run(["osascript", "-e", script], check=False, timeout=30)
    if result.returncode:
        raise CarPlayError(f"could not click the {wanted} CarPlay toggle: {result.stderr.strip()}")
    time.sleep(2)


def hardware_app() -> Path | None:
    return next((path for path in HARDWARE_APPS if path.exists()), None)


def connected_iphones() -> list[dict[str, Any]]:
    try:
        devices = fast_device.physical_devices()
    except fast_device.FastDeviceError:
        return []
    return [device for device in devices if device.get("connected")]


def check_line(level: str, name: str, detail: str, fix: str = "") -> tuple[str, str, str, str]:
    suffix = f"; fix: {fix}" if fix and level != "OK" else ""
    print(f"{level} {name}: {detail}{suffix}")
    return level, name, detail, fix


def doctor(target: str, udid: str | None, device: str | None, display: str) -> int:
    checks: list[tuple[str, str, str, str]] = []
    if target == "sim":
        simulator_app = Path("/Applications/Xcode.app/Contents/Developer/Applications/Simulator.app")
        checks.append(check_line("OK" if simulator_app.exists() else "FAIL", "xcode-26.6-simulator",
                                 str(simulator_app) if simulator_app.exists() else "not found",
                                 "install/select Xcode 26.6 at /Applications/Xcode.app"))
        version = run(["/usr/bin/xcodebuild", "-version"], check=False).stdout.splitlines()
        actual = version[0] if version else "unknown"
        level = "OK" if re.search(r"Xcode 26\.6(?:\D|$)", actual) else "WARN"
        checks.append(check_line(level, "xcode-version", actual,
                                 "CarPlay needs Xcode 26.6 Simulator.app; the build toolchain may remain Xcode 27"))
        devices = simctl_devices()
        ios265 = any("iOS-26-5" in simulator_runtime(str(item.get("udid"))) for item in devices)
        checks.append(check_line("OK" if ios265 else "FAIL", "runtime", "iOS 26.5 available" if ios265 else "iOS 26.5 missing",
                                 "install the iOS 26.5 Simulator runtime"))
        chosen = None
        if udid:
            try:
                chosen = resolve_simulator(udid)
                checks.append(check_line("OK", "simulator-name", f"{chosen['name']} ({chosen['udid']})"))
                expected = parse_display(display)
                armed, detail = armed_display(str(chosen["udid"]))
                wanted = f"{expected[1]}x{expected[2]}@{expected[3]:g}"
                exact = armed and detail == wanted
                checks.append(check_line("OK" if exact else "FAIL", "display-armed",
                                         detail if armed else detail,
                                         f"arm preset {expected[0]} ({wanted}) with setup.carplay_arm_script"))
            except CarPlayError as error:
                checks.append(check_line("FAIL", "simulator-name", str(error), "create an agent-tmp-* simulator"))
        else:
            candidates = [item for item in devices if str(item.get("name", "")).startswith("agent-tmp-")]
            checks.append(check_line("OK" if candidates else "WARN", "simulator-name",
                                     f"{len(candidates)} agent-tmp-* simulator(s)" if candidates else "no target selected",
                                     "pass --udid after creating an agent-tmp-* simulator"))
        binary = baguette_path()
        version = baguette_version(binary)
        checks.append(check_line("OK" if binary else "FAIL", "baguette",
                                 f"{version or 'unknown'} ({binary})" if binary else "missing",
                                 f"{BAGUETTE_INSTALL_HINT}; doctor never installs tools"))
    else:
        app = hardware_app()
        checks.append(check_line("OK" if app else "FAIL", "carplay-simulator-app", str(app) if app else "not found",
                                 "mount Additional Tools or copy CarPlay Simulator.app to /Applications"))
        phones = connected_iphones()
        selected = [phone for phone in phones if not device or device in json.dumps(phone)]
        checks.append(check_line("OK" if selected else "FAIL", "iphone-usb",
                                 f"{len(selected)} matching connected iPhone(s)" if selected else "no matching connected iPhone",
                                 "unlock the iPhone and connect it over USB"))
        try:
            info = hardware_window()
            checks.append(check_line("OK", "carplay-window", f"{info['name']} {info['width']}x{info['height']}"))
            text = carplay_ui_text()
            disconnected = "automaker ui" in text.lower() or "disconnected" in text.lower()
            checks.append(check_line("FAIL" if disconnected else "OK", "connection",
                                     "Automaker UI / disconnected" if disconnected else "connected",
                                     "click Disconnected or relaunch CarPlay Simulator if Connecting is stuck"))
        except CarPlayError as error:
            checks.append(check_line("WARN", "carplay-window", str(error), "open a CarPlay Simulator session"))
        # Cheap relaunch heuristic: compare the app process start against the newest .app mtime known to devicectl.
        ps = run(["ps", "-axo", "lstart=,comm="], check=False).stdout
        process_line = next((line for line in ps.splitlines() if line.rstrip().endswith("CarPlay Simulator")), "")
        checks.append(check_line("WARN", "relaunch-after-install",
                                 (process_line.strip() + "; app install time unavailable") if process_line
                                 else "CarPlay Simulator is not running",
                                 "after every device install, quit the whole app and reopen it"))
        checks.append(check_line("WARN", "build", "cannot prove DEV/STG from the simulator window",
                                 "use a DEV/STG build and record its build marker; DEV may need a granted carplay-video profile"))
    failed = any(level == "FAIL" for level, *_ in checks)
    print(f"DOCTOR {'FAIL' if failed else 'OK'} target={target}")
    return 1 if failed else 0


def quit_simulator_app_for_rearm() -> None:
    """Clear Simulator.app's cached CarPlayConfig without touching simulator device state."""
    script = r'''tell application "System Events"
if not (exists process "Simulator") then return "not-running"
tell process "Simulator"
repeat with w in windows
set windowName to name of w as text
if windowName does not contain "agent-tmp-" then return "unsafe:" & windowName
end repeat
click menu item "Quit Simulator" of menu "Simulator" of menu bar 1
end tell
return "quit"
end tell'''
    result = run(["osascript", "-e", script], check=False, timeout=20)
    answer = result.stdout.strip()
    if result.returncode or answer.startswith("unsafe:"):
        detail = answer.removeprefix("unsafe:") or (result.stderr or "System Events failed").strip()
        raise CarPlayError(
            f"cannot re-arm while a non-agent Simulator window is open ({detail}); close it and retry"
        )
    if answer != "quit":
        return
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if run(["pgrep", "-x", "Simulator"], check=False).returncode:
            return
        time.sleep(0.25)
    raise CarPlayError("Simulator.app did not quit before CarPlay re-arm")


def preflight_simulator(spec: dict[str, Any], udid: str,
                        display: tuple[str, int, int, float], record: bool) -> str:
    if record:
        raise CarPlayError(
            "--record is not supported for --target sim; use car_screenshot steps or run hardware recording"
        )
    simulator_app = Path("/Applications/Xcode.app/Contents/Developer/Applications/Simulator.app")
    if not simulator_app.is_dir():
        raise CarPlayError("Xcode 26.6 Simulator.app is missing; run doctor --target sim")
    binary = baguette_path()
    if not binary:
        raise CarPlayError(f"baguette is missing; {BAGUETTE_INSTALL_HINT}")
    baguette_version(binary)
    _, width, height, scale = display
    wanted = f"{width}x{height}@{scale:g}"
    armed, current = armed_display(udid)
    if not armed or current != wanted:
        script = spec.get("setup", {}).get("carplay_arm_script")
        if not script or not Path(str(script)).expanduser().resolve().is_file():
            raise CarPlayError(
                f"CarPlay display is {current if armed else 'not armed'}; requested {wanted}; "
                "set setup.carplay_arm_script to an existing file"
            )
    return binary


def preflight_hardware(app: dict[str, Any], device_name: str | None) -> dict[str, Any]:
    if not hardware_app():
        raise CarPlayError("Apple CarPlay Simulator.app not found; run doctor --target hardware")
    device = fast_device.resolve_device(device_name or app.get("device"))
    if not device.get("connected"):
        raise CarPlayError(f"{device.get('name')} is not connected")
    hardware_window()
    return device


def arm_simulator(spec: dict[str, Any], udid: str, display: tuple[str, int, int, float]) -> None:
    setup = spec.get("setup", {})
    _, width, height, scale = display
    wanted = f"{width}x{height}@{scale:g}"
    armed, current = armed_display(udid)
    if armed and current == wanted:
        return
    script = setup.get("carplay_arm_script")
    if not script:
        raise CarPlayError(
            f"CarPlay display is {current if armed else 'not armed'}; requested {wanted}; "
            "set setup.carplay_arm_script"
        )
    script_path = Path(str(script)).expanduser().resolve()
    if not script_path.is_file():
        raise CarPlayError(f"carplay_arm_script not found: {script_path}")
    scale_text = str(int(scale)) if scale.is_integer() else str(scale)
    quit_simulator_app_for_rearm()
    run([str(script_path), udid, str(width), str(height), scale_text], timeout=180)


def require_armed_display(udid: str, display: tuple[str, int, int, float]) -> None:
    _, width, height, scale = display
    wanted = f"{width}x{height}@{scale:g}"
    deadline = time.monotonic() + 10
    armed, current = armed_display(udid)
    while (not armed or current != wanted) and time.monotonic() < deadline:
        time.sleep(0.5)
        armed, current = armed_display(udid)
    if not armed or current != wanted:
        raise CarPlayError(
            f"CarPlay display opened as {current if armed else 'not armed'}, requested {wanted}"
        )


def ensure_sim_carplay_window() -> None:
    """SimulatorExternalDisplay normally opens it; use the menu only when the window is absent."""
    script = r'''tell application "System Events" to tell process "Simulator"
set frontmost to true
set hasCarPlay to false
repeat with w in windows
if (name of w as text) contains "CarPlay" then set hasCarPlay to true
end repeat
if not hasCarPlay then
click menu item "CarPlay…" of menu 1 of menu item "External Displays" of menu "I/O" of menu bar 1
delay 3
if exists window "TV Out Extended Setup" then click button "Run" of window "TV Out Extended Setup"
delay 7
end if
return hasCarPlay
end tell'''
    result = run(["osascript", "-e", script], check=False, timeout=20)
    if result.returncode:
        raise CarPlayError(
            "could not open Simulator.app's CarPlay window through System Events; "
            "allow Accessibility or open I/O > External Displays > CarPlay"
        )


def sim_carplay_window_exists(simulator_name: str) -> bool:
    script = r'''on run argv
set simulatorName to item 1 of argv
tell application "System Events"
if not (exists process "Simulator") then return "false"
tell process "Simulator"
repeat with w in windows
set windowName to name of w as text
if windowName contains simulatorName and windowName contains "CarPlay" then return "true"
end repeat
end tell
end tell
return "false"
end run'''
    result = run(["osascript", "-e", script, simulator_name], check=False, timeout=20)
    return result.returncode == 0 and result.stdout.strip() == "true"


def close_sim_carplay_window(simulator_name: str) -> None:
    script = r'''on run argv
set simulatorName to item 1 of argv
tell application "System Events"
if not (exists process "Simulator") then return
tell process "Simulator"
repeat with w in windows
set windowName to name of w as text
if windowName contains simulatorName and windowName contains "CarPlay" then perform action "AXClose" of w
end repeat
end tell
end tell
end run'''
    run(["osascript", "-e", script, simulator_name], check=False, timeout=20)


def ensure_simulator_ready(udid: str) -> None:
    """Boot without re-arming, then select the device in Xcode 26.6 Simulator.app."""
    fast_ui.ensure_booted(udid)
    app = Path("/Applications/Xcode.app/Contents/Developer/Applications/Simulator.app")
    run(["open", "-a", str(app), "--args", "-CurrentDeviceUDID", udid], timeout=30)
    time.sleep(2)


def reattach_sim_carplay_window() -> None:
    """Recovery for a visible but detached/black framebuffer; one Disabled -> CarPlay cycle."""
    script = r'''tell application "System Events" to tell process "Simulator"
set frontmost to true
click menu item "Disabled" of menu 1 of menu item "External Displays" of menu "I/O" of menu bar 1
delay 2
click menu item "CarPlay…" of menu 1 of menu item "External Displays" of menu "I/O" of menu bar 1
delay 3
if exists window "TV Out Extended Setup" then click button "Run" of window "TV Out Extended Setup"
delay 7
end tell'''
    result = run(["osascript", "-e", script], check=False, timeout=20)
    if result.returncode:
        raise CarPlayError("could not reattach Simulator.app's CarPlay framebuffer through System Events")


def relaunch_hardware_app() -> None:
    app = hardware_app()
    if not app:
        raise CarPlayError("Apple CarPlay Simulator.app not found")
    run(["osascript", "-e", 'tell application "CarPlay Simulator" to quit'], check=False, timeout=20)
    time.sleep(2)
    run(["open", "-a", str(app)], timeout=30)
    time.sleep(5)


def phone_flow_file(spec: dict[str, Any], simulator: str, folder: Path) -> Path:
    phone = {key: value for key, value in spec.items() if key not in ("actions", "case")}
    phone["actions"] = []
    phone.setdefault("app", {})["simulator"] = simulator
    path = folder / "phone-session.json"
    path.write_text(json.dumps(phone, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def snapshot_session_pointers(udid: str) -> dict[Path, bytes | None]:
    pointers = (fast_ui.session_pointer(None), fast_ui.session_pointer(udid))
    return {path: path.read_bytes() if path.exists() else None for path in pointers}


def restore_session_pointers(snapshot: dict[Path, bytes | None]) -> None:
    for path, contents in snapshot.items():
        if contents is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(contents)


def run_phone_sim(action: dict[str, Any], session: dict[str, Any], index: int, artifacts: Path) -> None:
    clean = {key: value for key, value in action.items() if key != "surface"}
    fast_ui.execute_action(clean, session["udid"], artifacts, index,
                           session.get("setup", {}).get("optional_permission_labels", []), {}, session["bundle_id"])


def run_phone_hardware(action: dict[str, Any], device: dict[str, Any], artifacts: Path) -> None:
    clean = {key: value for key, value in action.items() if key != "surface"}
    timeout = 30 + float(clean.get("timeout", 6)) + float(clean.get("seconds", 0))
    response = fast_device.request(device["udid"], {"op": "action", "action": clean, "wait_for_idle": False}, timeout=timeout)
    fast_device.save_screenshots(response, artifacts)
    if response.get("status") != "pass":
        raise CarPlayError(str(response.get("error", "phone action failed")))


def require_phone_response(response: dict[str, Any], fallback: str) -> None:
    if response.get("status") != "pass":
        raise CarPlayError(str(response.get("error") or fallback))


def car_action_sim(action: dict[str, Any], baguette: BaguetteInput, udid: str,
                   width: int, height: int, artifacts: Path, index: int) -> Path | None:
    kind = action["type"]
    if kind == "car_tap":
        baguette.send({"type": "tap", "x": coordinate(action.get("x"), width, "x"),
                       "y": coordinate(action.get("y"), height, "y"), "width": width, "height": height})
    elif kind == "car_swipe":
        event = {"type": "swipe", "startX": coordinate(action.get("x1"), width, "x1"),
                 "startY": coordinate(action.get("y1"), height, "y1"),
                 "endX": coordinate(action.get("x2"), width, "x2"),
                 "endY": coordinate(action.get("y2"), height, "y2"), "width": width, "height": height,
                 "duration": float(action.get("duration", 0.35))}
        baguette.send(event)
    elif kind == "car_screenshot":
        output = artifacts / str(action.get("file") or f"{index:02d}-{action.get('name', 'car')}.png")
        baguette_screenshot(udid, output, (width, height))
        return output
    elif kind == "car_wait_stable":
        return stable_screenshot(lambda path: baguette_screenshot(udid, path, (width, height)), artifacts,
                                 f"{index:02d}-{action.get('name', 'stable')}", float(action.get("timeout", 8)))
    else:
        raise CarPlayError(f"{kind} is hardware-only")
    return None


def car_action_hardware(action: dict[str, Any], artifacts: Path, index: int) -> Path | None:
    kind = action["type"]
    if kind == "carplay_connect":
        toggle_connection(True)
    elif kind == "carplay_disconnect":
        toggle_connection(False)
        return None
    elif kind == "car_tap":
        hardware_tap(float(action.get("x")), float(action.get("y")), normalized=bool(action.get("normalized")))
    elif kind == "car_screenshot":
        output = artifacts / str(action.get("file") or f"{index:02d}-{action.get('name', 'car')}.png")
        hardware_capture(output)
        return output
    elif kind == "car_wait_stable":
        return stable_screenshot(hardware_capture, artifacts, f"{index:02d}-{action.get('name', 'stable')}",
                                 float(action.get("timeout", 8)))
    elif kind == "car_swipe":
        raise CarPlayError("car_swipe is not supported by Apple CarPlay Simulator; use named taps")
    if kind != "carplay_disconnect" and hardware_disconnected():
        raise VoidResult("Automaker UI / not connected")
    return None


class VoidResult(CarPlayError):
    pass


def run_flow(flow_path: Path, target: str, udid_arg: str | None, device_arg: str | None,
             record: bool, artifacts_root: Path | None, display_override: str | None) -> int:
    started = time.monotonic()
    spec = load_flow(flow_path)
    display = flow_display(spec, display_override)
    display_tag = display[0]
    name = str(spec["name"])
    if display_tag != "widescreen":
        name += f"@cp-{display_tag}"
    case = str(spec.get("case", ""))
    app = spec.get("app", {})
    project_root = Path(app.get("project_root", flow_path.parent)).expanduser().resolve()
    root = (artifacts_root or project_root / "build/fast-carplay").expanduser().resolve()
    artifacts = root / name / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    artifacts.mkdir(parents=True, exist_ok=True)
    status, error, failed_step = "pass", "", None
    screenshots: list[str] = []
    sim_session: dict[str, Any] | None = None
    device: dict[str, Any] | None = None
    recorder: subprocess.Popen[str] | None = None
    input_session: BaguetteInput | None = None
    sim_lease: fast_ui.SimulatorLease | None = None
    sim_udid = ""
    sim_name = ""
    sim_was_booted = True
    sim_window_was_open = False
    sim_mutated = False
    session_snapshot: dict[Path, bytes | None] = {}
    result_target: dict[str, Any] = {}
    has_phone_steps = any(action.get("surface", "phone") == "phone" for action in spec["actions"])
    fresh_install = bool(spec.get("setup", {}).get("fresh_install", not app.get("prebuilt")))
    temp = Path(tempfile.mkdtemp(prefix="fast-carplay-"))
    try:
        if target == "sim":
            sim = resolve_simulator(udid_arg or app.get("simulator"))
            sim_udid = str(sim["udid"])
            sim_name = str(sim["name"])
            result_target = {"simulator": sim_udid}
            preflight_simulator(spec, sim_udid, display, record)
            sim_was_booted = sim.get("state") == "Booted"
            sim_window_was_open = sim_carplay_window_exists(sim_name)
            sim_mutated = True
            arm_simulator(spec, sim_udid, display)
            ensure_simulator_ready(sim_udid)
            ensure_sim_carplay_window()
            require_armed_display(sim_udid, display)
            _, width, height, _ = display
            if has_phone_steps:
                phone_path = phone_flow_file(spec, sim_udid, temp)
                session_snapshot = snapshot_session_pointers(sim_udid)
                previous_root = os.environ.get("FAST_UI_ROOT")
                os.environ["FAST_UI_ROOT"] = str(temp / "fast-ui")
                try:
                    fast_ui.session_main(["start", str(phone_path)])
                finally:
                    if previous_root is None:
                        os.environ.pop("FAST_UI_ROOT", None)
                    else:
                        os.environ["FAST_UI_ROOT"] = previous_root
                _, sim_session = fast_ui.load_session(sim_udid)
                sim_lease = fast_ui.SimulatorLease(sim_udid, flow_path)
                sim_lease.acquire(float(os.environ.get("FAST_UI_LOCK_WAIT", "0")))
                sim_lease.touch("bundle_id", sim_session["bundle_id"])
                preferences = sim_session.get("setup", {}).get("preferences", {})
                if preferences:
                    sim_lease.touch("preferences", sorted(preferences))
                fast_ui.PREVIOUS_UI.clear()
                fast_ui.LEASE = sim_lease
            input_session = BaguetteInput(sim_udid, int(width), int(height))
            input_session.__enter__()
        else:
            device = preflight_hardware(app, device_arg)
            result_target = {"device": device.get("name"), "udid": device.get("udid")}
            if app.get("install_path"):
                fast_device.install_app(device["udid"], str(Path(app["install_path"]).expanduser()))
                relaunch_hardware_app()
                hardware_window()
            fast_device.start_server(device, False)
        if record:
            info = hardware_window()
            video = artifacts / "carplay.mov"
            recorder = subprocess.Popen(["screencapture", "-v", "-l", str(info["id"]), str(video)],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for index, action in enumerate(spec["actions"], 1):
            failed_step = index
            if action.get("surface", "phone") == "phone":
                if target == "sim":
                    assert sim_session is not None
                    run_phone_sim(action, sim_session, index, artifacts)
                else:
                    assert device is not None
                    run_phone_hardware(action, device, artifacts)
            elif target == "sim":
                assert input_session is not None
                shot = car_action_sim(action, input_session, sim_udid, int(width), int(height), artifacts, index)
                if shot:
                    screenshots.append(str(shot))
            else:
                shot = car_action_hardware(action, artifacts, index)
                if shot:
                    screenshots.append(str(shot))
        failed_step = None
        # A run always leaves both surfaces in its artifacts, even if the authored steps omitted shots.
        if target == "sim":
            phone_final = artifacts / "phone-final.png"
            if sim_session:
                fast_ui.execute_action(
                    {"type": "screenshot", "name": phone_final.name}, sim_session["udid"], artifacts,
                    len(spec["actions"]) + 1, [], {}, sim_session["bundle_id"],
                )
            else:
                fast_ui.screenshot(sim_udid, phone_final)
            car_final = artifacts / "car-final.png"
            baguette_screenshot(sim_udid, car_final, (int(width), int(height)))
        else:
            assert device is not None
            response = fast_device.request(device["udid"], {"op": "action", "action": {
                "type": "screenshot", "name": "phone-final.png"}, "wait_for_idle": False}, timeout=30)
            fast_device.save_screenshots(response, artifacts)
            require_phone_response(response, "final phone screenshot failed")
            car_final = artifacts / "car-final.png"
            hardware_capture(car_final)
        screenshots.append(str(car_final))
    except VoidResult as exc:
        status, error = "void", str(exc)
    except (CarPlayError, fast_ui.FastUIError, fast_device.FastDeviceError, OSError, ValueError,
            subprocess.TimeoutExpired) as exc:
        status, error = "fail", str(exc)
    finally:
        try:
            if recorder:
                recorder.terminate()
                try:
                    recorder.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    recorder.kill()
            if input_session:
                input_session.__exit__(None, None, None)
            if sim_session and sim_lease:
                clean = False
                try:
                    fast_ui.teardown(
                        sim_session["udid"], sim_session["bundle_id"], sim_lease.journal,
                        fast_ui.PREVIOUS_UI, sim_session.get("setup", {}).get("preferences", {}),
                        fresh_install, False,
                    )
                    clean = True
                finally:
                    sim_lease.release(clean=clean)
                    fast_ui.LEASE = None
            elif sim_session:
                run(["xcrun", "simctl", "terminate", sim_session["udid"], sim_session["bundle_id"]], check=False)
        finally:
            restore_session_pointers(session_snapshot)
            if status == "fail" and sim_mutated:
                if not sim_window_was_open and sim_carplay_window_exists(sim_name):
                    close_sim_carplay_window(sim_name)
                if not sim_was_booted:
                    run(["xcrun", "simctl", "shutdown", sim_udid], check=False, timeout=30)
            shutil.rmtree(temp, ignore_errors=True)
    payload = {"status": status, "task": name, "case": case, "target": target,
               "display": display_tag,
               "total_seconds": round(time.monotonic() - started, 1), "artifacts": str(artifacts),
               "screenshots": screenshots, **result_target,
               **({"step": failed_step, "error": error} if error else {})}
    (artifacts / "metrics.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    label = status.upper()
    suffix = f" case={case}" if case else ""
    if failed_step:
        suffix += f" step={failed_step}"
    if error:
        suffix += f" error={error}"
    print(f"{label} task={name}{suffix} target={target} total={payload['total_seconds']}s artifacts={file_link(artifacts)}",
          file=sys.stderr if status == "fail" else sys.stdout)
    return 0 if status in ("pass", "void") else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="fastCarPlayTest", description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    doctor_parser = commands.add_parser("doctor", help="Read-only CarPlay rig checks")
    doctor_parser.add_argument("--target", required=True, choices=("sim", "hardware"))
    doctor_parser.add_argument("--udid")
    doctor_parser.add_argument("--device")
    doctor_parser.add_argument("--display", default="widescreen",
                               help="Expected display: widescreen, standard, hd, or WxH@S")
    run_parser = commands.add_parser("run", help="Run one mixed phone + car flow")
    run_parser.add_argument("flow", type=Path)
    run_parser.add_argument("--target", required=True, choices=("sim", "hardware"))
    run_parser.add_argument("--udid")
    run_parser.add_argument("--device")
    run_parser.add_argument("--record", action="store_true",
                            help="Record the standalone hardware CarPlay window; unsupported for sim")
    run_parser.add_argument("--display",
                            help="One display: widescreen, standard, hd, or WxH@S")
    run_parser.add_argument("--artifacts-root", type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "doctor":
        return doctor(args.target, args.udid, args.device, args.display)
    if args.display and "," in args.display:
        raise CarPlayError("--display takes one value; run the command twice only when both sizes were requested")
    return run_flow(args.flow.expanduser().resolve(), args.target, args.udid, args.device,
                    args.record, args.artifacts_root, args.display)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CarPlayError as error:
        print(f"FAIL error={error}", file=sys.stderr)
        raise SystemExit(1)
