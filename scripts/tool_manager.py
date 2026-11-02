#!/usr/bin/env python3
"""Install or update the project-managed tools pinned in vendor/tools.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
TOOL_SPECS = {
    "axe": {
        "api": "https://api.github.com/repos/cameroncooke/AXe/releases/latest",
        "asset": re.compile(r"^AXe-macOS-v(?P<version>[^/]+)-universal\.tar\.gz$"),
        "host": "https://github.com/cameroncooke/AXe/releases/download/",
        "archive_binary": "axe",
        "binary": "axe",
        "env": "FAST_IOS_AXE_DIR",
        "default": ".local/share/axe",
    },
    "baguette": {
        "api": "https://api.github.com/repos/tddworks/baguette/releases/latest",
        "asset": re.compile(r"^baguette_v(?P<version>[^/]+)_macOS_arm64\.tar\.gz$"),
        "host": "https://github.com/tddworks/baguette/releases/download/",
        "archive_binary": "Baguette",
        "binary": "baguette",
        "env": "FAST_IOS_BAGUETTE_DIR",
        "default": ".local/share/baguette",
    },
}


class ToolError(RuntimeError):
    pass


def pin_path(root: Path) -> Path:
    return root / "vendor" / "tools.json"


def read_pins(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    path = pin_path(root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as error:
        raise ToolError(f"cannot read tool pins {path}: {error}") from error
    if not isinstance(value, dict) or set(value) != set(TOOL_SPECS):
        raise ToolError(f"{path} must pin exactly: {', '.join(TOOL_SPECS)}")
    for name, pin in value.items():
        spec = TOOL_SPECS[name]
        if not isinstance(pin, dict) or not all(key in pin for key in ("version", "url", "sha256", "license")):
            raise ToolError(f"invalid {name} pin")
        version, url = str(pin["version"]), str(pin["url"])
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", version):
            raise ToolError(f"invalid {name} pinned version: {version!r}")
        match = spec["asset"].fullmatch(Path(url).name)
        if not url.startswith(spec["host"]) or not match or match.group("version") != version:
            raise ToolError(f"{name} pinned version and archive URL do not match")
        if not re.fullmatch(r"[0-9a-f]{64}", str(pin["sha256"])):
            raise ToolError(f"invalid {name} pinned sha256")
        if name == "baguette" and pin.get("architectures") != ["arm64"]:
            raise ToolError("baguette release asset must declare its arm64 architecture")
    return value


def read_pin(name: str, root: Path = ROOT) -> dict[str, Any]:
    return read_pins(root)[name]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "fast-ios-device-test"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed GitHub API
        value = json.load(response)
    if not isinstance(value, dict):
        raise ToolError(f"unexpected JSON from {url}")
    return value


def latest_release(name: str, payload: dict[str, Any]) -> dict[str, str]:
    spec = TOOL_SPECS[name]
    tag = str(payload.get("tag_name", "")).removeprefix("v")
    for asset in payload.get("assets", []):
        if not isinstance(asset, dict):
            continue
        match = spec["asset"].fullmatch(str(asset.get("name", "")))
        url = str(asset.get("browser_download_url", ""))
        if match and match.group("version") == tag and url.startswith(spec["host"]):
            return {"version": tag, "url": url}
    description = "universal macOS" if name == "axe" else "macOS arm64"
    raise ToolError(f"{name} release v{tag or '?'} has no prebuilt {description} tarball")


def download(url: str, target: Path, timeout: float = 120.0) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "fast-ios-device-test"})
    with urllib.request.urlopen(request, timeout=timeout) as response, target.open("wb") as stream:  # noqa: S310
        shutil.copyfileobj(response, stream)


def checked_archive(name: str, root: Path, pin: dict[str, Any]) -> tuple[Path, bool]:
    vendored = root / "vendor" / Path(str(pin["url"])).name
    if pin.get("vendored") and vendored.exists():
        archive, temporary = vendored, False
    else:
        handle, raw = tempfile.mkstemp(prefix=f"fast-ios-{name}-", suffix=".tar.gz")
        os.close(handle)
        archive, temporary = Path(raw), True
        download(str(pin["url"]), archive)
    actual = sha256(archive)
    if actual != pin["sha256"]:
        if temporary:
            archive.unlink(missing_ok=True)
        raise ToolError(f"{name} archive checksum mismatch: expected {pin['sha256']}, got {actual}")
    return archive, temporary


def safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as bundle:
        root = destination.resolve()
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise ToolError(f"archive contains an unsafe path: {member.name}")
        if sys.version_info >= (3, 12):
            bundle.extractall(destination, filter="data")  # noqa: S202 - pinned and SHA-256 verified
        else:
            bundle.extractall(destination)  # noqa: S202 - paths checked above; compatibility for Python 3.11


def binary_version(binary: Path) -> str | None:
    try:
        result = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = re.search(r"\d+(?:\.\d+)+", f"{result.stdout}\n{result.stderr}")
    return found.group(0) if result.returncode == 0 and found else None


def extracted_payload(name: str, archive: Path, destination: Path) -> tuple[Path, Path]:
    safe_extract(archive, destination)
    archive_name = str(TOOL_SPECS[name]["archive_binary"])
    matches = [path for path in destination.rglob(archive_name) if path.is_file()]
    if len(matches) != 1:
        raise ToolError(f"{name} archive has {len(matches)} {archive_name!r} binaries, expected one")
    return matches[0].parent, matches[0]


def install_home(name: str) -> Path:
    spec = TOOL_SPECS[name]
    default = Path.home() / str(spec["default"])
    return Path(os.environ.get(str(spec["env"]), default)).expanduser()


def selected_tools(name: str) -> list[str]:
    if name != "all":
        return [name]
    configured = os.environ.get("FAST_IOS_INSTALL_TOOLS", "axe,baguette")
    selected = [item.strip() for item in configured.split(",") if item.strip()]
    unknown = set(selected) - set(TOOL_SPECS)
    if unknown:
        raise ToolError(f"unknown FAST_IOS_INSTALL_TOOLS: {', '.join(sorted(unknown))}")
    return selected


def installed_pin_matches(home: Path, pin: dict[str, Any], binary_name: str) -> bool:
    try:
        installed = json.loads((home / ".fast-ios-pin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return (installed.get("version") == pin["version"]
            and installed.get("sha256") == pin["sha256"]
            and binary_version(home / binary_name) == pin["version"])


def write_wrapper(name: str, home: Path, bin_dir: Path) -> None:
    binary_name = str(TOOL_SPECS[name]["binary"])
    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper = bin_dir / name
    temporary_wrapper = wrapper.with_name(f".{wrapper.name}.{os.getpid()}.tmp")
    temporary_wrapper.write_text(f'#!/bin/bash\nexec "{home / binary_name}" "$@"\n', encoding="utf-8")
    temporary_wrapper.chmod(0o755)
    temporary_wrapper.replace(wrapper)


def install_one(name: str, root: Path = ROOT, force: bool = False) -> str:
    pin = read_pin(name, root)
    home = install_home(name)
    bin_dir = Path(os.environ.get("FAST_IOS_BIN_DIR", Path.home() / ".local/bin")).expanduser()
    binary_name = str(TOOL_SPECS[name]["binary"])
    if not force and installed_pin_matches(home, pin, binary_name):
        write_wrapper(name, home, bin_dir)
        print(f"{name}: pinned {pin['version']} already installed at {home}")
        return str(pin["version"])
    if name == "baguette" and platform.machine() != "arm64":
        raise ToolError("baguette publishes a prebuilt macOS arm64 asset only; this Mac is not arm64")
    archive, temporary_archive = checked_archive(name, root, pin)
    home.parent.mkdir(parents=True, exist_ok=True)
    unpacked = Path(tempfile.mkdtemp(prefix=f".{name}-unpack-", dir=home.parent))
    staged = Path(tempfile.mkdtemp(prefix=f".{name}-install-", dir=home.parent))
    try:
        payload, source_binary = extracted_payload(name, archive, unpacked)
        shutil.copytree(payload, staged, dirs_exist_ok=True)
        binary = staged / source_binary.name
        target_binary = staged / binary_name
        if binary != target_binary:
            binary.replace(target_binary)
        actual = binary_version(target_binary)
        if actual != pin["version"]:
            raise ToolError(f"{name} archive runs as {actual or 'unknown'}, expected {pin['version']}")
        license_file = root / "vendor" / str(pin["license_file"])
        if not license_file.is_file():
            raise ToolError(f"{name} licence file is missing: {license_file}")
        shutil.copy2(license_file, staged / "LICENSE")
        (staged / "NOTICE").write_text(str(pin["notice"]).rstrip() + "\n", encoding="utf-8")
        (staged / ".fast-ios-pin.json").write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(staged)], capture_output=True, check=False)
        if home.exists() or home.is_symlink():
            shutil.rmtree(home) if home.is_dir() and not home.is_symlink() else home.unlink()
        staged.replace(home)
        write_wrapper(name, home, bin_dir)
    finally:
        shutil.rmtree(unpacked, ignore_errors=True)
        shutil.rmtree(staged, ignore_errors=True)
        if temporary_archive:
            archive.unlink(missing_ok=True)
    print(f"{name}: installed pinned {pin['version']} into {home}")
    return str(pin["version"])


def install(name: str = "all", root: Path = ROOT, force: bool = False) -> None:
    for tool in selected_tools(name):
        try:
            install_one(tool, root, force=force)
        except (ToolError, OSError, ValueError, tarfile.TarError) as error:
            if name != "all" or tool != "baguette":
                raise
            print(
                f"note: optional baguette was not installed ({error}); "
                "fastSimulatorTest and fastDeviceTest are ready. Retry with: ./install.sh --install-baguette",
                file=sys.stderr,
            )


def write_pins(root: Path, pins: dict[str, dict[str, Any]]) -> None:
    path = pin_path(root)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(pins, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def update_one(name: str, root: Path = ROOT, install_local: bool = True) -> str:
    pins = read_pins(root)
    old_pin = pins[name]
    release = latest_release(name, request_json(str(TOOL_SPECS[name]["api"])))
    handle, raw = tempfile.mkstemp(prefix=f"fast-ios-{name}-update-", suffix=".tar.gz")
    os.close(handle)
    downloaded = Path(raw)
    try:
        download(release["url"], downloaded)
        with tempfile.TemporaryDirectory(prefix=f"fast-ios-{name}-verify-") as folder:
            _, binary = extracted_payload(name, downloaded, Path(folder))
            actual = binary_version(binary)
        if actual != release["version"]:
            raise ToolError(f"{name} release runs as {actual or 'unknown'}, expected {release['version']}")
        pin = {**old_pin, **release, "sha256": sha256(downloaded)}
        pins[name] = pin
        if pin.get("vendored"):
            vendor = root / "vendor"
            target = vendor / Path(release["url"]).name
            replacement = target.with_name(f".{target.name}.{os.getpid()}.tmp")
            shutil.copy2(downloaded, replacement)
            replacement.replace(target)
            for old in vendor.glob("AXe-macOS-*-universal.tar.gz"):
                if old != target:
                    old.unlink()
        write_pins(root, pins)
    finally:
        downloaded.unlink(missing_ok=True)
    print(f"{name}: pinned {release['version']} ({pin['sha256']})")
    if install_local:
        install_one(name, root, force=True)
    return release["version"]


def update(name: str = "all", root: Path = ROOT, install_local: bool = True) -> None:
    for tool in selected_tools(name):
        update_one(tool, root, install_local)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "update"))
    parser.add_argument("tool", nargs="?", choices=(*TOOL_SPECS, "all"), default="all")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-install", action="store_true", help="Update repo pins without installing locally")
    parser.add_argument("--force", action="store_true", help="Reinstall even when the current pin is healthy")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            install(args.tool, args.root.resolve(), force=args.force)
        else:
            update(args.tool, args.root.resolve(), install_local=not args.no_install)
    except (ToolError, OSError, ValueError, tarfile.TarError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
