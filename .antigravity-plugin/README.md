# Fast iOS Device Test

Run focused iOS UI-flow verification from Antigravity on a local Mac. The bundled skill writes
guarded JSON flows, drives Simulator, a connected iPhone, or a mixed phone + CarPlay rig, records runs, reviews video, and
prepares captioned PR evidence.

It also drives the Xcode 27.1 iPhone Duo through the installed `fastSimulatorTest` launcher:
outer and inner displays, closed/open/book/tabletop poses, framebuffer-specific screenshots and
one-pose-per-row recordings. The agent never needs to click Device Hub directly.

The plugin bundles `iphone-duo-swiftui` for fold-aware SwiftUI code changes. If
`apple-app-resizability` has been exported from the user's local Xcode, use both skills together.
Run `npx fast-ios-device-test xcode-skills` to export it without redistributing Apple content;
`npx fast-ios-device-test xcode-skills --list` shows other locally available Xcode skills.

## Requirements

- macOS with Xcode 26 or 27
- Xcode 27.1 for iPhone Duo
- Python 3
- A development profile that includes the target iPhone for physical-device runs

Run the suggested setup prompt after installing the plugin. It installs the local launchers and
bundled AXe runtime with `npx fast-ios-device-test`, then verifies the setup without changing an
iOS project.

## Examples

- “Verify the login-to-home flow on Simulator and record it.”
- “Verify Home on iPhone Duo closed, open, book and tabletop, with screenshots and video.”
- “Run this regression flow on my connected iPhone.”
- “Run this mixed phone and CarPlay flow on the simulator.”
- “Review the last recorded session and prepare its evidence sheet.”

For Duo, put `"simulator":"iPhone Duo"` in the flow. Use
`{"type":"duo","pose":"closed|open|book|tabletop"}` for screenshots within one flow. For
video, run one `--duo-pose` row per pose with a shared `--session --record`, then review every
`@duo-<pose>` case with `fastUIReview`. A recording contains one display framebuffer; screenshots
are the proof when one flow switches displays.

Source and full documentation:
[github.com/DungVC-Dev/fast-ios-device-test](https://github.com/DungVC-Dev/fast-ios-device-test)
