---
name: fast-ios-device-test-setup
description: Use when installing, upgrading, or checking Fast iOS Device Test on a local Mac before running iOS Simulator or physical-iPhone UI flows.
---

# Set up Fast iOS Device Test

This is a local macOS tool. Never attempt setup in a cloud or Linux sandbox.

1. Confirm that the host is macOS and run `xcodebuild -version`. Xcode 26 or 27 is required.
2. Run `npx fast-ios-device-test`. This installs or upgrades the engine in
   `~/.local/share/fast-ios-device-test`, links its launchers into `~/.local/bin`, and installs the
   exact AXe and baguette versions pinned and SHA-256-verified by the project into
   `~/.local/share/{axe,baguette}`, regardless of Homebrew or PATH copies. baguette's official
   arm64 asset is downloaded at install time and its LICENSE/NOTICE are retained beside it.
3. Ensure `~/.local/bin` is on `PATH` for the current shell. Do not edit a shell profile without
   the user's approval; export it for the current command when needed.
4. Run `npx fast-ios-device-test --check`. Setup is complete only when the last line is
   `CHECK OK`. It also fails on a broken link (a moved or deleted clone) and on a Codex or
   Antigravity skill that will not load; follow the fix printed on that line. The AXe and baguette
   lines report pinned, installed and latest versions. Update them only when requested with
   `npx fast-ios-device-test update-tools` (or a per-tool update command).
5. When the user wants physical-iPhone runs, also run
   `npx fast-ios-device-test --check --device "<iPhone name or UDID>"` and follow the reported
   signing, trust, Developer Mode, or profile fix. Do not guess a device when several are present.

The installer also exposes the same skill to Claude Code. That extra link is harmless and does not
change the active agent's configuration. Never probe `install.sh` with unknown arguments: only its
documented `--link`, `--check`, tool install/update, and `--uninstall` modes are safe.
