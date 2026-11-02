# Fast iOS Device Test extension

Use the bundled `fast-ios-device-test` skill for iOS Simulator and physical-iPhone UI-flow
verification. If its launchers are not available on `PATH`, use the bundled
`fast-ios-device-test-setup` skill before running a flow. Do not treat this extension as a release,
archive, or full XCTest-suite runner.

For iPhone Duo, use Xcode 27.1 and the installed `fastSimulatorTest` launcher. Put
`"simulator":"iPhone Duo"` in the flow; the engine selects Xcode 27.1, boots it and opens
Device Hub. Never click Device Hub directly.

- In one flow, change state with `{"type":"duo","pose":"closed|open|book|tabletop"}`.
  `closed` uses the outer portrait display; `open`, `book` and `tabletop` use the inner display.
- A following `screenshot` targets the selected framebuffer. `screenshot` and `motion` may set
  `"display":"outer|inner"` explicitly.
- For reviewable video, run one fixed-pose row per `--duo-pose closed|open|book|tabletop`, with
  the same `--session` and `--record`. One recording contains one framebuffer; use screenshots
  when a single flow switches poses.
- Review all four `@duo-<pose>` cases with `fastUIReview`, then collate them with `fastUIReport`.

Read the bundled skill's `references/usage.md#iphone-duo-xcode-271` section for the complete
flow shape, matrix commands, Accessibility prerequisite and troubleshooting.
