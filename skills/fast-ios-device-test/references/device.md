# fastDeviceTest — the same flows on a physical iPhone

Read this before running on a device. The flow format, selectors and timing rules are the
ones in [../SKILL.md](../SKILL.md); only what differs on a device is listed here.

New iPhone, or a run that fails before any step: `fastDeviceTest check --device <udid|name>`
lists pairing, connection, Developer Mode, the Xcode and signing profile it will use, and the
fix for each gap ([../../../SETUP.md](../../../SETUP.md) has the whole setup).

`fastDeviceTest <flow.json> [--device <udid|name>] [--install <App.app>]` builds a
generic XCUITest runner once (cached in `~/Library/Caches/fast-device-test`),
re-signs it with an existing development profile, and runs the flow on the device.

Every flow and live `do`/`serve`/`lock` request first runs a sub-two-second readiness check. It
reuses one `devicectl` result (briefly cached per UDID) and stops before install/build with exactly
one `FAIL error=<problem>: <fix>` line when pairing, connection, Developer Mode, the developer disk
image, Xcode/iOS compatibility, or a development profile is missing. `fastDeviceTest check` remains
the full multi-line report.

- **Signing needs no Apple ID login.** The launcher picks a non-expired
  development profile that lists the device and matches a non-revoked keychain
  identity, preferring a wildcard profile, then the fewest capabilities. It
  never takes the bundle id of an app installed on the iPhone (or a child id
  such as an extension); override with `FAST_DEVICE_PROFILE=<uuid>`.
- **Xcode is chosen per device:** the oldest installed Xcode whose iphoneos SDK
  covers the device's iOS (`FAST_DEVICE_DEVELOPER_DIR` overrides).
- **The app is not built or fresh-installed.** It drives what is installed;
  `--install` pushes an iphoneos `.app` first.
- **`setup.preferences` become launch arguments** (typed plist fragments, `$json_data`
  as `<hex>`): the argument domain lasts one launch and is never written, so no
  cleanup is needed. Anything the app itself writes while running does persist.
- **Other apps:** add `"app": "<bundle id>"` to an action to drive Settings,
  Shortcuts or SpringBoard from that step on; `activate` / `launch` / `terminate`
  act on the current app. Permission alerts are looked up on SpringBoard (XCUITest reports
  them as `Alert` on iOS 26, where AXe on the Simulator says `Sheet`); `screenshot` taps a
  declared one away first, as on the Simulator.
- Supported actions: `wait`, `wait_absent`, `assert_absent`, `tap_label`,
  `tap_first`, `tap_nearest`, `tap_point`, `long_press`, `double_tap`, `drag`, `edge_swipe`,
  `swipe` (points or `direction`), `scroll_to`, `type_text`, `press_key`, `key_combo`,
  `clear_text`, `press_button`, `set_slider`, `pause`, `screenshot`, `dump`, `activate`, `launch` (optional
  `launch_arguments`), `terminate`, `open_url`, and the iPhone-only `two_finger_tap`, `two_finger_drag`, `pinch`, `rotate`,
  `orientation` (see [usage.md](usage.md#gestures-keyboard-controls-assertions-and-device-state)). `motion` and `shake` are
  simulator-only; `press_button` `lock` is refused inside a flow (the next steps would wait
  for the passcode): lock at the end with `fastDeviceTest lock`.
- **Editing a Home Screen widget:** go home with `terminate` on the app, then
  `long_press` the widget on `com.apple.springboard` (the widget node carries the app's
  name as `id`), then tap `id`
  `com.apple.springboardhome.application-shortcut-item.configure-widget` (`Edit Widget`).
  The sheet that opens is not in SpringBoard's tree: drive it with
  `"app": "com.apple.WorkflowUI.WidgetConfigurationExtension"`. Close it with a `tap_point`
  above the sheet on SpringBoard. Checked on an iPhone 11, iOS 26.7.1.
- Also on the iPhone: `back`, `pull_to_refresh`, `dismiss_keyboard`, `set_switch`, `set_picker`
  (`option`, a selector or the `index`-th wheel), `tap_alert`, `assert_value`, `assert_count`,
  `set_appearance`, `set_location`, `set_permission` (`reset` only), clipboard. Earlier names
  `rotate_gesture` and `set_orientation` still run. Simulator-only: `motion`, `shake`,
  `push_notification`, `status_bar`, permission `grant`/`revoke`.
- iPhone-only, for device conditions and long waits: `network_condition`, `low_power` (see
  "Device conditions" below) and `wait_change` (a selector; waits up to `timeout` seconds, minutes
  are fine, until the first matching node shows another label or value or is gone, and returns
  `from`/`to`). Any step may say `"optional": true`: when its target is absent it is skipped
  (`skipped_optional=<step>` in the PASS line) instead of failing the request, and its default
  timeout drops to 2 s. Use it for "tap Play if paused" or a third-party upsell's `Close` / `Not now`.
- When `tap_label` finds nothing, the error lists the types that text has on screen
  ("that text is on screen as Cell, StaticText"): set `element_type` to one of them.
- `set_slider` and `set_picker` use XCUITest's own adjustments (`adjust(toNormalizedSliderPosition:)`,
  `adjust(toPickerWheelValue:)`); `tap_alert` looks on SpringBoard first, then the app.

Checked on an iPhone 15 Plus with iOS 26.6.1 (AssistiveTouch on):

- **Clipboard:** iOS keeps the pasteboard from a background process, so `set_clipboard` /
  `assert_clipboard` bring the runner to the front for a moment and then reactivate the app
  under test; the status bar briefly shows a "◀ FastDeviceUITests" back link.
- **`open_url`** goes to the system handler (`https://` opens Safari, `App-prefs:` Settings),
  like `simctl openurl`.
- **Notification Center or banners on screen** make XCTest wait ~15 s, up to 4 times, before
  each event, which can outlast the ~48 s request timeout. Close Notification Center with
  `press_button` `home`, not `edge_swipe` `bottom`.
- **A Home Screen context menu** (after `long_press` on an icon) keeps SpringBoard from going
  idle: run those steps with `--no-idle-wait` / `"wait_for_idle": false`.
- **`two_finger_tap` / `pinch` on the whole app** can fail with "Unable to compute coordinates
  for gesture" when a full-screen overlay (AssistiveTouch) covers it; target a labelled element
  or an `id`. The XCTest failure is a normal step FAIL and the runner keeps serving.
- **`pinch` below 1 (zoom out)** did not zoom Maps out on that phone (it pulled the sheet or
  panned); zoom in did. Check it on a phone without AssistiveTouch before relying on it.
- **`set_location`** also moves the automatic time zone, and `clear: true` does not move it
  back: toggle Settings › General › Date & Time › Set Automatically afterwards.
- **`dismiss_keyboard`** cannot close the keyboard of an empty search field (iOS disables its
  Search key); pass `button`.
- `type_text` with a selector taps the field near its trailing edge but left of any small
  button inside it (a search bar's Dictate button opens the Siri sheet). A search field is
  `SearchField`; `element_type: "TextField"` matches it too.
- `fastDeviceTest do` prints PASS/FAIL and labels; per-step results (`count`, `toggled`,
  `value`) are in the flow's `metrics.json` / `--json`.
- Only on-screen nodes match: hidden tabs stay in the SwiftUI tree, and text in a
  list row scrolled out of view reports a made-up frame near the top of the list,
  so a node must also sit inside its own cell. Use `scroll_to` to bring a row in.
- `launch_arguments` stick to the app object: a later `launch` without them reuses
  the previous ones. Pass `"launch_arguments": []` to launch clean.
- Selectors take `id` (accessibilityIdentifier) and `value` as on the simulator; `dump`
  nodes carry `id` and `value` when set. `tap_label` falls back to the one node of any
  type with that label when `element_type` is not given (result `fallback_type`).
- **Screens that never go idle** (a GIF, a ticking clock) make XCUITest wait ~2.5 s after
  every tap. `fastDeviceTest do` runs with that wait off by default (`--idle-wait` turns it
  on); a flow switches it off with `"setup": {"wait_for_idle": false}` (private XCTest API,
  found at runtime). The runner then settles on its own: a tap by selector waits until two snapshots
  agree on the target's frame (up to 1.5 s, ~0.5 s per tap), `launch` / `activate` wait
  until the app is frontmost and its layout stops moving (up to 2 s; changing text such as a
  clock does not count), and a `do` reads the screen it ends on once the layout stops moving
  (up to 1.5 s). The PASS/FAIL line says `wait_for_idle=unsupported` when this Xcode
  has no such API and the wait stayed on.
- **Prompts are per request.** A `do` taps no permission prompt unless it passes
  `--prompt-labels` (`"Allow, Don’t Allow"`, or a JSON array with rules as in
  [usage.md](usage.md)); labels a flow declared do not carry over to later requests. Every
  prompt the runner answered is listed as `dismissed=["<title> → <button>"]`. When the prompt
  is what you are testing, tap it in its own step (`tap_label` with
  `"app": "com.apple.springboard"`) and leave its labels out.
- `type_text` goes through the iPhone's current keyboard: a Vietnamese Telex keyboard turns
  `wifi` into other letters. Type digits, or switch the keyboard by hand; the runner never
  changes the phone's keyboards.
- **Screen map:** the runner returns what it read and the steps that succeeded with every
  response, and the launcher adds them to `fastUIMap` (see [usage.md](usage.md)). A `do` that
  only taps a point starts from the screen the previous `do` ended on (within 2 minutes). A
  runner already started with `serve` before this feature records nothing until
  `fastDeviceTest stop`.
- `--device` (or `FAST_DEVICE`) accepts a UDID, the full name, or a unique part of the name
  (`Blue`); a part that matches two iPhones is refused. An iPhone named by its UDID or full name
  whose `serve` runner answers is taken from the runner's state file, without `xcrun devicectl
  list devices` (0.15–1 s); a part of a name always asks devicectl.

### Screen recording (`--record`)

The iPhone screen **can** be recorded: XCTest records every UI test on a device by itself
(`PreferredScreenCaptureFormat = screenRecording` is the runner's default), but its default
attachment lifetime (`deleteOnSuccess`) throws the clip away when the test passes. `--record`
sets `SystemAttachmentLifetime = keepAlways` in that run's `.xctestrun`, and the clip comes
back with the other attachments. No Control Center, no QuickTime, no recording dot on screen,
nothing written to the iPhone's Photos.

```bash
fastDeviceTest flow.json --device <d> --record --session pr-12
# PASS … video=file://…/<task>/final-pr-12.mp4 artifacts=file://…
```

- One-shot runs only: the persistent runner is one long test, so its clip would span the
  whole session. `--record` runs one-shot; while `serve` holds the iPhone it is refused.
  A recorded flow costs one-shot time (~20 s) plus ~2 s to re-encode.
- The clip is re-encoded at review quality (H.264 MP4, long side 960 px, ~800 kbit/s:
  17 s of a 1290×2796 recording goes from 20 MB to ~1.4 MB). A PASS keeps
  `<task>/final[-<session>].mp4` (one per task, older clips deleted), a FAIL keeps `run.mp4`
  in its run folder. The full-resolution original stays in `result.xcresult`.
- Without `--record` nothing is kept, a FAIL included: the runner reports a failed flow
  in its result file, so for XCTest the test passed.
- Video inside the app keeps playing while XCTest records (checked on iOS 26.6 with an
  `AVPlayer` guide video). Recording over the USB cable with QuickTime / CoreMediaIO
  is the method that froze in-app video; do not use it.
- The run has no per-step timestamps, so `fastUIReview` samples device clips on its
  interval grid.

### Persistent runner — use it for anything beyond one run

A flow and every `do` start the runner if it is not up (`fastDeviceTest serve --device
<udid|name>` does it alone, ~5 s) and reuse it; it answers on the CoreDevice tunnel (port
8765) and idles out after 5 min (`FAST_DEVICE_IDLE`). While it is up, a flow takes ~4–6 s
instead of ~14–20 s, and single actions ~1 s; `--one-shot` (and `--record`) run a flow
through one xcodebuild test instead:

```bash
fastDeviceTest do '{"type":"tap_label","label":"Lyrics","element_type":"RadioButton"}' --device <d>
fastDeviceTest do '{"type":"screenshot","name":"now"}' --device <d> --out <dir>
fastDeviceTest do '{"type":"launch"}' --app com.apple.Preferences --device <d>
fastDeviceTest serve --install <path/to/App.app> --device <d>   # install, then start the runner
fastDeviceTest status|stop --device <d>
fastDeviceTest lock --device <d>     # end of the work: stop, then lock the screen
```

Each `do` prints PASS/FAIL plus the visible labels after the action, so an agent
can look, decide, and act step by step. On a long screen add `--labels changed` (only
`labels_added=` / `labels_gone=` since the previous `do` on that iPhone) or `--labels none`.
Screenshots and dumps go to a per-iPhone cache folder (printed as links) unless `--out <dir>`
names one; nothing is written into the current directory.

Once the steps are known, send them as one JSON array: the runner executes them in
one request, stops at the first failure (`FAIL actions=N step=K type=…`) and snapshots
the hierarchy once at the end, instead of a process, a round trip and a snapshot per
step:

```bash
fastDeviceTest do '[{"type":"terminate"},{"type":"launch"},
  {"type":"tap_label","label":"Wi-Fi, Office"},
  {"type":"tap_nearest","target":{"label":"More Info"},"anchor":{"label":"Office","element_type":"StaticText"}},
  {"type":"scroll_to","label":"Configure Proxy"},{"type":"screenshot","name":"wifi"}]' \
  --app com.apple.Preferences --device <d> --out <dir>
```

`dump` writes the on-screen nodes with type and frame to `<out>/<name>-ui.json`
(`ui=` in the PASS line); the frame keys are the selector keys, so a dump feeds
`frame` bounds, `tap_point` and `tap_nearest` directly. In a flow they land in the
run's artifacts folder. Always `stop` when done (`lock` at the end of the work, which also
locks the screen): the runner holds the device, and another
agent's xcodebuild run on the same iPhone will collide with it. A device that already has a
runner is refused ("is busy"); pick another iPhone, never `stop` a runner you did not start.
A runner this Mac started that no longer answers (after an idle-out, while xcodebuild
collects diagnostics) is ended and replaced; a locked iPhone is reported in seconds.

- Artifacts: `<project_root>/build/fast-device/<task>/<run>/` with screenshots,
  `failure.png`, `failure-ui.txt`, `metrics.json`, the `.xcresult` and, with `--record`,
  the clip (`run.mp4` on FAIL; `<task>/final[-<session>].mp4` on PASS).
- Device must be unlocked, in Developer Mode, trusting the Mac; enable
  Settings › Developer › Enable UI Automation if iOS asks. One run per device at a time.

### Device conditions: weak network, heat, Low Power Mode, app logs

Checked on an iPhone 15 Plus, iOS 26.6.1, Xcode 27.1. Use these to test how an app behaves on a
bad connection or a hot phone, and write the result per condition (the CARFACE
`docs/test-cases/lyrics-regression.md` §4.13 is an example matrix).

- **Weak network:** `{"type":"network_condition","profile":"3G"}` switches Network Link
  Conditioner on in Settings › Developer with that preset, then activates the flow's app again
  (in `do`: the `--app` app, or `"return_to"`). Presets: `100% Loss`, `3G`, `DSL`, `Edge`,
  `High Latency DNS`, `LTE`, `Very Bad Network`, `Wi-Fi`, `Wi-Fi 802.11ac`; `"profile":"off"`
  switches it off.
- **Low Power Mode:** `{"type":"low_power","on":true}` (Settings › Battery).
- Both are remembered per iPhone and **switched off again on their own**: at the end of the flow
  (PASS or FAIL; `setup.keep_conditions: true` keeps them), at `fastDeviceTest stop`, or with
  `fastDeviceTest conditions off --device <d> [--app <bundle id>]` after a series of `do`
  requests; `conditions status` shows what is on, and every `do` prints `conditions_on=` while
  something is. A condition left on survives app restarts and makes every later run on a shared
  phone look broken.
- Settings may reopen on the page it was left on; the steps cope with the start page, the
  Developer page and the Network Link Conditioner page. A FAIL names the step you wrote
  (`step=2 type=network_condition (tap_label)`).
- **Heat: Xcode › Debug › Induce Device Conditions › Thermal State › Fair / Serious / Critical**
  (the same submenu has Network Link and GPU Performance State). No command line reaches it:
  Xcode 27 has no Devices window, Device Hub has no conditions, `devicectl` has none. The condition
  applies to the scheme's **Active Run Destination**, so select the test iPhone there first; the
  submenu then reads `Thermal State (Active)`. To stop it, pick the same profile again; the menu
  shows the change only after a few seconds. Put the run destination back afterwards.
  - Agents doing this through GUI automation: a Mac often runs two Xcodes. `tell application
    "Xcode"`, `process "Xcode"` and plain keystrokes can reach the other one and type into its
    editor. Address Xcode by path (`tell application "/path/to/Xcode.app"`), set the destination
    with `set active run destination of workspace document "<X>.xcodeproj" to run destination
    "<device name>" of …`, click the menu on `first application process whose unix id is <pid>`
    after checking it is frontmost, and never send typed text or Return. Tell the user before
    bringing Xcode to the front, and run `git status` in the other open projects afterwards.

#### App logs

Most pass criteria of a background feature live in the app's log (`song changed:`,
`not_authorized`). The app is launched with its console attached (`devicectl … --console`,
`os_log` mirrored); the console lives as long as the app, so ending the capture ends the app.

- **In a flow:** `--app-log`, or list regexes in the flow's `"expect_log": [...]` (each must
  match somewhere in the run's log) and `"expect_no_log": [...]` (none may match). The log is
  kept as `<artifacts>/app.log` (`app_log=` in the result) and a miss turns a PASS into
  `FAIL step=expect_log`. The flow then drives the console-launched app (`setup.launch` is set
  to false for it).
- **Step by step:**

  ```bash
  fastDeviceTest log start --app <bundle id> --device <d>   # (re)launches the app with its console
  fastDeviceTest do '{"type":"tap_label","label":"Next"}' --device <d>   # drives that app, no --app needed
  fastDeviceTest log wait 'song changed: .+' --timeout 120 --device <d>
  fastDeviceTest log assert-absent 'not_authorized' --device <d>
  fastDeviceTest log show --lines 30 [<regex>] --device <d>
  fastDeviceTest log stop --device <d>
  ```

  `wait` and `assert` read only lines after the previous match (or `log mark`), so a line logged
  between two commands is neither missed nor matched twice. `assert` / `assert-absent` do not
  wait. `idevicesyslog` and `devicectl` cannot read an app group's log files.
- **Long waits** (a song that ends on its own after ~80 s): `log wait … --timeout 120`, or a
  `wait_change` step on the title (`{"type":"wait_change","id":"songTitle","timeout":120}`). A
  `do` request's budget is the sum of its steps' `timeout` and `pause` seconds plus 30 s, so a
  long `timeout` is all it takes.

#### Third-party apps in tests

- Spotify **Free** allows 6 skips per hour and a few song picks per day; after that Spotify
  rejects Next from every surface (App Remote returns `Code=-2001`, `wamp.error.not_authorized`)
  and shows "You've got 6 skips per hour". A "Next keeps the old song" result on a Free account is
  that limit, not the app. Use Premium for skip cases. Labels in Spotify (`com.spotify.client`):
  `Next track`, `Previous track`, `Close the Now Playing View`, `Close` on its upsell sheets
  (close those with an optional step: `{"type":"tap_label","label":"Close","optional":true}`).

### Troubleshooting before and during a run

| Reported problem | Fix |
|---|---|
| Not paired/trusted or disconnected | Unlock the iPhone, tap Trust, keep USB/Wi-Fi connected; pair it once in Xcode if needed. |
| Developer Mode off / developer disk image unavailable | Enable Settings › Privacy & Security › Developer Mode, restart, then open Xcode once with the unlocked phone connected. |
| No development profile lists the iPhone | Sign in under Xcode Settings › Accounts and run an app on this iPhone once. |
| UI Automation disabled | Settings › Developer › Enable UI Automation. |
| Untrusted Developer / developer profile not trusted | Settings › General › VPN & Device Management › trust the developer. |
| Device busy preparing or copying shared cache | Wait, keep it unlocked and connected, then retry later. |
| iOS newer than selected Xcode | Install a matching Xcode or set `DEVELOPER_DIR` (`FAST_DEVICE_DEVELOPER_DIR` also selects the preflight/build Xcode). |
| Developer Mode requires a passcode | Set a device passcode, enable Developer Mode, then retry. |
| Device disconnected mid-run | Reconnect it, keep it unlocked, and rerun the same flow. |
