# fast-ios-device-test

Claude Code slash commands for fast iOS verification:

| Command | What it does |
|---|---|
| `/fastSimulatorTest <screen or flow>` | Drives the app on Simulator through a JSON flow (fresh install, injected UserDefaults, PASS/FAIL line). Fans out one agent per simulator for a matrix. |
| `/fastDeviceTest <screen or flow>` | Runs the same JSON flow on a physical iPhone through a cached, auto-signed XCUITest runner; can also drive Settings, Shortcuts and SpringBoard. |
| `/fastUIReview <session>` | Builds contact sheets from a recorded session so every case's video is reviewed, not just its PASS line. |

Plus the `fastEvidenceSheet <spec.json>` launcher: one captioned JPEG of chosen screenshots
for a PR or ticket. Both engines record with `--record` (the iPhone through XCTest's own
screen recording) and keep the clip at review quality (H.264, 960 px, ~1–2 MB for 20 s).

## Install (once per machine)

Needs Xcode (26 or 27). Nothing else: AXe 1.8.0 is bundled in `vendor/`.

```bash
git clone https://github.com/kiluss2/fast-ios-device-test.git ~/fast-ios-device-test
~/fast-ios-device-test/install.sh --link
```

Restart Claude Code. To upgrade later: `git -C ~/fast-ios-device-test pull`. With
`--link` the skill, commands and launchers point into the clone, so keep that folder.

Without git: download `fast-ios-device-test-<version>.zip` from the
[Releases](https://github.com/kiluss2/fast-ios-device-test/releases) page, unzip it
anywhere and run its `install.sh` (no flag). That copies the tool to
`~/.local/share/fast-ios-device-test`, so the unzipped folder can be deleted.

Either way the installer unpacks the bundled `axe` into `~/.local/share/axe` when none
new enough is on PATH, installs Pillow if it can (only video review needs it), and
links the skill into `~/.claude/skills`, the commands into `~/.claude/commands` and
the launchers (`fastSimulatorTest`, `fastDeviceTest`, `fastUIReport`, `fastUIReview`, `fastUIMap`)
into `~/.local/bin`. `install.sh --check` prints what it sees and what is missing,
without changing anything.

Optional, for exploring a screen with Apple's own tools (pinch, drag, rotate, app
console log) before writing a flow: register Xcode 27's MCP server once with
`claude mcp add xcode -- xcrun mcpbridge`; the skill says when to use which.

Maintainers: `bash make-zip.sh` builds the release zip next to the folder.

## What's new

See [CHANGELOG.md](CHANGELOG.md): 1.5.0 makes step-by-step runs fast on both engines
(`fastSimulatorTest do`, `expect` guards on multi-step requests, a refusal for destructive steps
in them). 1.4.0 adds the gestures a tester uses (hold, drag, edge
swipes, keys, pinch, rotate, orientation, Siri…), a screen map (`fastUIMap`) recorded from
normal runs, and prompt rules that answer each permission prompt its own way. 1.3.0 records the
iPhone screen, keeps every clip light
enough for a PR, and adds `fastEvidenceSheet`. 1.2.0 made the tool faster, made failures
explain themselves, drove system apps and installed without Homebrew.

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
- `bin/` — launchers (`fastSimulatorTest`, `fastDeviceTest`, `fastUIReport`, `fastUIReview`, `fastEvidenceSheet`, `fastUIMap`) for the plugin install
- `scripts/fast_ui.py` — Simulator flow engine (`scripts/test_fast_ui.py` tests it); `--record`, `--session`
- `scripts/fast_ui_report.py` — collates a fan-out session into a flow × simulator table (`fastUIReport`)
- `scripts/fast_ui_review.py` — contact sheets and review notes for recorded runs (`fastUIReview`)
- `scripts/fast_evidence_sheet.py` — captioned evidence sheet for a PR (`fastEvidenceSheet`; `scripts/test_fast_evidence_sheet.py`)
- `scripts/fast_ui_map.py` — screen map recorded from both engines' runs, and its `fastUIMap` launcher (`scripts/test_fast_ui_map.py`)
- `scripts/fast_media.py` — review-quality video re-encode and the one-final-clip rule, shared by both engines (`scripts/test_fast_media.py`)
- `scripts/fast_device.py` + `device-runner/` — physical-iPhone flow runner (XCUITest, auto-signed; the `.xcodeproj` is committed, regenerate with `xcodegen generate` after editing `project.yml`)
- `vendor/` — the AXe release tarball `install.sh` unpacks when no `axe` ≥ 1.8.0 is on PATH (MIT, see `vendor/AXe-LICENSE`)
- `docs/` — optimization research and the implementation plan behind 1.2.0
