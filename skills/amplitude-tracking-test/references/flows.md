# Flow format for run_flow.py

Minimal flow (premium, onboarded, tracking capture on); the app, keys and labels are examples:

```json
{
  "version": 1,
  "name": "home-library",
  "app": {
    "project": "<repo>/MyApp.xcodeproj", "project_root": "<repo>",
    "scheme": "MyApp-DEV", "configuration": "Debug-DEV",
    "bundle_id": "com.example.myapp", "simulator": "<SIMULATOR_UDID>",
    "derived_data": "<DerivedData>/MyApp-…", "app_path": "<derived_data>/Build/Products/Debug-DEV-iphonesimulator/MyApp.app"
  },
  "setup": {
    "capture_console": true,
    "preferences": {
      "onboardingDone": true, "isFirstLaunch": false, "hasSeenTutorial": true,
      "currentPurchase": {"$json_data": {"transactionId": "ui-test", "productId": "premium_weekly", "periodEnd": "2099-01-01T00:00:00.000Z", "status": "active", "accessLevel": "premium"}}
    },
    "optional_permission_labels": ["Allow", "Ask App Not to Track", "Don’t Allow"]
  },
  "actions": [
    {"type": "wait", "label": "Home", "element_type": "StaticText", "timeout": 20},
    {"type": "tap_label", "label": "Library", "element_type": "RadioButton"},
    {"type": "pause", "seconds": 2}
  ]
}
```

Expectations file (`<journey>.expect.json`): `[{"event": "Home Screen Viewed", "params": {"access level": "premium"}, "once": true}]`.

Seeded preferences are removed from the simulator after every run (`--keep-state` keeps them).
Timing: first `wait` ≤ 20 s, later ≤ 8 s, `post_delay` ≤ 1 s. Tab bar items are `RadioButton`,
large titles `Heading`. Unknown label → one `{"type": "dump"}` and read the PASS line.

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
- `swipe`: gesture from `from` to `to` coordinates.
- `tap_first`: filter nodes, sort by frame keys, and tap the first match.
- `tap_nearest`: tap a target closest to one unambiguous anchor.
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

Selectors accept `label`, `label_is_empty`, `element_type`, and frame bounds
such as `min_y`, `max_y`, `min_width`, and `max_width`. Missing or ambiguous
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

If an `axe` call fails with a SimulatorKit/PrivateFrameworks error, the selected
Xcode is a 27 beta (AXe issue); rerun with
`DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`.

For a new task, generate the smallest temporary flow containing only its
state/actions/assertions, then remove it after the run. Save reusable flows only
when the user requests persistence. The engine itself should never be changed
for a new screen.

