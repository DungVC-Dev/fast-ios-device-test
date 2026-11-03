#!/usr/bin/env python3
"""Export agent skills from a locally installed Xcode without redistributing them."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


RESOURCE_SUFFIX = Path(
    "Contents/PlugIns/IDEIntelligenceChat.framework/Versions/A/Resources"
)
MARKER = ".xcode-skill-export.json"
SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ExportError(RuntimeError):
    """A local Xcode skill could not be found or exported."""


def _app_from_path(path: Path) -> Path | None:
    path = path.expanduser().resolve()
    for candidate in (path, *path.parents):
        if candidate.suffix == ".app":
            return candidate
    return None


def xcode_candidates(extra: list[Path] | None = None) -> list[Path]:
    """Return unique Xcode applications from explicit, selected and standard paths."""
    paths: list[Path] = []
    paths.extend(extra or [])
    if os.environ.get("FAST_IOS_XCODE_PATHS"):
        paths.extend(
            Path(item) for item in os.environ["FAST_IOS_XCODE_PATHS"].split(os.pathsep) if item
        )
    if os.environ.get("DEVELOPER_DIR"):
        paths.append(Path(os.environ["DEVELOPER_DIR"]))
    try:
        selected = subprocess.run(
            ["xcode-select", "-p"], capture_output=True, text=True, timeout=5, check=False
        )
        if selected.returncode == 0 and selected.stdout.strip():
            paths.append(Path(selected.stdout.strip()))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    paths.extend(sorted(Path("/Applications").glob("Xcode*.app")))

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        app = _app_from_path(path)
        if app and app not in seen and (app / RESOURCE_SUFFIX).is_dir():
            seen.add(app)
            unique.append(app)
    return unique


def xcode_version(app: Path) -> str:
    try:
        with (app / "Contents/Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        return str(info.get("CFBundleShortVersionString") or info.get("DTXcode") or "unknown")
    except (OSError, plistlib.InvalidFileException):
        return "unknown"


def _version_key(app: Path) -> tuple[tuple[int, ...], str]:
    parts = tuple(int(part) for part in re.findall(r"\d+", xcode_version(app)))
    return parts, app.name


def available_skills(app: Path) -> list[str]:
    resources = app / RESOURCE_SUFFIX
    skills = []
    for template in resources.glob("*.idechatprompttemplate"):
        try:
            head = template.read_text(errors="replace")[:4096]
        except OSError:
            continue
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", head, re.DOTALL)
        if match and re.search(r"^name:\s*\S+", match.group(1), re.MULTILINE) \
                and re.search(r"^description:\s*\S+", match.group(1), re.MULTILINE):
            skills.append(template.stem)
    return sorted(skills)


def choose_xcode(skill: str | None, extra: list[Path] | None = None) -> Path:
    candidates = xcode_candidates(extra)
    if skill:
        candidates = [
            app for app in candidates
            if (app / RESOURCE_SUFFIX / f"{skill}.idechatprompttemplate").is_file()
        ]
    if not candidates:
        detail = f" containing the {skill!r} skill" if skill else ""
        raise ExportError(f"no Xcode installation{detail} was found")
    return max(candidates, key=_version_key)


def exported_name(skill: str) -> str:
    if not SKILL_NAME.fullmatch(skill):
        raise ExportError(f"invalid skill name: {skill!r}")
    return skill if skill.startswith("apple-") else f"apple-{skill}"


def _with_export_header(text: str, header: str, name: str) -> str:
    match = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n)", text, re.DOTALL)
    if not match:
        raise ExportError("the Xcode template has no YAML frontmatter")
    frontmatter = re.sub(
        r"^name:\s*.*$", f"name: {name}", match.group(2), count=1, flags=re.MULTILINE
    )
    return f"{match.group(1)}{frontmatter}{match.group(3)}\n> {header}\n\n{text[match.end():]}"


def render_skill(app: Path, skill: str, destination: Path) -> Path:
    resources = app / RESOURCE_SUFFIX
    template = resources / f"{skill}.idechatprompttemplate"
    if not template.is_file():
        raise ExportError(f"Xcode {xcode_version(app)} does not contain skill {skill!r}")

    refs = sorted(resources.glob(f"{skill}-ref-*.md.packaged"))
    output_name = exported_name(skill)
    output = destination / output_name
    header = (
        f"Exported from {app} {xcode_version(app)} — Apple content, not redistributed"
    )
    text = template.read_text()
    for ref in refs:
        suffix = ref.name[len(f"{skill}-ref-") : -len(".md.packaged")]
        text = text.replace(ref.name, f"references/{suffix}.md")
    text = _with_export_header(text, header, output_name)

    destination.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_name}-", dir=destination))
    try:
        (temporary / "references").mkdir()
        (temporary / "SKILL.md").write_text(text)
        for ref in refs:
            suffix = ref.name[len(f"{skill}-ref-") : -len(".md.packaged")]
            (temporary / "references" / f"{suffix}.md").write_bytes(ref.read_bytes())
        (temporary / MARKER).write_text(json.dumps({
            "skill": skill,
            "xcode": str(app),
            "version": xcode_version(app),
        }, indent=2) + "\n")
        if output.exists() or output.is_symlink():
            if not (output / MARKER).is_file():
                raise ExportError(f"refusing to replace unmanaged skill folder: {output}")
            shutil.rmtree(output)
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output


def remove_skill(skill: str, destinations: list[Path]) -> list[Path]:
    removed = []
    for destination in destinations:
        output = destination.expanduser() / exported_name(skill)
        if not output.exists() and not output.is_symlink():
            continue
        if not (output / MARKER).is_file():
            raise ExportError(f"refusing to remove unmanaged skill folder: {output}")
        shutil.rmtree(output)
        removed.append(output)
    return removed


def default_destination() -> Path:
    return Path(os.environ.get("CLAUDE_SKILLS_DIR", "~/.claude/skills")).expanduser()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", default="app-resizability", help="Xcode skill to export")
    parser.add_argument("--list", action="store_true", help="list exportable skills")
    parser.add_argument("--remove", action="store_true", help="remove this exported skill")
    parser.add_argument(
        "--destination", action="append", type=Path,
        help="agent skills directory (repeatable; defaults to Claude Code)",
    )
    parser.add_argument(
        "--xcode", action="append", type=Path, help=argparse.SUPPRESS
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    destinations = args.destination or [default_destination()]
    try:
        if args.remove:
            for path in remove_skill(args.skill, destinations):
                print(f"removed: {path}")
            return 0
        app = choose_xcode(None if args.list else args.skill, args.xcode)
        if args.list:
            print(f"Xcode {xcode_version(app)} ({app})")
            for name in available_skills(app):
                print(name)
            return 0
        for destination in destinations:
            output = render_skill(app, args.skill, destination.expanduser())
            print(f"exported: {output}")
        return 0
    except (ExportError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
