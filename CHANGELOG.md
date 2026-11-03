# Changelog

## Unreleased

### Physical iPhone

- New `network_condition` (Network Link Conditioner presets such as `3G`, `Edge`,
  `Very Bad Network`) and `low_power` steps for `fastDeviceTest`. They drive Settings, return to
  the app, and are switched off again at the end of the flow (PASS or FAIL), at
  `fastDeviceTest stop`, or with `fastDeviceTest conditions off`.
- App logs: `fastDeviceTest <flow> --app-log` keeps the app's console as `app.log`. A flow's
  `expect_log` / `expect_no_log` regexes decide PASS or FAIL. For step-by-step work there is
  `fastDeviceTest log start|wait|assert|assert-absent|mark|show|stop`; `do` then drives the
  logged app on its own.
- Any step can be `"optional": true` and is skipped when its target is absent, for example a
  Play button or a third-party upsell. `wait_change` waits, minutes if needed, until a label or
  value changes.
- When `tap_label` misses, the error names the element types that text has on screen.
- Network Link Conditioner also slows the USB link to the runner, so requests made while a
  profile is on get 3–8× more time. `100% Loss` is refused, because nothing could switch it off
  again. Switching conditions off retries once with a fresh runner.
- `set_switch` waits for the switch to stop moving before it taps. The `low_power` step allows
  for Settings › Battery drawing late, and Settings' start page now gets time to finish loading
  before a row is tapped.
- `do --labels changed|none` shortens the report. `do` no longer writes screenshots and
  `step-NN-ui.json` into the current directory: they go to a cache folder unless `--out` says
  otherwise. `serve --install <app>` installs before starting the runner.
- Document heat through Xcode 27's Debug › Induce Device Conditions › Thermal State: driven with
  computer use, or by process id through the Accessibility API when two Xcodes run (checked on an
  iPhone 15 Plus). Also document Spotify Free skip limits.

### Repository

- `scripts/setup_repo_rules.sh` protects the `origin` repository (or `--repo OWNER/NAME`) instead of a fork's `upstream`, which `gh repo view` picked.

## 2.2.0 — 2026-11-03

### Updates

- The daily updater does nothing when the installed version is already the latest, finds `npx` from nvm/fnm/volta installs, and gives up after 15 minutes instead of hanging.
- Enable a per-user daily launchd updater on normal installs, with explicit on/off/status controls,
  patch/minor-only application, major-version notices, shared fast* run locking, small rotated logs,
  linked-clone git advice, uninstall cleanup and `FAST_IOS_NO_AUTO_UPDATE=1` opt-out.
- Make `npx fast-ios-device-test update` update installed Antigravity and Gemini plugins as well as
  Codex and Claude Code; document Claude marketplace opt-in and Gemini's native `--auto-update`.
- Check a linked clone against `origin/main` only in the cached daily refresh and report when it is
  behind without adding network latency to normal engine runs.

### Physical iPhone

- `fastDeviceTest` saved a screenshot named `general.png` as `general.png.png`; it now keeps a single `.png` like the Simulator engine.
- Run a fast, briefly cached one-`devicectl` readiness gate before every physical-iPhone flow and
  live request, while keeping `fastDeviceTest check` as the complete pairing/Xcode/signing report.
- Turn UI Automation, developer trust, device preparation/shared-cache, Xcode/iOS, passcode,
  lock and mid-run disconnect logs into concise errors with the exact next fix.
- Detect launchers or linked Claude slash commands missing from an existing install once a day and
  point linked-clone users back to `install.sh --link`; fix clean-host baguette resolution and make
  iPhone Duo tests independent of locally installed Xcode components.
- Leave `XCUIDevice.appearance` untouched when a flow does not request light or dark, and never try
  to restore XCTest's non-assignable `.unspecified` appearance value on a physical iPhone.

### CI/CD

- Add pull-request/main CI for linear rebased history, the complete macOS test/package suite,
  provider/document consistency, npm size/content checks and live README links using Node 24 actions.
- Gate tag publishing on the reusable CI checks, main ancestry and the reviewer-protected `npm`
  environment; keep upstream sync linear and fall back to a PR when main cannot fast-forward.
- Add a dry-run-by-default `scripts/setup_repo_rules.sh` for rebase-only merging, protected main,
  required CI checks and the npm environment.

### Disk usage

- Share `fastSimulatorTest` DerivedData across every worktree of a repository under
  `~/Library/Caches/fast-ios-device-test/dd`, with automatic app discovery, safe legacy-flow
  redirection and `FAST_IOS_DERIVED_DATA_ROOT` / `app.derived_data` overrides.
- Make `fastUIClean` report and remove stale repo caches, or dry-run least-recently-used trimming
  with `--max-dd-gb N`; existing project DerivedData is never migrated or deleted automatically.

### iPhone Duo

- Bundle the company `iphone-duo-swiftui` skill across Claude Code, Codex, Gemini CLI and
  Antigravity packages, with `fastSimulatorTest` as its primary four-pose verification path.
- Add `npx fast-ios-device-test xcode-skills` / `install.sh --xcode-skills` to list, export and
  remove agent skills from a locally installed Xcode. Apple content remains local and is never
  redistributed in the repository or npm/provider packages.
- iPhone Duo flows can request `portrait` or `landscape` on a `duo` action, through
  `setup.duo_orientation`, or with `--duo-orientation`. Device Hub rotates until the selected
  framebuffer dimensions match, and non-default rows use names such as `@duo-closed-landscape`.

### Liquid Glass

- Add a design-recognition and `LG-` test-case derivation guide covering system and custom glass,
  accessibility, scrolling, Dynamic Type, widgets, and iPhone Duo evidence.
- Add `xcode-skills --docs liquid-glass` to export Xcode's four framework guides into a local-only
  `apple-liquid-glass` skill; Apple documentation is never committed or packaged.
- Make the Pillow-dependent evidence and review test modules skip cleanly when Pillow is absent,
  so full unittest discovery remains usable with only Python's standard library.

### Fixed

- Apply requested iPhone Duo orientation after launching the target app, so a portrait-only app
  left open from an earlier run cannot reject a landscape-capable app's flow; invalid variants now
  print a concise `FAIL error=...` line instead of a Python traceback.
- Preserve skill, command, agent and launcher symlinks managed by another checkout or company
  skill repository during install and uninstall; only verified links into this tool are replaced
  or removed, while dangling links are still repaired.

### Gemini CLI & Antigravity

- Update `GEMINI.md`, `GEMINI_EXTENSION.md`, and `.antigravity-plugin/README.md` to comprehensively guide Gemini CLI and Antigravity agents on launcher usage (`fastSimulatorTest`, `fastDeviceTest`, `fastCarPlayTest`, `fastUIReview`), iPhone Duo, CarPlay, Liquid Glass verification, and local Xcode skill exports (`apple-app-resizability`, `apple-liquid-glass`).
- Support optional `export` argument in `install.sh --xcode-skills` and automatically export Xcode skills to Antigravity (`~/.gemini/config/skills/`) when the Antigravity plugin is installed.
- Document non-Claude alternatives for slash commands and subagents across all bundled skills.

## 2.1.1 — 2026-11-03

- README: restored the per-agent plugin install steps (Codex, Antigravity, Gemini CLI, Claude Code)
  that the 2.1.0 README rewrite dropped.
- README leads with how people actually use it: slash commands and plain requests to the agent;
  the flow JSON and engine options move under "Under the hood".
- README adds real Simulator and CarPlay captures, a three-step quick start, target support matrix,
  concise value proposition, and FAQ based on established developer-tool README patterns.

## 2.1.0 — 2026-11-03

- README reorganised around target selection, quick install, engine flows, variants, troubleshooting,
  and verified command examples.
- Fixed iPhone Duo display selection across separate `do` and session processes: screenshots and
  recordings now retain the selected outer/inner framebuffer until the simulator is shut down.
- Claude Code, Gemini CLI and Antigravity instructions now explain the complete iPhone Duo
  workflow: outer/inner flow steps, closed/open/book/tabletop pose matrices, per-framebuffer
  recordings and review of every pose row.
- Known limitation: the iPhone Duo pose and display path is covered by unit tests only. It has not
  yet been run on a real Duo simulator, because Xcode 27.1's additional components (CoreSimulator
  1174.9.2) were not installed on the release machine.
- AXe and baguette are project-managed dependencies pinned by version, release URL, SHA-256 and
  licence. Installs use verified local copies instead of Homebrew; baguette's large official arm64
  asset remains download-only, while AXe remains available offline. Tool updates and the daily
  workflow refresh both pins and only open (never merge) dependency PRs.
- Healthy matching tool pins are reused. AXe remains required, while optional baguette no longer
  blocks install or `CHECK OK` on offline, proxy-restricted or Intel Macs; `--force` reinstalls a pin.
- Add `fastCarPlayTest doctor|run` for mixed phone + CarPlay flows. Simulator runs use a persistent
  project-pinned `baguette` session and safe screenshots; hardware runs capture/tap Apple's CarPlay
  Simulator window, control its Connected/Disconnected state, and report Automaker UI as `VOID`.
- Add one selectable display per run: `widescreen` (1920×720@2), `standard` (800×480@2), `hd`
  (1280×720@2), or custom `WxH@S`. Matching armed displays skip the reboot; project-specific
  arming remains in `setup.carplay_arm_script`. Size changes safely clear Simulator.app's cached
  mode, traverse the I/O submenu reliably, and verify both the armed plist and captured PNG
  dimensions before reporting `PASS`.
- Hardware capture matches only Apple's standalone CarPlay Simulator window, never the similarly
  named CarPlay window in Xcode Simulator.app.
- CarPlay results include optional case IDs for `fastUIReport` and always retain phone + car stills.
- Harden CarPlay preflight and cleanup: preserve existing `fastSimulatorTest` session pointers,
  restore simulator/window lifecycle after setup failures, reject unsupported Simulator recording,
  transactionally restore prior CarPlay display/defaults after failed re-arming, install before
  relaunching and waiting for the hardware window, propagate failed hardware phone captures, and
  fully reap stuck `baguette` input processes.

## 2.0.4 — 2026-11-03

- `fastSimulatorTest` supports the Xcode 27.1 iPhone Duo in Device Hub: a flow can select the
  simulator by name, switch between `closed`, `open`, `book` and `tabletop` with the `duo`
  action, and capture the outer or inner framebuffer. `setup.duo_pose` / `--duo-pose` create
  named matrix rows and target screen recordings at the matching display.

## 2.0.3 — 2026-11-02

- `npx fast-ios-device-test update`: installs the latest npm version (an older cached npx package
  hands over to it), then updates the Codex and Claude Code plugins and prints the Antigravity and
  Gemini CLI commands. A `--link` clone is not overwritten; it prints the `git pull` to run.
- `fastSimulatorTest` and `fastDeviceTest` print `update available: <installed> -> <latest>` at most
  once a day when npm has a newer version (checked in the background, never blocks a run, never
  installs; `FAST_IOS_NO_UPDATE_CHECK=1` or `CI` turns it off). `install.sh --check` prints the
  installed and the latest version.
- A plain install (`npx fast-ios-device-test`, `install.sh` without a flag) refuses to replace
  `~/.local/share/fast-ios-device-test` when it is a git clone, instead of deleting it.

- `install.sh --check` fails on a broken link (a launcher, the skill or the subagent pointing at
  a moved or deleted clone) instead of passing it, and reports the Codex and Antigravity skill:
  a dangling `~/.codex/skills` or `~/.gemini/config/skills` link, or a Codex or Antigravity plugin
  folder without the skill, hid the skill from that agent while `CHECK OK` still printed.
- README and GEMINI.md: Antigravity loads global skills from `~/.gemini/config/skills`, not
  `~/.gemini/antigravity-cli/skills`; Claude Code needs no plugin on top of the runtime install.
- GUIDE.md (Vietnamese): install covers Codex, Antigravity and Gemini CLI, not only Claude Code.
- An install (`--link` or the default copy) re-points a dangling Codex or Antigravity skill link
  at the installed skill; a working link to another clone stays. `--uninstall` removes such a link
  when it points into the removed copy or at nothing.
- Skill: one flow per requested behavior by default (cases, variants or a matrix only when the
  user lists them); after two fix-and-rerun rounds on a product bug, stop and report; a failing
  flow is no reason to switch to `osascript`, `cliclick` or a hand-written XCUITest; CarPlay
  Simulator, Mac apps and Apple Watch are out of reach and reported at once.

## 2.0.2 — 2026-11-02

- Put Codex and Antigravity marketplace installs first in the README and replace the long bullet
  table of contents with a compact icon navigation bar.

- Give the README a branded icon header, release/platform badges, agent support badges, and a
  one-command install callout.

## 2.0.1 — 2026-11-02

- Add installable packages for the Codex plugin directory, Antigravity Marketplace, and Gemini
  CLI extension gallery, with provider manifests, marketplace metadata, a generated icon, guided
  local setup, and release-version synchronization.

## 2.0.0 — 2026-11-02

- README: install in two steps (the tool, then each agent), with how to use the skill from Codex
  (`~/.codex/skills`) and Antigravity CLI (`~/.gemini/config/skills`) next to Claude Code.
- `AGENTS.md`, `CLAUDE.md` and `GEMINI.md` give Codex, Claude Code and Antigravity CLI the
  project guidance for editing this repo.

## 1.11.4 — 2026-11-02

- `clean --scope current|others` deletes only the current task's runs, or every other task's
  (keeping the test builds and caches the current task uses); the current task is the latest
  run's, or `--task <name>`. In a terminal, `clean --project <root>` asks which and confirms.
  `--project` now also deletes the iPhone runs in `build/fast-device`.
- `./release.sh patch|minor|major|X.Y.Z` cuts a release; the publish workflow now also creates
  the GitHub release with the zip and the CHANGELOG section.

## 1.11.3 — 2026-11-02

- `npx fast-ios-device-test --uninstall` (`install.sh --uninstall`) removes the tool: the links that
  point at it, the copied tool and the bundled AXe. Caches and build output stay.
- `npx fast-ios-device-test clean` runs `fastUIClean` without an install; `--project` now also
  deletes `build/fast-ui-dd`, the Simulator app builds. README separates cleaning from uninstalling.

## 1.11.2 — 2026-11-02

- README: every way to install (npx, asking Claude, the Claude Code plugin, a clone, the release
  zip), what goes where, and how to uninstall. SETUP.md installs with npx first.

## 1.11.1 — 2026-11-02

- First release on npm (`npx fast-ios-device-test`); the same code as 1.11.0.

## 1.11.0 — 2026-11-02

### Faster to prepare, safer to reuse a simulator

Found and measured with a debate-and-experiment pass on the fixture app (load 20–390 on a
shared Mac; ratios from interleaved runs):

- **`start` / `do` / `labels` / `save`:** build a flow on the live app one action at a time,
  then save it and verify it with one fresh-install run. Exploring a screen two steps deep
  went from 49 s and 5 flow rewrites (rerun + `dump`) to 15 s and one write.
- **SwiftLint skipped in test builds** through a no-op `swiftlint` shim on `PATH` (no-op
  build 6–9 s → 2–3 s; a lint error no longer fails the test build). `lint=not-shimmable`
  names phases the shim cannot reach; `"skip_lint": false` / `FAST_UI_SKIP_LINT=0` lints.
- **Build failures say why:** the failing phase and first `error:` line (they were read from
  stderr while `-quiet` prints them on stdout), full log in `<derived_data>/.fastui-build.log`.
- **No state left for the next run:** a per-simulator lock (`simulator busy`), a journal of
  what the run changed, undone in teardown and on SIGTERM / SIGHUP / Ctrl-C (`status=interrupted`),
  and repaired by the next run after a SIGKILL (`WARN dirty=1`). Appearance changed by
  `set_appearance`, status bar overrides, location and granted permissions no longer leak
  (a following flow used to PASS wrongly in dark mode). The app is terminated at the end, and
  relaunched with `--terminate-running-process` when `fresh_install` is false.
  Keychain reset on fresh install for `fastui-…` simulators or `setup.reset_keychain`.
- **System alerts:** a declared bare label outside any sheet is tapped only on a system
  screen, never on an in-app button with the same label (prompt rules work as in 1.4.0),
  and one wait taps at most 4 prompts; `tap_alert` takes `system` and `optional`;
  an alert left on screen is reported (`WARN system_alert_seen`, `setup.system_alert: "fail"`);
  `scroll_to` stops at once when a system alert covers the app.

### Every interaction a real UI test needs

Flows could tap, swipe, type and wait. They can now drive the whole surface of an app, with the
same action names on Simulator and iPhone (table in `references/usage.md`):

- **Gestures:** `long_press`, `double_tap`, `drag` (hold, then move: reorder, Home Screen
  icons, drag-and-drop), `swipe` inside an element (swipe-to-delete), `back`, `edge_swipe`,
  `pull_to_refresh`; on the iPhone `pinch`, `rotate_gesture`, `two_finger_tap`.
- **Keyboard:** `type_text` into a named field with `clear: true`, `clear_text`, `press_key`,
  `dismiss_keyboard`.
- **Controls:** `set_switch` (taps only when needed and waits for the new value), `set_slider`,
  `set_picker`, `tap_alert` (system or app alert).
- **Assertions:** `assert_value` (`equals` / `not_equals` / `contains` / `matches` on a value or
  label, polled), `assert_count`, and the selector key `enabled`.
- **Device state:** `press_button`, `activate`, `set_appearance`, `set_location`,
  `set_permission`, `set_clipboard` / `assert_clipboard`; Simulator `push_notification` and
  `status_bar`; iPhone `set_orientation`, `open_url`.

Measured on Xcode 27.0 / iOS 27 and built into the Simulator engine: a switch flips only for a
~0.3 s touch; the back gesture, row swipe actions and edge swipes need `axe drag`, not `axe
swipe`; keys are dropped unless sent inside an `axe batch` with a sleep on both sides; AXe sends
numeric values as numbers (row 0 of a wheel is `0`, not empty).

On the iPhone (checked on iOS 26.6.1): `open_url` uses the system handler instead of handing the
URL to the current app; the clipboard is read and written with the runner briefly in front
(iOS drops background access); an XCTest gesture failure is now a step FAIL instead of ending
the persistent runner; search fields are `SearchField` and match `TextField`; `dump` lists
unlabelled nodes that carry an identifier.

### Fixed

- Swipes by `direction` measured the screen as the largest frame in the tree, which in a long
  list is the scroll content (y −1580); they now use the application's frame.

### Install with npx

- `npx fast-ios-device-test` installs the tool (copied to `~/.local/share/fast-ios-device-test`) and
  wires the skill, commands and launchers; `--check` reports what is missing.

### Cleaning up, and SwiftLint that still ran

- `fastUIClean` lists the caches the tools leave on the Mac with their sizes and deletes them with
  `--yes`: the iPhone runner build (`~/Library/Caches/fast-device-test`), the review helper, idle
  simulator locks, session pointers, and with `--project <root>` that project's `build/fast-ui`
  and `build/fast-device-tests`; screen maps only with `--maps`. Evidence on the Desktop is never
  touched. A lock a running flow holds, the journal a killed run left (the next run repairs from
  it) and the runner cache while a runner serves are skipped and named.
- SwiftLint skipped in test builds also when the run-script phase puts `/opt/homebrew/bin` ahead on
  `PATH` first (SwiftLint's README form, which the PATH shim lost to): `swiftlint` is now also an
  exported shell function for sh/bash phases. `fastDeviceTest`'s build of an app's own tests
  (`fast_device_test.sh`) skips it the same way; `FAST_UI_SKIP_LINT=0` lints.

### Scrolling and taps that do not miss

- `scroll_to` stops when two swipes in a row moved nothing (the end of the list, or a screen that
  does not scroll) with `the screen stopped moving`, on both engines, instead of spending every
  `max_swipes`.
- On the Simulator, `tap_label`, `tap_first` and selector gestures take a match whose centre is on
  screen before one scrolled above or below it (a top-left match at y < 0 used to be tapped and miss).

### Merged with 1.10.0

- One handler per action on each engine. Where both lines had one, the 1.10.0 action keeps
  its keys and the earlier names still run: `rotate_gesture` (`degrees`) = `rotate`,
  `set_orientation` (`orientation`) = `orientation`, `set_slider` takes `percent` or `value`
  (0–1), `set_picker` takes `option` or `value`. `back` is a left `edge_swipe`.
- `set_picker` now runs on the Simulator too (it steps the wheel); `press_key` takes letters
  and digits and is sent inside one AXe batch; `press_button` adds `side`, `apple_pay` on the
  Simulator and `action`, `camera` on the iPhone.
- `fastSimulatorTest do` acts on the given simulator (`--simulator` / `FAST_SIMULATOR`), or
  on the open `start` session when none is given.

## 1.10.0 — 2026-10-31

### Locking the iPhone and shutting simulators down at the end

- `fastDeviceTest lock --device <d>`: the runner's last request presses the lock button, then the
  iPhone is freed as `stop` frees it (`LOCKED device=<name>`). For a test phone kept on Auto-Lock
  "Never": the agent locks it once the work is done. XCUIDevice has no public lock button, so the
  runner calls the private `pressLockButton` (as WebDriverAgent does), looked up at runtime; an
  Xcode without it refuses with the reason (checked: iPhone 15 Pro Max, iOS 27, the lock state
  read `passcodeRequired: true` right after). A lock that fails still frees the runner.
- `press_button` `lock` inside a flow stays refused on an iPhone (the next steps would wait for
  the passcode); its message now points at `fastDeviceTest lock`.
- `fastSimulatorTest shutdown` shuts down every booted simulator, `--simulator <udid>` only that
  one, ending a recorder left running first (`SHUTDOWN simulators=…`).

## 1.9.0 — 2026-10-30

### Screenshots wait until the screen stops moving

- `screenshot` on the Simulator and on an iPhone now shoots until two shots 0.25 s apart differ by
  at most 0.5 % of the screen below the status bar (at most 3 s), and keeps the last one. An
  evidence sheet once shipped a "Trip is very short" popup caught half-faded mid-slide because a
  fixed `pause` was too short. A screen that never settles is named in the PASS line as
  `unsettled=<name>`; `"stable": false` keeps the old single shot. Tunable per action with
  `stable_ratio` and `stable_timeout`.
- A Simulator screenshot now gives up after 30 s. `simctl io … screenshot` on a simulator that died
  mid-run used to hang the flow for good (one sat for 19 minutes); the flow now fails with the reason.

## 1.8.1 — 2026-10-30

### Restarting a stopped runner no longer fails

- `fastDeviceTest do` after `fastDeviceTest stop` could end in `shutil.SameFileError` on
  `serve-<udid>.xctestrun`: the runner picked its xctestrun with a glob that skipped the per-run
  `run-` copies but not the `serve-` copy left beside the build, so whichever came first was copied
  onto itself. The build's own file is now chosen in one place, ignoring both prefixes (checked:
  three `do` / `stop` cycles in a row on an iPhone 15 Pro Max with the `serve-` file present).

## 1.8.0 — 2026-10-30

### Two fingers dragging together

- New iPhone-only action `two_finger_drag`: two fingers side by side move up or down together
  (`dy`, `spread`, `duration`, `at`, on a selector or `element_type`, else the whole app). On Apple
  Maps, `{"type": "two_finger_drag", "dy": -0.25, "element_type": "Map"}` tilts the map into 3D
  (checked on an iPhone 15 Pro Max, iOS 27.2). XCUITest's public API has no such gesture, so the
  runner builds the touch events from the private `XCPointerEventPath` / `XCSynthesizedEventRecord`
  classes, looked up at runtime like the quiescence switch: an Xcode without them refuses the
  action with the reason and nothing else changes.
- Dragging up tilts the map, down flattens it again (both checked). Fingers that land on Maps'
  bottom sheet drag the sheet instead, so start above it: `"at": 0.3`.
- The Simulator refuses it like `pinch`; the screen map records it with `dy` and `spread`.

## 1.7.0 — 2026-10-29

### Evidence lands on the Desktop by itself

- Every PASS flow run on either engine is filed in `~/Desktop/<project> <ticket>/`
  (`FAST_EVIDENCE_DIR`): a captioned sheet `<ticket>.jpg`, the run's clip as `<case>.mp4`, and
  `source/` with each shot at 720 px (JPEG 80) and the `fastEvidenceSheet` spec, so a sheet can
  be reordered, recaptioned or given another shot and rendered again without loss. The ticket
  comes from the git branch (`evidence.ticket` / `FAST_EVIDENCE_TICKET` override it), the
  project from the main checkout, so a `git worktree` of the base branch files beside it.
- `--before` (or `"evidence": {"role": "before"}`) marks a run that shows the bug, e.g. the
  same flow on the base build. It is filed when it fails at or after its outcome step (an
  action with `"outcome": true`, else the last action that is not a screenshot, dump, motion or
  pause), so a flow that broke on the way is not shown as the bug. Before cells sit next to the
  case's after cells.
- A re-run of a case replaces its images and clip, keeps the cell's edited text and place, and
  does not bring back a cell listed in the spec's `"removed"`.
- A filed PASS run in the default root keeps only `metrics.json` (its `video` points at the
  filed clip); `fastUIReport`, `fastUIReview` and `task` cells keep working. Custom roots are
  never emptied. `fastDeviceTest` now prunes run folders after `FAST_UI_KEEP_DAYS` (3) days, as
  `fastSimulatorTest` did.
- `fastEvidenceSheet --folder <project root>` prints the ticket's evidence folder and creates
  its `source/flows/`: a ticket's flows live there, found by any later session and deleted with
  the folder after the merge, never under the pruned `build/` roots.
- Lines end with `evidence=file://…`, or `evidence_error=…` without changing PASS/FAIL.
  `FAST_EVIDENCE=0` or `"evidence": false` files nothing; a `project_root` outside git with no
  ticket given files nothing.

## 1.6.1 — 2026-10-27

### Setup an AI can follow

- `SETUP.md`: install, check, restart, a Simulator and an iPhone smoke test, every step with its
  expected output and a table of messages with their fixes.
- `fastDeviceTest check --device <name>` (and `install.sh --check --device <name>`): pairing,
  connection, Developer Mode, developer disk image, the Xcode and signing profile a run will use,
  whether the runner is built and serving, each gap with its fix. Lock state and the
  "Enable UI Automation" switch are not readable and are said so.
- GUIDE.md and README brought up to 1.6: `do`, `--path-to`, gestures, the iPhone checklist.

## 1.6.0 — 2026-10-27

- `fastUIMap <bundle id> --path-to <text>` prints the recorded way from an entry screen to a
  screen as one `do` request, each step with an `expect` that only the next screen shows (a
  title the screen before also lists, such as Settings' "General" row, is skipped). A screen
  visited before is reached in one request and one model turn.
- `fastSimulatorTest do` skips `simctl bootstatus` (0.3 s a step): a shut-down simulator fails
  the first step before it acts, and only then is it booted and the request run again.
- `fastDeviceTest do` skips its closing read when the last step already read the screen (a
  `wait`, a `dump`, an `expect`): with the idle wait off that read settled for up to 1.5 s.
- `expect` from `--path-to` names something only the next screen shows, never chrome (Back,
  chevron, Close, Done…) and text with digits last (a version differs on the next iPhone).
- iPhone flows start or reuse the persistent runner (14–20 s one-shot → 4–6 s); `--one-shot`
  and `--record` keep the old way. The runner idles out after 5 min instead of 30. A runner this
  Mac started that stopped answering is replaced instead of reported "busy", and a locked
  iPhone fails in seconds ("is locked: unlock it") instead of after 120 s, leaving no runner.
- `agents/ui-explorer.md` (experimental): a Haiku subagent for long step-by-step searches that
  returns one guarded request; `FAST_GUARD_SINGLE=1` applies the destructive-step refusal to
  one-action requests too. `install.sh` links it into `~/.claude/agents`.

## 1.5.0 — 2026-10-26

### Faster step-by-step runs

- `fastSimulatorTest do '<action or array>'` acts on what the Simulator shows now, like
  `fastDeviceTest do`: no build, install or launch, one PASS/FAIL line with the labels after the
  actions. Exploring the Simulator used to re-run a whole flow per step.
- `expect` on any action waits for the screen the step leads to, so one request can carry the
  predictable steps of a path and stop at the first surprise.
- A destructive-looking step (Delete, Pay, Send, Sign Out, Xóa, Đăng xuất…, ids such as
  `deleteAccountButton` included) inside a multi-action `do` is refused unless it says
  `"confirm": true`; `FAST_GUARD_WORDS` adds words. A request that is not valid JSON or has a
  non-object `expect` is refused before it runs.
- `fastDeviceTest do` resolves a serving iPhone from the runner's state file instead of
  `xcrun devicectl list devices` on every call, and runs with XCTest's idle wait off by default
  (`--idle-wait` turns it on). `FAST_DEVICE`, `FAST_SIMULATOR` and `FAST_UI_APP` are defaults.
- SKILL.md: step-by-step rules (no routine `dump`/`screenshot`/`pause`, guarded arrays).

## 1.4.0 — 2026-10-26

### More gestures

- `double_tap`, `drag` (with a `hold` on the start point for drag and drop and reorders),
  `edge_swipe` (back swipe, Control Center, Notification Center, home), `press_key` (`delete`,
  `return`, `tab`, `escape`, `space`), `press_button` (`home`; `lock` on the Simulator,
  `volume_up`/`volume_down` on the iPhone) and `set_slider`, on the Simulator and the iPhone.
- iPhone only, where AXe has no way: `pinch`, `rotate` (two fingers), `orientation` (a flow turns
  the phone back to portrait at its end) and `set_picker`; the Simulator names the reason.
- `open_url` on the iPhone; `shake` on the Simulator (no XCUITest API on a device).
- `key_combo` (a key held with `command`, `shift`, `option`, `control`), `clear_text` (deletes what
  a field holds), arrow keys for `press_key`, `press_button` `siri` (with the request as `text` on
  the iPhone), and the iPhone-only `two_finger_tap`, which zooms a map out where a pinch cannot.
- `press_button` `lock` is refused on an iPhone: a shared test phone would wait for its passcode.
- All of them join the screen map as steps.
- On the iPhone, `type_text`, `press_key`, `key_combo` and `clear_text` refuse to type with no
  focused field, and an unknown `element_type` is refused: both would have been UI Automation
  failures that end the runner. `clear_text` taps near the field's trailing edge and selects all
  before deleting, skips a caption with the field's label, and fails on the iPhone if text is
  left. A runner that dies mid-request is ended by the same pattern `stop` uses.
- Checked on an iOS 26.5 Simulator and an iPhone 11 on iOS 26.7.1, which showed what the first
  version got wrong:
  - Simulator edge swipes put the finger down before moving: a plain `axe swipe` or `axe drag`
    missed the back swipe and the home swipe (1 unlock in 3).
  - `edge_swipe` travels 80 % of the screen by default; an iPhone back swipe that stops at half
    the screen springs back.
  - `press_button` `home` on the iPhone brings SpringBoard forward; `XCUIDevice.press(.home)` did
    nothing on iOS 26.7.1.
  - The Simulator's `lock` is a 0.3 s press: AXe's default press locks but never wakes.
  - A runner that ends mid-request (a `set_picker` value the wheel does not have ends XCTest's
    test) is cleaned up and the FAIL line quotes XCTest's reason, instead of "server closed the
    connection"; the next request no longer finds the iPhone busy.
- `scroll_to` and `swipe` `direction` take the screen from the `Application` node: a scroll
  view's content taller than the screen sent swipes off screen (y = -277).

### Screen map

- Both engines now keep what their runs already read: the screens of each app, the nodes a
  flow can select on them (label, id, element type per engine) and the steps that led from one
  screen to the next, in `~/Library/Caches/fast-ui-map/<bundle id>.json`. No extra tree read,
  tap or crawl.
- `fastUIMap <bundle id>` lists the screens with the steps from launch; `--find <text>` prints a
  selector, its types and the steps to reach it; `--screen`, `clear <bundle id>|--all`. Agents
  look there before exploring with `dump`.
- Only steps that succeeded become paths. Screens unseen for 60 days drop out, at most 400 per
  app. `FAST_UI_MAP=0` turns it off; a map that cannot be saved prints `map=not-saved` and never
  changes PASS/FAIL. Maps hold on-screen labels and stay on the Mac.
- An optional `tap_label` that finds nothing reports `optional_missing` in its step result.

### Long press

- `long_press` holds for `duration` seconds (default 1) on a selector or on `x`/`y`, on the
  Simulator (`axe touch --down --up --delay`) and on the iPhone (XCUITest `press(forDuration:)`).
  It opens a context menu, such as a Home Screen widget's `Edit Widget`; `device.md` has the
  whole path into the widget's configuration sheet, checked on an iPhone 11 on iOS 26.7.1.

### Prompt rules

- `optional_permission_labels` takes rules beside bare labels:
  `{"title_contains": "track", "tap": "Ask App Not to Track"}` answers one kind of prompt,
  matched by its title, on the Simulator and on the iPhone. Bare labels answered every prompt
  with the first declared label it carried, so notifications and tracking (both `Allow`) could
  not get different answers, and a location prompt fell to `Don’t Allow` when its own button was
  not declared. A rule whose title matches owns the prompt: a missing button taps nothing.
- Device: each request starts with no prompt labels. A `do` used to keep the labels of the last
  flow the runner served and tapped those prompts unasked; it now taps only what
  `--prompt-labels` declares. PASS/FAIL lines list what was answered:
  `dismissed=["<title> → <button>"]`.

### Idle wait off, safely

- Device, with `wait_for_idle: false` / `--no-idle-wait`: a tap by selector (`tap_label`,
  `tap_first`, `tap_nearest`) waits until two snapshots agree on the target's frame (up to
  1.5 s), so it no longer lands on a button still sliding in; `launch` and `activate` wait until
  the app is frontmost and its layout stops moving (up to 2 s), so the next `screenshot`,
  `tap_point` or `swipe` no longer acts on the launch screen.
- `do --no-idle-wait` reads the screen it ends on only once the layout stops moving (up to
  1.5 s): its labels used to show two screens mid-push (checked on an iPhone 11, iOS 26.7.1).
- `do --no-idle-wait` reports `wait_for_idle=unsupported` when the private API is missing, as
  flows already did; it used to keep waiting without a word.
- The runner's pure logic (prompt rules, settling) is checked on the Mac by
  `RunnerLogicTests`, which compiles it with `swiftc`. The next device run rebuilds the runner by
  itself (its cache key covers the Swift sources); a runner already started with `serve` keeps
  the old code until `fastDeviceTest stop`.

### Fixes

- `screenshot` taps away a declared `optional_permission_labels` prompt before capturing, on the
  Simulator and on the iPhone (the device runner needs `--rebuild-runner` once). It read no tree,
  so a notification or location request raised after the flow's last `wait` (during a `pause`)
  ended up in the evidence image. Checked on iOS 26.5 Simulators and an iPhone 11 on iOS 26.7.1.

### Docs

- Only actions that read the tree (and now `screenshot`) dismiss prompts; `pause`, `tap_point` and
  `swipe` do not. iOS 26 labels for the tracking (`Ask App Not to Track`) and location prompts.

- The App Store review sheet is not in the accessibility tree; close it with `tap_point`.
- `open_url` delivers a link with no prompt; a link tapped in Safari raises "Open in …?", where the
  StoreKit `Cancel` label would drop it, so that flow declares `Open`.

## 1.3.0 — 2026-10-13

### The iPhone screen can be recorded

`fastDeviceTest --record` keeps XCTest's own screen recording of a one-shot run. XCTest records
every UI test on a device by default, but its attachment lifetime `deleteOnSuccess` threw the
clip away whenever the test passed — and the runner's tests always pass, even when the flow
fails, because the flow reports its result in a file. `--record` sets `SystemAttachmentLifetime =
keepAlways` in that run's `.xctestrun`. No Control Center, no QuickTime, no recording dot, nothing
in Photos; video inside the app keeps playing (QuickTime/CoreMediaIO capture froze it).

- A PASS keeps `<task>/final[-<session>].mp4`, a FAIL `run.mp4`, as on the Simulator; the PASS and
  FAIL lines carry `video=file://…`. The full-resolution original stays in `result.xcresult`.
- `--record` is refused with `--serve` or while a persistent runner holds the iPhone: the runner
  is one long test, so its clip would span the whole session.
- `fastDeviceTest --session` (or `FAST_UI_SESSION`, shared with the Simulator) tags device runs;
  `fastUIReport` and `fastUIReview` now read them (keyed by the iPhone's UDID).

### Clips light enough for a PR

Both engines re-encode recordings at review quality: H.264 MP4, long side 960 px, ~800 kbit/s.

| Clip | Before | After |
|---|---|---|
| iPhone, 17 s, 1290×2796 | 20 MB (H.264, 10 Mbit/s) | 1.4 MB, 442×960, ~2 s to encode |
| Simulator, 23 s | full-resolution HEVC | 0.4 MB H.264, plays in every browser |

The re-encode replaces a clip only when it succeeded and came out smaller; any failure keeps
the original. `FAST_VIDEO_LONG_SIDE` / `FAST_VIDEO_KBPS` tune it, `FAST_VIDEO_LONG_SIDE=0` keeps
originals. AVFoundation only, no ffmpeg.

### `fastEvidenceSheet`

A new launcher lays chosen screenshots into one captioned sheet for a PR or ticket: a title,
then a label and a wrapped caption above each shot, from a JSON spec. Task cells take the shot
from the task's newest passing run; JPEG quality 80 by default (seven phone shots ≈ 300 KB);
the font covers Vietnamese diacritics; one FAIL line lists every missing shot with the shots
that exist.

### Smaller fixes

- `fastUIReview` prints its sheets, notes and review folder as `file://` links, like the engines.
- Tests: `test_fast_media.py` (including a real AVFoundation encode) and
  `test_fast_evidence_sheet.py`; 102 tests in all, one of them runs every launcher as the copy a
  zip stores. `install.sh` self-tests the media module too.

## 1.2.0 — 2026-10-13

Compared with the first version (1.1.0 by DungVC, with the Xcode 27 fixes listed below).
Every change came from measurements on Xcode 27.0 and from 63 past sessions that used the
tool; the research and the plan are in `docs/`.

### Fewer reruns: failures explain themselves

The most common failure in those sessions was a wrong selector, and each rerun waited out a
20 s timeout because the FAIL line showed labels without saying why none matched.

- A FAIL line now lists `label (Type)` for every visible label, says when the wanted label
  exists under another element type (`'Add Widget' exists as StaticText, not Button`), and
  otherwise suggests the closest labels.
- `tap_label` without `element_type` taps the one node carrying the label when no Button
  does, and reports `fallback_type`. It never taps the Application or Window root, and on
  a device it treats nested containers with the same label and frame as one target.
- New selectors on simulator and device: `id` (accessibilityIdentifier, the most stable
  key) and `value` (a switch's `1`/`0`, a field's text). `tap_label` accepts every key.
- AXe sometimes fails to open its automation session on the first tap after a boot; the
  engine now retries once instead of failing the flow.

### Faster

| Where | Before | After |
|---|---|---|
| Simulator, each `wait` followed by a tap | two `describe-ui` calls (0.9–2.7 s each) | one: a tree younger than 300 ms is reused |
| iPhone, each tap on a screen that never stops animating | ~2.4 s of XCUITest wait-for-idle | ~0 with `setup.wait_for_idle: false` or `do --no-idle-wait` |
| `fastUIReview` helper | interpreted by `swift` on every run (~4 s cold) | compiled once and cached |
| Install on a new Mac with Xcode | Homebrew had to install AXe and xcodegen | under a second, nothing downloaded |

`"settle": true` on a tap or swipe is new and opt-in: it waits until the hierarchy stops
changing (at most 2.5 s), for screens where a fixed `post_delay` is a guess.

### Does more

- Simulator actions `type_text`, `launch`, `terminate` and `open_url` (deep links).
- `"prebuilt": true` in `app` drives what is already on the simulator, such as Settings or
  a build Xcode installed, without a project, DerivedData or fresh install.
- `--device` accepts a unique part of the iPhone's name; a part shared by two is refused.
- The engine runs without Pillow; only `motion` and `fastUIReview` need it.

### Lighter on tokens and disk

- `dump` and `failure-ui.json` are a flat list of label, type, id, value, frame and tap
  centre. A real failure dump went from 11 MB to 47 KB.
- `SKILL.md` went from 1366 to 887 words and the two main slash commands from 316 and 231
  to 158 and 135 words, so each invocation loads about 1.5k fewer tokens. In a before/after
  test an agent found the prebuilt-app mode in `SKILL.md` and passed on the first run
  (3 tool calls instead of 8).
- `SKILL.md` now says when to use Xcode 27's own `device-interaction` MCP tools (exploring
  an unknown screen, pinch, drag, console log) and when to use this tool (repeatable proof,
  matrix, video, report).

### Install and packaging

- AXe 1.8.0 ships in `vendor/` (MIT, licence included) and the device runner's `.xcodeproj`
  is committed: no Homebrew and no xcodegen.
- `install.sh --check` prints Xcode, AXe, Python, Pillow and signing-profile status and what
  is missing, and still reports cleanly on a Mac with no Xcode selected.
- `make-zip.sh` builds `fast-ios-device-test-<version>.zip`.
- Unit tests: 53 → 77; the suite runs with or without Pillow.

### Known limitations, planned for 1.2.1

- The docs tell prebuilt flows to start with `launch`, but the engine already launches the
  app, so that step costs an extra ~0.5 s.
- Editing `device-runner/project.yml` without regenerating the committed `.xcodeproj`
  builds the old project silently.
- `fastDeviceTest do --no-idle-wait` cannot report when the private XCTest selector is
  missing (flows do report it).
- `install.sh` does not warn when an older `axe` earlier on PATH shadows the bundled one.
- The "add element_type" hint appears even when the selector already has one.

## 1.1.0-xcode27 — 2026-10-02

Local fixes on top of 1.1.0, which was written against Xcode 26.

- The engine opens Device Hub on Xcode 27; AXe's automation session times out without it.
- Taps linger 0.4 s under Device Hub (measured: a post-delay of 0 lost 6 of 6 taps, 0.15 s
  lost 2 of 6, 0.25 s lost none).
- A flow without `build_inputs` no longer reuses a stale app forever.
- `SKILL.md` gained a complete flow example and was split into `references/device.md` and
  `references/review.md`; fan-out uses `sonnet` agents, and only for 2+ simulators or more
  than 5 flows.

## 1.1.0 — DungVC

The original tool: `/fastSimulatorTest`, `/fastDeviceTest` and `/fastUIReview`, JSON flows,
fresh install with seeded UserDefaults, dark and Dynamic Type variants, recording with
contact-sheet review, per-simulator fan-out and the `fastUIReport` table.
