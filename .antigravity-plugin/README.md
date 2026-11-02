# Fast iOS Device Test

Run focused iOS UI-flow verification from Antigravity on a local Mac. The bundled skill writes
guarded JSON flows, drives Simulator or a connected iPhone, records runs, reviews video, and
prepares captioned PR evidence.

## Requirements

- macOS with Xcode 26 or 27
- Python 3
- A development profile that includes the target iPhone for physical-device runs

Run the suggested setup prompt after installing the plugin. It installs the local launchers and
bundled AXe runtime with `npx fast-ios-device-test`, then verifies the setup without changing an
iOS project.

## Examples

- “Verify the login-to-home flow on Simulator and record it.”
- “Run this regression flow on my connected iPhone.”
- “Review the last recorded session and prepare its evidence sheet.”

Source and full documentation:
[github.com/DungVC-Dev/fast-ios-device-test](https://github.com/DungVC-Dev/fast-ios-device-test)
