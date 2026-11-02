#!/usr/bin/env python3
"""Installed/latest package status, pinned/latest AXe status, and the once-a-day notice.

The engines call `print_notice()` after a run. It never blocks and never installs anything:
it reads a small cache, starts a detached refresh at most once a day, and prints one line to
stderr at most once a day when npm has a newer version. `FAST_IOS_NO_UPDATE_CHECK=1` (or `CI`)
turns it off.

    fast_update.py --status [root]   version=<installed> latest=<npm> (asks npm now, 3 s timeout);
                                     root: the installed tool's folder (default: this one)
    fast_update.py --refresh    update the cache (what the detached refresh runs)
    fast_update.py --axe-status <pin.json> <axe>   pinned/installed/latest AXe (one-day cache)
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PACKAGE = "fast-ios-device-test"
REGISTRY = f"https://registry.npmjs.org/{PACKAGE}/latest"
AXE_RELEASE = "https://api.github.com/repos/cameroncooke/AXe/releases/latest"
DAY = 24 * 60 * 60
ROOT = Path(__file__).resolve().parent.parent


def cache_file() -> Path:
    default = Path.home() / "Library" / "Caches" / PACKAGE / "update.json"
    return Path(os.environ.get("FAST_IOS_UPDATE_CACHE", default))


def axe_cache_file() -> Path:
    default = Path.home() / "Library" / "Caches" / PACKAGE / "axe-update.json"
    return Path(os.environ.get("FAST_IOS_AXE_UPDATE_CACHE", default))


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


def fetch_latest_axe(timeout: float = 3.0) -> str | None:
    if os.environ.get("FAST_IOS_LATEST_AXE_VERSION"):
        return os.environ["FAST_IOS_LATEST_AXE_VERSION"]
    try:
        request = urllib.request.Request(
            AXE_RELEASE,
            headers={"Accept": "application/vnd.github+json", "User-Agent": PACKAGE},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (fixed HTTPS URL)
            return str(json.load(response)["tag_name"]).removeprefix("v")
    except Exception:
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
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(data))
        temporary.replace(path)
    except OSError:
        pass


def read_axe_cache() -> dict:
    try:
        data = json.loads(axe_cache_file().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_axe_cache(data: dict) -> None:
    path = axe_cache_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(data))
        temporary.replace(path)
    except OSError:
        pass


def latest_axe_once_a_day(now: float | None = None) -> tuple[str | None, str]:
    """Return the cached/latest AXe version and how it was obtained for install.sh --check."""
    if os.environ.get("FAST_IOS_NO_UPDATE_CHECK") or os.environ.get("CI"):
        return None, "disabled"
    current_time = time.time() if now is None else now
    data = read_axe_cache()
    source = "cache"
    if "checked_at" not in data or current_time - float(data["checked_at"]) >= DAY:
        latest = fetch_latest_axe()
        data["checked_at"] = current_time
        if latest:
            data["latest"] = latest
        write_axe_cache(data)
        source = "github" if latest else "offline"
    return data.get("latest"), source


def pinned_axe_version(path: Path) -> str | None:
    try:
        return str(json.loads(path.read_text(encoding="utf-8"))["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def axe_binary_version(path: Path) -> str | None:
    try:
        result = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = re.search(r"\d+(?:\.\d+)+", f"{result.stdout}\n{result.stderr}")
    return found.group(0) if result.returncode == 0 and found else None


def refresh() -> None:
    latest = fetch_latest()
    with cache_lock():
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


@contextlib.contextmanager
def cache_lock():
    """Serialises read-modify-write of the cache across engines running at once."""
    handle = None
    try:
        path = cache_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path.with_name(path.name + ".lock"), "a")
        fcntl.flock(handle, fcntl.LOCK_EX)
    except OSError:
        pass
    try:
        yield
    finally:
        if handle:
            handle.close()


def notice(now: float | None = None, current: str | None = None, spawn: bool = True) -> str | None:
    """The line to print, or None. Starts a refresh when the cache is a day old."""
    if os.environ.get("FAST_IOS_NO_UPDATE_CHECK") or os.environ.get("CI"):
        return None
    with cache_lock():
        return _notice(time.time() if now is None else now, current, spawn)


def _notice(now: float, current: str | None, spawn: bool) -> str | None:
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
    if sys.stderr is None:  # stderr closed (`2>&-`): print(file=None) would write to stdout
        return
    try:
        line = notice()
        if line:
            print(line, file=sys.stderr)
    except Exception:  # a closed stderr must not replace the engine's exit code
        with contextlib.suppress(Exception):
            sys.stderr = open(os.devnull, "w")  # nothing left for the exit-time flush to fail on


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
    if argv[:1] == ["--axe-status"] and len(argv) >= 3:
        pinned = pinned_axe_version(Path(argv[1]))
        installed = axe_binary_version(Path(argv[2]))
        latest, source = latest_axe_once_a_day()
        line = f"axe-pin={pinned or 'unknown'} installed={installed or 'missing'} latest={latest or source}"
        if is_newer(latest, pinned):
            line += f" (update: npx {PACKAGE} update-axe)"
        print(line)
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
