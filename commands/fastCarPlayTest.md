---
description: Run a mixed phone + CarPlay flow on Simulator.app or Apple's CarPlay Simulator
argument-hint: <flow.json> --target sim|hardware
allowed-tools: Bash(fastCarPlayTest:*)
---

Run `fastCarPlayTest doctor --target sim|hardware` first, then execute the requested flow with
`fastCarPlayTest run`. Read the `fast-ios-device-test` skill's CarPlay reference before authoring a
flow. Never use `simctl io screenshot --display external`; it destructively remodes iOS 27 CarPlay.
