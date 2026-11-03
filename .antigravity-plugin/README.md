# Fast iOS Device Test

Run focused iOS UI-flow verification from Antigravity and Gemini CLI on a local Mac. The bundled
skills write guarded JSON flows, drive Simulator, a connected iPhone, or a mixed phone + CarPlay rig,
record runs, review video, and prepare captioned PR evidence.

It also drives the Xcode 27.1 iPhone Duo through the installed `fastSimulatorTest` launcher:
outer and inner displays, closed/open/book/tabletop poses, framebuffer-specific screenshots, and
one-pose-per-row recordings. The agent never needs to click Device Hub directly.

The plugin bundles `iphone-duo-swiftui` for fold-aware SwiftUI code changes, `fast-ios-device-test`
for UI testing, and `fast-ios-device-test-setup` for environment readiness.
Run `npx fast-ios-device-test xcode-skills` to export Apple's `apple-app-resizability` guidance
without redistributing Apple content (`--docs liquid-glass` exports `apple-liquid-glass`; `--list`
shows other locally available Xcode skills).

## Requirements

- macOS with Xcode 26 or 27
- Xcode 27.1 for iPhone Duo
- Python 3
- A development profile that includes the target iPhone for physical-device runs

## Quick Setup

1. Install the plugin:
   ```bash
   agy plugin install https://github.com/DungVC-Dev/fast-ios-device-test
   ```
2. Install the CLI launchers and required AXe dependency:
   ```bash
   npx fast-ios-device-test
   ```
3. Verify readiness:
   ```bash
   npx fast-ios-device-test --check
   ```
   Setup is complete when the last line reports `CHECK OK`.

## Launchers & Capabilities

Antigravity and Gemini CLI run engines via the launchers in `~/.local/bin`:

- **Simulator flows (`fastSimulatorTest`):**
  `fastSimulatorTest <flow.json> [--reuse-app] [--record]`
  Explore live screens step by step with `fastSimulatorTest start <draft.json>`,
  `fastSimulatorTest do '<action>'`, `fastSimulatorTest labels`, and `fastSimulatorTest save <flow.json>`.
- **Physical iPhone (`fastDeviceTest`):**
  `fastDeviceTest <flow.json> [--device <name|udid>] [--record]`
  Rig check with `fastDeviceTest check [--device <name|udid>]`; lock when done with `fastDeviceTest lock`.
- **iPhone Duo (Xcode 27.1):**
  Put `"simulator":"iPhone Duo"` in the flow. Switch pose and orientation with
  `{"type":"duo","pose":"closed|open|book|tabletop","orientation":"portrait|landscape"}`.
  For video, run one `--duo-pose` row per pose with a shared `--session --record`, then review every
  `@duo-<pose>` case with `fastUIReview`. A recording contains one display framebuffer; screenshots
  are the proof when one flow switches displays.
- **CarPlay (`fastCarPlayTest`):**
  Check the rig with `fastCarPlayTest doctor --target sim|hardware`.
  Run mixed phone + car flows with `fastCarPlayTest run <flow.json> --target sim|hardware [--display widescreen|standard|hd|WxH@S]`.
- **Liquid Glass:**
  Derive cases LG-01..LG-11 using `references/liquid-glass.md`. Run appearance and Dynamic Type variants
  with `fastSimulatorTest flow.json --appearance light|dark --session liquid-glass`.
- **Review (`fastUIReview`):**
  `fastUIReview --root <artifacts-root> --session <name>` builds contact sheets and review notes;
  collate with `fastUIReport --root <artifacts-root> --session <name>`.

## Examples

- “Verify the login-to-home flow on Simulator and record it.”
- “Verify Home on iPhone Duo closed, open, book and tabletop, with screenshots and video.”
- “Run this regression flow on my connected iPhone.”
- “Run this mixed phone and CarPlay flow on the simulator.”
- “Review the last recorded session and prepare its evidence sheet.”

Source and full documentation:
[github.com/DungVC-Dev/fast-ios-device-test](https://github.com/DungVC-Dev/fast-ios-device-test)
