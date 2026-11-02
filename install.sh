#!/usr/bin/env bash
# One-shot setup. Default: copy this folder to ~/.local/share and wire the skill,
# the slash commands and the launchers into Claude Code + PATH.
# `install.sh --link`  links this folder in place instead of copying (for editing).
# `install.sh --install-axe` installs only the pinned AXe; `--update-axe` updates the repo pin,
# vendored archive and local AXe. `--uninstall` removes what install.sh put in place.
# Codex and Antigravity skill links (README, "Development install") are never created here, but
# one left dangling (its clone moved or deleted) is re-pointed at this copy: a dead link hides
# the skill from that agent while the launchers still work.
# `install.sh --check` prints versions and what is missing or broken, and changes nothing;
# `install.sh --check --device <name|udid>` also checks that iPhone (fastDeviceTest check).
# Safe to re-run; re-running from a newer shared folder upgrades in place.
set -euo pipefail

SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${FAST_IOS_INSTALL_DIR:-$HOME/.local/share/fast-ios-device-test}"
SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
COMMANDS_DIR="${CLAUDE_COMMANDS_DIR:-$HOME/.claude/commands}"
BIN_DIR="${FAST_IOS_BIN_DIR:-$HOME/.local/bin}"
AGENTS_DIR="${CLAUDE_AGENTS_DIR:-$HOME/.claude/agents}"
AXE_HOME="${FAST_IOS_AXE_DIR:-$HOME/.local/share/axe}"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
CODEX_SKILLS_DIR="${CODEX_SKILLS_DIR:-$CODEX_HOME_DIR/skills}"
CODEX_PLUGIN_CACHE="${CODEX_PLUGIN_CACHE:-$CODEX_HOME_DIR/plugins/cache/fast-ios-device-test}"
ANTIGRAVITY_SKILLS_DIR="${ANTIGRAVITY_SKILLS_DIR:-$HOME/.gemini/config/skills}"
ANTIGRAVITY_PLUGIN_DIR="${ANTIGRAVITY_PLUGIN_DIR:-$HOME/.gemini/config/plugins/fast-ios-device-test}"
MODE="copy"
CHECK_DEVICE=""
case "${1:-}" in
    --link) MODE="link" ;;
    --check) MODE="check"; [[ "${2:-}" == "--device" ]] && CHECK_DEVICE="${3:-}" ;;
    --install-axe) MODE="install-axe" ;;
    --update-axe) MODE="update-axe" ;;
    --uninstall) MODE="uninstall" ;;
esac

LINKS=(
    "$SKILLS_DIR/fast-ios-device-test"
    "$COMMANDS_DIR/fastSimulatorTest.md" "$COMMANDS_DIR/fastDeviceTest.md" "$COMMANDS_DIR/fastUIReview.md"
    "$AGENTS_DIR/ui-explorer.md"
    "$BIN_DIR/fastSimulatorTest" "$BIN_DIR/fastUITest" "$BIN_DIR/fastDeviceTest" "$BIN_DIR/fastUIReport"
    "$BIN_DIR/fastUIReview" "$BIN_DIR/fastEvidenceSheet" "$BIN_DIR/fastUIMap" "$BIN_DIR/fastUIClean"
)

# Other agents' links to this skill: the user makes them, install.sh only keeps them working.
OTHER_SKILL_LINKS=("codex:$CODEX_SKILLS_DIR/fast-ios-device-test" "antigravity:$ANTIGRAVITY_SKILLS_DIR/fast-ios-device-test")

# A link's target as an absolute path (`readlink` returns a relative target as written).
link_target() {
    local target
    target="$(readlink "$1")"
    [[ "$target" == /* ]] || target="$(dirname "$1")/$target"
    printf '%s\n' "$target"
}

# True when a plugin folder holds the main skill (not only the setup skill).
plugin_has_skill() {
    [[ -n "$(find "$1" -path '*/skills/fast-ios-device-test/SKILL.md' 2>/dev/null | head -1)" ]]
}

if [[ "$MODE" == "install-axe" || "$MODE" == "update-axe" ]]; then
    action="install"
    [[ "$MODE" == "update-axe" ]] && action="update"
    exec python3 "$SOURCE/scripts/axe_manager.py" "$action" --root "$SOURCE"
fi

if [[ "$MODE" == "uninstall" ]]; then
    # Only links that point at a copy of this tool (any folder holding scripts/fast_ui.py
    # or the skill): a file the user put there, or a link elsewhere, stays.
    for path in "${LINKS[@]}"; do
        [[ -L "$path" ]] || continue
        target="$(readlink "$path")"
        case "$target" in
        */scripts/fast_*.py | */skills/fast-ios-device-test | */commands/fast*.md | */agents/ui-explorer.md)
            rm "$path"; echo "removed: $path" ;;
        *) echo "kept: $path (points at $target)" ;;
        esac
    done
    # A Codex/Antigravity link into the copy deleted below would be left dangling; one already
    # dangling serves nothing. A link to a clone that still exists stays.
    install_real="$(cd "$INSTALL_DIR" 2>/dev/null && pwd -P || echo "$INSTALL_DIR")"
    for entry in "${OTHER_SKILL_LINKS[@]}"; do
        path="${entry#*:}"
        [[ -L "$path" ]] || continue
        target="$(link_target "$path")"
        target_real="$(cd "$(dirname "$target")" 2>/dev/null && echo "$(pwd -P)/$(basename "$target")" || echo "$target")"
        if [[ ! -e "$path" || "$target_real" == "$install_real" || "$target_real" == "$install_real/"* \
              || "$target" == "$INSTALL_DIR" || "$target" == "$INSTALL_DIR/"* ]]; then
            rm "$path"; echo "removed: $path"
        fi
    done
    # The project-managed local AXe only when its wrapper is the one install.sh wrote; unrelated
    # PATH copies stay.
    if [[ -f "$BIN_DIR/axe" ]] && grep -q "exec \"$AXE_HOME/axe\"" "$BIN_DIR/axe" 2>/dev/null; then
        rm -f "$BIN_DIR/axe"; rm -rf "$AXE_HOME"; echo "removed: local AXe ($AXE_HOME)"
    fi
    echo "uninstalled. Caches, screen maps and build output under each project's build/ were kept;"
    echo "delete them first with: npx fast-ios-device-test clean [--project <root>] --maps --yes"
    echo "A clone used with --link stays where it is."
    # Last: this script may itself live in the copied tool.
    if [[ -d "$INSTALL_DIR" && -f "$INSTALL_DIR/install.sh" ]]; then
        echo "removed: $INSTALL_DIR"; rm -rf "$INSTALL_DIR"
    fi
    exit 0
fi

# `|| true`: with no Xcode selected `xcodebuild` is a failing shim, and under `set -eo pipefail`
# that would end the script before it could say so.
xcode_major="$(xcodebuild -version 2>/dev/null | sed -n 's/^Xcode \([0-9]*\).*/\1/p' || true)"

axe_version() { "$1" --version 2>/dev/null | grep -Eo '[0-9]+(\.[0-9]+)+' | head -1; }

profile_count() {
    ls "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"/*.mobileprovision \
       "$HOME/Library/MobileDevice/Provisioning Profiles"/*.mobileprovision 2>/dev/null | wc -l | tr -d ' '
}

if [[ "$MODE" == "check" ]]; then
    missing=()
    [[ -n "$xcode_major" ]] && echo "xcode=$(xcodebuild -version | head -1 | sed 's/Xcode //')" || { echo "xcode=missing"; missing+=(xcode); }
    pinned_axe="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$SOURCE/vendor/axe.json" 2>/dev/null || true)"
    installed_axe="$(axe_version "$AXE_HOME/axe" || true)"
    python3 "$SOURCE/scripts/fast_update.py" --axe-status "$SOURCE/vendor/axe.json" "$AXE_HOME/axe"
    if [[ -z "$pinned_axe" ]]; then
        missing+=("axe pin")
    elif [[ "$installed_axe" != "$pinned_axe" ]]; then
        missing+=("axe-$pinned_axe")
    elif [[ ! -x "$BIN_DIR/axe" ]] || ! grep -Fq "exec \"$AXE_HOME/axe\"" "$BIN_DIR/axe" 2>/dev/null; then
        missing+=("axe wrapper")
    else
        echo "axe=local $installed_axe ($AXE_HOME/axe)"
    fi
    echo "python=$(python3 --version 2>&1 | sed 's/Python //') ($(command -v python3))"
    # The version the launchers run (a --link clone or the copy), and the latest on npm.
    installed_root=""
    [[ -e "$BIN_DIR/fastSimulatorTest" ]] && installed_root="$(cd "$(dirname "$(link_target "$BIN_DIR/fastSimulatorTest")")/.." 2>/dev/null && pwd -P || true)"
    python3 "$SOURCE/scripts/fast_update.py" --status "${installed_root:-$SOURCE}" || true
    python3 -c "import PIL" 2>/dev/null && echo "pillow=yes" || echo "pillow=no (only fastUIReview, fastEvidenceSheet and the motion action need it)"
    command -v xcodegen >/dev/null && echo "xcodegen=yes (optional)" || echo "xcodegen=no (optional: device-runner ships its xcodeproj)"
    echo "profiles=$(profile_count) development profiles (fastDeviceTest needs one that lists the iPhone)"
    # `-L` alone is true for a link whose target was deleted (a moved or removed clone).
    need_link() {
        if [[ ! -L "$1" ]]; then missing+=("$2")
        elif [[ ! -e "$1" ]]; then echo "  broken link: $1 -> $(readlink "$1")"; missing+=("$2 (broken link)")
        fi
    }
    for name in fastSimulatorTest fastDeviceTest fastUIReview fastUIReport fastEvidenceSheet fastUIMap fastUIClean; do
        need_link "$BIN_DIR/$name" "$name launcher"
    done
    need_link "$SKILLS_DIR/fast-ios-device-test" skill
    need_link "$AGENTS_DIR/ui-explorer.md" "ui-explorer agent"
    # Codex and Antigravity are optional; a broken install of either is not.
    for entry in "${OTHER_SKILL_LINKS[@]}"; do
        agent="${entry%%:*}"; path="${entry#*:}"
        if [[ -L "$path" && ! -e "$path" ]]; then
            echo "$agent=broken skill link: $path -> $(readlink "$path") (rerun install.sh, or relink it: README \"Development install\")"
            missing+=("$agent skill (broken link)")
        elif [[ -e "$path/SKILL.md" ]]; then
            echo "$agent=skill link ($(readlink "$path" 2>/dev/null || echo "$path"))"
        else
            if [[ "$agent" == codex ]]; then
                plugin="$CODEX_PLUGIN_CACHE"; home="$CODEX_HOME_DIR"
                fix="codex plugin add fast-ios-device-test@fast-ios-device-test, then restart Codex"
            else
                plugin="$ANTIGRAVITY_PLUGIN_DIR"; home="$(dirname "$ANTIGRAVITY_SKILLS_DIR")"
                fix="agy plugin install https://github.com/DungVC-Dev/fast-ios-device-test, then restart Antigravity"
            fi
            if plugin_has_skill "$plugin"; then
                echo "$agent=plugin ($plugin)"
            elif [[ -d "$plugin" ]]; then
                echo "$agent=plugin folder without the fast-ios-device-test skill: $plugin ($fix)"
                missing+=("$agent skill (empty plugin)")
            elif [[ -d "$home" ]]; then
                echo "$agent=no skill (optional: $fix)"
            fi
        fi
    done
    if [[ -n "$CHECK_DEVICE" ]]; then
        python3 "$SOURCE/scripts/fast_device.py" check --device "$CHECK_DEVICE" | sed 's/^/  /' || missing+=("iPhone $CHECK_DEVICE")
    fi
    if [[ ${#missing[@]} -eq 0 ]]; then echo "CHECK OK"; else echo "CHECK missing: ${missing[*]} (run install.sh; iPhone fixes are listed above)"; exit 1; fi
    exit 0
fi

if [[ "$MODE" == "copy" ]]; then
    # Default: copy the shared folder to a stable local path, so the original
    # (Downloads, AirDrop, a synced drive) can be deleted or moved afterwards.
    if [[ "$SOURCE" != "$INSTALL_DIR" ]]; then
        if [[ -e "$INSTALL_DIR/.git" ]]; then
            echo "error: $INSTALL_DIR is a git clone; a plain install would delete it."
            echo "  Update it with: git -C \"$INSTALL_DIR\" pull && \"$INSTALL_DIR/install.sh\" --link"
            exit 1
        fi
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
mkdir -p "$SKILLS_DIR" "$COMMANDS_DIR" "$BIN_DIR" "$AGENTS_DIR"
python3 "$SOURCE/scripts/axe_manager.py" install --root "$SOURCE"
python3 -c "import PIL" 2>/dev/null || python3 -m pip install --user pillow >/dev/null 2>&1 \
    || echo "note: Pillow not installed; only fastUIReview, fastEvidenceSheet and the motion action need it (python3 -m pip install --user pillow)"

link "$HERE/skills/fast-ios-device-test" "$SKILLS_DIR/fast-ios-device-test"
link "$HERE/commands/fastSimulatorTest.md" "$COMMANDS_DIR/fastSimulatorTest.md"
link "$HERE/commands/fastDeviceTest.md" "$COMMANDS_DIR/fastDeviceTest.md"
link "$HERE/commands/fastUIReview.md" "$COMMANDS_DIR/fastUIReview.md"
link "$HERE/agents/ui-explorer.md" "$AGENTS_DIR/ui-explorer.md"
link "$HERE/scripts/fast_ui.py" "$BIN_DIR/fastSimulatorTest"
link "$HERE/scripts/fast_ui.py" "$BIN_DIR/fastUITest"
link "$HERE/scripts/fast_device.py" "$BIN_DIR/fastDeviceTest"
link "$HERE/scripts/fast_ui_report.py" "$BIN_DIR/fastUIReport"
link "$HERE/scripts/fast_ui_review.py" "$BIN_DIR/fastUIReview"
link "$HERE/scripts/fast_evidence_sheet.py" "$BIN_DIR/fastEvidenceSheet"
link "$HERE/scripts/fast_ui_map.py" "$BIN_DIR/fastUIMap"
link "$HERE/scripts/fast_ui_clean.py" "$BIN_DIR/fastUIClean"
for entry in "${OTHER_SKILL_LINKS[@]}"; do
    path="${entry#*:}"
    # Only a dangling link (its name says it is this skill): a working one may be a clone the
    # user links on purpose.
    [[ -L "$path" && ! -e "$path" ]] || continue
    link "$HERE/skills/fast-ios-device-test" "$path"
done
chmod +x "$HERE/scripts/fast_ui.py" "$HERE/scripts/fast_ui_report.py" "$HERE/scripts/fast_ui_review.py" "$HERE/scripts/fast_device.py" \
    "$HERE/scripts/fast_evidence_sheet.py" "$HERE/scripts/fast_ui_map.py" "$HERE/scripts/fast_ui_clean.py" \
    "$HERE/scripts/fast_device_test.sh" "$HERE/scripts/shims/swiftlint"

case ":$PATH:" in
*":$BIN_DIR:"*) ;;
*) echo "note: add '$BIN_DIR' to PATH, e.g. echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc" ;;
esac

(cd "$HERE/scripts" && python3 -m unittest test_fast_ui test_fast_media test_fast_ui_map test_fast_guard >/dev/null 2>&1) && echo "engine self-test: OK" \
    || echo "engine self-test: FAILED (cd scripts && python3 -m unittest test_fast_ui test_fast_media test_fast_ui_map test_fast_guard)"
echo "done. In Claude Code: /fastSimulatorTest <flow>, /fastDeviceTest <flow>, /fastUIReview <session>"
