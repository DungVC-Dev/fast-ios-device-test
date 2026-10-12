# fastDeviceTest — the same flows on a physical iPhone

Read this before running on a device. The flow format, selectors and timing rules are the
ones in [../SKILL.md](../SKILL.md); only what differs on a device is listed here.

`fastDeviceTest <flow.json> [--device <udid|name>] [--install <App.app>]` builds a
generic XCUITest runner once (cached in `~/Library/Caches/fast-device-test`),
re-signs it with an existing development profile, and runs the flow on the device.

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
  act on the current app. Permission alerts are looked up on SpringBoard.
- Supported actions: `wait`, `wait_absent`, `assert_absent`, `tap_label`,
  `tap_first`, `tap_nearest`, `tap_point`, `swipe` (points or `direction`),
  `scroll_to`, `type_text`, `pause`, `screenshot`, `dump`, `activate`, `launch`
  (optional `launch_arguments`), `terminate`. `motion` is simulator-only.
- Only on-screen nodes match: hidden tabs stay in the SwiftUI tree, and text in a
  list row scrolled out of view reports a made-up frame near the top of the list,
  so a node must also sit inside its own cell. Use `scroll_to` to bring a row in.
- `launch_arguments` stick to the app object: a later `launch` without them reuses
  the previous ones. Pass `"launch_arguments": []` to launch clean.

### Persistent runner — use it for anything beyond one run

`fastDeviceTest serve --device <udid|name>` starts the runner once (~5 s) and keeps
it answering on the CoreDevice tunnel (port 8765, idles out after 30 min). While
it is up, a flow takes ~4–6 s instead of ~14 s, and single actions ~1 s:

```bash
fastDeviceTest do '{"type":"tap_label","label":"Lyrics","element_type":"RadioButton"}' --device <d>
fastDeviceTest do '{"type":"screenshot","name":"now"}' --device <d> --out <dir>
fastDeviceTest do '{"type":"launch"}' --app com.apple.Preferences --device <d>
fastDeviceTest status|stop --device <d>
```

Each `do` prints PASS/FAIL plus the visible labels after the action, so an agent
can look, decide, and act step by step.

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
run's artifacts folder. `--serve` on a flow run starts the server
if needed. Always `stop` when done: the runner holds the device, and another
agent's xcodebuild run on the same iPhone will collide with it. `serve` refuses a
device that already has a runner ("is busy"); pick another iPhone, never `stop`
a runner you did not start.

- Artifacts: `<project_root>/build/fast-device/<task>/<run>/` with screenshots,
  `failure.png`, `failure-ui.txt`, `metrics.json` and the `.xcresult`.
- Device must be unlocked, in Developer Mode, trusting the Mac; enable
  Settings › Developer › Enable UI Automation if iOS asks. One run per device at a time.
