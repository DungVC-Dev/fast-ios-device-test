# Usage reference

## Prerequisites

- The iPhone is trusted and available through Xcode/CoreDevice.
- Developer Mode is enabled.
- The device OS satisfies the app deployment target.
- Development signing and provisioning already work in Xcode.

## Common commands

Run a generated or user-provided Simulator UI flow with automatic app freshness checking:

```bash
scripts/fast_ui.py /absolute/path/to/task-flow.json
```

Fastest repeat when the cached app definitely matches current source:

```bash
scripts/fast_ui.py /absolute/path/to/task-flow.json --reuse-app
```

Refresh the cached app once before fanning flows out to several simulators:

```bash
scripts/fast_ui.py /absolute/path/to/any-flow.json --build-only   # prints READY
```

The app is built once per DerivedData, not per simulator: the fingerprint
excludes the simulator UDID, and a file lock in DerivedData serializes
concurrent builds. Flows running in parallel on different simulators should
all pass `--reuse-app`. Artifacts land in
`build/fast-ui/<task>/<timestamp>-<udid8>-<pid>/`, so parallel runs never
overwrite each other.

`--record` captures the simulator screen (`simctl io recordVideo`, HEVC). On
PASS the clip becomes `<artifacts-root>/<task>/final.mp4` (`final-<session>.mp4`
when `--session` is set, so two sessions never overwrite each other) and every
older clip of that task is deleted; on FAIL the clip stays as `run.mp4` in that
run's folder. The artifacts root defaults to `<project_root>/build/fast-ui`, which
is scratch space: pass `--artifacts-root <dir>` (or `FAST_UI_ROOT`) to keep runs,
screenshots and videos somewhere durable, e.g. the QA report folder, and set
`FAST_UI_KEEP_DAYS=0` there. Every run first prunes the root: run folders and
final videos untouched for 3 days are deleted (`FAST_UI_KEEP_DAYS` overrides; `0`
disables).
`--session <name>` (or `FAST_UI_SESSION`) tags `metrics.json`;
`scripts/fast_ui_report.py --root <project>/build/fast-ui --session <name>`
(launcher `fastUIReport`) collates every tagged run into a flow × simulator
table; `--since YYYYmmdd-HHMMSS` works without tags; `--json` for raw cells.

The engine boots the simulator (`simctl bootstatus -b`) before building, so a
shut-down device fails in seconds instead of after a full build.

The runner prints one PASS/FAIL line and stores screenshots, failure hierarchy,
and per-step timings under `build/fast-ui/<task>/<timestamp>/`. Add `--json`
only when full machine-readable results are needed.

## Dynamic UI flow format

A flow contains app/build configuration, fresh-install state, and an ordered
list of generic actions. Feature-specific labels belong only in flow files.

Supported actions:

- `wait`: wait for a selector.
- `pause`: hold for `seconds` without touching the UI.
- `wait_absent`: wait until nothing matches the selector (a popup closed, a
  sheet dismissed); fails if it is still there at `timeout`.
- `assert_absent`: poll for `seconds` and fail the moment the selector appears.
  This is how a "must NOT show" case is proven — never infer absence from a tap
  that happens to succeed (a full-screen cover can leave the tab bar tappable).
- `tap_label`: accessibility tap; resolves the selector through the same polling
  loop as `wait`, so a permission alert that appears between actions is dismissed
  instead of swallowing the tap. Pass `optional: true` to skip that resolution and
  tolerate a missing control.
- `tap_point`: tap a declared coordinate.
- `swipe`: gesture from `from` to `to` coordinates, or `direction`
  (`up`/`down`/`left`/`right`, the way the finger moves: `up` scrolls content down).
- `scroll_to`: swipe in `direction` (default `up`) until the selector is on screen,
  at most `max_swipes` (default 6) times; fails with the visible labels otherwise.
- `tap_first`: filter nodes, sort by frame keys, and tap the first match.
- `tap_nearest`: tap a target closest to one unambiguous anchor, e.g. the ⓘ of one
  Wi-Fi row: `{"type": "tap_nearest", "target": {"label": "More Info"},
  "anchor": {"label": "Office", "element_type": "StaticText"}}`. `axis` is `y`
  (same row, default) or `x` (same column).
- `screenshot`: save one named image.
- `motion`: capture frames and assert a minimum changed-pixel ratio in a
  normalized `[left, top, right, bottom]` region.
- `dump`: write the current UI hierarchy to `<name>-ui.json` and print the
  visible labels (screen order, status-bar digits removed) in the PASS line.
  Use it once to discover a selector; remove it from the final flow.

Every `wait` timeout failure prints `visible labels: [...]` for the screen the
flow stopped on, so a wrong selector is fixed from the FAIL line alone.

Visual capture uses Simulator's native framebuffer rather than AXe. Passing
flows capture nothing unless they contain `screenshot` or `motion`; passing
`motion` frames are deleted by default. Set `keep_frames: true` only when the
images themselves are needed. A failing run always keeps one screenshot and UI
hierarchy for diagnosis.

`post_delay` is capped at AXe's 10-second limit and the remainder is held by the
runner, so a longer settle time is expressed directly rather than by chaining
gestures. Prefer `pause` over a one-pixel `swipe` when a flow only needs to wait:
a swipe can scroll the screen it was meant to leave alone.

Selectors accept `label`, `label_contains`, `label_is_empty`, `element_type`, and bounds nested under
`frame`, such as `{"frame": {"min_y": 400, "max_width": 200}}` (`min_`/`max_` of
`x`, `y`, `width`, `height`). Missing or ambiguous
required selectors fail closed. Optional system prompts are declared under
`setup.optional_permission_labels`. The runner dismisses them from the same UI
hierarchy polling loop used by selectors, so prompts that appear late do not
need fixed sleeps or a separate retry loop.

System sheets that block a Simulator flow and their dismiss labels: notification
permission (`Allow` / `Don’t Allow`), App Tracking Transparency (`Allow Tracking`
/ `Ask App Not to Track`), StoreKit sandbox sign-in "You must enter both your
Apple Account and password." (`Cancel`). Declare all of them in
`setup.optional_permission_labels` for any flow that reaches a paywall or
StoreKit call; the sheet persists across fresh installs.

`tap_nearest` may declare a `success` selector and one or more `dismiss`
selectors. If a declared modal appears instead of success, the runner dismisses
it, resolves the original anchor/target again, retries once, and requires the
success selector. This keeps paywalls and other gates in flow data rather than
feature-specific Python.

Scalar preferences support booleans, numbers, and strings. For a Codable value
stored as JSON `Data` in UserDefaults, use `{"$json_data": {...}}`; the runner
encodes that object as UTF-8 data before launch. Keep model-specific fixtures in
the flow file, never in the engine.

Matrix variants: `setup.appearance` (`light`/`dark`) and `setup.content_size`
(a `simctl ui content_size` name), or `--appearance` / `--content-size` on the
command line, which win over the flow. The runner applies them with `simctl ui`
before launch, restores the simulator's previous values after the run (pass or
fail), and names the task `<flow>@dark@xxl` so each variant is its own report
row. An app that forces its own theme from stored settings needs that setting
seeded in `preferences` as well.

With `--record`, every step also stores the visible labels in `metrics.json`
(`step_labels`, with the second it ended in the video); `fastUIReview` prints
them per SHEET and copies them into the review notes.

If an `axe` call fails with a SimulatorKit/PrivateFrameworks error, AXe is older
than 1.8.0 and the selected Xcode is 27: upgrade AXe (`axe --version`). On Xcode 27
AXe also needs Device Hub running; the engine opens it when it is not.

For a new task, generate the smallest temporary flow containing only its
state/actions/assertions, then remove it after the run. Save reusable flows only
when the user requests persistence. The engine itself should never be changed
for a new screen.

## Physical iPhone (`fastDeviceTest`)

The same flow JSON runs on a device. Unused keys (`simulator`, `derived_data`,
`app_path`, `fresh_install`) are ignored; `app.device` or `--device` picks the
iPhone (required when several are connected).

```bash
fastDeviceTest flow.json --device "My iPhone"          # one-shot, ~14 s
fastDeviceTest serve --device "My iPhone"              # keep a runner alive, ~5 s
fastDeviceTest flow.json --device "My iPhone"          # via the runner, ~5 s
fastDeviceTest do '{"type":"tap_label","label":"Continue"}' --device <d>   # ~1 s
fastDeviceTest do '{"type":"screenshot","name":"now"}' --device <d> --out <dir>
fastDeviceTest stop --device <d>
```

- The runner (`device-runner/`, built with xcodegen) is cached per Xcode +
  signing profile + runner source in `~/Library/Caches/fast-device-test`;
  `--rebuild-runner` forces a rebuild.
- Signing: an existing development profile that lists the device and matches a
  non-revoked keychain identity; never the bundle id of an installed app.
  `FAST_DEVICE_PROFILE=<uuid>` pins one.
- `setup.preferences` → launch arguments (one launch, never persisted);
  `setup.content_size` → `-UIPreferredContentSizeCategoryName`; `setup.appearance`
  → `XCUIDevice.appearance`, restored after the flow.
- Artifacts: `<project_root>/build/fast-device/<task>/<run>/` (`FAST_DEVICE_ROOT`).

## Reviewing recordings

`scripts/fast_ui_review.py --root <artifacts-root> --session <name> [--interval 1.0]
[--change-threshold 0.01] [--columns 6] [--out <dir>]` (launcher `fastUIReview`)
reads every `metrics.json` of the session that has a video and writes
`<out>/<task>-<sim>.png`: a header with the case name, status and the flow's
`expect` text, then one frame at the end of each flow step (labelled with the
step name) plus one every `--interval` seconds. Interval frames whose pixels
changed less than `--change-threshold` (share, 0–1) against the previous kept
frame are dropped; step frames are always kept. Each `SHEET` line reports
`frames=kept/total` and `tokens≈` (pixels / 750, Claude's image cost).

It also writes `<out>/review-notes-<session>.json`:

```json
{"a01-native": {"simulator": "452BF01E", "status": "pass", "expect": "...",
                "sheet": "...png", "video": "...mp4", "verdict": null, "note": ""}}
```

The reviewer fills `verdict` (`OK` / `product bug` / `flow bug`) and `note`;
running the tool again keeps them. The `NOTES ... pending=N` line counts cases
without a verdict.

`--combined <video.mp4> --manifest <items.json> [--title-seconds 2.5] [--tolerance 0.5]`
verifies a concatenated deliverable instead: the manifest is the list of
`{path, title, subtitle}` the file was built from (one title card per clip). The
tool reads every clip's duration, samples the middle of each title card and the
last second of each clip into `combined-titles.png` / `combined-ends.png`, writes
`combined-timeline.json`, and prints `COMBINED items=N expected=…s actual=…s
delta=…s OK|MISMATCH` (exit 2 on mismatch).

Frames come from AVFoundation through a Swift helper, so no ffmpeg is needed. The
sheets are meant to be read one by one; the PASS line only proves the selectors
resolved.

## Matrix: appearance and Dynamic Type

Both engines take `setup.appearance` / `setup.content_size` or the CLI overrides
`--appearance light|dark` and `--content-size <simctl name>`, and suffix the task
(`flow@dark@xxl`) so `fastUIReport` shows each variant as its own row. The
Simulator engine sets `simctl ui` and restores the previous values afterwards;
the device runner sets `XCUIDevice.appearance` (restored after the flow) and
passes the size as `-UIPreferredContentSizeCategoryName`, which lasts one launch.
An app that pins its own theme (e.g. an `appThemeMode` setting) or uses fixed point
sizes ignores these; seed the theme via preferences, and treat text that does
not grow at `accessibility-*` sizes as a product finding.

## Environment variables

- `FAST_UI_ROOT`: artifacts root for `fastSimulatorTest` (runs, screenshots, videos).
- `FAST_UI_KEEP_DAYS`: prune age for that root; `0` disables pruning.
- `FAST_DEVICE_ROOT`: artifacts root for `fastDeviceTest`.
- `FAST_DEVICE_PROFILE`: provisioning profile UUID or path for the device runner.
- `FAST_DEVICE_DEVELOPER_DIR`: Xcode to build/run the device runner with.
- `FAST_DEVICE_PORT` / `FAST_DEVICE_IDLE`: runner port (8765) and idle timeout in seconds (1800).
- `FAST_DEVICE_CACHE`: runner cache root.

## Cache model

The engine also stores its app-build fingerprint inside the configured
DerivedData directory. It never compares source timestamps with the `.app`
directory timestamp, because incremental Xcode builds can preserve an older
output timestamp and otherwise trigger the same build forever. If inputs change
during a build, no new fingerprint is committed and the next invocation safely
rebuilds once more.

## Troubleshooting

- Several iPhones connected → pass `--device` (name or UDID); the launcher never guesses.
- `is busy: another runner holds it` → another agent is serving that iPhone; use a
  different one. Never `stop` a runner you did not start.
- `no usable development profile` → sign in to Xcode once (Settings › Accounts)
  and run any app on that iPhone, or set `FAST_DEVICE_PROFILE`.
- `Unable to Install … identity no longer valid` → a revoked certificate; rerun
  with `--rebuild-runner` after removing it from the keychain.
- The device must be unlocked, in Developer Mode, trusting this Mac, with
  Settings › Developer › Enable UI Automation on if iOS asks.
- A tap reports PASS but nothing changed → check `labels` in the output; only
  on-screen elements match, so the target may need a `swipe` first.
