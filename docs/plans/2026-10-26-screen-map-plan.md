# Screen map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record a per-app screen map passively from Simulator and iPhone runs and print it with `fastUIMap`, so an agent writes flows right the first time.

**Architecture:** Each engine builds a *trail* (screen reads and successful gestures) beside its normal work; `scripts/fast_ui_map.py` merges trails into `~/Library/Caches/fast-ui-map/<bundle id>.json` under a lock and renders the map. The device runner builds its trail in a pure `Trail.swift` and returns it in every response.

**Tech Stack:** Python 3 stdlib (`fcntl`, `json`, `unittest`), Swift/XCUITest, AXe.

**Spec:** `docs/plans/2026-10-26-screen-map-design.md`

## Global Constraints

- Passive only: no extra tree read, no extra tap, no crawl.
- Map path `~/Library/Caches/fast-ui-map/<bundle id>.json`; `FAST_UI_MAP=0` disables recording in both launchers; `FAST_UI_MAP_DIR` overrides the folder (tests).
- Recording never changes PASS/FAIL or the exit code; a failure prints `map=not-saved (<reason>)` on stderr.
- Engines are named `simulator` and `device` in node `types`.
- Thresholds: title match Jaccard ≥ 0.3; id-only match ≥ 0.5 when both sides have ≥ 3 `id:` tokens; otherwise ≥ 0.6. StaticText > 40 chars dropped; other labels > 40 chars stored cut to 40 as `label_contains`; ≤ 150 nodes per screen, interactive first; screens unseen 60 days dropped; ≤ 400 screens per app; device trail ≤ 50 entries; device carry-over ≤ 120 s; BFS path ≤ 6 gestures; Simulator title = top-most `Heading` starting in the top 20 % of the `Application` frame.
- The repo is public: no company app names, UDIDs or user data in code, tests or docs (generic examples: Settings, `com.example.app`).
- No commits during the tasks; the user decides when to commit and push.

## Review Focus

- A label that contains user data longer than 40 characters (a message preview in a Button) is stored only as a 40-character `label_contains`, never whole. → Task 1 test `test_long_interactive_label_becomes_label_contains`.
- Two parallel Simulator runs merging into the same map both survive. → Task 2 test `test_two_records_on_one_app_keep_both_screens`.
- A map file someone edited by hand into invalid JSON does not stop a run and is kept aside. → Task 2 test `test_corrupt_map_is_renamed_bad_and_restarted`.
- A Simulator flow that leaves the app (opens Safari) does not file Safari's screens under the app. → Task 4 test `test_reads_of_another_app_break_the_trail`.
- An old device runner without `trail` in its response does not break `do`. → Task 6 test `test_do_without_trail_records_nothing`.

---

### Task 1: Node filtering, tokens and matching (`fast_ui_map.py`, pure)

**Files:**
- Create: `scripts/fast_ui_map.py`
- Create: `scripts/test_fast_ui_map.py`

**Interfaces:**
- Produces:
  - `KEPT_TYPES: frozenset[str]` = `Button, Cell, Switch, RadioButton, Tab, Link, TextField, SecureTextField, TextView, Slider, Heading, StaticText`; `INTERACTIVE = KEPT_TYPES - {"StaticText", "Heading"}`.
  - `normalize_nodes(nodes: list[dict]) -> list[dict]` — input `{"label","type","id"}` (missing keys allowed), output `{"label"|"label_contains", "type", "id"?}` after the spec's rules, deduped on `(label|label_contains, id)`, interactive first, ≤ 150.
  - `simulator_screen(nodes: list[dict]) -> tuple[str, str, list[dict]]` — AXe flattened nodes (`AXLabel`, `type`, `AXUniqueId`, `frame`) → `(application_label, title, nodes in the input format of normalize_nodes)`, keeping nodes with non-zero frame whose centre is inside the `Application` frame.
  - `tokens(nodes: list[dict]) -> set[str]` — `id:<id>` and interactive labels; falls back to StaticText labels; empty set for neither.
  - `match(screens: dict[str, dict], title: str, nodes: list[dict]) -> str | None` — key of the best screen per the three rules, or `None`.
  - `kept_gesture(action: dict) -> dict` — `type` plus `label, label_contains, id, element_type, target, anchor, x, y, direction` when present.

- [ ] **Step 1: Write the failing tests** in `test_fast_ui_map.py` (`unittest`, style of `test_fast_ui.py`):
  - `test_normalize_drops_noise_and_decoration`: input has `{"label":"12:41","type":"StaticText"}`, `{"label":"Vertical scroll bar, 2 pages","type":"Other"}`, `{"label":"q","type":"Other"}`, `{"type":"Image"}`, `{"label":"General","type":"Cell","id":""}`, `{"type":"Other","id":"close"}` → output is exactly `[{"label":"General","type":"Cell"}, {"type":"Other","id":"close"}]` in that order.
  - `test_long_static_text_is_dropped`: a 41-char StaticText → `[]`.
  - `test_long_interactive_label_becomes_label_contains`: Button label of 60 chars → `[{"label_contains": label[:40], "type":"Button"}]`.
  - `test_nodes_are_capped_interactive_first`: 200 StaticText + 10 Buttons → 150 nodes, first 10 are the Buttons.
  - `test_simulator_screen_keeps_on_screen_nodes_and_heading_title`: Application `{"AXLabel":"Settings","type":"Application","frame":{x0 y0 w400 h800}}`, Heading `General` at y 40, Heading `About` at y 300 (section header), Button `Off` at x 500 (off screen), Button `About` at y 300 → `("Settings", "General", [...About button, About heading...])` without `Off`.
  - `test_tokens_ignore_types_and_fall_back_to_text`: `[{"label":"Go","type":"Button"},{"id":"x","type":"Group"}]` → `{"Go","id:x"}`; a StaticText-only screen → its labels; `[]` → `set()`.
  - `test_match_with_title_needs_same_title`, `test_match_by_ids_only_on_data_screens` (two screens sharing 3 of 4 ids but no common labels → match), `test_match_without_title_needs_0_6` (5 of 8 tokens shared → no match; 6 of 8 → match), `test_match_crosses_engine_types` (`Button "Lyrics"` vs `RadioButton "Lyrics"` → match).
  - `test_kept_gesture_never_keeps_text`: `{"type":"type_text","text":"secret"}` → `{"type":"type_text"}`; `tap_nearest` keeps `target` and `anchor`; `launch` drops `launch_arguments`.

- [ ] **Step 2:** Run `cd scripts && python3 -m unittest test_fast_ui_map -v` — expect errors: `No module named 'fast_ui_map'`.
- [ ] **Step 3:** Implement the five functions in `scripts/fast_ui_map.py`. Noise patterns: reuse the definitions of `NOISE_LABEL` and `SCROLL_BAR_LABEL` from `fast_ui.py` by copying them here and importing them back into `fast_ui.py` from `fast_ui_map` (one definition). Jaccard = `len(a & b) / len(a | b)`, 0 when both empty.
- [ ] **Step 4:** Run the same command — all pass; run `python3 -m unittest discover -s scripts -p 'test_*.py'` — all pass.

### Task 2: Merge, prune and the locked map file

**Files:**
- Modify: `scripts/fast_ui_map.py`
- Modify: `scripts/test_fast_ui_map.py`

**Interfaces:**
- Consumes: Task 1.
- Produces:
  - Trail entry shapes (both engines): `{"screen": {"app": str, "title": str, "nodes": [...]}}`, `{"gesture": dict}` with optional `"from": None`, `{"break": True}`.
  - `merge_trail(maps: dict[str, dict], trail: list[dict], engine: str, now: datetime) -> None` — mutates one map per app in `maps` (created as `new_map(app)` when absent); only apps already in `maps` are written to.
  - `prune(map_: dict, now: datetime) -> None`.
  - `map_dir() -> Path` (`FAST_UI_MAP_DIR` or `~/Library/Caches/fast-ui-map`).
  - `record(trail: list[dict], engine: str, now: datetime | None = None) -> None` — for each app in the trail, in sorted order and one at a time: `flock` `<app>.json.lock`, load (corrupt → rename `.json.bad`, start new), `merge_trail({app: map}, …)`, `prune`, write temp + `os.replace`, unlock. Does nothing when `FAST_UI_MAP=0` or the trail is empty.

Merge algorithm (the part the tests do not fully determine):

```
prev = None        # (app, key) of the last merged screen
pending = None     # (from_key or None, gesture)
entry_next = False
for e in trail:
    "break"   -> prev = pending = None
    "gesture" -> from_key = prev if "from" not in e else None
                 pending = (from_key, e["gesture"])
                 entry_next = e["gesture"]["type"] in ("launch", "activate")
    "screen"  -> nodes = normalize_nodes(...); if not tokens(nodes): prev = pending = None; continue
                 app not in maps            -> prev = pending = None; continue (another app's map handles it)
                 if pending and pending.from_key and pending.from_key.app == app
                    and gesture type in (swipe, scroll_to)
                    and (same title or both titles empty): key = pending.from_key.key
                 else: key = match(...) or new key "s<next_key>"
                 union nodes (types[engine] = type), last_seen = now, seen += 1, first_seen once,
                 title kept if empty before; entry = True if entry_next
                 if pending and pending.from_key and same app and key != from key:
                     upsert edge keyed by (from, json.dumps(gesture, sort_keys=True)): to, last_seen, count += 1
                 prev = (app, key); pending = None; entry_next = False
```

- [ ] **Step 1: Write the failing tests:**
  - `test_merge_builds_screens_edges_and_entry`: trail `launch, screen Settings, tap_label General, screen General` → 2 screens, `s1.entry is True`, one edge `s1 → s2` with gesture `{"type":"tap_label","label":"General"}`, `count == 1`.
  - `test_same_edge_twice_counts_and_later_landing_replaces_to`.
  - `test_gesture_without_fresh_read_makes_no_edge`: `{"gesture": {...}, "from": None}` between two screens → no edge.
  - `test_scroll_merges_into_origin`: `screen List(title "Settings", tokens A–F), swipe up, screen (title "Settings", tokens G–L)` → one screen with the union, no edge.
  - `test_break_and_screen_without_tokens_cut_edges`.
  - `test_other_app_screen_is_not_written_and_cuts_edge`: maps has only `com.example.app`; a springboard screen between two app screens → no edge.
  - `test_prune_drops_old_screens_and_their_edges` (61 days) and `test_prune_keeps_400_most_recent`.
  - `test_record_writes_atomically_under_lock` (uses `FAST_UI_MAP_DIR` temp dir; file content round-trips; a `.lock` file exists).
  - `test_two_records_on_one_app_keep_both_screens`: two `record` calls from two `multiprocessing` processes with different screens → both screens in the file.
  - `test_corrupt_map_is_renamed_bad_and_restarted`.
  - `test_record_is_off_with_fast_ui_map_0`.
- [ ] **Step 2:** Run `cd scripts && python3 -m unittest test_fast_ui_map -v` — new tests fail with `AttributeError`.
- [ ] **Step 3:** Implement `new_map`, `merge_trail`, `prune`, `map_dir`, `record` in `fast_ui_map.py` (map shape per the spec's "The map file"; timestamps ISO-8601 UTC with `Z`).
- [ ] **Step 4:** Run the module tests and the whole suite — all pass.

### Task 3: The `fastUIMap` CLI

**Files:**
- Modify: `scripts/fast_ui_map.py` (`main()`, `if __name__ == "__main__"`, the `sys.path` preamble of `fast_ui.py` so a copied launcher works)
- Create: `bin/fastUIMap` (symlink `../scripts/fast_ui_map.py`)
- Modify: `install.sh` (link + chmod), `scripts/test_fast_media.py` (`LauncherCopyTests` gains `"fastUIMap": "fast_ui_map.py"`)
- Test: `scripts/test_fast_ui_map.py`

**Interfaces:**
- Consumes: Task 2 map shape, `map_dir()`.
- Produces: `main(argv: list[str] | None = None) -> int`; `shortest_paths(map_: dict) -> dict[str, list[dict]]` (BFS from entry screens over edges, cycles skipped, ≤ 6 gestures; entry screens map to `[]`).

Output lines (exact prefixes):
- `fastUIMap` → `MAP app=<id> screens=<n> size=<k>K updated=<YYYY-MM-DD> path=<file link>` per map, or `MAP none dir=<file link>`.
- `fastUIMap <id>` → header `MAP app=<id> screens=<n> edges=<m> updated=<date> path=<link>`, then per screen `s3 "General" seen=4 last=2026-10-26 labels=[About, Software Update] path=[{"type":"tap_label","label":"General"}]` (`path=entry` for entry screens, `path=unknown` when unreachable; at most 8 labels).
- `--find <text>` → per match `s5 "About" select={"label":"About"} types=simulator:Button,device:Cell path=[…]` (`select` uses `id` when the node has one, else `label`, else `label_contains`); none → `FIND none text=<text>`.
- `--screen <key>` → header then one line per node `label=<…> id=<…> types=<…>`.
- `clear <id>` → `CLEARED app=<id>`; `clear --all` → `CLEARED apps=<n>`.
- Missing map → `MAP none app=<id>`, exit 0. File links via the same `file://` helper the other launchers use (copy `file_link` from `fast_ui.py` or import it).

- [ ] **Step 1: Write the failing tests:** `test_cli_lists_maps`, `test_cli_index_shows_paths_from_entry` (map with a cycle s1→s2→s1 and s2→s3: s3 path is two gestures, no hang), `test_cli_find_prints_selector_types_and_path`, `test_cli_screen_lists_nodes`, `test_cli_clear_one_and_all`, `test_cli_missing_map_is_not_an_error`; each calls `fast_ui_map.main([...])` with stdout captured and `FAST_UI_MAP_DIR` set.
- [ ] **Step 2:** Run module tests — new ones fail.
- [ ] **Step 3:** Implement `shortest_paths` and `main` (argparse; `clear` as the first positional word).
- [ ] **Step 4:** Create the symlink, extend `install.sh` (`link "$HERE/scripts/fast_ui_map.py" "$BIN_DIR/fastUIMap"`, add to `chmod` and to the `--check` loop of launchers), extend `LauncherCopyTests`. Run the whole suite — all pass; run `bin/fastUIMap` with `FAST_UI_MAP_DIR` pointing to an empty temp folder → `MAP none dir=…`.

### Task 4: Simulator trail

**Files:**
- Modify: `scripts/fast_ui_map.py` (`Trail` class for the Simulator)
- Modify: `scripts/fast_ui.py` — `hierarchy()` (report reads), `execute_action` (report gestures), `run_action` optional `tap_label` miss, `main()` (create trail, launch gesture, merge at the end)
- Test: `scripts/test_fast_ui.py`

**Interfaces:**
- Consumes: `simulator_screen`, `kept_gesture`, `record`.
- Produces:
  - `class Trail:` `__init__(self, bundle_id: str)`, `read(self, nodes: list[dict]) -> None`, `gesture(self, action: dict) -> None`, `finish(self) -> list[dict]`. Semantics: keeps only the latest read; `gesture` flushes it (screen entry, or `{"break": True}` when its Application label differs from the one captured from the first read after a `launch`/`activate`, deduped against the previous screen entry) and appends the gesture with `"from": None` when no read happened since the previous gesture; `finish` flushes once.
  - `fast_ui.TRAIL: Trail | None` module global; `hierarchy()` calls `TRAIL.read(nodes)` on every fresh describe-ui (not on cache hits).
  - `TRAIL_GESTURES = {"tap_label","tap_first","tap_nearest","tap_point","long_press","swipe","scroll_to","type_text","launch","activate","terminate","open_url"}`.
  - `run_action` returns `{"optional_missing": True}` when an optional `tap_label` finds no target.

- [ ] **Step 1: Write the failing tests** (mock `axe`/`hierarchy` as the existing tests do; set `fast_ui.TRAIL = fast_ui_map.Trail("com.example.app")`):
  - `test_trail_keeps_the_read_before_each_gesture`: hierarchy returns screen A three times (a polling `wait`), then `tap_label` → trail is `[screen A, gesture tap_label]`, one screen entry.
  - `test_trail_skips_prompt_taps_and_scroll_inner_swipes`: a prompt in the first poll is tapped via `tap_point`; `scroll_to` swipes twice → trail gestures are exactly `tap_label`, `scroll_to`.
  - `test_trail_marks_gesture_without_read`: `tap_label` then `tap_point` → second gesture has `"from": None`.
  - `test_timed_out_selector_records_no_gesture`.
  - `test_optional_tap_label_without_target_records_no_gesture`.
  - `test_reads_of_another_app_break_the_trail`: first read after launch has Application `Demo`, a later read has `Safari` → `{"break": True}` entry, no Safari screen.
  - `test_flow_merges_trail_and_keeps_pass` (patch `fast_ui_map.record` to raise → stdout still `PASS`, exit 0, stderr has `map=not-saved`); `test_build_only_and_fast_ui_map_0_record_nothing`.
- [ ] **Step 2:** Run `cd scripts && python3 -m unittest test_fast_ui -v -k trail` and the two flow tests — fail.
- [ ] **Step 3:** Implement `Trail` and the hooks. In `main()`: `TRAIL = Trail(bundle_id)` unless `FAST_UI_MAP=0`; `TRAIL.gesture({"type": "launch"})` right before the simctl launch; after the PASS/FAIL line is printed (both branches) and only if `current_step != "prepare"` and not `--build-only`: `try: record(TRAIL.finish(), "simulator") except Exception as error: print(f"map=not-saved ({error})", file=sys.stderr)`. The FAIL branch's existing `hierarchy(udid)` read becomes the last screen automatically.
- [ ] **Step 4:** Run the whole suite — all pass. Time `Trail.read` + `finish` + `record` on a 600-node fixture with `time.perf_counter()` in a test: assert < 0.05 s.

### Task 5: Device runner trail (`Trail.swift`)

**Files:**
- Create: `device-runner/UITests/Trail.swift`
- Modify: `device-runner/UITests/FlowRunner.swift`, `device-runner/FastDeviceRunner.xcodeproj` (regenerate with `xcodegen generate --quiet` in `device-runner/`)
- Modify: `scripts/runner_logic_checks.swift`, `scripts/test_fast_ui.py` (`RunnerLogicTests` compiles `Trail.swift` too)

**Interfaces:**
- Produces:
  - `struct TrailNode { let label: String; let type: String; let id: String }`
  - `struct Trail` with `static let keptTypes: Set<String>` (the device names of `KEPT_TYPES`), `static let gestureKinds: Set<String>` (= `TRAIL_GESTURES`), `static let maxEntries = 50`, `static let carryAge = 120.0`;
    `mutating func start(carry: Bool, now: Double)`, `mutating func read(app: String, title: String, nodes: [TrailNode], now: Double)`, `mutating func gesture(_ action: [String: Any])`, `mutating func finish() -> [[String: Any]]`.
    Same semantics as the Python `Trail` (latest read only, flush on gesture, `"from": NSNull()` when stale, dedupe, keep the last 50); `start(carry: true)` keeps the last screen entry of the previous request as the latest read when it is younger than `carryAge`; nodes filtered to `!id.isEmpty || keptTypes.contains(type)` with a non-empty label or id. Gesture keys as `kept_gesture`.
  - `FlowRunner`: `currentBundleID: String` set wherever `current` is set (a helper `use(_ bundleID: String)`); `snapshotNodes()` passes on-screen nodes (`isOnScreen`) and the title (first `.navigationBar` snapshot: identifier, else label) to `trail.read`; `execute()` calls the existing body (renamed `perform`) and then `trail.gesture(action)` when it returned without throwing, the kind is a gesture and the result is not `optional_missing`; `tap_label` optional miss returns `["optional_missing": true]`.
  - `handle()`: `trail.start(carry: operation != "flow", now:)`; `runFlow` records `launch`/`activate` before the first action; `testServe` adds `response["trail"] = trail.finish()`; `testFlow` adds `report["trail"]`.

- [ ] **Step 1: Write the failing checks** in `runner_logic_checks.swift` (same style as the PromptRules/Settle checks): latest read only; gesture flushes; stale gesture gets `from` null; dedupe; `text` dropped from `type_text`; cap keeps the last 50; carry-over used at 119 s, dropped at 121 s; nodes filtered by type/id.
- [ ] **Step 2:** Run `cd scripts && python3 -m unittest test_fast_ui -k RunnerLogic` — fails (Trail not found / not compiled).
- [ ] **Step 3:** Implement `Trail.swift`; add it to the `swiftc` file list in `RunnerLogicTests`; wire `FlowRunner.swift`; regenerate the project.
- [ ] **Step 4:** Run the logic checks — pass. Compile the runner: `xcodebuild build-for-testing -project device-runner/FastDeviceRunner.xcodeproj -scheme FastDevice -destination generic/platform=iOS -derivedDataPath <scratch>/dd CODE_SIGNING_ALLOWED=NO > <scratch>/build.log 2>&1; echo exit=$?` → `exit=0`, no `error:`.

### Task 6: Device launcher merge, docs and changelog

**Files:**
- Modify: `scripts/fast_device.py` (`run_flow`, `run_command` `do`)
- Modify: `skills/fast-ios-device-test/SKILL.md`, `references/usage.md`, `references/device.md`, `README.md`, `GUIDE.md` (launcher lists), `CHANGELOG.md`
- Test: `scripts/test_fast_ui.py` (`DeviceLauncherTests`, using its `run_do` helper)

**Interfaces:**
- Consumes: `record`.
- Produces: `save_trail(report: dict) -> None` in `fast_device.py`: `record(report.get("trail") or [], "device")` inside `try/except Exception` → `map=not-saved (<reason>)` on stderr; called in `run_flow` and `do` before the PASS/FAIL line.

- [ ] **Step 1: Write the failing tests:** `test_do_records_the_response_trail` (fake response with a trail → `record` called with it and `"device"`), `test_do_without_trail_records_nothing` (no `trail` key → PASS line unchanged, no stderr warning), `test_flow_records_the_report_trail`, `test_record_error_keeps_the_pass_line`.
- [ ] **Step 2:** Run them — fail.
- [ ] **Step 3:** Implement `save_trail` and the two calls.
- [ ] **Step 4:** Docs: SKILL.md gets the three lines from the spec; usage.md a short "Screen map" section (what is recorded, `fastUIMap` commands, `FAST_UI_MAP=0`, privacy line); device.md one bullet (trail travels in the response; a running `serve` needs `stop` to pick it up); README/GUIDE launcher lists; CHANGELOG `### Screen map` under Unreleased. Run the whole suite — all pass. Scan the diff and the new files for private app names, UDIDs and user data with the maintainer's private-name list → nothing.

### Task 7: Hardware check (asks the user first)

- [ ] **Step 1:** Ask the user for a Simulator that Xcode is not using and for the iPhone; a yes covers that run only.
- [ ] **Step 2:** Simulator: a prebuilt flow on `com.apple.Preferences`: launch, `tap_label` General, `wait` About, `tap_label` About, `wait` Name. Then `fastUIMap com.apple.Preferences --find About` → a line with `select=` and a path starting with `tap_label General`.
- [ ] **Step 3:** iPhone: `serve`, then `do` steps Settings → General → About one request at a time, one deliberately failing `do` (`tap_label` a missing label), `stop`. `fastUIMap com.apple.Preferences` shows both engines' types on the General screen and the failing `do` added no edge. Confirm the device title came from the NavigationBar (`"General"`).
- [ ] **Step 4:** Report to the user with the outputs; commit and push only when they say so.
