# SDD ledger — plan: docs/plans/2026-10-12-optimization-plan.md
Setup: no worktree; branch optimize-1.2.0 created in place because ~/.claude symlinks point at this folder and the plan's real-run steps use the live launchers. Ruling: work in place on branch optimize-1.2.0 — the live install is the only place real-run steps can execute — cost if wrong: a broken intermediate commit affects the live tool until fixed (backup zip exists).
Ruling: plan task ids renumbered 1..16 (A1..D3 kept in titles) — task-brief script matches numeric headings only — cost if wrong: none.
Pre-flight: A2 selector_of → A4 resolve_tap_target(selector) consistent; A3 FastUIError.nodes not consumed by A4 (predicate-based) ok; A5 hierarchy(max_age)/invalidate_hierarchy → A6 wait_settled and A7 lifecycle actions consistent; A6 execute_action(defaults) → A7 positional {} then bundle_id consistent; A8 prepare_app Optional path → main consistent; B2 Swift mirrors A2/A4 selector keys; D2 build_runner skips xcodegen when xcodeproj committed.
Task 0: complete (commits 0412303..429c5ac, tests: python3 -m unittest test_fast_ui test_fast_ui_review → Ran 53 tests OK)
Task 1: complete (commits 429c5ac..b39ac91, tests: python3 -m unittest test_fast_ui test_fast_ui_review → OK)
Task 2: complete (commits b39ac91..9f2113a, tests: python3 -m unittest test_fast_ui test_fast_ui_review → OK)
Task 3: complete (commits 9f2113a..55ab821, tests: python3 -m unittest test_fast_ui test_fast_ui_review → OK)
Task 4: complete (commits 55ab821..39b0ced, tests: python3 -m unittest test_fast_ui test_fast_ui_review → OK)
Task 5: complete (commits 39b0ced..b2a7090, tests: python3 -m unittest test_fast_ui test_fast_ui_review → OK)
Task 6: complete (commits b2a7090..98bbba2, tests: python3 -m unittest test_fast_ui test_fast_ui_review → OK)
Task 7: complete (commits 98bbba2..1f1f5a8, tests: python3 -m unittest test_fast_ui test_fast_ui_review → OK)
Task 8: complete (commits 1f1f5a8..8e58cee, tests: python3 -m unittest test_fast_ui test_fast_ui_review → OK)
Task 8: real run: fastSimulatorTest settings-smoke.json (prebuilt com.apple.Preferences, iPhone 17e) → PASS total=70.1s, dump 166 nodes / 30 ids / 26 KB
Task 9: complete (commits 8e58cee..3b41220, tests: python3 -m unittest test_fast_ui test_fast_ui_review → OK)
Task 10: complete (commits 3b41220..13a7769, tests: python3 -m unittest test_fast_ui test_fast_ui_review → OK)
Task 11: complete (commits 13a7769..3ca41ed, tests: python3 -m unittest test_fast_ui test_fast_ui_review → OK)
Task 11: device smoke on a test iPhone (iOS 26.6.1, FAST_DEVICE_PROFILE=<uuid>): runner rebuilt+served 11.7 s; dump 71 nodes / 25 ids / 10 values; batch [launch, wait General, wait label+value, swipe up, tap_label id=com.apple.settings.general, wait About, terminate] → PASS actions=7.
Task 11: Ruling: StaticText-only fallback not exercised on device (every Settings label also has a Button) — logic mirrors Python resolve_tap_target which has unit tests — cost if wrong: a device-only fallback bug surfaces on first SwiftUI app use, fixable in one function.
Task 11: note (pre-existing): a row whose centre sits under the bottom toolbar (General at y=900) is "on screen" and the tap hits the toolbar; flows must swipe first. Not changed.
Task 12: complete (commits 3ca41ed..10dc2de, tests: python3 -m unittest test_fast_ui test_fast_ui_review → PASS wait labels=[])
Task 12: evidence: runner rebuilt with Quiescence.swift; flow with setup.wait_for_idle=false → PASS and metrics.json reports wait_for_idle=false (both private selectors found on Xcode 27.0 / iOS 26.6.1); `do --no-idle-wait` batches PASS; tap gaps on the app A paywall 0.77–0.94 s with the flag vs 0.53–1.99 s without.
Task 12: Ruling: the plan's "<1.0 s vs ~2.8 s on the dashboard" comparison was not reproduced — the DEV app re-shows its paywall after every launch so the animated dashboard was never reached in this session — accepted on the flow-level proof that the swizzle applies and nothing breaks — cost if wrong: smaller speed-up than the 2.4 s/tap estimate on animated screens; no correctness impact.
Task 13: complete (commits 10dc2de..0019eed, tests: python3 -m unittest test_fast_ui test_fast_ui_review → PASS wait labels=[])
Task 13: real check: helper_command first call 5.67 s (swiftc), second 0.000 s (cached binary), durations(widgetTutorial.mp4) via binary 2.65 s → [69.2]
Task 14: baseline (sonnet subagent, docs unchanged): did not find `prebuilt` in SKILL.md/usage.md, found it by reading fast_ui.py; wrote a correct flow (timeouts 20/8, no dump); run 1 FAIL "axe tap … Timed out creating the simulator remote automation session" (AXe session flake right after boot), run 2 PASS 11.6 s.
Task 14: Ruling: finding from baseline — AXe "Timed out creating the simulator remote automation session" on the first tap after boot is a transient; add one retry in `axe()` for that message as Task 17 after Task 16 — cost if wrong: one extra ~1 s on a genuine failure.
Ruling: Task 15 executed before Task 14 while the Task 14 baseline subagent was running — no interface between them — cost if wrong: none (commit order only).
Task 15: complete (commits 0019eed..b80e927, tests: python3 -m unittest test_fast_ui test_fast_ui_review → PASS wait labels=[])
Task 17: complete (commit acaed42, tests: python3 -m unittest test_fast_ui test_fast_ui_review → Ran 76 tests OK) — added from the Task 14 baseline finding: axe() retries once on 'automation session' errors
Task 14: complete (commits b80e927..c458d41, tests: python3 -m unittest test_fast_ui test_fast_ui_review → PASS wait labels=[])
Task 14: after-edit run (sonnet subagent, same prompt): found `prebuilt` in SKILL.md "Flow file" and quoted it, used launch + wait/tap/wait with timeouts 20/8, PASS on the first run (48.6 s incl. boot), 3 tool uses / 37.8k tokens vs baseline 8 / 42.7k.
Task 14: Ruling: commands are 158/135 words including frontmatter against the plan's ≤120 target — the remaining text is the engine command line and the shape decision, which the command must carry — cost if wrong: ~50 tokens per invocation.
Task 16: complete (commit fcc66bf, tag v1.2.0, tests: Ran 76 tests OK, zip built by make-zip.sh)
Final review: fresh reviewer (fable) on 0412303..fcc66bf — 0 Critical, 3 Important, 7 Minor; verdict "with fixes".
Final: fixed install.sh exits silently without a selected Xcode — reproduced with a failing xcodebuild shim (no output, exit 1) → `|| true` on the version pipeline → `--check` now prints xcode=missing and "CHECK missing: xcode"; normal mode prints the error line.
Final: fixed test module needs Pillow — reproduced with sys.modules['PIL']=None (ModuleNotFoundError) → Pillow import moved into the motion test under skipUnless → 65 engine tests run, 1 skipped, 0 failures without Pillow; suite 77/77 with it.
Final: fixed (re-graded Important: a wrong tap, not a FAIL) tap_label fallback onto the Application root — test_tap_label_never_falls_back_to_the_application_root RED→GREEN, suite 77/77; Swift mirrors it (Application/Window excluded, typeName now names them).
Final: fixed device fallback never firing on nested same-label containers — FlowRunner.resolveTapTarget dedupes loose candidates by rounded frame and taps the innermost; runner rebuilt; device flow fallback-probe on Settings › General: tap_label label_contains "Manage your overall" → PASS, results [{"fallback_type": "StaticText", "step": 5}]; "General" (two distinct StaticText frames) correctly stays ambiguous → FAIL.
Final: minor (deferred): docs tell prebuilt flows to start with {"type":"launch"} although the engine already launches (redundant ~0.5 s on simulator).
Final: minor (deferred): stale committed .xcodeproj builds silently when project.yml changes; warn or regenerate when xcodegen is present.
Final: minor (deferred): Quiescence.disable() allocates a new IMP trampoline per call (never freed) and handle() drops its return value, so `do --no-idle-wait` cannot report "unsupported".
Final: minor (deferred): test_do_passes_no_idle_wait_into_the_request prints PASS lines to stdout (noise in unittest output and in this ledger's "→" fields).
Final: minor (deferred): install.sh does not warn when an older axe earlier on PATH shadows the bundled one.
Final: minor (deferred): selector_hints says "add element_type" even when the selector already had one.
Final: Ruling: reviewer set aside flow-config errors (missing simulator, bad version, prebuilt+fresh_install without app_path) printing a traceback instead of a FAIL line — pre-existing behaviour for every required() check; stands — cost if wrong: an agent reads a traceback instead of one line.
Final: Ruling: reviewer set aside "settle": "true" (string) raising ValueError — malformed input, same as every numeric key; stands.
Final: Ruling: reviewer set aside two concurrent fastUIReview processes racing on swiftc — not a realistic single-Mac use; stands.
Final: Ruling: reviewer set aside the optional tap path fetching a fresh tree instead of the cache — more conservative than planned; stands.
Final: Ruling: device rows under the bottom toolbar count as on-screen — pre-existing, documented in the Task 11 note; stands.
