---
name: fast-ios-device-test
description: Use when asked to run, verify, re-test, or record an iOS screen or flow quickly on Simulator (/fastSimulatorTest) or a physical iPhone (/fastDeviceTest), including a matrix of several cases or several devices. Not for release, archive, or full-suite runs.
---

# Fast iOS Device Test

Pick the narrowest runner:

| Request | Runner |
|---|---|
| Any Simulator UI behavior described in words | `fastSimulatorTest <flow.json>` (`scripts/fast_ui.py`, fresh install) |
| The same kind of flow on a physical iPhone | `fastDeviceTest <flow.json>` (`scripts/fast_device.py`, XCUITest runner) — read [references/device.md](references/device.md) first |
| Watch the videos of a `--record` session | `fastUIReview` (`scripts/fast_ui_review.py`) — read [references/review.md](references/review.md) first |

Scripts live in `../../scripts/` relative to this file. `fastSimulatorTest` (on PATH after
`install.sh`, or `${CLAUDE_PLUGIN_ROOT}/bin/fastSimulatorTest` as a plugin) is the same
engine as `scripts/fast_ui.py`. If `axe` is missing: `brew install cameroncooke/axe/axe`;
if Pillow is missing: `python3 -m pip install --user pillow`.

The Python engine is feature-agnostic. Screen names, labels, navigation and
assertions live only in flow JSON. Never edit the engine for one screen.

## Flow file

Everything the engine needs is in the flow; there is no per-project config.
The smallest complete flow:

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
    "simulator": "<simulator UDID>",
    "derived_data": "/abs/MyApp/build/fast-ui-dd",
    "app_path": "/abs/MyApp/build/fast-ui-dd/Build/Products/Debug-DEV-iphonesimulator/MyApp.app",
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

- Use absolute paths: relative ones resolve against the flow file's directory,
  which is a temporary one.
- `project` is the `.xcworkspace` or `.xcodeproj`. `simulator` is a UDID from
  `xcrun simctl list devices available`; take one that Xcode or another agent is
  not running the app on, because the fresh install replaces the app and wipes
  its defaults.
- `derived_data` is a folder of its own, never Xcode's DerivedData: two builds
  in one DerivedData at the same time break each other. `app_path` is the `.app`
  inside it (`Build/Products/<configuration>-iphonesimulator/<Product>.app`).
- `build_inputs` are the source folders plus `project.pbxproj`. The build cache
  watches only these; leave them out and every run goes through `xcodebuild`.
- Selector keys sit directly on `wait`, `wait_absent`, `assert_absent` and
  `tap_first`: `label` (exact accessibility label), `element_type`,
  `label_is_empty`, `label_contains` (a substring, for long row labels such as
  `"Office, No Internet Connection, …"`), and bounds under `frame`
  (`{"frame": {"min_y": 400}}`).
  `tap_label` matches a `Button` unless `element_type` says otherwise.
- Every action type, `setup` key and CLI flag is in
  [references/usage.md](references/usage.md).

## fastSimulatorTest — one flow

1. Write the smallest version-1 flow for only the requested behavior into a
   temporary directory. Delete it after the run unless the user asks to keep it.
2. Selectors: prefer accessibility labels from the Swift view. If a label is
   unknown, put one `{"type": "dump"}` action at that point — the PASS line
   prints the visible labels. Never fake a `wait` on a label that cannot exist
   to force a hierarchy dump; that burns the whole timeout.
3. Run `scripts/fast_ui.py <flow.json>`. It boots the simulator, reuses the
   cached app when build inputs are unchanged, fresh-installs, injects
   `setup.preferences`, and prints one PASS/FAIL line.
4. On FAIL, the line already carries `visible labels: [...]` for the screen the
   flow was stuck on. Fix exactly one selector, rerun with `--reuse-app`. After
   two reruns of the same flow, stop and report the failure with the artifact
   path instead of iterating further.

### Flow timing rules (these are what make it fast)

- First `wait` after launch: `timeout` ≤ 20. Every later `wait`/`tap_*`: ≤ 8.
- `post_delay` ≤ 1. To let a screen settle, `wait` for a selector on the next
  screen instead of sleeping. A `swipe` with `post_delay: 12` is a bug.
- Use `pause` only for a product-defined delay (e.g. "popup closes after 5 s").
- A "must not show" outcome is asserted with `assert_absent` (`seconds` ≤ 8);
  a "closes" outcome with `wait_absent`. A tap that succeeds proves nothing
  about absence.
- Fresh install also wipes the app's defaults domain, so `setup.preferences`
  of one flow never leak into the next. After every run (PASS or FAIL) the
  engine removes the seeded preferences again, so a hard-coded `currentPurchase`
  / onboarding flag never stays on the simulator; pass `--keep-state` to inspect
  the app afterwards with them still in place. Seed `@ObjectUserDefaultWrapper` values
  as `{"$json_data": ...}`; a plain string for a JSON-backed key decodes to nil.
- Apple's own sheets (StoreKit review, system alerts from other processes) are
  not in the accessibility tree: prove them with `screenshot`, not `wait`.
- `tap_label` resolves the control from one hierarchy poll and taps its frame;
  no separate `wait` for the same label is needed before it.
- These limits apply to flows you write. If the user asks to rerun an existing
  flow, run it with its own values and list any violations in the report.
- Delete temporary flow files one by one (`rm <file>`); recursive deletes are
  blocked by the permission system.

Every file or folder the runners print (`artifacts=`, `screenshot=`, `ui=`, `video=`,
`path=`) is an absolute `file://` URL. Relay it as a markdown link,
`[evidence](file:///…)`, never as a bare or relative path: those are not clickable.

## Verify the real behavior, not just the selectors

A flow is only evidence when its last actions assert the product outcome
(the next screen's label, a toast, a popup gone). A FAIL splits two ways:

- The `visible labels` show the expected screen but under a different label
  → selector bug → fix the flow.
- The labels show the app in the wrong state (popup did not close, wrong tab,
  gate not applied) → product bug → fix the app code under the project rules,
  rebuild (`--build-only`, or drop `--reuse-app`), rerun the same flow.

With `--record`, metrics.json also carries `step_labels` (visible labels after
every step); `fastUIReview` prints them under each SHEET and copies them into the
review notes, so copy is checked from text rather than pixels.

Record when the user asks for video or when a flow proves a fix:
`fastSimulatorTest <flow.json> --record`. A PASS keeps exactly one clip per task at
`<artifacts-root>/<task>/final[-<session>].mp4` and deletes earlier clips; a FAIL keeps its
own `run.mp4` beside `failure.png` for diagnosis. Screenshots in the artifacts
folder are what you read to confirm the state; the video is for the human.

## fastSimulatorTest — several flows or several simulators

Build once from the main agent: `scripts/fast_ui.py <any-flow.json> --build-only`
→ prints `READY`. Every run after that passes `--reuse-app`.

- **One simulator, up to about 5 flows:** run them one after another in this
  conversation. A run is one command and one PASS/FAIL line, so a subagent
  costs more than it saves.
- **2+ simulators, or more flows than that:** fan out. Do NOT loop the flows in
  this conversation.

Fanning out:

1. Group the flows by simulator. One booted simulator per agent, never two
   agents on the same simulator (AXe and `simctl` serialize per device).
   List booted devices with `xcrun simctl list devices booted`.
2. Pick a session name (e.g. `review-2026-09-08`). Dispatch one agent per
   simulator, all in ONE message, `model: sonnet` (the agent only runs commands
   and fixes one selector from a FAIL line; use `opus` when the user asks for
   it). Each agent's prompt: the absolute flow paths, its simulator UDID, the
   exact command
   `fastSimulatorTest <flow> --reuse-app --session <name> [--record]`, the two-rerun
   cap, and "return only the PASS/FAIL lines".
3. Collate with the tool, not by hand:
   `fastUIReport --root <artifacts-root> --session <name>` prints the
   flow × simulator table (latest attempt per cell, attempt counts, failure
   causes with artifact paths, final videos). Paste it as the report. It works
   the same for runs made in this conversation with `--session <name>`.

The engine takes a build lock on DerivedData, so a stray build from an agent
cannot corrupt the shared app, but agents should not need to build at all.

Appearance and Dynamic Type variants: `--appearance light|dark` and
`--content-size <simctl name>`; each variant is its own report row
(see "Matrix" in [references/usage.md](references/usage.md)).

Read
[references/usage.md](references/usage.md) for the flow action reference,
device selection, cache model, and troubleshooting.
