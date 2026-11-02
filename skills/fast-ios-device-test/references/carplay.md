# CarPlay flows

`fastCarPlayTest` combines the existing phone engines with a driver for the car surface. Phone steps
default to `"surface":"phone"`; car steps say `"surface":"car"`. Every car step needs a descriptive
`name` or `comment`, because coordinates alone are not reviewable.

## Rig checks

```sh
fastCarPlayTest doctor --target sim [--udid agent-tmp-...]
fastCarPlayTest doctor --target hardware [--device <name-or-udid>]
```

Doctor is read-only and prints `OK`, `WARN`, or `FAIL` with a fix. Simulator runs require Xcode
26.6's `Simulator.app`, an iOS 26.5 runtime by default, a disposable simulator named
`agent-tmp-*`, an armed CarPlay display, and `baguette`. The launcher resolves
`FAST_IOS_BAGUETTE`, then the installer's pinned copy under `~/.local/share` / `~/.local/bin`, then
`PATH`. Xcode 27 Device Hub has no CarPlay.
For an iOS 27 runtime, point `setup.carplay_arm_script` at the project's iOS-27 arming script.
Only one Simulator.app and one CarPlay window may run at once. The launcher refuses every simulator
whose name does not start with `agent-tmp-`; do not reuse a person's simulator. It opens menus only
through System Events and never sends mouse clicks to Simulator.app.

Never run `xcrun simctl io ... screenshot --display external`: on iOS 27 it remodes TVOut and
restarts CarPlay. AXe and XCUITest cannot see the car framebuffer either.

Hardware runs need Apple's standalone CarPlay Simulator from Additional Tools, an unlocked iPhone
over USB, and a DEV/STG build with the right CarPlay entitlement. Quit and relaunch the whole
CarPlay Simulator app after every device install; reopening only its session window is insufficient.
When `app.install_path` is present, the launcher installs through the existing device engine and
performs that full app relaunch automatically.
If the screen says **Automaker UI**, or its toolbar is **Disconnected**, the case is `VOID`, not
`FAIL`. Use `carplay_connect` / `carplay_disconnect` for CPR route-loss cases.

Simulator.app has no video-in-car. A committed `carplay-video` build can be hidden there; browse
tests normally use a throwaway audio-entitled build created outside the app repository. Never edit or
commit the project's entitlement. Point the flow at the resulting `.app` with `app.prebuilt: true`,
`app.app_path`, and `setup.fresh_install: true`. Rebuild normally before judging release behavior.
Cases marked 🚗 need a video-capable Apple CarPlay Simulator profile or a real car, not Simulator.app.

## Displays

The flow default is `widescreen`. Override one run with exactly one display:

```sh
fastCarPlayTest run flow.json --target sim --display widescreen
fastCarPlayTest run flow.json --target sim --display standard
fastCarPlayTest run flow.json --target sim --display 720x480@1
```

| Name | Pixels | Scale | Purpose |
|---|---:|---:|---|
| `widescreen` | 1920×720 | 2 | default / normal review |
| `standard` | 800×480 | 2 | small head unit / clipping check |
| `hd` | 1280×720 | 2 | optional |
| `WxH@S` | custom | custom | project-specific or iOS 27 fallback |

`widescreen` adds no run-name suffix. A non-default selection gets a name such as
`browse@cp-standard`. Changing the size shuts down and reboots the simulator, so one command accepts
one size. Run the command again only when the user explicitly asks for another size; never add the
small-head-unit pass by default. If the requested display is already armed, the launcher skips
re-arming and the reboot. The project owns arming:

```json
"setup": {
  "carplay_display": "widescreen",
  "carplay_arm_script": "/absolute/project/tools/carplay_sim_display.sh"
}
```

The launcher calls the script as `<script> <udid> <width> <height> <scale>`. It never copies or
modifies project scripts.

## Actions

Simulator car input uses one persistent `baguette input --display carplay` session, sends a warm-up
event, and heals/retries once if input fails. Coordinates can be display pixels or normalized
numbers from 0 through 1.

```json
{"surface":"car","type":"car_tap","name":"Open TV card","x":0.55,"y":0.42}
{"surface":"car","type":"car_swipe","name":"Next shelf","x1":1700,"y1":500,"x2":500,"y2":500}
{"surface":"car","type":"car_screenshot","name":"TV shelves"}
{"surface":"car","type":"car_wait_stable","name":"Loaded shelves","timeout":8}
```

On hardware, `car_tap`, `car_screenshot`, `car_wait_stable`, `carplay_connect`, and
`carplay_disconnect` are supported. Taps are relative to the CarPlay Simulator window. macOS window
capture is black for protected video; that is not proof that the car got no picture. For a cast/HLS
case, fetch `live.m3u8`, `init.mp4`, and the newest segment from the iPhone's 169.254 address,
concatenate init + segment, and extract one frame with ffmpeg as the product runbook describes.

Every successful run automatically saves final phone and car screenshots. `--record` records the car
window when macOS exposes one. An optional top-level `"case":"CPR-01"` is printed and written to
`metrics.json`; `fastUIReport` uses it as the row key.

For widgets, verify the actual car render (background removal/mirror, margins, current lyric line)
and the app's `buildMarker`; a running Live Activity does not prove the CarPlay widget is advancing.
