#!/usr/bin/env python3
"""Installed/latest package status, pinned/latest tool status, and once-a-day notices.

The engines call `print_notice()` after a run. It never blocks and never installs anything:
it reads a small cache, starts a detached refresh at most once a day, and prints one line to
stderr at most once a day when npm has a newer version or an existing install lacks launchers/
linked Claude commands. `FAST_IOS_NO_UPDATE_CHECK=1` (or `CI`) turns it off.

    fast_update.py --status [root]   version=<installed> latest=<npm> (asks npm now, 3 s timeout);
                                     root: the installed tool's folder (default: this one)
    fast_update.py --refresh    update the cache (what the detached refresh runs)
    fast_update.py --tool-status <name> <tools.json> <binary>   pinned/local/latest tool
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
TOOL_RELEASES = {
    "axe": "https://api.github.com/repos/cameroncooke/AXe/releases/latest",
    "baguette": "https://api.github.com/repos/tddworks/baguette/releases/latest",
}
DAY = 24 * 60 * 60
ROOT = Path(__file__).resolve().parent.parent


def cache_file() -> Path:
    default = Path.home() / "Library" / "Caches" / PACKAGE / "update.json"
    return Path(os.environ.get("FAST_IOS_UPDATE_CACHE", default))


def tool_cache_file(name: str) -> Path:
    default = Path.home() / "Library" / "Caches" / PACKAGE / f"{name}-update.json"
    return Path(os.environ.get(f"FAST_IOS_{name.upper()}_UPDATE_CACHE", default))


def installed_version(root: Path = ROOT) -> str | None:
    try:
        return str(json.loads((root / "package.json").read_text())["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def expected_links(root: Path = ROOT) -> tuple[list[str], list[str]]:
    """Read install.sh so the daily self-check cannot drift from newly shipped launchers."""
    try:
        script = (root / "install.sh").read_text(encoding="utf-8")
    except OSError:
        return [], []
    launchers = re.findall(r'link "\$HERE/scripts/[^"]+" "\$BIN_DIR/([^"]+)"', script)
    commands = re.findall(r'link "\$HERE/commands/[^"]+" "\$COMMANDS_DIR/([^"]+)\.md"', script)
    return list(dict.fromkeys(launchers)), list(dict.fromkeys(commands))


def missing_links(root: Path = ROOT) -> tuple[list[str], Path]:
    launchers, commands = expected_links(root)
    bin_dir = Path(os.environ.get("FAST_IOS_BIN_DIR", Path.home() / ".local/bin")).expanduser()
    skills_dir = Path(os.environ.get("CLAUDE_SKILLS_DIR", Path.home() / ".claude/skills")).expanduser()
    commands_dir = Path(os.environ.get("CLAUDE_COMMANDS_DIR", Path.home() / ".claude/commands")).expanduser()
    skill = skills_dir / PACKAGE
    # A direct source checkout is not an incomplete install. Once any launcher or the Claude
    # skill link exists, however, compare it with every link the current install.sh ships.
    installed = any((bin_dir / name).exists() for name in launchers) or skill.is_symlink()
    if not installed:
        return [], root
    missing = [name for name in launchers if not (bin_dir / name).exists()]
    if skill.is_symlink():
        missing += [name for name in commands if not (commands_dir / f"{name}.md").exists()]
        try:
            clone = skill.resolve().parents[1]
        except (OSError, IndexError):
            clone = root
    else:
        clone = root
    return list(dict.fromkeys(missing)), clone


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


def fetch_latest_tool(name: str, timeout: float = 3.0) -> str | None:
    override = f"FAST_IOS_LATEST_{name.upper()}_VERSION"
    if os.environ.get(override):
        return os.environ[override]
    try:
        request = urllib.request.Request(
            TOOL_RELEASES[name],
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


def read_tool_cache(name: str) -> dict:
    try:
        data = json.loads(tool_cache_file(name).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_tool_cache(name: str, data: dict) -> None:
    path = tool_cache_file(name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(data))
        temporary.replace(path)
    except OSError:
        pass


def latest_tool_once_a_day(name: str, now: float | None = None) -> tuple[str | None, str]:
    """Return a cached/latest tool version and its source for install.sh --check."""
    if os.environ.get("FAST_IOS_NO_UPDATE_CHECK") or os.environ.get("CI"):
        return None, "disabled"
    current_time = time.time() if now is None else now
    data = read_tool_cache(name)
    source = "cache"
    if "checked_at" not in data or current_time - float(data["checked_at"]) >= DAY:
        latest = fetch_latest_tool(name)
        data["checked_at"] = current_time
        if latest:
            data["latest"] = latest
        write_tool_cache(name, data)
        source = "github" if latest else "offline"
    return data.get("latest"), source


def pinned_tool_version(name: str, path: Path) -> str | None:
    try:
        return str(json.loads(path.read_text(encoding="utf-8"))[name]["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def tool_binary_version(path: Path) -> str | None:
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
    missing, clone = missing_links()
    signature = ",".join(missing)
    if missing and (
        data.get("links_signature") != signature
        or "links_notified_at" not in data
        or now - float(data["links_notified_at"]) >= DAY
    ):
        data["links_signature"] = signature
        data["links_notified_at"] = now
        write_cache(data)
        return (
            f"{PACKAGE}: new commands not linked ({', '.join(missing)}); "
            f"run ./install.sh --link in {clone} or npx {PACKAGE}"
        )
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
    if argv[:1] == ["--tool-status"] and len(argv) >= 4 and argv[1] in TOOL_RELEASES:
        name = argv[1]
        pinned = pinned_tool_version(name, Path(argv[2]))
        installed = tool_binary_version(Path(argv[3]))
        latest, source = latest_tool_once_a_day(name)
        line = f"{name}-pin={pinned or 'unknown'} installed={installed or 'missing'} latest={latest or source}"
        if is_newer(latest, pinned):
            line += f" (update: npx {PACKAGE} update-{name})"
        print(line)
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
