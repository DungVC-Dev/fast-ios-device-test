---
name: iphone-duo-swiftui
description: Adapt a SwiftUI iOS app (any deployment target) to iPhone Duo following Apple's guidance — vertical bars, fold-aware layouts, reserved regions, two-pane inner display — and verify it on the Xcode 27.1 iPhone Duo simulator through Device Hub. Use whenever a screen, view, toolbar, sheet or footer is built or changed in an app that supports iPhone Duo, and when asked to support, audit, fix, or test iPhone Duo, the outer/inner display, the fold, book/tabletop poses, or the vertical toolbar.
---

# iPhone Duo for SwiftUI apps

A field-tested workflow: audit → fix with a small set of reusable components → verify every pose on the simulator. Built from Apple's iPhone Duo HIG, the "Preparing your app for iPhone Duo" overview and talks 111461–111466 (digest in `reference/apple-guidance.md`), plus the traps hit while shipping a real TCA app.

When a Duo design uses Liquid Glass, derive its legibility, accessibility, scroll-edge, and
outer/inner-display cases with the fast test skill's
[Liquid Glass guide](../fast-ios-device-test/references/liquid-glass.md). For code changes, also
use the locally exported `apple-liquid-glass` skill when it is installed.

For code changes, also use `apple-app-resizability` when that locally exported Xcode skill is
installed. It contains Apple's current guidance and is intentionally not redistributed here.

## 0. Prerequisites

- **Xcode 27.1** (iOS 27.1 SDK). Building with an older SDK gives compatibility mode: letterboxed, no vertical bar. Keep the project buildable on the older toolchain too.
- Gate every 27.1 API with **both** `#if compiler(>=6.4)` and `if #available(iOS 27.1, *)`. The compiler check keeps the code building on Xcode 26.
- Build into a separate DerivedData so the default toolchain's cache stays intact:
  `DEVELOPER_DIR="/Applications/Xcode 27.1.app/Contents/Developer" xcodebuild build ... -derivedDataPath <scratch>/DD27`
- Simulator: **Device Hub** (`/Applications/Xcode 27.1.app/Contents/Applications/DeviceHub.app`). There is no Simulator.app for Duo. Use `fastSimulatorTest` (section 6); keep `scripts/duo-sim.sh` as the fallback.

## 1. Ground rules from Apple (do not deviate)

1. **Design to size classes, not poses.** Outer display = compact width; inner = regular. No breakpoints or per-pose layouts. The only sanctioned bespoke layout is tabletop (media up, controls down).
2. **Use container-provided bars.** Use `.toolbar` inside a `NavigationStack`/`NavigationSplitView`, plus `TabView`. Only those move into the vertical bar. Hand-built header rows, bottom bars, and standalone `UINavigationBar`/`UIToolbar` stay horizontal and fight the bar.
3. **Every bar item needs title + icon.** Use `Button("Title", systemImage:)` or `Label`. Icon-only image buttons and text-only buttons stay horizontal. Text buttons (e.g. "History") and segmented controls *may* legitimately stay horizontal.
4. **Order in the vertical bar:**
   - Back/close first, using `.cancellationAction` or `.topBarLeading`.
   - Then the prominent action: `.confirmationAction`, or `.topBarPinnedTrailing` (27.0).
   - Then the remaining groups.
   - Bottom-bar items (`ToolbarItemGroup(placement: .bottomBar)`) go to the bottom of the strip.
5. **Use layout APIs, never the hinge, for layout.**
   - Layout tools: `ArrangementView`, `GeometryProxy.reservedRegions(kind:options:)` (`.division` = fold, `.occlusion` = camera), safe areas.
   - `onHingeChange` is for effects only.
6. **The fold:**
   - Keep *fixed interactive* controls out of an **active** fold (book pose). The system does this for its own components (alerts, sheets, toolbars).
   - Scrolling content is exempt.
   - Move as little as possible.
   - Prefer even column counts.
7. **Don't put navigation containers inside an `ArrangementView`, or an arrangement inside a `List`/`ScrollView`.**
8. **Inner display: don't just stretch.** Choose one:
   - Reveal one more hierarchy level (split view).
   - Reflow into two columns.
   - Use a tab sidebar.
9. **Avoid `UIScreen.main`.** On Duo it reports the *outer* display even while the app runs on the inner one. Use the window scene or the environment.
10. **One-button sheets may opt out of the vertical bar.** A sheet whose only control is a close button can keep its in-content header. Don't convert it.

## 2. Building a new screen — decide up front

Answer these while designing the view, not afterwards:

1. **Bars.** Which actions belong in the bar?
   - Put them in `.toolbar` with title + icon: back/close, prominent action, secondary groups, and a bottom tool row as `.bottomBar`.
   - A full-screen flow needs a `NavigationStack`, including inside a `fullScreenCover`.
   - If the design draws a custom header, wrap it with `adaptiveBar` so Duo gets the system bar.
2. **Inner display.** What does the regular-width layout show?
   - Reveal one more level, reflow to two columns, or split at the fold with `FoldSplitLayout`.
   - Don't stretch a phone column across 951pt.
3. **Fixed controls.** Is anything pinned (CTA, slider, tool row)?
   - Pinned, non-scrolling controls get `.foldAvoiding()` on the control itself.
   - Scrolling strips don't.
4. **Short outer display** (≈466×678pt; ≈678×466pt in landscape). Does the screen still fit?
   - Hero art shrinks or hides before text or CTAs clip.
   - Nothing important sits under the camera (`trailingOcclusionWidth`).
5. **Width math.**
   - Use adaptive grids and size classes.
   - Read a measured width rather than assume a screen width.
   - Never use `UIScreen.main`.

Then verify as in section 6.

## 3. Audit — find what breaks

Grep the project and classify each hit:

```bash
grep -rln "toolbar(.hidden" Sources            # hand-built chrome replacing the nav bar
grep -rln "safeAreaInset(edge: .top" Sources    # custom header rows
grep -rln "safeAreaInset(edge: .bottom" Sources # footers: CTAs vs icon tool rows
grep -rln "navigationBarBackButtonHidden" Sources
grep -rln "contentMargins(.horizontal" Sources  # fixed margins that clip next to the bar
grep -rn  "UIScreen.main" Sources               # wrong screen on Duo (also inside 3rd-party SDKs)
```

| Finding | Fix |
|---|---|
| Full-screen screen (editor, camera, preview) with a custom header of icon buttons | `adaptiveBar(header:items:)` (+ `footer:` for icon tool rows) |
| Same, presented as `fullScreenCover` | Wrap the cover's content in `NavigationStack { }` first. Toolbars need a container. |
| Bottom row of icon tools (crop/filter/rotate/delete…) | `ToolbarItemGroup(placement: .bottomBar)` via `adaptiveBar(footer:)` |
| Fixed CTA footer (Continue / Preview / Save) | `.foldAvoiding()` on the button, *inside* any full-width background |
| Horizontally scrolling tool strip / chips | Leave it. Scrolling content is exempt. Never fold-avoid it. |
| Single-column screen that stretches on the inner display | `horizontalSizeClass == .regular` → two columns (`HStack`), capped width |
| Content + secondary pane (list/preview, hero/paywall form, picker/library) | `FoldSplitLayout(leading:trailing:stacked:)` |
| `List`/inset-grouped list flush against the vertical bar | `.verticalBarClearance()` |
| Tab title drawn leading but the design centers it | `ToolbarItem(placement: .principal) { Text(title) }` when `hasVerticalBar` |
| Fixed-width grid columns | `GridItem(.adaptive(minimum:))` (check iPad column counts!) |
| Art/badge under the outer camera | `proxy.trailingOcclusionWidth` |

## 4. Components (copy from `components/`)

All compile on iOS 17 and on Xcode 26. On older OS/SDK they degrade to plain iPhone behaviour.

| File | API | Purpose |
|---|---|---|
| `VerticalBarReader.swift` | `VerticalBarReader { hasVerticalBar in … }` | `toolbarVerticalEdge != nil`. True on the outer display and in inner landscape; false in inner portrait and on iPhone. |
| `GeometryProxy+Duo.swift` | `verticalFold`, `activeVerticalFold`, `trailingOcclusionWidth` | Reserved-region queries. `verticalFold` includes the inactive (flat) fold as a zero-width line, for stable two-pane splits. |
| `FoldSplitLayout.swift` | `FoldSplitLayout { leading } trailing: { … } stacked: { … }` | Two panes split exactly at the fold (flat or book). `stacked` elsewhere. Not inside a ScrollView. |
| `FoldAvoidingModifier.swift` | `.foldAvoiding()` | Pads fixed controls to the trailing side of an **active** fold only. Animates. |
| `AdaptiveBarModifier.swift` | `.adaptiveBar(header:footer:items:)` | Shows the hand-built header/footer with horizontal bars. With a vertical bar it hides them and shows the nav bar with `items`. Includes the back-button settle fix (section 5). |
| `VerticalBarClearanceModifier.swift` | `.verticalBarClearance(16)` | Safe-area padding on the bar side. |

Typical editor conversion:

```swift
content
    .adaptiveBar { header } footer: { toolRow } items: {
        ToolbarItem(placement: .cancellationAction) {
            Button("Back", systemImage: "chevron.left") { send(.back) }
        }
        ToolbarItem(placement: .confirmationAction) {
            Button("Save", systemImage: "checkmark") { send(.save) }
                .tint(.accentColor)
                .disabled(!canSave)
        }
        ToolbarItemGroup(placement: .primaryAction) {
            Button("Undo", systemImage: "arrow.uturn.backward") { send(.undo) }.disabled(!canUndo)
            Button("Redo", systemImage: "arrow.uturn.forward") { send(.redo) }.disabled(!canRedo)
        }
        ToolbarItemGroup(placement: .bottomBar) { /* icon tools, each with title + icon */ }
    }
    .navigationBarBackButtonHidden(true)
```

## 5. Traps already paid for

- **`ToolbarContent` has no `.disabled`.**
  - Apply `.disabled` to each `Button` inside `ToolbarItemGroup`.
  - Wrapping the buttons in a `Group` may merge them into one item.
- **`.toolbar(.hidden, for: .navigationBar)` must be removed** from screens converted to `adaptiveBar`, because the modifier toggles visibility itself. If the screen also shows an onboarding/overlay branch, move the `.hidden` onto that branch only.
- **Extra system back button after a sheet (iOS 27.1 bug).**
  - Symptom: a screen pushed while a picker sheet is dismissing shows a second, live system "<" in the vertical bar, despite `navigationBarBackButtonHidden`. It also skips "unsaved changes" confirms.
  - Fix: insert your items one tick later (`@State hasSettled`, `.task { hasSettled = true }`, only add vertical-bar items when settled). `adaptiveBar` already does this; do the same in any hand-rolled toolbar switch.
- **Fold-avoid the control, not its background.** Applying `.foldAvoiding()` outside a full-width card/bar shifts the whole card and leaves it floating. Put it on the button, before `.background`.
- **Active fold only for controls.**
  - Pushing CTAs aside while the device lies flat looks broken.
  - Use `activeVerticalFold` for controls.
  - Use `verticalFold` (includes inactive) only for pane splits, which should stay put.
- **Don't fold-avoid editor tool strips** (scrolling `HStack`s of tools). They are scroll content and become half-width.
- **Content that fills the width on a landscape viewport** (document pages) shows only its top third. Fit to the viewport when `width > height`.
- **`List` + `.contentMargins(.horizontal, 16)`** clips the inset-grouped card next to the vertical bar. Keep the margin only when `!hasVerticalBar` and add `verticalBarClearance()`.
- **AdMob (and other SDKs) use `UIScreen.main`.**
  - On the inner display, an adaptive banner wider than 466pt fails with *"Ad size will not fit on screen"* and leaves an empty reserved slot.
  - Fix in the delegate: on failure retry with `AdSizeBanner` (320×50), compared with `isAdSizeEqualToSize(size1:size2:)`. On a second failure collapse the slot to 0.
  - Interstitials render in a ~400pt column. That is SDK-side and can't be fixed in-app.
- **Banner/footer background on Duo:** with a vertical bar there's no bottom tab bar, so let the background `ignoresSafeAreaEdges: .bottom`. Otherwise content peeks under it.
- **Title position:**
  - With a vertical bar the inline title is drawn leading.
  - If the design centers it, add a `.principal` `Text` only when `hasVerticalBar`.
  - Keep leading for split panes (title belongs to the list pane).
- **Hero art on the short outer display:** hide decorative art when even its minimum size doesn't fit. Put the title beside the close button and scroll the rest. Don't clip the headline.
- **Pickers that remount on fold/unfold** re-send `.load`. Guard reducers so an already-resolved permission/load does nothing.

## 6. Verify on the simulator (every changed screen)

Use this repository's `fastSimulatorTest` engine as the primary verification path. Put
`"simulator":"iPhone Duo"` in the flow, then switch pose and framebuffer in the actions:

```json
{
  "version": 1,
  "name": "duo-layouts",
  "app": {
    "project_root": "/absolute/path/to/project",
    "bundle_id": "com.example.app",
    "simulator": "iPhone Duo",
    "prebuilt": true
  },
  "actions": [
    {"type":"duo","pose":"closed"},
    {"type":"screenshot","display":"outer","name":"closed-outer.png"},
    {"type":"duo","pose":"open"},
    {"type":"screenshot","display":"inner","name":"open-inner.png"},
    {"type":"duo","pose":"book"},
    {"type":"screenshot","display":"inner","name":"book-inner.png"},
    {"type":"duo","pose":"tabletop"},
    {"type":"screenshot","display":"inner","name":"tabletop-inner.png"}
  ]
}
```

In Claude Code, ask `/fastSimulatorTest` to run the flow. From Gemini CLI, Antigravity, Codex,
or a shell, run `fastSimulatorTest <flow.json>` directly. For independent evidence rows or recordings, repeat the run with
`--duo-pose closed|open|book|tabletop`; `closed` records the outer display and the other poses
record the inner display. A `duo` action also persists its selected display for a following
separate `fastSimulatorTest do '{"type":"screenshot"}'` process.

If the engine is unavailable, `scripts/duo-sim.sh` remains the Device Hub + `simctl` fallback:

```bash
D=scripts/duo-sim.sh
$D build-run <project.xcodeproj> <scheme> <bundle-id> # Xcode 27.1 build → install → launch
$D pose closed|book|flat|rotate                       # Device Hub pose buttons
$D shot outer|inner <name>                            # per-display screenshot → <scratch>/duo/<name>_s.png
$D tap-inner <x> <y>                                  # inner-display tap in points (needs calibration, see script)
```

- The iOS-simulator MCP tool / `simctl` taps only reach the **outer** display. For the inner display, `tap-inner` does a real click on the Device Hub window. Doing that briefly brings Device Hub forward, then returns focus to whatever app the user had in front.
- `tap-inner` setup:
  - Run `calibrate` once, then read the inner display's top-left and width (in capture pixels) off `devicehub.png`.
  - Export `DUO_INNER_RECT="<left> <top> <width>"`.
  - Example: a 1920×1050pt window with the device zoomed to fit gave `742 289 685`.
- Coordinates are **points**:
  - Outer `_s.png` images (678px tall) are ≈1:1 with points.
  - Inner `_s.png` images are 1000px wide, so multiply image x/y by 0.951 in landscape (951pt wide), or 0.669 in portrait.
- **Never quit Device Hub.** Quitting shuts the Duo simulator down. If it shows "Connecting display…", detach the MCP panel and wait; reboot the device only as a last resort.
- Check each screen in four states:
  - closed (outer, vertical bar): `--duo-pose closed`, display `outer`;
  - flat landscape (inner, vertical bar, inactive fold): `--duo-pose open`, display `inner`;
  - book (active fold): `--duo-pose book`, display `inner`;
  - tabletop (active horizontal fold on the inner display): `--duo-pose tabletop`, display `inner`.
- If ads or paywalls get in the way, unlock premium in Debug builds only (e.g. `#if DEBUG return true` in the entitlement resolver). Never in Release, and keep analytics reporting the real state.

## 7. Done checklist

- [ ] No hand-built chrome left on full-screen screens with vertical bars; one-button sheets intentionally excluded.
- [ ] All bar items have title + icon; prominent action tinted; back/close first.
- [ ] No fixed control inside an active fold; nothing shifted while flat.
- [ ] Inner display uses split/two columns where content is wider than a phone column.
- [ ] Nothing clipped under the outer camera (occlusion) or flush against the bar.
- [ ] Builds on both the new and the old toolchain; scoped tests for touched reducers pass.
