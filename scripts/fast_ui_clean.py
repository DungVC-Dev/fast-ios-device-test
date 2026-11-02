#!/usr/bin/env python3

"""Clear the caches fastSimulatorTest / fastDeviceTest leave on the Mac.

    fastUIClean                      list what would go, with sizes (nothing is deleted)
    fastUIClean --yes                delete it
    fastUIClean --project <root>     also that project's build/fast-ui and build/fast-device-tests
    fastUIClean --maps --yes         also the screen maps (~/Library/Caches/fast-ui-map)

Evidence filed on the Desktop is never touched. A simulator lock a running flow holds, and the
iPhone runner's cache while a runner is serving, are skipped and named.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CACHES = Path.home() / "Library/Caches"


def lock_dir() -> Path:
    return Path(os.environ.get("FAST_UI_LOCK_DIR") or CACHES / "fast-ui/locks")


def map_dir() -> Path:
    return Path(os.environ.get("FAST_UI_MAP_DIR") or CACHES / "fast-ui-map").expanduser()


def device_cache() -> Path:
    return Path(os.environ.get("FAST_DEVICE_CACHE") or CACHES / "fast-device-test")


def helper_cache() -> Path:
    return CACHES / "fast-ios-device-test"


def size_of(path: Path) -> int:
    if path.is_symlink() or path.is_file():
        return path.lstat().st_size
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).lstat().st_size
            except OSError:
                pass
    return total


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{size}B"


def held(lock: Path) -> bool:
    """A lock file a running flow holds right now."""
    try:
        with lock.open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(handle, fcntl.LOCK_UN)
    except OSError:
        return False
    return False


def dirty(lock: Path) -> bool:
    try:
        lines = lock.read_text(encoding="utf-8").strip().splitlines()
        return bool(lines) and json.loads(lines[-1]).get("dirty") == 1
    except (OSError, ValueError, AttributeError):
        return False


def runner_serving() -> bool:
    """An iPhone runner (xcodebuild test-without-building of FastDeviceRunner) is running."""
    found = subprocess.run(["pgrep", "-f", "test-without-building.*(serve|run)-"], capture_output=True, text=True)
    return found.returncode == 0


def targets(project: Path | None, maps: bool) -> tuple[list[Path], list[str]]:
    """What to delete, and what is skipped with the reason."""
    remove: list[Path] = []
    skipped: list[str] = []
    locks = sorted(lock_dir().glob("*.lock")) if lock_dir().is_dir() else []
    busy = [lock for lock in locks if held(lock)]
    for lock in locks:
        if lock in busy:
            skipped.append(f"{lock} (a flow is running on {lock.stem})")
        elif dirty(lock):
            # The journal of a killed run: the next run on that simulator undoes its changes from it.
            skipped.append(f"{lock} (a killed run left {lock.stem} changed; the next run there repairs it)")
        else:
            remove.append(lock)
    if device_cache().exists():
        if runner_serving():
            skipped.append(f"{device_cache()} (an iPhone runner is serving: `fastDeviceTest stop --device <d>` first)")
        else:
            remove.append(device_cache())
    if helper_cache().exists():
        remove.append(helper_cache())
    remove += sorted(Path(tempfile.gettempdir()).glob("fast-ui-session-*"))
    if maps and map_dir().exists():
        remove.append(map_dir())
    if project is not None:
        for name in ("build/fast-ui", "build/fast-device-tests"):
            path = project / name
            if not path.exists():
                continue
            if busy and name == "build/fast-ui":
                skipped.append(f"{path} (a flow is running; its run folder is being written)")
            else:
                remove.append(path)
    return remove, skipped


def delete(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fastUIClean", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--yes", action="store_true", help="Delete; without it only list")
    parser.add_argument("--project", type=Path, help="Project root whose build/fast-ui and build/fast-device-tests go too")
    parser.add_argument("--maps", action="store_true", help="Also the screen maps fastUIMap prints")
    args = parser.parse_args(argv)
    project = args.project.expanduser().resolve() if args.project else None
    if project is not None and not project.is_dir():
        print(f"FAIL error=no such project root: {project}", file=sys.stderr)
        return 1
    remove, skipped = targets(project, args.maps)
    total = 0
    for path in remove:
        size = size_of(path)
        total += size
        print(f"{'DELETE' if args.yes else 'WOULD-DELETE'} {human(size)} {path}")
        if args.yes:
            delete(path)
    for reason in skipped:
        print(f"SKIP {reason}")
    verb = "CLEANED" if args.yes else "DRY-RUN"
    hint = "" if args.yes or not remove else " (add --yes to delete)"
    print(f"{verb} paths={len(remove)} size={human(total)} skipped={len(skipped)}{hint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
