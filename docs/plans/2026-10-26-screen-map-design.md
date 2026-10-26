# Screen map — design

Status: draft, revised after review, 2026-10-26.

## Goal

An agent that writes a flow for an app it has driven before should get the selectors and the
way to a screen right on the first run, without a `dump` per screen to explore and without a
20 s selector timeout per wrong guess (the dominant failure in the 63 sessions measured on
2026-10-12). The tool records what it already reads during normal runs into a per-app map and
prints it on request.

Success means:

- After one session that walked Settings → General → About on a Simulator or an iPhone,
  `fastUIMap com.apple.Preferences --find About` prints the About row with its element type and
  the steps from launch that reach it.
- In a before/after test like the 1.2.0 SKILL.md test, an agent given the map writes a passing
  flow for a screen it has not dumped in that session, with fewer tool calls than without it.
- Recording adds under 50 ms to a Simulator run, and under 10 KB to the response of a
  single-action `do`.

## Decisions already made

- The map helps the agent write flows. It is not used to tap faster: no cached coordinates.
- Recording is passive: only what `do` and flow runs read anyway. No background crawl, no extra
  tree read, no extra tap. Shared iPhones and analytics in apps under test rule a crawl out.
- One map per bundle id on this Mac, shared by Simulator and iPhone runs:
  `~/Library/Caches/fast-ui-map/<bundle id>.json`. Never in a repo or an artifacts folder.
  A cache folder can be emptied by cleaners; the map is a hint and refills from later runs.
- On by default; `FAST_UI_MAP=0` turns it off in both launchers.

## What a run records: the trail

Each run builds a trail beside its normal work:

```json
[{"screen": {"app": "com.apple.Preferences", "title": "Settings", "nodes": [{"label": "General", "type": "Cell"}]}},
 {"gesture": {"type": "tap_label", "label": "General"}},
 {"screen": {"app": "com.apple.Preferences", "title": "General", "nodes": ["…"]}}]
```

### Where reads and gestures are captured

- **Reads**: every tree read of the flow's own polling goes through `hierarchy()` in
  `fast_ui.py` and `snapshotNodes()` in the device runner. The trail keeps only the latest read
  since the last recorded gesture, not every poll of a `wait`.
- **Gestures** are recorded at the action level (`execute_action` / `execute()`), **after the
  action returned without an error**, never from the low-level helpers (`tap_point`, `swipe`,
  `tap()`): those also run for prompt dismissal inside `wait_nodes`, for the inner swipes of
  `scroll_to` and for the dismiss taps of `tap_nearest`, none of which is a step of the flow.
  - A selector action that timed out or raised records nothing, so a wrong selector never
    becomes an edge.
  - `tap_label` with `optional: true` that found no target records nothing.
  - `tap_nearest` records its `target` and `anchor` selectors; `scroll_to` records itself once.
- When a gesture is recorded, the latest read (if any) is appended as a screen entry, then the
  gesture. At the end of a request or flow, the latest read is appended if it is newer than
  the last entry. A read equal to the previous screen entry is not appended again.

### What is recorded

- **Gesture kinds**: `tap_label`, `tap_first`, `tap_nearest`, `tap_point`, `long_press`,
  `swipe`, `scroll_to`, `type_text`, `launch`, `activate`, `terminate`, `open_url`. Kept keys:
  `type`, the selector keys (`label`, `label_contains`, `id`, `element_type`, and `target` /
  `anchor` for `tap_nearest`), `x`/`y`, `direction`. Never the `text` of `type_text`, never
  `launch_arguments`.
- **Freshness**: a gesture with no tree read since the previous gesture (a `tap_point` right after
  a `swipe`) is recorded with `"from": null`; it makes no edge.
- **Device requests in a row**: the runner keeps the last screen entry of the previous request
  (it already reads the tree at the end of every `do`) and uses it as the starting read of the
  next request if it is under 2 minutes old. A `do` that is a single `tap_point`, `swipe` or
  `type_text` then still gets an edge. A flow request starts clean.
- **Flows** start with a `launch` gesture (`activate` when `setup.launch` is false), so the first
  screen of a flow is an entry point of the app.
- **End of a PASS flow**: neither engine reads the tree after the last action today, and the
  map adds no read. A flow whose last gesture is followed by no read (a `tap_label` then a
  `screenshot`) loses that last edge. A `do`, the way an agent explores, always ends with a read.
- **Nodes**: `label`, `type`, `id` of on-screen nodes that can be a selector.
  - On screen: the device uses its existing `isOnScreen` (centre on screen, inside its cell).
    The Simulator keeps nodes with a non-zero frame whose centre lies inside the
    `Application` frame; `dump` keeps writing every node, as now.
  - Kept: any node with an `id`; `Button`, `Cell`, `Switch`, `RadioButton`, `Tab`, `Link`,
    `TextField`, `SecureTextField`, `TextView`, `Slider`, `Heading`, `StaticText` with a label.
  - Dropped: `value` (field text, switch state), frames, `Other` / `Image` / `Group` without an
    `id` (keyboard keys, decoration), labels that are only digits, times or punctuation,
    scroll-bar labels, `StaticText` longer than 40 characters (message bodies, descriptions).
  - Another label longer than 40 characters is stored cut to 40 as `label_contains`, which is a
    valid selector key.
  - At most 150 nodes per screen, interactive types first.
- **Title**: the navigation title when there is one. Device: the `NavigationBar` element's
  identifier, else its label, read from the snapshot's element type (`dump` and selector types
  do not change). Simulator: the top-most `Heading` whose frame starts in the top 20 % of the
  screen. The first implementation step checks this on a Settings dump on both engines; if AXe
  reports no `Heading` there, the Simulator records no title.

### Which app a read belongs to

- **Device**: the runner snapshots its `current` app, so a read belongs to the bundle id the
  runner made current. `XCUIApplication` exposes no bundle id, so the runner keeps it beside
  `current` (it already keys `apps` by bundle id).
- **Simulator**: `describe-ui` returns whatever is in front, and only the `Application` node's
  display name says which app that is. The engine stores that name from the first read after
  the flow's launch and drops reads whose `Application` label differs (Safari, SpringBoard after
  a `terminate`). A gesture whose next kept read is in another app makes no edge.
- **No cross-app edges in this version.** On the device, reads under `"app": "<other bundle id>"`
  go to that app's map as plain screens.

### Transport

- Simulator: `fast_ui.py` keeps the trail in the process and merges it at the end of `main()`,
  after the PASS/FAIL payload is built, inside `except Exception`, and only when the flow got past
  `prepare` (never for `--build-only`). On FAIL it uses the read the engine already takes for
  `failure-ui.json`.
- iPhone, persistent runner: every response carries `"trail"` beside `labels`, from all return
  paths of `handle()`, `runActions()` and `runFlow()`, PASS and FAIL.
- iPhone, one-shot: the trail goes into `zz_result.json` with the report.
- `fast_device.py` merges the trail after `flow` and `do`, before it prints the PASS/FAIL line.
- The runner caps a trail at 50 entries per request and keeps the last 50.
- An old runner without `"trail"` records nothing; no error.

## Which screen is it

The launcher merges each screen entry into the map of its app.

1. **Tokens.** `id:<id>` for nodes with an id; `<label>` for interactive nodes (every kept type
   except `StaticText` and `Heading`). Types are not part of a token, so a Simulator `Group` and
   a device `Other` with the same id, or one engine's `Button` and the other's `RadioButton`,
   agree. An observation with no tokens uses its `StaticText` labels instead; one with neither
   is not recorded (a loading screen).
2. **Match**, against the screens of the same app:
   - Both have a title: only screens with the same title compete; best Jaccard of tokens, at
     least 0.3.
   - Both have at least three `id:` tokens: Jaccard of the `id:` tokens only, at least 0.5 (a
     feed or inbox whose rows are data but whose controls carry ids).
   - Otherwise: best Jaccard of all tokens, at least 0.6.
   - A `swipe` or `scroll_to` edge whose destination has the same title as its origin, or no
     title on either side, merges the destination into the origin: scrolling a list does not
     make a new screen.
   - No match makes a new screen.
3. **Merge.** A matched screen takes the union of nodes (type kept per engine), `last_seen`
   becomes now, `seen` goes up by one.
4. **Name.** The title; else the first `id`; else the first interactive label; shown with a short
   stable key (`s12`) that `--screen` takes.

Known limits, accepted for a first version and visible in the output (`seen`, `last_seen`):

- Two screens with most controls in common and no title (two steps of a wizard) can merge.
- A node removed from the app stays in its screen until the screen ages out.
- The map is a hint. Flows still verify; a stale entry costs one failed run, as today.

## The map file

```json
{"version": 1, "app": "com.apple.Preferences", "updated": "2026-10-26T14:12:00Z",
 "screens": {"s1": {"title": "Settings", "first_seen": "…", "last_seen": "…", "seen": 4,
                    "entry": true,
                    "nodes": [{"label": "General", "types": {"simulator": "Cell", "device": "Cell"}}]}},
 "edges": [{"from": "s1", "gesture": {"type": "tap_label", "label": "General"},
            "to": "s2", "last_seen": "…", "count": 3}]}
```

- An edge is keyed by `from` and the gesture; a later run that lands elsewhere replaces `to`.
- `entry: true` marks screens seen first after a `launch` or `activate`.
- Read, merge and write all happen under an exclusive `flock` on `<bundle id>.json.lock`; the
  write goes to a temp file and replaces the map with `os.replace`. Parallel Simulator runs
  neither lose updates nor corrupt the file.
- On each write: screens not seen for 60 days and their edges are dropped; at most 400 screens
  per app, least recently seen first.
- Size: a stored node is about 60–90 bytes, so a screen is roughly 1–12 KB (a Settings screen
  has up to ~150 on-screen nodes before filtering) and a full map a few MB at most.
- A file that fails to parse is renamed `<bundle id>.json.bad` and a new map starts.

## How an agent uses it: `fastUIMap`

A new launcher, installed like `fastUIReport`. Output is compact text, one line per item,
because it lands in the agent's context.

- `fastUIMap`: every app with a map, its screen count, size, last update and file path.
- `fastUIMap <bundle id>`: one line per screen with key, name, `seen`, `last_seen`, the first
  interactive labels, and the shortest known path from an entry screen (breadth-first over
  edges, cycles skipped, at most 6 gestures), as gestures ready to paste into a flow.
- `fastUIMap <bundle id> --find <text>`: nodes whose label or id contains the text, case
  insensitive: a selector JSON with the element type per engine, the screen, and the path.
- `fastUIMap <bundle id> --screen <key>`: every node of one screen.
- `fastUIMap clear <bundle id>` / `fastUIMap clear --all`: delete maps.
- A bundle id with no map prints `MAP none app=<bundle id>` and exits 0.

SKILL.md gets three lines: before exploring an app with `dump`, run `fastUIMap <bundle id>
--find <label>`; the map is a hint from earlier runs and may be stale; maps live in
`~/Library/Caches/fast-ui-map/`, hold on-screen labels that can include user data, and are
never copied into a repo, PR or ticket.

## Errors

- Recording or merging never changes PASS/FAIL or the exit code. A failure prints one line on
  stderr, `map=not-saved (<reason>)`, and the run goes on.

## Code layout

- `scripts/fast_ui_map.py` (new): tokens, filters, matching, merge, prune, file I/O with the
  lock, rendering, and the `fastUIMap` CLI. Pure functions apart from the file I/O and the CLI.
- `scripts/fast_ui.py`: a trail object beside `_HIERARCHY_CACHE`; `hierarchy()` reports reads,
  `execute_action` reports successful gestures; merge at the end of `main()`.
- `device-runner/UITests/Trail.swift` (new, pure, its own value types, no reference to
  `FlowRunner.Node` or XCTest): reads, gestures, freshness, dedupe, carry-over, cap. Compiled by
  `RunnerLogicTests` with the other pure files. `FlowRunner.swift` feeds it from
  `snapshotNodes()` and `execute()`, tracks the current bundle id and returns the trail on
  every response path.
- `scripts/fast_device.py`: merge `trail` from responses and one-shot reports; honour
  `FAST_UI_MAP=0`.
- `install.sh`, `make-zip.sh`, README, GUIDE, SKILL.md, CHANGELOG.

## Testing

- `test_fast_ui_map.py`: tokens and filters (40-character rules, noise labels); matching with
  and without titles, the id-only rule, thresholds, cross-engine types; the scroll self-merge;
  merge and edge replacement; prune by age and count; lock, read-modify-write and atomic write;
  a corrupt file; index paths with a cycle in the edges; `--find`, `--screen`, `clear`, and a
  missing map.
- `test_fast_ui.py` with mocked `axe`: a Simulator flow produces the expected trail (polls
  collapsed, prompt taps and `scroll_to`'s inner swipes not recorded, `from: null` after a
  read-less gesture, a timed-out selector records no gesture, reads of another `Application`
  dropped, the failure read on FAIL); `FAST_UI_MAP=0` writes nothing; a merge error leaves PASS
  and the exit code untouched; `--build-only` records nothing.
- `RunnerLogicTests` (swiftc): `Trail` freshness, dedupe, carry-over and its age limit, the cap.
- Launcher tests: `do` and flow merge a response `trail`; a response without one is fine;
  `FAST_UI_MAP=0` on the device launcher.
- On hardware, after the unit tests and with the user's go-ahead for each device: one Simulator
  session in Settings and one `do` session on an iPhone the user names, including one failing
  `do`; then `fastUIMap com.apple.Preferences --find About`.

## Out of scope

Tapping from cached coordinates, sharing maps through a repo, cross-app edges, app version
tracking, per-node expiry, per-screen screenshots, and any crawl.
