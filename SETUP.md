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
npx fast-ios-device-test
```

Expected: `link: …` lines, `engine self-test: OK` and `done.` To upgrade later:
`npx fast-ios-device-test update` (also updates the Codex and Claude Code plugins). No
Node.js (`npx: command not found`), or the user wants to edit the tool: clone instead:

```bash
git clone https://github.com/DungVC-Dev/fast-ios-device-test.git ~/fast-ios-device-test
~/fast-ios-device-test/install.sh --link
```

Already cloned: run
`git -C ~/fast-ios-device-test pull` and the same `install.sh --link`. Without git: download the
release zip, unzip it, run its `install.sh` (no flag).

The installer needs no Homebrew: it verifies `vendor/tools.json`, installs required AXe and
attempts optional arm64 baguette under `~/.local/share`, creates wrappers in `~/.local/bin`, and
links both bundled skills into `~/.claude/skills`, the slash commands into `~/.claude/commands`, the `ui-explorer`
subagent into `~/.claude/agents` and the launchers into `~/.local/bin`.

For iPhone Duo code changes, optionally export Apple's current app-resizability skill from the
locally installed Xcode: `npx fast-ios-device-test xcode-skills`. Apple content stays under the
agent skill directories and is not shipped by this project. Use `xcode-skills --list`,
`--skill <name>`, and `--remove` to manage other Xcode skills. `--check` reports exports for
information only.

The tools have a locked-dependency update path: `npx fast-ios-device-test update-tools`, or
`./install.sh --update-tools` in a clone (per-tool variants also exist). It verifies downloaded
binaries, rewrites version/URL/SHA-256 pins and AXe's offline tarball, then reinstalls. baguette's
large arm64 asset is downloaded, never committed or packed into npm; LICENSE/NOTICE remain beside it.
An offline, blocked-GitHub or Intel Mac continues without baguette because only the upcoming
`fastCarPlayTest` needs it. Matching healthy pins are reused; install baguette later with
`./install.sh --install-baguette`.

That is all Claude Code needs. Any other agent also needs the skill installed for it; this
installer does not do that:

| Agent | Command |
|---|---|
| Codex | `codex plugin marketplace add DungVC-Dev/fast-ios-device-test` then `codex plugin add fast-ios-device-test@fast-ios-device-test` |
| Antigravity | `agy plugin install https://github.com/DungVC-Dev/fast-ios-device-test` |
| Gemini CLI | `gemini extensions install https://github.com/DungVC-Dev/fast-ios-device-test` |

## 3. Check

```bash
npx fast-ios-device-test --check      # or ~/fast-ios-device-test/install.sh --check for a clone
```

Expected last line: `CHECK OK`. The `axe-pin=` line shows the pinned, local and latest release
(cached for one day); `FAST_IOS_NO_UPDATE_CHECK=1` disables the latest lookup. `CHECK missing: …`
names what to fix:

| Missing | Fix |
|---|---|
| `xcode` | step 1 |
| `axe-<pinned version>`, `baguette-<pinned version>` or wrapper | rerun the matching `install.sh --install-…` (or `--install-tools`) |
| a launcher, `skill`, `iphone-duo-swiftui skill`, `ui-explorer agent` | rerun `install.sh --link` |
| `… (broken link)`: a link whose clone was moved or deleted (a `broken link:` line names it) | rerun `install.sh --link` from the clone you keep |
| `codex <skill> (broken link)` | rerun `install.sh --link` (it re-points a dangling Codex or Antigravity link), or relink by hand (README, "Development install") |
| `codex <skill> (empty plugin)` | `codex plugin add fast-ios-device-test@fast-ios-device-test`, then restart Codex |
| `antigravity <skill> (empty plugin)` | `agy plugin install https://github.com/DungVC-Dev/fast-ios-device-test`, then restart Antigravity |
| `~/.local/bin` not on PATH (a `note:` line) | add `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc`, open a new shell |

`pillow=no` and `xcodegen=no` are fine: only video review needs Pillow; the runner project ships
ready.

## 4. Restart the agent

The skills (and in Claude Code the slash commands and the subagent) load when the agent starts.
An agent cannot restart itself: tell the user to quit and reopen it (or start a new session),
then continue with step 5 in that session.

## 5. Simulator smoke test

Pick a simulator Xcode is not running the app on: a shut-down one is safest (`Booted` ones may be
Xcode's run destination; ask the user before using one of those).

```bash
xcrun simctl list devices available | grep -E "iPhone"     # (Shutdown) / (Booted) per simulator
fastSimulatorTest do '[{"type":"launch"},{"type":"wait","label":"General","timeout":90}]' \
  --simulator '<udid or unique simulator name>' --app com.apple.Preferences
```

Expected: `PASS actions=2 labels=["Settings", …, "General", …]`. The first run boots the
simulator and, on Xcode 27, opens Device Hub (Xcode's simulator window) by itself; there is
nothing to open by hand. Allow a minute. Shut it down afterwards if the user
does not need it: `xcrun simctl shutdown <udid>`. Save the UDID for later as
`FAST_SIMULATOR=<udid>` if the user wants a default.

App builds use one DerivedData per git repository under
`~/Library/Caches/fast-ios-device-test/dd/<repo-key>/`, shared by all worktrees. Normal flows omit
`derived_data` and `app_path`; `FAST_IOS_DERIVED_DATA_ROOT` moves the shared root and
`app.derived_data` is an explicit override. `fastUIClean --max-dd-gb N` dry-runs LRU trimming;
add `--yes` only after reviewing the reported paths and sizes.

For iPhone Duo, install Xcode as `/Applications/Xcode 27.1.app` and use
`--simulator 'iPhone Duo'`; the engine selects that toolchain automatically. For another path,
set `DUO_XCODE` (or `DEVELOPER_DIR`). Device Hub must have Accessibility permission to change pose.
The engine can then use `--duo-pose closed|open|book|tabletop` with optional
`--duo-orientation portrait|landscape` (`setup.duo_orientation` in a flow), or put both values on
the `duo` action. `book` is landscape-only and `tabletop` portrait-only because they name the
vertical and horizontal fold respectively.
Use the bundled `iphone-duo-swiftui` skill for code changes, together with the locally exported
`apple-app-resizability` skill when installed.

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

## 6b. CarPlay (optional)

Run the read-only checks before a CarPlay flow:

```bash
fastCarPlayTest doctor --target sim
fastCarPlayTest doctor --target hardware
```

Simulator CarPlay needs Xcode 26.6's Simulator.app, an iOS 26.5 runtime by default, the installed
`baguette` binary (`./install.sh --install-baguette`), and a disposable simulator named
`agent-tmp-*`. Hardware needs Apple's CarPlay
Simulator from Additional Tools and an unlocked USB iPhone. Doctor prints `OK/WARN/FAIL` plus the
specific fix; it never installs, launches, or changes either rig. Full setup and display presets are
in `skills/fast-ios-device-test/references/carplay.md`.

## 7. Optional

- Defaults so commands need fewer flags: `FAST_DEVICE=<udid or full name>`,
  `FAST_SIMULATOR=<udid or unique full name>`, `FAST_UI_APP=<bundle id>`.
- Xcode 27's MCP server for exploring with Apple's tools: `claude mcp add xcode -- xcrun mcpbridge`
  (skip it when `claude mcp list` already shows `xcode`).
- Nothing is configured per project: flows carry the scheme, bundle id and simulator.

## Git workflow and CI (contributors)

Use a topic branch and focused commits, then rebase it on the current main before opening or
updating one PR for the batch:

```bash
git fetch origin
git rebase origin/main
```

The required checks are `history`, `test` and `consistency`; finish accepted work with a rebase
merge so main stays linear. Agents do not push, merge, tag, release or publish unless the
maintainer explicitly asks.

The publish workflow targets a GitHub Environment named `npm`. A maintainer must create it and
set a required reviewer—declaring `environment: npm` in YAML does not itself enforce approval.
Repository administrators can preview all recommended settings without changing GitHub, then
apply them once:

```bash
scripts/setup_repo_rules.sh --dry-run
scripts/setup_repo_rules.sh --apply --maintainer <github-login>
```

Add `--include-admins` if branch protection should also bind administrators. The script is
idempotent; it enables only rebase merging, deletes merged head branches, protects `main`, and
creates or updates the reviewer-gated `npm` environment.

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
| `Device Hub's iPhone Duo controls are not reachable` | the Duo window is closed or macOS Accessibility is denied | open the Duo device window in Device Hub and allow the terminal/agent under Privacy & Security › Accessibility |
| `CHECK missing: …` | see the table in step 3 | rerun `install.sh --link` |

Where to read next: [skills/fast-ios-device-test/SKILL.md](skills/fast-ios-device-test/SKILL.md)
(how to write and run flows and `do` steps), `references/device.md` (iPhone specifics),
`references/usage.md` (every action, flag and environment variable).
