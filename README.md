# fast-ios-device-test

Claude Code slash commands for fast iOS verification:

| Command | What it does |
|---|---|
| `/fastSimulatorTest <screen or flow>` | Drives the app on Simulator through a JSON flow (fresh install, injected UserDefaults, PASS/FAIL line). Fans out one agent per simulator for a matrix. |
| `/fastDeviceTest <screen or flow>` | Runs the same JSON flow on a physical iPhone through a cached, auto-signed XCUITest runner; can also drive Settings, Shortcuts and SpringBoard. |
| `/fastUIReview <session>` | Builds contact sheets from a recorded session so every case's video is reviewed, not just its PASS line. |

## Setup (once per machine)

Share this folder any way you like (zip, AirDrop, shared drive). The recipient
runs one command from wherever the folder landed:

```bash
~/Downloads/fast-ios-device-test/install.sh
```

It copies the folder to `~/.local/share/fast-ios-device-test`, unpacks the bundled
`axe` (`vendor/`, 1.8.0, needed for Xcode 27) into `~/.local/share/axe` when none
new enough is on PATH, installs Pillow if it can, and wires the skill into
`~/.claude/skills`, the commands into `~/.claude/commands`, and the launchers
(`fastSimulatorTest`, `fastDeviceTest`, `fastUIReport`, `fastUIReview`) into
`~/.local/bin`. No Homebrew and no xcodegen are needed. The shared copy can be
deleted afterwards. Restart Claude Code once. To upgrade, run `install.sh` again
from a newer folder. `install.sh --check` prints the versions it sees and what is
missing without changing anything.

Maintainers who edit the tool in place: `install.sh --link` links this folder
instead of copying it. To make a shareable zip: `bash make-zip.sh`.

Optional, for exploring a screen with Apple's own tools (pinch, drag, rotate, app
console log) before writing a flow: register Xcode 27's MCP server once with
`claude mcp add xcode -- xcrun mcpbridge`; the skill says when to use which.

## Setup per project

None. `/fastSimulatorTest` and `/fastDeviceTest` read everything from the flow
JSON the agent writes (scheme, bundle id, simulator, build folder); the skill
shows the smallest complete flow.

## Contents

- `.claude-plugin/` — plugin + marketplace manifests
- `skills/fast-ios-device-test/SKILL.md` — agent instructions (flow file, single flow, several flows or simulators)
- `skills/fast-ios-device-test/references/device.md` — fastDeviceTest on a physical iPhone
- `skills/fast-ios-device-test/references/review.md` — reviewing recorded runs with fastUIReview
- `skills/fast-ios-device-test/references/usage.md` — flow action reference, matrix, cache model, troubleshooting
- `commands/` — the three slash commands
- `bin/` — launchers (`fastSimulatorTest`, `fastDeviceTest`, `fastUIReport`, `fastUIReview`) for the plugin install
- `scripts/fast_ui.py` — Simulator flow engine (`scripts/test_fast_ui.py` tests it); `--record`, `--session`
- `scripts/fast_ui_report.py` — collates a fan-out session into a flow × simulator table (`fastUIReport`)
- `scripts/fast_ui_review.py` — contact sheets and review notes for recorded runs (`fastUIReview`)
- `scripts/fast_device.py` + `device-runner/` — physical-iPhone flow runner (XCUITest, auto-signed; the `.xcodeproj` is committed, regenerate with `xcodegen generate` after editing `project.yml`)
- `vendor/` — the AXe release tarball `install.sh` unpacks when no `axe` ≥ 1.8.0 is on PATH (MIT, see `vendor/AXe-LICENSE`)
- `docs/` — optimization research and the implementation plan behind 1.2.0
