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

It copies the folder to `~/.local/share/fast-ios-device-test`, installs `axe`
(Homebrew; 1.8.0 or newer for Xcode 27), `xcodegen` and Pillow if missing, and
wires the skill into `~/.claude/skills`, the commands into `~/.claude/commands`,
and the launchers (`fastSimulatorTest`, `fastDeviceTest`, `fastUIReport`,
`fastUIReview`) into `~/.local/bin`. The shared copy can be deleted afterwards.
Restart Claude Code once. To upgrade, run `install.sh` again from a newer folder.

Maintainers who edit the tool in place: `install.sh --link` links this folder
instead of copying it.

To make a shareable zip: `zip -r fast-ios-device-test.zip fast-ios-device-test -x '*.DS_Store'`.

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
- `scripts/fast_device.py` + `device-runner/` — physical-iPhone flow runner (XCUITest, auto-signed)
