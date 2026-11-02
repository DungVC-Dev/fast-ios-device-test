# fast-ios-device-test

Claude Code slash commands for fast iOS verification:

| Command | What it does |
|---|---|
| `/fastSimulatorTest <screen or flow>` | Drives the app on Simulator through a JSON flow (fresh install, injected UserDefaults, PASS/FAIL line). Fans out one agent per simulator for a matrix. |
| `/fastDeviceTest <screen or flow>` | Runs the same JSON flow on a physical iPhone through a cached, auto-signed XCUITest runner; can also drive Settings, Shortcuts and SpringBoard. |
| `/fastUIReview <session>` | Builds contact sheets from a recorded session so every case's video is reviewed, not just its PASS line. |

Step by step, without writing a flow: `fastSimulatorTest do '<action or array>'` and
`fastDeviceTest do …` act on what is on screen and print the labels after the actions; `expect`
guards let one request carry several steps. `fastUIMap` prints what earlier runs saw of an app
(`--path-to <screen>` gives the way there as one request), and the `ui-explorer` subagent
(Haiku) runs long searches.

Every PASS flow run, and every `--before` run that failed at its outcome step, is filed as PR
evidence in `~/Desktop/<project> <ticket>/` (the ticket from the git branch): one captioned
sheet, the clips, and light per-shot JPEGs that `fastEvidenceSheet <spec.json>` renders again
after an edit. A filed run keeps only its `metrics.json` under `build/`. Both engines record with `--record` (the iPhone through XCTest's own
screen recording) and keep the clip at review quality (H.264, 960 px, ~1–2 MB for 20 s).

## Install

Needs a Mac with Xcode 26 or 27. AXe 1.8.0 (the Simulator driver) is bundled, so neither Homebrew
nor xcodegen is needed. Restart Claude Code after installing.

### npx (recommended)

```bash
npx fast-ios-device-test                                   # install, or upgrade to the latest
npx fast-ios-device-test --check                           # what is there and what is missing; changes nothing
npx fast-ios-device-test --check --device "<iPhone name>"  # also checks that iPhone for fastDeviceTest
npx fast-ios-device-test clean                             # caches and test builds (see below)
npx fast-ios-device-test --uninstall                       # remove the tool
```

Needs Node.js 18+ for `npx`. The tool is copied to `~/.local/share/fast-ios-device-test`, so it
does not depend on npx's temporary folder. The last line of `--check` is `CHECK OK`, or
`CHECK missing: …` with the fix for each item.

### Let Claude install it

Ask Claude Code: *"Install fast-ios-device-test with npx and check it"*. For a step-by-step setup
with the expected output and the fix for each failure (iPhone checks included), point it at
[SETUP.md](SETUP.md).

### Claude Code plugin

```
/plugin marketplace add DungVC-Dev/fast-ios-device-test
/plugin install fast-ios-device-test@fast-ios-device-test
```

This adds the skill and the slash commands. The engines also need their launchers on `PATH` and
AXe, which the plugin does not set up: run `npx fast-ios-device-test` once as well.

### git clone (to edit the tool)

```bash
git clone https://github.com/DungVC-Dev/fast-ios-device-test.git ~/fast-ios-device-test
~/fast-ios-device-test/install.sh --link
```

With `--link` the skill, commands and launchers point into the clone, so keep that folder.
Upgrade with `git -C ~/fast-ios-device-test pull`.

### Release zip (no Node.js, no git)

Download `fast-ios-device-test-<version>.zip` from
[Releases](https://github.com/DungVC-Dev/fast-ios-device-test/releases), unzip it anywhere and run
its `install.sh`. The tool is copied to `~/.local/share/fast-ios-device-test`, so the unzipped
folder can be deleted.

### What the installer puts where

| What | Where |
|---|---|
| The tool | `~/.local/share/fast-ios-device-test` (or your clone with `--link`) |
| Skill | `~/.claude/skills/fast-ios-device-test` |
| Slash commands `/fastSimulatorTest`, `/fastDeviceTest`, `/fastUIReview` | `~/.claude/commands` |
| `ui-explorer` subagent | `~/.claude/agents` |
| Launchers `fastSimulatorTest`, `fastDeviceTest`, `fastUIReport`, `fastUIReview`, `fastEvidenceSheet`, `fastUIMap`, `fastUIClean` | `~/.local/bin` (add it to `PATH` if the installer says so) |
| AXe, when none ≥ 1.8.0 is on `PATH` | `~/.local/share/axe` |

Pillow is installed when possible; only video review (`fastUIReview`, `fastEvidenceSheet`, the
`motion` action) needs it.

### Clean caches and test builds

The tools leave builds and run output behind; this deletes them and keeps the tool installed.
It lists what would go with sizes, and deletes only with `--yes`:

```bash
npx fast-ios-device-test clean                          # list: iPhone runner build, helpers, idle locks, sessions
npx fast-ios-device-test clean --project ~/MyApp --yes  # also that project's runs and test builds
npx fast-ios-device-test clean --maps --yes             # also the screen maps fastUIMap prints
npx fast-ios-device-test clean --project ~/MyApp --scope current --yes   # only the current task's runs
npx fast-ios-device-test clean --project ~/MyApp --scope others --yes    # every task's runs but the current one
```

A task is a flow: its runs sit in `build/fast-ui/<task>/` and `build/fast-device/<task>/`
(`home@dark` counts as `home`). The current task is the one with the latest run, or
`--task <name>`. `--scope others` keeps the test builds and the tools' caches, which the current
task still uses. Run in a terminal with `--project` and no `--scope`, it asks which of the three
and confirms before deleting.

`--project <root>` adds `build/fast-ui` and `build/fast-device` (runs, screenshots, videos), `build/fast-ui-dd` (the
Simulator app builds, the flows' `derived_data` by convention) and `build/fast-device-tests` (the
iPhone test builds). `fastUIClean` is the same command once installed. Evidence on the Desktop is
never touched; a simulator a flow is using, a running iPhone runner and the journal a killed run
left for its repair are skipped and named. A flow whose `derived_data` points elsewhere keeps that
folder: delete it yourself.

### Uninstall

```bash
npx fast-ios-device-test --uninstall      # or install.sh --uninstall from a clone
```

Removes the skill, the slash commands, the subagent, the launchers (only links that point at this
tool), the copied tool in `~/.local/share/fast-ios-device-test` and the bundled AXe (a Homebrew
`axe` stays). Caches, screen maps and each project's `build/` output stay: run `clean` first to
remove them too. A clone used with `--link` stays where it is.

### Optional: Apple's own tools

For exploring a screen with Xcode 27's tools (pinch, drag, rotate, app console log) before
writing a flow, register its MCP server once: `claude mcp add xcode -- xcrun mcpbridge`. The
skill says when to use which.

Maintainers: write what changed under `## Unreleased` in CHANGELOG.md, then
`./release.sh patch` (or `minor`, `major`, `X.Y.Z`). It sets the version, runs the tests, commits,
tags and pushes; GitHub Actions then publishes to npm and creates the GitHub release with the zip.

## What's new

See [CHANGELOG.md](CHANGELOG.md). 1.11 installs with `npx`, adds `fastUIClean`, `start` / `do` /
`save` sessions that build a flow on the live app, controls (`set_switch`, `set_slider`,
`set_picker`, `tap_alert`), assertions (`assert_value`, `assert_count`), device state
(appearance, location, permissions, clipboard, status bar), skips SwiftLint in test builds, and
stops `scroll_to` at the end of a list. 1.10.0 locks the iPhone and shuts simulators down at the
end of the work. 1.9.0 waits for a still screen before each screenshot. 1.8.0 adds
`two_finger_drag` on an iPhone. 1.7.0 files every passing run as PR evidence in one folder per
ticket on the Desktop. 1.6.0 reaches a screen visited before in one request (`fastUIMap
--path-to`). 1.5.0 makes step-by-step runs fast on both engines. 1.4.0 adds the gestures a tester
uses and a screen map recorded from normal runs.

## Setup per project

None. `/fastSimulatorTest` and `/fastDeviceTest` read everything from the flow
JSON the agent writes (scheme, bundle id, simulator, build folder); the skill
shows the smallest complete flow.

## Contents

- `SETUP.md` — setup an AI agent can follow, with checks and fixes
- `.claude-plugin/` — plugin + marketplace manifests
- `package.json`, `npm/install.js` — the npm package behind `npx fast-ios-device-test`
- `agents/ui-explorer.md` — Haiku subagent for long step-by-step searches (experimental)
- `skills/fast-ios-device-test/SKILL.md` — agent instructions (flow file, single flow, several flows or simulators)
- `skills/fast-ios-device-test/references/device.md` — fastDeviceTest on a physical iPhone
- `skills/fast-ios-device-test/references/review.md` — reviewing recorded runs with fastUIReview
- `skills/fast-ios-device-test/references/usage.md` — flow action reference, matrix, cache model, troubleshooting
- `commands/` — the three slash commands
- `bin/` — launchers (`fastSimulatorTest`, `fastDeviceTest`, `fastUIReport`, `fastUIReview`, `fastEvidenceSheet`, `fastUIMap`, `fastUIClean`) for the plugin install
- `scripts/fast_ui.py` — Simulator flow engine (`scripts/test_fast_ui.py` tests it); `--record`, `--session`
- `scripts/fast_ui_report.py` — collates a fan-out session into a flow × simulator table (`fastUIReport`)
- `scripts/fast_ui_review.py` — contact sheets and review notes for recorded runs (`fastUIReview`)
- `scripts/fast_evidence.py` — files each qualifying flow run into the ticket's evidence folder, shared by both engines (`scripts/test_fast_evidence.py`)
- `scripts/fast_evidence_sheet.py` — captioned evidence sheet for a PR (`fastEvidenceSheet`; `scripts/test_fast_evidence_sheet.py`)
- `scripts/fast_ui_clean.py` — `fastUIClean`: lists, then with `--yes` deletes, the caches the tools leave (`scripts/test_fast_ui_clean.py`)
- `scripts/fast_ui_map.py` — screen map recorded from both engines' runs, and its `fastUIMap` launcher (`scripts/test_fast_ui_map.py`)
- `scripts/fast_guard.py` — checks a `do` request before it runs (destructive steps, shapes), shared by both launchers (`scripts/test_fast_guard.py`)
- `scripts/fast_media.py` — review-quality video re-encode and the one-final-clip rule, shared by both engines (`scripts/test_fast_media.py`)
- `scripts/fast_device.py` + `device-runner/` — physical-iPhone flow runner (XCUITest, auto-signed; the `.xcodeproj` is committed, regenerate with `xcodegen generate` after editing `project.yml`)
- `vendor/` — the AXe release tarball `install.sh` unpacks when no `axe` ≥ 1.8.0 is on PATH (MIT, see `vendor/AXe-LICENSE`)
