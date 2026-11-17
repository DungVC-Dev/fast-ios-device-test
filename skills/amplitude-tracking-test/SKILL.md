---
name: amplitude-tracking-test
description: Use when asked to verify Amplitude (analytics) tracking against a tracking-plan doc (xlsx) — which events fire, with which properties — by diffing the plan against the code and driving the app on Simulator or a cabled iPhone. Self-contained: ships with fast-ios-device-test but has its own runners.
---

# Amplitude tracking test

Scripts live in the tool's `amplitude-tracking-test/scripts/`: `../../amplitude-tracking-test/scripts/`
from this file's real location (resolve a symlinked skill folder with `realpath` first; the
installed copy is `~/.local/share/fast-ios-device-test/amplitude-tracking-test/scripts/`). Below,
`scripts/` means that folder. Work in a scratch folder `<work>`. Needs `openpyxl` (plan) and Pillow (Simulator runs): `python3 -m pip install --user
openpyxl pillow`; a script that lacks one says so and stops.

**Token rule:** the model never reads the workbook, raw logs or full reports. Every step is a
script whose one-line summary you read; open a report only for its non-PASS rows.

## Steps

1. **Plan** → `python3 scripts/tracking_plan.py <plan.xlsx> --out <work>/events.json`
   One PLAN line: events by kind (client / sdk / backend) and property count.
2. **Static diff (no build, no UI, < 1 s)** →
   `python3 scripts/tracking_static.py <work>/events.json <repo>/<App>/Sources --out <work>/static.json`
   Reads every `eventName` / `parameters` switch in the code. Report MISSING (planned, not in code),
   KEYS (property keys differ) and UNPLANNED (in code, not in the plan). Often this alone answers.
3. **Key guard** → `python3 scripts/amplitude_key.py <built .app> --project-root <repo>`.
   Exit 2 = the build sends to the production key → stop; never test against production.
4. **Journeys on Simulator** → one flow per user journey (onboarding, home, settings, playback…),
   run with `python3 scripts/run_flow.py <flow.json> --reuse-app --artifacts-root <work>/runs`.
   - Reuse saved flows first: `<work>/flows/<app>/J*.json` + `J*.expect.json` (set `app.simulator`); this package ships none.
   - Every flow sets `"setup": {"capture_console": true, …}`: the app's
     `[TRACKING][Amplitude] event=… params=…` lines land in the run folder's `console.log`.
   - Flow format (actions, selectors, preferences seeding, timing rules): `references/flows.md`.
   - 2+ journeys → one agent per booted simulator in parallel, never two agents on one simulator.
4b. **Same journeys on a physical iPhone** (only an iPhone plugged in by cable; Wi-Fi devices are
   refused) → `python3 scripts/run_flow_device.py <flow.json> --device <name|udid> --artifacts-root <work>/devruns`.
   Same flow JSON (`app.bundle_id` is enough); the app must already be installed (`--install <App.app>`
   otherwise). With `capture_console` the Mac launches the app via `devicectl --console` so its log
   lands in `console.log`, and the XCUITest runner only attaches. Use it for what a simulator cannot
   fire: music recognition, microphone, camera, on-device ML.
   Several flows → `run_flow_device.py serve --device <d>` first (~8 s per flow), `stop` when done.
   Its runner has its own cache, port (8766) and bundle id, so it never touches a `fastDeviceTest`
   runner; still never run both on one iPhone at the same time.
5. **Match** → `python3 scripts/tracking_match.py <work>/events.json <run folder> --expect <journey>.expect.json --out <journey>.report.md`
   A run folder of `fastSimulatorTest` / `fastDeviceTest` with `--app-log` works too (its `app.log`
   is read like `console.log`); `-` instead of `events.json` lists what fired without a plan.
   Statuses: PASS, FAIL (missing/extra keys or wrong value), MISSING (not fired), DUPLICATE
   (`once` events fired twice), EXTRA (planned but not expected here), UNPLANNED (not in the plan).
   MISSING is an app finding only when the run's labels prove the flow reached the trigger screen;
   otherwise fix the flow (max 4 runs per journey).
6. **Amplitude confirmation (optional)** → only when Amplitude MCP tools are connected in the
   session (`get_amplitude_context`, `get_amp_user_data`, `get_amp_taxonomy`): confirm ingestion for
   the test device, check keys added by SDK plugins (`app theme`, `from background` never appear in
   the local log), and backend events. If not connected, say so; setup is in `references/amplitude-mcp.md`.
   **Read-only, always.** Call only the read tools listed in `references/amplitude-mcp.md`. Never
   call a tool that creates, updates, deletes, restores or shares anything (taxonomy, events,
   properties, charts, dashboards, cohorts, flags, experiments, comments), even when the plan and
   Amplitude disagree: report the mismatch and leave the fix to the person. Never query
   `… Production` projects; use the project whose key matches the build (Staging).

## Report

One table per journey (Event | Status | Detail), then app findings (event, what is wrong, file:line
or payload), then what could not be tested by UI (backend events, real sign-in, purchases, camera)
and how to cover it. Offer to save new/fixed flows into a folder the user picks (for example the ticket's evidence
folder), never into this package.

## Known traps

- Never tap purchase / subscribe / restore: the StoreKit sign-in sheet blocks the simulator.
- A/B-tested onboarding differs between installs: assert labels before tapping.
- Apple's review sheet (`SKStoreReviewController`) is not in the accessibility tree: close it with
  `tap_point` on "Not Now" (find the point once from a screenshot).
- Premium state without a paywall: seed the stored purchase the app reads (see
  `references/flows.md`), not a bare `isPremium` flag the app may recompute.
