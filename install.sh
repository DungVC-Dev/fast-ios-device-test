#!/usr/bin/env bash
# One-shot setup. Default: copy this folder to ~/.local/share and wire the skill,
# the two slash commands and the two launchers into Claude Code + PATH.
# `install.sh --link` skips the copy and links this folder in place (for editing).
# Safe to re-run; re-running from a newer shared folder upgrades in place.
set -euo pipefail

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${FAST_IOS_INSTALL_DIR:-$HOME/.local/share/fast-ios-device-test}"
MODE="copy"
[[ "${1:-}" == "--link" ]] && MODE="link"

if [[ "$MODE" == "copy" ]]; then
    # Default: copy the shared folder to a stable local path, so the original
    # (Downloads, AirDrop, a synced drive) can be deleted or moved afterwards.
    if [[ "$SOURCE" != "$INSTALL_DIR" ]]; then
        rm -rf "$INSTALL_DIR"
        mkdir -p "$(dirname "$INSTALL_DIR")"
        cp -R "$SOURCE" "$INSTALL_DIR"
        echo "copy: $SOURCE -> $INSTALL_DIR"
    fi
    HERE="$INSTALL_DIR"
else
    HERE="$SOURCE"
fi
SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
COMMANDS_DIR="${CLAUDE_COMMANDS_DIR:-$HOME/.claude/commands}"
BIN_DIR="${FAST_IOS_BIN_DIR:-$HOME/.local/bin}"

link() {
    local target="$1" path="$2"
    if [[ -e "$path" && ! -L "$path" ]]; then
        echo "skip: $path exists and is not a symlink (remove it to let install.sh manage it)"
        return
    fi
    ln -sfn "$target" "$path"
    echo "link: $path -> $target"
}

command -v xcodebuild >/dev/null || { echo "error: Xcode command line tools not found"; exit 1; }
if ! command -v axe >/dev/null; then
    command -v brew >/dev/null || { echo "error: 'axe' missing and Homebrew not found (brew install cameroncooke/axe/axe)"; exit 1; }
    # Homebrew refuses to install anything while the Command Line Tools are older than
    # macOS expects; the release tarball needs no Homebrew.
    brew install cameroncooke/axe/axe || { echo "error: Homebrew could not install 'axe'. Update the Command Line Tools, or unpack the universal tarball from https://github.com/cameroncooke/AXe/releases and put its 'axe' on PATH, then re-run."; exit 1; }
fi
xcode_major="$(xcodebuild -version | sed -n 's/^Xcode \([0-9]*\).*/\1/p')"
axe_version="$(axe --version 2>/dev/null | tr -dc '0-9.')"
if [[ "${xcode_major:-0}" -ge 27 && "$(printf '%s\n1.8.0\n' "$axe_version" | sort -V | head -1)" != "1.8.0" ]]; then
    echo "warn: Xcode $xcode_major needs AXe 1.8.0 or newer, found '${axe_version:-unknown}' (brew upgrade cameroncooke/axe/axe)"
fi
command -v xcodegen >/dev/null || brew install xcodegen
python3 -c "import PIL" 2>/dev/null || python3 -m pip install --user pillow \
    || echo "warn: could not install Pillow for $(command -v python3); install it for that interpreter (the engine imports PIL)"

mkdir -p "$SKILLS_DIR" "$COMMANDS_DIR" "$BIN_DIR"
link "$HERE/skills/fast-ios-device-test" "$SKILLS_DIR/fast-ios-device-test"
link "$HERE/commands/fastSimulatorTest.md" "$COMMANDS_DIR/fastSimulatorTest.md"
link "$HERE/commands/fastDeviceTest.md" "$COMMANDS_DIR/fastDeviceTest.md"
link "$HERE/scripts/fast_ui.py" "$BIN_DIR/fastSimulatorTest"
link "$HERE/scripts/fast_ui.py" "$BIN_DIR/fastUITest"
link "$HERE/scripts/fast_device.py" "$BIN_DIR/fastDeviceTest"
link "$HERE/scripts/fast_ui_report.py" "$BIN_DIR/fastUIReport"
link "$HERE/commands/fastUIReview.md" "$COMMANDS_DIR/fastUIReview.md"
link "$HERE/scripts/fast_ui_review.py" "$BIN_DIR/fastUIReview"
chmod +x "$HERE/scripts/fast_ui.py" "$HERE/scripts/fast_ui_report.py" "$HERE/scripts/fast_ui_review.py" "$HERE/scripts/fast_device.py"

case ":$PATH:" in
*":$BIN_DIR:"*) ;;
*) echo "note: add '$BIN_DIR' to PATH, e.g. echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc" ;;
esac

python3 "$HERE/scripts/test_fast_ui.py" >/dev/null 2>&1 && echo "engine self-test: OK" || echo "engine self-test: FAILED (run python3 scripts/test_fast_ui.py)"
echo "done. In Claude Code: /fastSimulatorTest <flow>, /fastDeviceTest <flow>, /fastUIReview <session>"
