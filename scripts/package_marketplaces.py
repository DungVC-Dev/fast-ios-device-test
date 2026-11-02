#!/usr/bin/env python3
"""Build clean provider packages from the shared plugin source."""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read_version() -> str:
    return json.loads((ROOT / "package.json").read_text())["version"]


def copy_shared(destination: Path) -> None:
    shutil.copytree(ROOT / "skills", destination / "skills")
    shutil.copytree(ROOT / "assets", destination / "assets")


def write_zip(source: Path, archive: Path) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"refusing symlink in marketplace package: {path}")
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            info = zipfile.ZipInfo.from_file(path, relative.as_posix())
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            output.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)


def build(out_dir: Path) -> list[Path]:
    version = read_version()
    stage = out_dir / "stage"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    stage.mkdir(parents=True)

    codex = stage / "codex"
    codex.mkdir()
    copy_shared(codex)
    shutil.copy2(ROOT / "plugin.json", codex / "plugin.json")

    antigravity = stage / "antigravity"
    antigravity.mkdir()
    copy_shared(antigravity)
    shutil.copy2(ROOT / ".antigravity-plugin" / "plugin.json", antigravity / "plugin.json")
    shutil.copy2(ROOT / ".antigravity-plugin" / "README.md", antigravity / "README.md")

    gemini = stage / "gemini-cli"
    gemini.mkdir()
    copy_shared(gemini)
    shutil.copy2(ROOT / "gemini-extension.json", gemini / "gemini-extension.json")
    shutil.copy2(ROOT / "GEMINI_EXTENSION.md", gemini / "GEMINI_EXTENSION.md")
    shutil.copy2(ROOT / ".antigravity-plugin" / "README.md", gemini / "README.md")

    archives = []
    for provider, source in (
        ("codex", codex),
        ("antigravity", antigravity),
        ("gemini-cli", gemini),
    ):
        archive = out_dir / f"fast-ios-device-test-{provider}-{version}.zip"
        write_zip(source, archive)
        archives.append(archive)
    return archives


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "build" / "plugin-packages",
        help="directory for clean staging folders and provider ZIPs",
    )
    args = parser.parse_args()
    for archive in build(args.out_dir.resolve()):
        print(archive)


if __name__ == "__main__":
    main()
