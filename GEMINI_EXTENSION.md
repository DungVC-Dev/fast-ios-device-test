# Fast iOS Device Test extension

Use the bundled `fast-ios-device-test` skill for iOS Simulator, iPhone Duo, physical-iPhone, and
CarPlay UI-flow verification. If its launchers are not available on `PATH`, use the bundled
`fast-ios-device-test-setup` skill or run `npx fast-ios-device-test` and verify with
`npx fast-ios-device-test --check` before running a flow. Do not treat this extension as a release,
archive, or full XCTest-suite runner.

Gemini CLI has no Claude slash commands; drive every engine through the CLI launchers in `~/.local/bin`:

## 1. Simulator flows (`fastSimulatorTest`)

Run a JSON UI flow on iOS Simulator:
```bash
fastSimulatorTest /path/to/flow.json [--reuse-app] [--record]
```
- Explore an unknown screen step by step on the live app:
  `fastSimulatorTest start /abs/draft.json`, then one `fastSimulatorTest do '<action>'` per step,
  `fastSimulatorTest labels`, and `fastSimulatorTest save /abs/flow.json`.
- Shut down simulators when done: `fastSimulatorTest shutdown [--simulator <udid>]`.

## 2. Physical iPhone (`fastDeviceTest`)

Run the same guarded JSON flows on a connected iPhone via the bundled, auto-signed XCUITest runner:
```bash
fastDeviceTest /path/to/flow.json [--device <name|udid>] [--record]
```
- Verify device pairing, Developer Mode and signing: `fastDeviceTest check [--device <name|udid>]`.
- Step-by-step exploration: `fastDeviceTest do '<action>' [--device <name|udid>]`.
- Lock the screen when testing is complete: `fastDeviceTest lock [--device <name|udid>]`.

## 3. iPhone Duo (Xcode 27.1)

For iPhone Duo code changes, use the bundled `iphone-duo-swiftui` skill. If Apple's locally exported
`apple-app-resizability` skill is installed, use it alongside the bundled skill. Export it from the
user's local Xcode with `npx fast-ios-device-test xcode-skills` (list with `--list`).

For verification, use Xcode 27.1 and the installed `fastSimulatorTest` launcher. Put
`"simulator":"iPhone Duo"` in the flow; the engine selects Xcode 27.1, boots it, and opens
Device Hub. Never click Device Hub directly.

- In one flow, change state with
  `{"type":"duo","pose":"closed|open|book|tabletop","orientation":"portrait|landscape"}`.
  Orientation is optional: `closed`/`open` allow both; `book` is vertical-fold landscape and
  `tabletop` horizontal-fold portrait.
- A following `screenshot` targets the selected framebuffer. `screenshot` and `motion` may set
  `"display":"outer|inner"` explicitly.
- For reviewable video, run one fixed-pose row per `--duo-pose closed|open|book|tabletop`, optionally
  with `--duo-orientation portrait|landscape`, and
  the same `--session` and `--record`. One recording contains one framebuffer; use screenshots
  when a single flow switches poses.
- Review all four `@duo-<pose>` cases with `fastUIReview`, then collate them with `fastUIReport`.

## 4. CarPlay (`fastCarPlayTest`)

Test mixed phone + CarPlay flows on Simulator.app or Apple's standalone CarPlay Simulator with a USB iPhone:
- Verify setup: `fastCarPlayTest doctor --target sim|hardware`.
- Run flow: `fastCarPlayTest run /path/to/flow.json --target sim|hardware [--display widescreen|standard|hd|WxH@S]`.
- Phone steps use `"surface":"phone"` (default); car steps declare `"surface":"car"` with actions
  `car_tap`, `car_swipe`, `car_screenshot`, and `car_wait_stable`.

## 5. Liquid Glass verification

When navigation or controls use Liquid Glass, derive test cases LG-01 through LG-11 with
`references/liquid-glass.md`. Run variants with:
```bash
fastSimulatorTest flow.json --appearance light --session liquid-glass
fastSimulatorTest flow.json --appearance dark --session liquid-glass
fastSimulatorTest flow.json --content-size accessibility-extra-extra-extra-large --session liquid-glass
```
Export local Apple Liquid Glass guides with `npx fast-ios-device-test xcode-skills --docs liquid-glass`.

## 6. Review recorded runs (`fastUIReview`)

After running with `--record --session <name>`:
```bash
fastUIReview --root <artifacts-root> --session <name>
```
Inspect contact sheets (`<task>-<sim>.png`) with your file-reading or image viewer tool, fill notes
and verdicts (`OK`, `product bug`, `flow bug`) in `review-notes-<session>.json` until `pending=0`,
and collate the summary table with `fastUIReport --root <artifacts-root> --session <name>`.
