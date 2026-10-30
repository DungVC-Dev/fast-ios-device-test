# Setup — steps an AI agent (or a person) can follow

Every step has a command and the output that means it worked. Run them in order on the Mac
that will run the tests. Ask the user before booting a simulator or touching an iPhone, and
name the iPhone: several may be paired, and test phones are often shared.

## 0. Already installed?

```bash
ls -l ~/.local/bin/fastDeviceTest
```

A link means the tool is installed: its target is `<folder>/scripts/fast_device.py`, and
`<folder>` is the install folder (not always `~/fast-ios-device-test`). Use that folder wherever
this document says `~/fast-ios-device-test`; to upgrade, `git -C <folder> pull` (when it is a git
clone) and `<folder>/install.sh --link`. Then go to step 3. No such file: start at step 1.

## 1. Xcode

```bash
xcode-select -p && xcodebuild -version
```

Expected: a path inside an `Xcode.app` and `Xcode 26.x` or `27.x`. If it prints
`/Library/Developer/CommandLineTools` or fails, the user must install Xcode and run
`sudo xcode-select -s /Applications/Xcode.app` (needs their password: ask them to run it).

## 2. Install

```bash
git clone https://github.com/kiluss2/fast-ios-device-test.git ~/fast-ios-device-test
~/fast-ios-device-test/install.sh --link
```

Expected: `link: …` lines, `engine self-test: OK` and `done.` Already cloned: run
`git -C ~/fast-ios-device-test pull` and the same `install.sh --link`. Without git: download the
release zip, unzip it, run its `install.sh` (no flag).

The installer needs no Homebrew: it unpacks the bundled AXe into `~/.local/share/axe`, links the
skill into `~/.claude/skills`, the slash commands into `~/.claude/commands`, the `ui-explorer`
subagent into `~/.claude/agents` and the launchers into `~/.local/bin`.

## 3. Check

```bash
~/fast-ios-device-test/install.sh --check
```

Expected last line: `CHECK OK`. `CHECK missing: …` names what to fix:

| Missing | Fix |
|---|---|
| `xcode` | step 1 |
| `axe` or `axe-1.8.0` (the check line reads `axe=<version>`) | rerun `install.sh --link` (it unpacks the bundled AXe) |
| a launcher, `skill`, `ui-explorer agent` | rerun `install.sh --link` |
| `~/.local/bin` not on PATH (a `note:` line) | add `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc`, open a new shell |

`pillow=no` and `xcodegen=no` are fine: only video review needs Pillow; the runner project ships
ready.

## 4. Restart Claude Code

The skill, the slash commands and the subagent load when Claude Code starts. An agent cannot
restart it: tell the user to quit and reopen Claude Code (or start a new session), then
continue with step 5 in that session.

## 5. Simulator smoke test

Pick a simulator Xcode is not running the app on: a shut-down one is safest (`Booted` ones may be
Xcode's run destination; ask the user before using one of those).

```bash
xcrun simctl list devices available | grep -E "iPhone"     # (Shutdown) / (Booted) per simulator
fastSimulatorTest do '[{"type":"launch"},{"type":"wait","label":"General","timeout":90}]' \
  --simulator <udid> --app com.apple.Preferences
```

Expected: `PASS actions=2 labels=["Settings", …, "General", …]`. The first run boots the
simulator and, on Xcode 27, opens Device Hub (Xcode's simulator window) by itself; there is
nothing to open by hand. Allow a minute. Shut it down afterwards if the user
does not need it: `xcrun simctl shutdown <udid>`. Save the UDID for later as
`FAST_SIMULATOR=<udid>` if the user wants a default.

## 6. iPhone (optional)

Prerequisites on the iPhone, which only its owner can set:

- Unlocked, connected by cable (or on the same Wi‑Fi after pairing), and "Trust This Computer"
  accepted.
- Settings › Privacy & Security › Developer Mode on (the iPhone restarts).
- A development profile that lists this iPhone, with its certificate in the Mac's keychain:
  the usual way is signing in to Xcode (Settings › Accounts) and running any app on the iPhone
  once from Xcode. No Apple ID login is needed by the tool itself.

```bash
xcrun devicectl list devices      # State "connected" = usable now; ask the user which one to use
fastDeviceTest check --device "<name or udid>"
```

Several iPhones may be connected: never pick one yourself; show the user the names and ask.

Expected: `CHECK OK` after lines such as `connected=yes`, `developer_mode=enabled`,
`signing=<profile> (<bundle id>)`. Each missing item prints its fix. The `ui_automation=` and
`lock=` lines are reminders, not failures: iOS does not let the Mac read them. Then the smoke test:

```bash
fastDeviceTest do '[{"type":"launch"},{"type":"wait","label":"General","timeout":20}]' \
  --app com.apple.Preferences --device "<name or udid>"
fastDeviceTest stop --device "<name or udid>"
```

Expected: `PASS actions=2 labels=[…]`. The first run builds and signs the runner (1–2 min);
later requests take about 2 s. Always `stop` when done: the runner holds the iPhone. At the end
of the work, `fastDeviceTest lock --device "<name or udid>"` stops it and locks the screen too,
and `fastSimulatorTest shutdown` shuts down the booted simulators.

## 7. Optional

- Defaults so commands need fewer flags: `FAST_DEVICE=<udid or full name>`,
  `FAST_SIMULATOR=<udid>`, `FAST_UI_APP=<bundle id>`.
- Xcode 27's MCP server for exploring with Apple's tools: `claude mcp add xcode -- xcrun mcpbridge`
  (skip it when `claude mcp list` already shows `xcode`).
- Nothing is configured per project: flows carry the scheme, bundle id and simulator.

## Troubleshooting

| Message | Cause | Fix |
|---|---|---|
| `is locked: unlock it and run again` | the iPhone locked itself | unlock it by hand and rerun; a longer Auto-Lock (Settings › Display & Brightness) on a test phone makes it rarer |
| `is not connected; unlock it and plug it in …` | cable, Wi‑Fi or lock | reconnect, unlock, then `fastDeviceTest check` |
| `no usable development profile for device …` | no profile lists this iPhone, or the identity is revoked | step 6, or set `FAST_DEVICE_PROFILE=<uuid>` |
| `no installed Xcode supports iOS …` | the iPhone's iOS is newer than every installed Xcode | install a newer Xcode |
| `is busy: another runner holds it` | another agent or session serves that iPhone | use another iPhone; never `stop` a runner you did not start |
| `the runner ended without a reply: …` | XCTest ended the test (the reason follows) | fix the step it names; the next request starts a new runner |
| iOS asks to "Enable UI Automation" | first UI test on that iPhone | Settings › Developer › Enable UI Automation |
| `describe-ui failed …` / `automation session` on the Simulator | Device Hub not running (Xcode 27) or the simulator still booting | rerun; the engine opens Device Hub itself |
| `CHECK missing: …` | see the table in step 3 | rerun `install.sh --link` |

Where to read next: [skills/fast-ios-device-test/SKILL.md](skills/fast-ios-device-test/SKILL.md)
(how to write and run flows and `do` steps), `references/device.md` (iPhone specifics),
`references/usage.md` (every action, flag and environment variable).
