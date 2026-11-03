#!/usr/bin/env python3

"""App logs during a fastDeviceTest run: launch the app with its console attached and read it.

`devicectl device process launch --console` is the one tool that reliably shows an app's own
`print` and `os_log` lines (with OS_ACTIVITY_DT_MODE) on iOS 26; the console process lives as
long as the app, and ending it ends the app. The log goes to a file per iPhone; a cursor in the
state file makes `wait` and `assert` read only lines after the last match (or `mark`), so a line
logged between two commands is never missed and never matched twice.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Callable


class AppLogError(RuntimeError):
    pass


def state_path(cache_root: Path, udid: str) -> Path:
    return cache_root / f"applog-{udid}.json"


def load(cache_root: Path, udid: str) -> dict[str, Any] | None:
    try:
        state = json.loads(state_path(cache_root, udid).read_text())
    except (OSError, ValueError):
        return None
    return state if alive(state.get("pid")) else None


def save(cache_root: Path, udid: str, state: dict[str, Any]) -> None:
    state_path(cache_root, udid).write_text(json.dumps(state) + "\n")


def alive(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
    except (TypeError, ValueError, ProcessLookupError, PermissionError):
        return False
    return True


def launch_command(udid: str, bundle_id: str) -> list[str]:
    return [
        "xcrun", "devicectl", "device", "process", "launch", "--device", udid, "--console",
        "--terminate-existing", "--environment-variables", json.dumps({"OS_ACTIVITY_DT_MODE": "YES"}), bundle_id,
    ]


def start(cache_root: Path, udid: str, bundle_id: str, log: Path | None = None,
          popen: Callable[..., Any] = subprocess.Popen) -> dict[str, Any]:
    """(Re)launch the app with its console going to the log file; ends an earlier capture first."""
    stop(cache_root, udid)
    cache_root.mkdir(parents=True, exist_ok=True)
    log = log or cache_root / f"applog-{udid}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as output:
        process = popen(launch_command(udid, bundle_id), stdout=output, stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL, start_new_session=True)
    state = {"pid": process.pid, "bundle_id": bundle_id, "log": str(log), "cursor": 0, "started": time.time()}
    save(cache_root, udid, state)
    return state


def stop(cache_root: Path, udid: str) -> dict[str, Any] | None:
    """End the capture (and with it the app); the log file stays."""
    path = state_path(cache_root, udid)
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    pid = state.get("pid")
    if alive(pid):
        try:
            os.killpg(int(pid), signal.SIGINT)
        except (ProcessLookupError, PermissionError):
            pass
        for _ in range(30):
            if not alive(pid):
                break
            time.sleep(0.1)
        if alive(pid):
            try:
                os.killpg(int(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    path.unlink(missing_ok=True)
    return state


def text_from(state: dict[str, Any], cursor: int | None = None) -> tuple[str, int]:
    """The log after the cursor and the file's end offset."""
    data = Path(state["log"]).read_bytes() if Path(state["log"]).exists() else b""
    start_at = state.get("cursor", 0) if cursor is None else cursor
    return data[start_at:].decode("utf-8", errors="replace"), len(data)


def find(pattern: str, text: str) -> re.Match[str] | None:
    try:
        return re.compile(pattern, re.MULTILINE).search(text)
    except re.error as error:
        raise AppLogError(f"bad regex '{pattern}': {error}") from error


def matched_line(text: str, match: re.Match[str]) -> str:
    start_at = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    return text[start_at: end if end >= 0 else len(text)].strip()


def wait(cache_root: Path, udid: str, pattern: str, timeout: float, poll: float = 0.3,
         clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> str:
    """Wait for a line after the cursor that matches; move the cursor past it and return it."""
    state = require(cache_root, udid)
    deadline = clock() + timeout
    while True:
        text, _ = text_from(state)
        match = find(pattern, text)
        if match:
            consumed = len(text[: match.end()].encode("utf-8"))
            state["cursor"] = state.get("cursor", 0) + consumed
            save(cache_root, udid, state)
            return matched_line(text, match)
        if clock() >= deadline:
            raise AppLogError(f"no app log line matched '{pattern}' within {timeout:g}s{tail_hint(text)}")
        if not alive(state.get("pid")):
            raise AppLogError(f"the app's console ended (the app quit) before a line matched '{pattern}'{tail_hint(text)}")
        sleep(poll)


def check(cache_root: Path, udid: str, pattern: str, present: bool) -> str:
    """`assert` (present) or `assert-absent` over the lines after the cursor, without waiting."""
    state = require(cache_root, udid)
    text, _ = text_from(state)
    match = find(pattern, text)
    if present and not match:
        raise AppLogError(f"no app log line after the last mark matches '{pattern}'{tail_hint(text)}")
    if not present and match:
        raise AppLogError(f"the app logged '{matched_line(text, match)}', which matches '{pattern}'")
    return matched_line(text, match) if match else ""


def mark(cache_root: Path, udid: str) -> None:
    state = require(cache_root, udid)
    state["cursor"] = text_from(state)[1]
    save(cache_root, udid, state)


def require(cache_root: Path, udid: str) -> dict[str, Any]:
    state = load(cache_root, udid)
    if state is None:
        raise AppLogError("no app log is being captured: run `fastDeviceTest log start --app <bundle id>` first")
    return state


def tail_hint(text: str, lines: int = 3) -> str:
    last = [line.strip() for line in text.strip().splitlines()[-lines:] if line.strip()]
    return f"; last lines: {json.dumps(last, ensure_ascii=False)}" if last else "; nothing logged since the last mark"


def check_expectations(text: str, present: list[str], absent: list[str]) -> list[str]:
    """Problems with a flow's `expect_log` / `expect_no_log` over the whole log."""
    problems = [f"expect_log '{pattern}' never matched" for pattern in present if not find(pattern, text)]
    for pattern in absent:
        match = find(pattern, text)
        if match:
            problems.append(f"expect_no_log '{pattern}' matched '{matched_line(text, match)}'")
    return problems
