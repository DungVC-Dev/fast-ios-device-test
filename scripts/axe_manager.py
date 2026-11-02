#!/usr/bin/env python3
"""Install and update the AXe version pinned in vendor/axe.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
RELEASE_API = "https://api.github.com/repos/cameroncooke/AXe/releases/latest"
ASSET = re.compile(r"^AXe-macOS-v(?P<version>[^/]+)-universal\.tar\.gz$")


class AxeError(RuntimeError):
    pass


def pin_path(root: Path) -> Path:
    return root / "vendor" / "axe.json"


def read_pin(root: Path = ROOT) -> dict[str, str]:
    try:
        value = json.loads(pin_path(root).read_text(encoding="utf-8"))
        pin = {key: str(value[key]) for key in ("version", "url", "sha256")}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise AxeError(f"cannot read AXe pin {pin_path(root)}: {error}") from error
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", pin["version"]):
        raise AxeError(f"invalid AXe pinned version: {pin['version']!r}")
    if not pin["url"].startswith("https://github.com/cameroncooke/AXe/releases/download/"):
        raise AxeError(f"invalid AXe pinned URL: {pin['url']!r}")
    asset = ASSET.fullmatch(Path(pin["url"]).name)
    if not asset or asset.group("version") != pin["version"]:
        raise AxeError("AXe pinned version and archive URL do not match")
    if not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]):
        raise AxeError("invalid AXe pinned sha256")
    return pin


def archive_name(pin: dict[str, str]) -> str:
    return Path(pin["url"]).name


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "fast-ios-device-test"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (fixed/pinned HTTPS URLs)
        value = json.load(response)
    if not isinstance(value, dict):
        raise AxeError(f"unexpected JSON from {url}")
    return value


def latest_release(payload: dict[str, Any]) -> dict[str, str]:
    tag = str(payload.get("tag_name", "")).removeprefix("v")
    for asset in payload.get("assets", []):
        if not isinstance(asset, dict):
            continue
        match = ASSET.fullmatch(str(asset.get("name", "")))
        url = str(asset.get("browser_download_url", ""))
        if match and match.group("version") == tag and url.startswith("https://github.com/cameroncooke/AXe/releases/download/"):
            return {"version": tag, "url": url}
    raise AxeError(f"AXe release v{tag or '?'} has no universal macOS tarball")


def download(url: str, target: Path, timeout: float = 60.0) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "fast-ios-device-test"})
    with urllib.request.urlopen(request, timeout=timeout) as response, target.open("wb") as stream:  # noqa: S310
        shutil.copyfileobj(response, stream)


def checked_archive(root: Path, pin: dict[str, str], allow_download: bool = True) -> tuple[Path, bool]:
    vendored = root / "vendor" / archive_name(pin)
    if vendored.exists():
        actual = sha256(vendored)
        if actual != pin["sha256"]:
            raise AxeError(f"AXe archive checksum mismatch: expected {pin['sha256']}, got {actual} ({vendored})")
        return vendored, False
    if not allow_download:
        raise AxeError(f"pinned AXe archive is missing: {vendored}")
    handle, raw = tempfile.mkstemp(prefix="fast-ios-axe-", suffix=".tar.gz")
    os.close(handle)
    temporary = Path(raw)
    try:
        download(pin["url"], temporary)
        actual = sha256(temporary)
        if actual != pin["sha256"]:
            raise AxeError(f"downloaded AXe checksum mismatch: expected {pin['sha256']}, got {actual}")
        return temporary, True
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as bundle:
        root = destination.resolve()
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise AxeError(f"AXe archive contains an unsafe path: {member.name}")
        bundle.extractall(destination)  # noqa: S202 - archive is pinned and SHA-256 verified


def binary_version(binary: Path) -> str | None:
    try:
        result = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = re.search(r"\d+(?:\.\d+)+", f"{result.stdout}\n{result.stderr}")
    return found.group(0) if result.returncode == 0 and found else None


def verify_archive(archive: Path, version: str) -> None:
    with tempfile.TemporaryDirectory(prefix="fast-ios-axe-verify-") as raw:
        folder = Path(raw)
        safe_extract(archive, folder)
        actual = binary_version(folder / "axe")
        if actual != version:
            raise AxeError(f"AXe archive runs as {actual or 'unknown'}, expected {version}")


def install(root: Path = ROOT) -> str:
    pin = read_pin(root)
    archive, temporary_archive = checked_archive(root, pin)
    axe_home = Path(os.environ.get("FAST_IOS_AXE_DIR", Path.home() / ".local/share/axe")).expanduser()
    bin_dir = Path(os.environ.get("FAST_IOS_BIN_DIR", Path.home() / ".local/bin")).expanduser()
    axe_home.parent.mkdir(parents=True, exist_ok=True)
    extracted = Path(tempfile.mkdtemp(prefix=".axe-install-", dir=axe_home.parent))
    try:
        safe_extract(archive, extracted)
        actual = binary_version(extracted / "axe")
        if actual != pin["version"]:
            raise AxeError(f"AXe archive runs as {actual or 'unknown'}, expected {pin['version']}")
        (extracted / ".fast-ios-pin.json").write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(extracted)], capture_output=True, check=False)
        if axe_home.exists() or axe_home.is_symlink():
            if axe_home.is_dir() and not axe_home.is_symlink():
                shutil.rmtree(axe_home)
            else:
                axe_home.unlink()
        extracted.replace(axe_home)
        bin_dir.mkdir(parents=True, exist_ok=True)
        wrapper = bin_dir / "axe"
        temporary_wrapper = wrapper.with_name(f".{wrapper.name}.{os.getpid()}.tmp")
        temporary_wrapper.write_text(f'#!/bin/bash\nexec "{axe_home / "axe"}" "$@"\n', encoding="utf-8")
        temporary_wrapper.chmod(0o755)
        temporary_wrapper.replace(wrapper)
    finally:
        shutil.rmtree(extracted, ignore_errors=True)
        if temporary_archive:
            archive.unlink(missing_ok=True)
    print(f"axe: installed pinned {pin['version']} into {axe_home}")
    return pin["version"]


def write_pin(root: Path, pin: dict[str, str]) -> None:
    path = pin_path(root)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def update(root: Path = ROOT, install_local: bool = True) -> str:
    release = latest_release(request_json(RELEASE_API))
    handle, raw = tempfile.mkstemp(prefix="fast-ios-axe-update-", suffix=".tar.gz")
    os.close(handle)
    downloaded = Path(raw)
    try:
        download(release["url"], downloaded)
        digest = sha256(downloaded)
        verify_archive(downloaded, release["version"])
        pin = {**release, "sha256": digest}
        vendor = root / "vendor"
        vendor.mkdir(parents=True, exist_ok=True)
        target = vendor / Path(release["url"]).name
        replacement = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        shutil.copy2(downloaded, replacement)
        replacement.replace(target)
        write_pin(root, pin)
        for old in vendor.glob("AXe-macOS-*-universal.tar.gz"):
            if old != target:
                old.unlink()
    finally:
        downloaded.unlink(missing_ok=True)
    print(f"axe: pinned {release['version']} ({digest})")
    if install_local:
        install(root)
    return release["version"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "update"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-install", action="store_true", help="Update the repo pin without installing AXe locally")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            install(args.root.resolve())
        else:
            update(args.root.resolve(), install_local=not args.no_install)
    except (AxeError, OSError, ValueError, tarfile.TarError) as error:
        print(f"error: {error}", file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
