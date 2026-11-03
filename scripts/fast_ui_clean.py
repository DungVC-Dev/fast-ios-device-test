#!/usr/bin/env python3

"""Clear the caches and build output fastSimulatorTest / fastDeviceTest leave on the Mac (the tool
itself stays installed; `install.sh --uninstall` removes it).

    fastUIClean                      list what would go, with sizes (nothing is deleted)
    fastUIClean --yes                delete it
    fastUIClean --project <root>     also that project's runs and test builds (build/fast-ui,
                                     build/fast-ui-dd, build/fast-device-tests)
    fastUIClean --maps --yes         also the screen maps (~/Library/Caches/fast-ui-map)
    fastUIClean --max-dd-gb 20       list stale/LRU shared DerivedData above a 20 GB cap
    fastUIClean --max-dd-gb 20 --yes delete those shared DerivedData repo caches
    fastUIClean --project <root> --scope current [--task <name>] --yes
                                     only the runs of the current task (default: the latest run's)
    fastUIClean --project <root> --scope others --yes
                                     the runs of every task but the current one; builds stay

A task is a flow: its runs sit in build/fast-ui/<task>/ (Simulator) and build/fast-device/<task>/
(iPhone); `home@dark` counts as `home`. Run in a terminal without --scope to pick from a menu.

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


def derived_data_cache() -> Path:
    return Path(
        os.environ.get("FAST_IOS_DERIVED_DATA_ROOT") or helper_cache() / "dd"
    ).expanduser().resolve()


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


# Per-task run folders (one subfolder per flow), then builds shared by every task.
RUN_ROOTS = ("build/fast-ui", "build/fast-device")
BUILD_DIRS = ("build/fast-ui-dd", "build/fast-device-tests")
SCOPES = ("all", "current", "others")
DD_METADATA = ".fastui-repo.json"


def task_of(folder: Path) -> str:
    """`home@dark@xxl` is a variant of `home`."""
    return folder.name.split("@")[0]


def task_folders(project: Path) -> list[Path]:
    return [folder for root in RUN_ROOTS if (project / root).is_dir()
            for folder in sorted((project / root).iterdir()) if folder.is_dir()]


def current_task(project: Path) -> str | None:
    """The task of the latest run in either engine."""
    latest: tuple[float, str] | None = None
    for folder in task_folders(project):
        for run in folder.iterdir():
            try:
                stamp = run.stat().st_mtime
            except OSError:
                continue
            if latest is None or stamp > latest[0]:
                latest = (stamp, task_of(folder))
    return latest[1] if latest else None


def task_targets(project: Path, scope: str, task: str) -> list[Path]:
    """Run folders of `task` (scope current) or of every other task (scope others)."""
    return [folder for folder in task_folders(project) if (task_of(folder) == task) == (scope == "current")]


def helper_targets() -> list[Path]:
    root = helper_cache()
    if not root.is_dir():
        return [root] if root.exists() else []
    dd = derived_data_cache()
    return [child for child in root.iterdir() if child.name != "dd" and child.resolve() != dd]


def dd_metadata(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads((path / DD_METADATA).read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) and isinstance(payload.get("common_dir"), str) else None
    except (OSError, ValueError):
        return None


def shared_dd_targets(max_gb: float | None) -> tuple[list[Path], list[str], int, int]:
    root = derived_data_cache()
    entries = [path for path in root.iterdir() if path.is_dir()] if root.is_dir() else []
    sizes = {path: size_of(path) for path in entries}
    remove: list[Path] = []
    skipped: list[str] = []
    live: list[Path] = []
    for path in entries:
        metadata = dd_metadata(path)
        if metadata is None:
            skipped.append(f"{path} (shared DerivedData has no repo metadata)")
            continue
        if not Path(str(metadata["common_dir"])).exists():
            if held(path / ".fastui-build.lock"):
                skipped.append(f"{path} (its build lock is held)")
            else:
                remove.append(path)
        else:
            live.append(path)
    if max_gb is not None:
        cap = int(max_gb * 1024 ** 3)
        remaining = sum(sizes[path] for path in live)
        ordered = sorted(
            live,
            key=lambda path: (path / DD_METADATA).stat().st_mtime,
        )
        for path in ordered:
            if remaining <= cap:
                break
            if held(path / ".fastui-build.lock"):
                skipped.append(f"{path} (LRU candidate but its build lock is held)")
                continue
            remove.append(path)
            remaining -= sizes[path]
    return remove, skipped, len(entries), sum(sizes.values())


def targets(project: Path | None, maps: bool, max_dd_gb: float | None = None) -> tuple[list[Path], list[str], int, int]:
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
    remove += helper_targets()
    dd_remove, dd_skipped, dd_count, dd_size = shared_dd_targets(max_dd_gb)
    remove += dd_remove
    skipped += dd_skipped
    remove += sorted(Path(tempfile.gettempdir()).glob("fast-ui-session-*"))
    if maps and map_dir().exists():
        remove.append(map_dir())
    if project is not None:
        # Run output, the Simulator app builds (the flows' `derived_data`, build/fast-ui-dd by
        # convention) and the iPhone test builds.
        for name in (*RUN_ROOTS, *BUILD_DIRS):
            path = project / name
            if not path.exists():
                continue
            if busy and name in RUN_ROOTS:
                skipped.append(f"{path} (a flow is running; its run folder is being written)")
            else:
                remove.append(path)
    return remove, skipped, dd_count, dd_size


def ask_scope(project: Path, task: str | None) -> str | None:
    """Menu for a person at a terminal; None when they cancel."""
    task = task or current_task(project) or "?"
    print(f"Clean what in {project}?")
    print(f"  1) the current task's runs ({task})")
    print(f"  2) the runs of every task but {task} (builds stay)")
    print("  3) everything: all runs, the test builds and the tools' caches")
    try:
        answer = input("1/2/3 (anything else cancels): ").strip()
    except EOFError:
        answer = ""
    return {"1": "current", "2": "others", "3": "all"}.get(answer)


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
    parser.add_argument("--scope", choices=SCOPES,
                        help="all (default): everything; current: the current task's runs; others: every other task's runs")
    parser.add_argument("--task", help="The current task (flow name); default: the task of the latest run")
    parser.add_argument("--max-dd-gb", type=float, metavar="N",
                        help="Trim least-recently-used shared repo DerivedData until it is at most N GB")
    args = parser.parse_args(argv)
    project = args.project.expanduser().resolve() if args.project else None
    if project is not None and not project.is_dir():
        print(f"FAIL error=no such project root: {project}", file=sys.stderr)
        return 1
    scope = args.scope
    if args.max_dd_gb is not None and args.max_dd_gb < 0:
        parser.error("--max-dd-gb must be zero or greater")
    asked = scope is None and project is not None and sys.stdin.isatty()
    if asked:
        scope = ask_scope(project, args.task)
        if scope is None:
            return 0
    scope = scope or "all"
    if scope == "all":
        remove, skipped, dd_count, dd_size = targets(project, args.maps, args.max_dd_gb)
    else:
        if project is None:
            print(f"FAIL error=--scope {scope} needs --project <root>", file=sys.stderr)
            return 1
        dd_count, dd_size = 0, 0
        task = args.task or current_task(project)
        if task is None:
            print(f"FAIL error=no runs under {project}/build/fast-ui or build/fast-device", file=sys.stderr)
            return 1
        print(f"TASK current={task}")
        remove, skipped = task_targets(project, scope, task), []
        if scope == "current" and any(held(lock) for lock in lock_dir().glob("*.lock")):
            # A flow is running, most likely this task's: its run folder is being written.
            skipped = [f"{path} (a flow is running; its run folder may be being written)" for path in remove]
            remove = []
    if asked and not args.yes and remove:
        # Someone at a terminal: list, then ask, instead of making them run it again with --yes.
        for path in remove:
            print(f"  {human(size_of(path))} {path}")
        try:
            args.yes = input(f"Delete these {len(remove)}? [y/N] ").strip().lower() in ("y", "yes")
        except EOFError:
            args.yes = False
        if not args.yes:
            print("CANCELLED")
            return 0
    if scope == "all":
        cap = f" cap={args.max_dd_gb:g}G" if args.max_dd_gb is not None else ""
        print(f"DD-CACHE repos={dd_count} size={human(dd_size)} root={derived_data_cache()}{cap}")
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
