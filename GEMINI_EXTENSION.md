# Fast iOS Device Test extension

Use the bundled `fast-ios-device-test` skill for iOS Simulator, physical-iPhone and CarPlay UI-flow
verification. If its launchers are not available on `PATH`, use the bundled
`fast-ios-device-test-setup` skill before running a flow. Do not treat this extension as a release,
archive, or full XCTest-suite runner.

Use the bundled `iphone-duo-swiftui` skill when changing SwiftUI code for iPhone Duo. If the
locally exported `apple-app-resizability` skill is installed, use it alongside the bundled skill
for Apple's current resizing guidance. Export it from the user's own Xcode without redistributing
Apple content with `npx fast-ios-device-test xcode-skills`; list other exportable Xcode skills with
`npx fast-ios-device-test xcode-skills --list`.

For iPhone Duo, use Xcode 27.1 and the installed `fastSimulatorTest` launcher. Put
`"simulator":"iPhone Duo"` in the flow; the engine selects Xcode 27.1, boots it and opens
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

Read the bundled skill's `references/usage.md#iphone-duo-xcode-271` section for the complete
flow shape, matrix commands, Accessibility prerequisite and troubleshooting.
