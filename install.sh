#!/usr/bin/env bash
# One-shot setup. Default: copy this folder to ~/.local/share and wire the skill,
# the slash commands and the launchers into Claude Code + PATH.
# `install.sh --link`  links this folder in place instead of copying (for editing).
# `install.sh --check` prints versions and what is missing, and changes nothing.
# Safe to re-run; re-running from a newer shared folder upgrades in place.
set -euo pipefail

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${FAST_IOS_INSTALL_DIR:-$HOME/.local/share/fast-ios-device-test}"
SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
COMMANDS_DIR="${CLAUDE_COMMANDS_DIR:-$HOME/.claude/commands}"
BIN_DIR="${FAST_IOS_BIN_DIR:-$HOME/.local/bin}"
AXE_HOME="${FAST_IOS_AXE_DIR:-$HOME/.local/share/axe}"
MODE="copy"
case "${1:-}" in
    --link) MODE="link" ;;
    --check) MODE="check" ;;
esac

# `|| true`: with no Xcode selected `xcodebuild` is a failing shim, and under `set -eo pipefail`
# that would end the script before it could say so.
xcode_major="$(xcodebuild -version 2>/dev/null | sed -n 's/^Xcode \([0-9]*\).*/\1/p' || true)"

axe_version() { axe --version 2>/dev/null | tr -dc '0-9.'; }

# True when the axe on PATH is new enough for the selected Xcode (27 needs 1.8.0+).
axe_ok() {
    command -v axe >/dev/null || return 1
    [[ "${xcode_major:-0}" -lt 27 ]] && return 0
    [[ "$(printf '%s\n1.8.0\n' "$(axe_version)" | sort -V | head -1)" == "1.8.0" ]]
}

# The release tarball ships in vendor/, so a fresh Mac needs neither Homebrew nor a
# download; Homebrew is only the fallback when the tarball is missing.
install_axe() {
    local tarball
    tarball="$(ls "$SOURCE"/vendor/AXe-macOS-*-universal.tar.gz 2>/dev/null | head -1 || true)"
    if [[ -n "$tarball" ]]; then
        rm -rf "$AXE_HOME"
        mkdir -p "$AXE_HOME" "$BIN_DIR"
        tar -xzf "$tarball" -C "$AXE_HOME"
        xattr -dr com.apple.quarantine "$AXE_HOME" 2>/dev/null || true
        printf '#!/bin/bash\nexec "%s/axe" "$@"\n' "$AXE_HOME" > "$BIN_DIR/axe"
        chmod +x "$BIN_DIR/axe" "$AXE_HOME/axe"
        export PATH="$BIN_DIR:$PATH"
        echo "axe: installed bundled $(basename "$tarball") into $AXE_HOME"
        return
    fi
    command -v brew >/dev/null || { echo "error: no vendor/AXe tarball and no Homebrew (brew install cameroncooke/axe/axe)"; exit 1; }
    brew install cameroncooke/axe/axe || { echo "error: Homebrew could not install 'axe'; unpack the universal tarball from https://github.com/cameroncooke/AXe/releases into $AXE_HOME"; exit 1; }
}

profile_count() {
    ls "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"/*.mobileprovision \
       "$HOME/Library/MobileDevice/Provisioning Profiles"/*.mobileprovision 2>/dev/null | wc -l | tr -d ' '
}

if [[ "$MODE" == "check" ]]; then
    missing=()
    [[ -n "$xcode_major" ]] && echo "xcode=$(xcodebuild -version | head -1 | sed 's/Xcode //')" || { echo "xcode=missing"; missing+=(xcode); }
    if command -v axe >/dev/null; then
        echo "axe=$(axe_version) ($(command -v axe))"
        axe_ok || { echo "  axe is older than 1.8.0, which Xcode $xcode_major needs"; missing+=(axe-1.8.0); }
    else
        echo "axe=missing"; missing+=(axe)
    fi
    echo "python=$(python3 --version 2>&1 | sed 's/Python //') ($(command -v python3))"
    python3 -c "import PIL" 2>/dev/null && echo "pillow=yes" || echo "pillow=no (only fastUIReview, fastEvidenceSheet and the motion action need it)"
    command -v xcodegen >/dev/null && echo "xcodegen=yes (optional)" || echo "xcodegen=no (optional: device-runner ships its xcodeproj)"
    echo "profiles=$(profile_count) development profiles (fastDeviceTest needs one that lists the iPhone)"
    for name in fastSimulatorTest fastDeviceTest fastUIReview fastUIReport fastEvidenceSheet fastUIMap; do
        [[ -L "$BIN_DIR/$name" ]] || missing+=("$name launcher")
    done
    [[ -L "$SKILLS_DIR/fast-ios-device-test" ]] || missing+=(skill)
    if [[ ${#missing[@]} -eq 0 ]]; then echo "CHECK OK"; else echo "CHECK missing: ${missing[*]} (run install.sh)"; exit 1; fi
    exit 0
fi

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

link() {
    local target="$1" path="$2"
    if [[ -e "$path" && ! -L "$path" ]]; then
        echo "skip: $path exists and is not a symlink (remove it to let install.sh manage it)"
        return
    fi
    ln -sfn "$target" "$path"
    echo "link: $path -> $target"
}

[[ -n "$xcode_major" ]] || { echo "error: Xcode command line tools not found"; exit 1; }
mkdir -p "$SKILLS_DIR" "$COMMANDS_DIR" "$BIN_DIR"
axe_ok || install_axe
python3 -c "import PIL" 2>/dev/null || python3 -m pip install --user pillow >/dev/null 2>&1 \
    || echo "note: Pillow not installed; only fastUIReview, fastEvidenceSheet and the motion action need it (python3 -m pip install --user pillow)"

link "$HERE/skills/fast-ios-device-test" "$SKILLS_DIR/fast-ios-device-test"
link "$HERE/commands/fastSimulatorTest.md" "$COMMANDS_DIR/fastSimulatorTest.md"
link "$HERE/commands/fastDeviceTest.md" "$COMMANDS_DIR/fastDeviceTest.md"
link "$HERE/commands/fastUIReview.md" "$COMMANDS_DIR/fastUIReview.md"
link "$HERE/scripts/fast_ui.py" "$BIN_DIR/fastSimulatorTest"
link "$HERE/scripts/fast_ui.py" "$BIN_DIR/fastUITest"
link "$HERE/scripts/fast_device.py" "$BIN_DIR/fastDeviceTest"
link "$HERE/scripts/fast_ui_report.py" "$BIN_DIR/fastUIReport"
link "$HERE/scripts/fast_ui_review.py" "$BIN_DIR/fastUIReview"
link "$HERE/scripts/fast_evidence_sheet.py" "$BIN_DIR/fastEvidenceSheet"
link "$HERE/scripts/fast_ui_map.py" "$BIN_DIR/fastUIMap"
chmod +x "$HERE/scripts/fast_ui.py" "$HERE/scripts/fast_ui_report.py" "$HERE/scripts/fast_ui_review.py" "$HERE/scripts/fast_device.py" \
    "$HERE/scripts/fast_evidence_sheet.py" "$HERE/scripts/fast_ui_map.py"

case ":$PATH:" in
*":$BIN_DIR:"*) ;;
*) echo "note: add '$BIN_DIR' to PATH, e.g. echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc" ;;
esac

(cd "$HERE/scripts" && python3 -m unittest test_fast_ui test_fast_media test_fast_ui_map >/dev/null 2>&1) && echo "engine self-test: OK" \
    || echo "engine self-test: FAILED (cd scripts && python3 -m unittest test_fast_ui test_fast_media test_fast_ui_map)"
echo "done. In Claude Code: /fastSimulatorTest <flow>, /fastDeviceTest <flow>, /fastUIReview <session>"
