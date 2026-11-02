#!/usr/bin/env python3
"""The installed version, the latest one on npm, and the once-a-day "update available" line.

The engines call `print_notice()` after a run. It never blocks and never installs anything:
it reads a small cache, starts a detached refresh at most once a day, and prints one line to
stderr at most once a day when npm has a newer version. `FAST_IOS_NO_UPDATE_CHECK=1` (or `CI`)
turns it off.

    fast_update.py --status [root]   version=<installed> latest=<npm> (asks npm now, 3 s timeout);
                                     root: the installed tool's folder (default: this one)
    fast_update.py --refresh    update the cache (what the detached refresh runs)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PACKAGE = "fast-ios-device-test"
REGISTRY = f"https://registry.npmjs.org/{PACKAGE}/latest"
DAY = 24 * 60 * 60
ROOT = Path(__file__).resolve().parent.parent


def cache_file() -> Path:
    default = Path.home() / "Library" / "Caches" / PACKAGE / "update.json"
    return Path(os.environ.get("FAST_IOS_UPDATE_CACHE", default))


def installed_version(root: Path = ROOT) -> str | None:
    try:
        return str(json.loads((root / "package.json").read_text())["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def parse_version(text: str | None) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(text).split("-")[0].split("."))
    except ValueError:
        return ()


def is_newer(latest: str | None, current: str | None) -> bool:
    new, old = parse_version(latest), parse_version(current)
    return bool(new and old and new > old)


def fetch_latest(timeout: float = 3.0) -> str | None:
    if os.environ.get("FAST_IOS_LATEST_VERSION"):  # tests, or a mirror the registry cannot reach
        return os.environ["FAST_IOS_LATEST_VERSION"]
    try:
        with urllib.request.urlopen(REGISTRY, timeout=timeout) as response:  # noqa: S310 (fixed https URL)
            return str(json.load(response)["version"])
    except Exception:  # offline, proxy, a registry change: no notice, never an error
        return None


def read_cache() -> dict:
    try:
        data = json.loads(cache_file().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_cache(data: dict) -> None:
    path = cache_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data))
        temporary.replace(path)
    except OSError:
        pass


def refresh() -> None:
    latest = fetch_latest()
    data = read_cache()
    data["checked_at"] = time.time()
    if latest:
        data["latest"] = latest
    write_cache(data)


def start_refresh() -> None:
    try:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--refresh"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def notice(now: float | None = None, current: str | None = None, spawn: bool = True) -> str | None:
    """The line to print, or None. Starts a refresh when the cache is a day old."""
    if os.environ.get("FAST_IOS_NO_UPDATE_CHECK") or os.environ.get("CI"):
        return None
    now = time.time() if now is None else now
    data = read_cache()
    if "checked_at" not in data or now - float(data["checked_at"]) >= DAY:
        data["checked_at"] = now  # one refresh a day even when several runs start together
        write_cache(data)
        if spawn:
            start_refresh()
    current = current or installed_version()
    latest = data.get("latest")
    if not is_newer(latest, current):
        return None
    if "notified_at" in data and now - float(data["notified_at"]) < DAY:
        return None
    data["notified_at"] = now
    write_cache(data)
    return f"update available: {PACKAGE} {current} -> {latest} (run: npx {PACKAGE} update)"


def print_notice() -> None:
    try:
        line = notice()
    except Exception:
        return
    if line:
        print(line, file=sys.stderr)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--refresh"]:
        refresh()
        return 0
    if argv[:1] == ["--status"]:
        latest = fetch_latest()
        current = installed_version(Path(argv[1]) if len(argv) > 1 else ROOT)
        line = f"version={current or 'unknown'} latest={latest or 'unknown (offline?)'}"
        if is_newer(latest, current):
            line += f" (update: npx {PACKAGE} update)"
        print(line)
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
