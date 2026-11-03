---
name: fast-ios-device-test
description: Use when asked to run, verify, re-test, or record an iOS screen or flow quickly on Simulator, iPhone Duo, CarPlay, or a physical iPhone, including a matrix of several cases or devices, or a system app such as Settings. Not for release, archive, or full-suite runs.
---

# Fast iOS Device Test

For iPhone Duo code changes, also use `apple-app-resizability` when that locally exported Xcode
skill is installed; use the bundled `iphone-duo-swiftui` skill for fold-aware SwiftUI patterns.
For Liquid Glass code changes, also use `apple-liquid-glass` when that local Xcode export is
installed; this repo ships only the test derivation guide, never Apple's source documentation.

Before the first run, confirm that `fastSimulatorTest` and `fastDeviceTest` are on `PATH`. If they
are missing, use the bundled `fast-ios-device-test-setup` skill or run `npx fast-ios-device-test`
and require its final `CHECK OK` before continuing. A run that ends with `update available: …`
(at most once a day): tell the user once, at the end of the task; never update mid-task.
The runtime uses required project-pinned AXe and optional baguette under `~/.local/share` before
PATH copies. A missing baguette is expected unless CarPlay support is needed and does not fail
`CHECK OK`; install it with `install.sh --install-baguette`. Only run
`npx fast-ios-device-test update-tools` when the user asks to update dependencies.

## Which tool

| Need | Use |
|---|---|
| Prove a behavior, rerun it, run a matrix, record video, report | this skill: `fastSimulatorTest <flow.json>` / `fastDeviceTest <flow.json>` |
| Explore an unknown screen on a Simulator, read the app's console log | Xcode 27's `device-interaction` tools when the active agent provides them, on a **different** simulator; then write the flow here. They refuse a physical iPhone (Xcode 27.0 and 27.2) |
| Explore or drive a physical iPhone: taps, pinch, rotate, `two_finger_drag` (a map's tilt) | this skill: `fastDeviceTest do '<action>'` step by step ([references/device.md](references/device.md)) |
| Watch the videos of a `--record` session | `fastUIReview` — read [references/review.md](references/review.md) first |
| PR evidence (sheet + clips) | nothing to run: every PASS flow run, and every `--before` run that failed at its outcome step, is filed in `~/Desktop/<project> <ticket>/` — "Evidence folder" in [references/usage.md](references/usage.md) |
| Change that sheet (order, captions, a shot) | edit `source/sheet.json` there, then `fastEvidenceSheet <it>` — "Evidence sheet" in [references/usage.md](references/usage.md) |
| Physical iPhone | read [references/device.md](references/device.md) first |
| CarPlay (Simulator.app or Apple CarPlay Simulator + iPhone) | `fastCarPlayTest`; read [references/carplay.md](references/carplay.md) first. It reuses the phone engines and safely drives/captures the separate car surface |
| Design or screen with Liquid Glass | identify the glass and derive the first `LG-` cases with [references/liquid-glass.md](references/liquid-glass.md) |
| Another Mac app, Apple Watch | out of reach of the engines: say so at once. Do not drive it with `osascript`, `cliclick`, `screencapture` or a hand-written XCUITest unless the user asks for that |

Never point both tools at one simulator: Xcode reinstalls the app over the fresh install.
The engine is feature-agnostic: screen names, labels and assertions live only in flow
JSON. Never edit the engine for one screen. Every action, `setup` key and CLI flag is in
[references/usage.md](references/usage.md).

CarPlay is the exception to the accessibility-only path: AXe/XCUITest cannot reach the car display,
and `simctl io --display external` is destructive on iOS 27. `fastCarPlayTest` uses `baguette` on a
disposable `agent-tmp-*` simulator or the standalone CarPlay Simulator window on hardware. Display
changes restart Simulator.app to clear its cached mode and are refused if a non-agent Simulator
window is open. Project-specific display arming stays in the flow's `setup.carplay_arm_script`.

## Flow file

Everything the engine needs is in the flow; there is no per-project config.

```json
{
  "version": 1,
  "name": "home-premium",
  "expect": "Home tab on screen, no paywall",
  "app": {
    "project_root": "/abs/MyApp",
    "project": "/abs/MyApp/MyApp.xcworkspace",
    "scheme": "MyApp-DEV",
    "configuration": "Debug-DEV",
    "bundle_id": "com.example.myapp.dev",
    "simulator": "<simulator UDID or unique full name>",
    "build_inputs": ["/abs/MyApp/MyApp", "/abs/MyApp/MyApp.xcodeproj/project.pbxproj"]
  },
  "setup": {
    "preferences": {"isPremium": true},
    "optional_permission_labels": ["Allow", "Don’t Allow"]
  },
  "actions": [
    {"type": "wait", "label": "Home", "timeout": 20},
    {"type": "tap_label", "label": "Lyrics", "element_type": "RadioButton"},
    {"type": "assert_absent", "label": "Upgrade to Premium", "seconds": 3},
    {"type": "screenshot", "name": "lyrics.png"}
  ]
}
```

- **App already on the simulator** (Settings, a build Xcode installed): `"app": {"bundle_id":
  "com.apple.Preferences", "prebuilt": true, "simulator": "<UDID>", "project_root": "<dir>"}`;
  no project, build or fresh install, start with `{"type": "launch"}`.
- **Where flows live**: a ticket's flows go in `fastEvidenceSheet --folder <project_root>`'s
  `flows=` folder (`~/Desktop/<project> <ticket>/source/flows/`, created on the spot), so a later
  session finds them and they go when the user deletes the folder after the merge. Never under
  `build/fast-ui` or `build/fast-device` (pruned after `FAST_UI_KEEP_DAYS`). Throwaway flows may
  stay in the session scratchpad.
- Absolute paths only (a flow outside the repo must name `project_root`). `simulator` is a UDID
  or unique full name from `xcrun simctl list devices available` that nobody else runs the app on.
  DerivedData defaults to `~/Library/Caches/fast-ios-device-test/dd/<repo-key>/`, shared by every
  worktree of the git repository and outside Spotlight indexing. Set `app.derived_data` only for
  an intentional override (`FAST_IOS_DERIVED_DATA_ROOT` overrides the shared root); the engine
  finds the built `.app` automatically. `build_inputs` (source folders + `project.pbxproj`) drive
  the build cache; without them every run rebuilds. A legacy `<project>/build/fast-ui-dd` value is
  redirected safely with a note; the tool never deletes that old data automatically.
- Selector keys on `wait`, `wait_absent`, `assert_absent`, `tap_first`, `tap_label`, `scroll_to`
  and every gesture, control and assertion action: `label` (exact), `label_contains`, `id`
  (accessibilityIdentifier), `value` (a switch's "1"/"0", a field's text), `element_type`,
  `enabled`, `label_is_empty`, `frame` bounds (`{"min_y": 400}`).
- Beyond taps and swipes: `long_press`, `double_tap`, `drag`, `back`, `edge_swipe`,
  `pull_to_refresh`, `type_text` into a named field (`clear: true`), `clear_text`, `press_key`,
  `dismiss_keyboard`, `set_switch`, `set_slider`, `set_picker`, `tap_alert`, `assert_value`,
  `assert_count`, `press_button`, `set_location`, `set_permission`, `push_notification`,
  `status_bar`, clipboard; on the iPhone also `pinch`, `rotate`, `two_finger_tap`,
  `two_finger_drag`, `orientation`. Keys and which engine runs what: the table in
  [references/usage.md](references/usage.md#gestures-keyboard-controls-assertions-and-device-state).
  Prove a control changed with `assert_value`, not by the tap succeeding.
- **iPhone Duo (Xcode 27.1):** use `"simulator": "iPhone Duo"`. A step
  `{"type":"duo","pose":"closed|open|book|tabletop","orientation":"portrait|landscape"}`
  selects the pose and optional orientation (`closed` uses the outer display; the others use the
  inner display). `closed`/`open` allow both orientations; `book` is landscape with a vertical
  fold and `tabletop` portrait with a horizontal fold. A following `screenshot` automatically
  targets that framebuffer, or can set `"display":"outer|inner"` explicitly. For a recorded
  matrix, run the flow once per `--duo-pose`; add `setup.duo_orientation` or
  `--duo-orientation` only when that orientation variant was requested. See
  [references/usage.md](references/usage.md#iphone-duo-xcode-271).
- `tap_label` matches a `Button`; when the flow sets no `element_type` and exactly one node of
  any type has the label, it taps that node and reports `fallback_type`.

## One flow

1. One flow by default: the state the behavior needs, the shortest way to it, and an assertion
   of the requested outcome. A flow the user gave runs unchanged. Add cases, variants
   (appearance, text size, other devices) or a matrix only when the user lists or asks for them;
   when the outcome to assert is unclear, ask one question. Write it as a version-1 flow in a
   temporary directory (delete it afterwards, one `rm <file>` per file).
2. App driven before → `fastUIMap <bundle id> --find <label>` first: selectors and the steps that
   reach them, from what earlier runs saw; `--path-to <screen>` prints them as one guarded `do`
   request. A hint that may be stale; the flow still verifies.
   Maps live in `~/Library/Caches/fast-ui-map/` and hold on-screen labels, which can include
   user data: never copy one into a repo, PR or ticket.
3. Unknown screen → build the flow on the live app instead of rerunning it:
   `fastSimulatorTest start <draft.json>` (only `app` + `setup`), then one
   `fastSimulatorTest do '<action json>'` per step (each prints the labels after it),
   then `fastSimulatorTest save <flow.json>`, which writes the steps and verifies them with
   one full run. A single unknown label in an existing flow → one `{"type": "dump"}` at that point: the PASS line prints the visible
   labels and `<name>-ui.json` has label, type, id, value and tap `center` per node. Never
   fake a `wait` on an impossible label to get a dump.
4. Run `fastSimulatorTest <flow.json>`. It boots the simulator, reuses the cached app when
   build inputs are unchanged, fresh-installs, seeds `setup.preferences`, prints one PASS/FAIL line.
5. On FAIL the line lists `visible labels: [Add Widget (StaticText), …]` with types, says when
   the label exists under another type, and suggests close labels. Fix one selector, rerun
   with `--reuse-app`. After two reruns stop and report with the artifact link. A failing flow
   is never a reason to switch to another driver (`osascript`, `cliclick`, a hand-written
   XCUITest): report instead.

## Step by step (exploring, or one quick check)

`fastSimulatorTest do '<action or array>' --simulator <udid> [--app <bundle id>]` and
`fastDeviceTest do … --device <udid|name>` act on what is on screen now (no build, install or
launch) and print one PASS/FAIL line with the visible labels after the actions.
`FAST_SIMULATOR`, `FAST_UI_APP` and `FAST_DEVICE` save the flags.

- The line already lists 40 labels: no `dump`, `screenshot` or `pause` in a routine step.
- Send the steps you can predict as one array with an `expect` selector on each gesture
  (`{"type": "tap_label", "label": "General", "expect": {"label": "About"}}`): the request stops
  at the first screen that is not the expected one. A destructive-looking step (Delete, Pay,
  Send, Sign Out…) in an array is refused unless it says `"confirm": true`.
- Between steps, one line of reasoning; turn a path that worked into a flow for reruns.
- A screen visited before: `fastUIMap <bundle id> --path-to <screen>` gives the whole way as one
  guarded request. A search of about six steps or more: in Claude Code, hand it to the `ui-explorer`
  subagent (Haiku, `FAST_GUARD_SINGLE=1`, returns the guarded request) and decide only the hard steps
  yourself — experimental, check its result before relying on it. In Gemini CLI, Antigravity, or
  Codex, perform the steps yourself directly with `fastSimulatorTest do` / `fastDeviceTest do`, or
  invoke your agent's subagent capability.

### Timing rules

- First `wait` after launch ≤ 20 s; every later `wait`/`tap_*` ≤ 8 s; `post_delay` ≤ 1 s.
  To let a screen settle, `wait` for the next screen's selector; `pause` only for a
  product-defined delay. `"settle": true` on a tap/swipe waits until the tree stops changing
  (max 2.5 s) — use it on screens that keep animating, not by default.
- "Must not show" → `assert_absent` (`seconds` ≤ 8); "closes" → `wait_absent`. A successful
  tap proves nothing about absence.
- Fresh install wipes the defaults domain, and the engine undoes what a run changed (seeded
  preferences, appearance, location, status bar, granted permissions; the app is terminated)
  even when the run is interrupted (`--keep-state` to inspect). One run per simulator: a second
  one fails with `simulator busy`. Seed Codable values as `{"$json_data": …}`.
- A launch permission prompt may never appear right after a boot: answer it with
  `tap_alert` `"system": true, "optional": true`.
- Test builds skip SwiftLint (`lint=shimmed`); `"skip_lint": false` in `app` lints.
- Apple's own sheets are not in the accessibility tree: prove them with `screenshot`.
- `open_url` delivers a link with no prompt. A link tapped in Safari asks "Open in …?": that flow
  declares `Open` and never `Cancel`, or the runner cancels the link.
- Rerunning a user's existing flow: keep its values, list violations in the report.

Every path the tools print (`artifacts=`, `screenshot=`, `ui=`, `video=`, `path=`) is a `file://`
URL: relay it as a markdown link.

## When the work is done

- iPhone: `fastDeviceTest lock --device <d>` instead of `stop`. It frees the runner and locks
  the screen, for a test phone kept on Auto-Lock "Never". Nothing can drive the phone again
  until someone types its passcode, so only at the very end; it refuses an iPhone another
  runner holds ("busy").
- Simulator: `fastSimulatorTest shutdown` shuts down every booted simulator;
  `--simulator <udid>` only that one. Spare one Xcode is running the app on unless the user is
  done with it too.

## Evidence, not just selectors

A flow is evidence only when its last actions assert the product outcome. A FAIL whose labels
show the expected screen under another label is a selector bug (fix the flow); labels showing
the wrong state (popup still there, gate not applied) are a product bug: fix the code, rebuild
(`--build-only`, or drop `--reuse-app`), rerun the same flow; after two fix-and-rerun rounds that
still fail, stop and report what the labels show. Record (`--record`) when the user
asks for video or a flow proves a fix: a PASS keeps one `final[-<session>].mp4` per task, a
FAIL keeps `run.mp4` beside `failure.png`. Both engines record — the iPhone through XCTest's own
screen recording, one-shot runs only ([references/device.md](references/device.md)) — and both
re-encode the clip at review quality (H.264, 960 px, ~1–2 MB for 20 s).

## Several flows or simulators

Build once: `fastSimulatorTest <any-flow.json> --build-only` → `READY`; then every run passes
`--reuse-app`. One simulator and up to about 5 flows: run them here, one after another.
2+ simulators or more flows: fan out (one subagent, worker, or Claude sonnet agent per booted
simulator, or run them sequentially), each with its flow paths, UDID, the command
`fastSimulatorTest <flow> --reuse-app --session <name> [--record]`, the two-rerun cap and
"return only the PASS/FAIL lines"; never two agents on one simulator. Collate with
`fastUIReport --root <artifacts-root> --session <name>` and paste its table. Variants:
`--appearance light|dark`, `--content-size <simctl name>` and iPhone Duo
`--duo-pose closed|open|book|tabletop [--duo-orientation portrait|landscape]` are their own rows.
