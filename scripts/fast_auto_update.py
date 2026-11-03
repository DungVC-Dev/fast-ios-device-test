#!/usr/bin/env python3
"""Manage and run fast-ios-device-test's per-user daily launchd updater."""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

import fast_update

# A stuck npm download must not keep the daily job alive until the next day.
UPDATE_TIMEOUT = 15 * 60

PACKAGE = fast_update.PACKAGE
LABEL = "com.dungvc.fast-ios-device-test.update"
MAX_LOG_BYTES = 1_000_000


def agent_path() -> Path:
    return Path(os.environ.get("FAST_IOS_LAUNCH_AGENT", Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"))


def log_path() -> Path:
    return Path(os.environ.get("FAST_IOS_UPDATE_LOG", Path.home() / "Library/Logs/fast-ios-device-test-update.log"))


def status_path() -> Path:
    default = Path.home() / "Library/Caches" / PACKAGE / "auto-update.json"
    return Path(os.environ.get("FAST_IOS_AUTO_UPDATE_STATUS", default))


def bin_dir() -> Path:
    return Path(os.environ.get("FAST_IOS_BIN_DIR", Path.home() / ".local/bin"))


def installed_root() -> Path | None:
    launcher = bin_dir() / "fastSimulatorTest"
    try:
        return launcher.resolve(strict=True).parent.parent
    except OSError:
        return None


def is_clone(root: Path | None) -> bool:
    return bool(root and (root / ".git").exists())


def rotate_log() -> None:
    path = log_path()
    try:
        if path.stat().st_size < MAX_LOG_BYTES:
            return
        previous = path.with_suffix(path.suffix + ".1")
        previous.unlink(missing_ok=True)
        path.replace(previous)
    except OSError:
        pass


def write_status(result: str, detail: str = "") -> None:
    path = status_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps({"last_run": time.time(), "result": result, "detail": detail}) + "\n")
        temporary.replace(path)
    except OSError:
        pass


def append_log(message: str) -> None:
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def plist(root: Path) -> dict:
    python = shutil.which("python3") or "/usr/bin/python3"
    # launchd starts with a bare PATH: keep the folder that holds this shell's npx (nvm, fnm,
    # volta, Homebrew) in front of the defaults, or the daily job cannot find npx.
    defaults = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    npx = shutil.which("npx")
    folders = ([str(Path(npx).parent)] if npx else []) + defaults
    environment = {"PATH": ":".join(dict.fromkeys(folders))}
    if os.environ.get("FAST_IOS_NO_UPDATE_CHECK"):
        environment["FAST_IOS_NO_UPDATE_CHECK"] = "1"
    return {
        "Label": LABEL,
        "ProgramArguments": [python, str(root / "scripts/fast_auto_update.py"), "--run", str(root)],
        "StartCalendarInterval": {"Hour": 9, "Minute": 0},
        "ProcessType": "Background",
        "EnvironmentVariables": environment,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
    }


def launchctl(*args: str, check: bool = False) -> int:
    command = shutil.which("launchctl") or "/bin/launchctl"
    result = subprocess.run([command, *args], capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise RuntimeError(message or f"launchctl {' '.join(args)} failed")
    return result.returncode


def enable(root: Path) -> int:
    script = root / "scripts/fast_auto_update.py"
    if not script.is_file():
        print(f"auto-update: cannot find {script}; install the tool first", file=sys.stderr)
        return 1
    path = agent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        plistlib.dump(plist(root.resolve()), stream)
    if not os.environ.get("FAST_IOS_AUTO_UPDATE_RUNNING"):
        domain = f"gui/{os.getuid()}"
        launchctl("bootout", domain, str(path))
        try:
            launchctl("bootstrap", domain, str(path), check=True)
        except RuntimeError as error:
            path.unlink(missing_ok=True)
            print(f"auto-update: failed to load {path}: {error}", file=sys.stderr)
            return 1
    print(f"auto-update: on (daily; turn off: npx {PACKAGE} auto-update off)")
    return 0


def disable() -> int:
    path = agent_path()
    launchctl("bootout", f"gui/{os.getuid()}", str(path))
    path.unlink(missing_ok=True)
    print("auto-update: off")
    return 0


def read_status() -> str:
    try:
        data = json.loads(status_path().read_text())
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(data["last_run"])))
        detail = f" ({data.get('detail')})" if data.get("detail") else ""
        return f"last={stamp} result={data.get('result', 'unknown')}{detail}"
    except (OSError, ValueError, KeyError, TypeError):
        return "last=never"


def show_status() -> int:
    state = "on" if agent_path().is_file() else "off"
    print(f"auto-update: {state}; {read_status()}")
    return 0


def run_daily(root: Path | None = None) -> int:
    rotate_log()
    if os.environ.get("FAST_IOS_NO_UPDATE_CHECK"):
        append_log("skipped: FAST_IOS_NO_UPDATE_CHECK=1 (no network checks)")
        write_status("skipped", "network checks disabled")
        return 0
    root = root or installed_root()
    if is_clone(root):
        advice = f'git -C "{root}" pull --rebase && "{root}/install.sh" --link'
        append_log(f"linked clone: no automatic update; run {advice}")
        write_status("skipped", "linked clone; use git")
        return 0
    with fast_update.exclusive_runtime_lock() as acquired:
        if not acquired:
            append_log("skipped: a fast* run is active; retrying next day")
            write_status("skipped", "fast* run active")
            return 0
        current = fast_update.installed_version(root) if root else None
        latest = fast_update.fetch_latest(timeout=5)
        if not latest:
            append_log("failed: npm registry unavailable")
            write_status("failed", "npm registry unavailable")
            return 1
        old, new = fast_update.parse_version(current), fast_update.parse_version(latest)
        if old and new and new <= old:
            append_log(f"up to date: {current}")
            write_status("ok", f"up to date {current}")
            return 0
        if old and new and new[0] > old[0]:
            detail = f"major update available {current} -> {latest}; run npx {PACKAGE} update manually"
            append_log(detail)
            write_status("notice", detail)
            return 0
        npx = shutil.which("npx")
        if not npx:
            append_log("failed: npx is not on PATH")
            write_status("failed", "npx missing")
            return 1
        append_log(f"updating {current or 'unknown'} -> {latest} and installed agent plugins")
        env = {**os.environ, "FAST_IOS_LATEST_VERSION": latest, "FAST_IOS_AUTO_UPDATE_RUNNING": "1"}
        try:
            result = subprocess.run(
                [npx, "--yes", f"{PACKAGE}@{latest}", "update"],
                capture_output=True, text=True, env=env, check=False, timeout=UPDATE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            append_log(f"failed: the update did not finish within {UPDATE_TIMEOUT}s")
            write_status("failed", "update timed out")
            return 1
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        if output:
            append_log(output)
        state = "ok" if result.returncode == 0 else "failed"
        append_log(f"finished: {state} exit={result.returncode}")
        write_status(state, f"version {latest}; exit {result.returncode}")
        return result.returncode


def main(argv: list[str]) -> int:
    if argv[:1] == ["--run"]:
        return run_daily(Path(argv[1]).expanduser() if len(argv) > 1 else None)
    if not argv or argv[0] == "status":
        return show_status()
    if argv[0] == "off":
        return disable()
    if argv[0] == "on":
        root = Path(argv[1]).expanduser() if len(argv) > 1 else installed_root()
        if root is None:
            print(f"auto-update: tool is not installed; run npx {PACKAGE} first", file=sys.stderr)
            return 1
        return enable(root)
    print("usage: fast_auto_update.py on [root] | off | status | --run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
