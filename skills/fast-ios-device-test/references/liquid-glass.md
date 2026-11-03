# Recognise and test Liquid Glass

Use this reference when a Figma frame, screenshot, PRD, or implementation shows glass-like
navigation or controls. It turns the first visual read into a small, reproducible test set. It is
not an implementation specification.

## Spot it in a design

Liquid Glass normally belongs to a navigation or control layer that appears to float above the
app's content. Look for several cues together:

- translucent material that refracts or lenses the content beneath it, especially around edges;
- highlights, shadows, and tint that adapt to the colours moving underneath;
- pill, capsule, circle, or continuously rounded control silhouettes;
- a floating tab bar, toolbar, search field, menu, or sheet rather than an opaque edge-to-edge bar;
- content continuing behind the control layer, with a fade, blur, or other scroll-edge separation;
- neighbouring glass controls joining, separating, or morphing during interaction;
- a selected or primary control with a stronger semantic tint.

One translucent rectangle is not enough evidence. A conventional blur/material usually stays
visually flat: it softens the same rectangular region, has no edge lensing, does not react as a
control is pressed, and does not merge with nearby shapes. Treat a static mock-up as *likely
glass* only when its depth, adaptive colour, control shape, and placement agree. Confirm in the
prototype or code when the distinction affects acceptance criteria.

On iOS 26 and later, standard tab bars, navigation and toolbar items, sheets and popovers,
search, menus, sliders, toggles, and other system controls can receive the new appearance from
the system. First test those as system components; do not assume each is custom. In SwiftUI,
custom glass is a stronger signal when code uses `.glassEffect(...)`, `GlassEffectContainer`,
`.buttonStyle(.glass)`, or `.buttonStyle(.glassProminent)`. Containers and matching effect IDs
can coordinate blending and morphing. UIKit equivalents include `UIGlassEffect` and
`UIGlassContainerEffect`.

Glass should clarify the hierarchy between content and controls. Flag glass stacked on glass,
glass used as ordinary content decoration, excessive tint, or a control layer that hides the
content it operates on.

## Derive the first test cases

Keep only rows that correspond to recognised elements. Each row needs a settled screenshot at
the state named under **Set up**; motion also needs a recording or before/after frames.

| ID | Recognised element | Set up | Inspect in evidence | PASS |
|---|---|---|---|---|
| LG-01 | Any glass control over content | Put it over light, dark, and visually busy content; scroll the content beneath it | Label/icon legibility, edge lensing, tint, separation from content | Text and symbols remain readable; the material adapts without losing control boundaries or obscuring important content |
| LG-02 | Floating bar or toolbar at a scroll edge | Capture at the top, while scrolling, and at the bottom | Edge fade/blur, content continuing behind the bar, abrupt seams | The edge treatment appears only where needed, changes smoothly, and never clips content or creates a hard unintended band |
| LG-03 | Every glass screen | Run light and dark appearance | Contrast, tint meaning, highlights, shadows, selected state | Same hierarchy and meaning in both appearances; no washed-out icons or accidental opaque blocks |
| LG-04 | Thin, transparent, or low-contrast glass | Enable Increase Contrast | Text/icon contrast and visible control boundaries | Controls remain distinguishable and all information stays legible |
| LG-05 | Transparent or refractive glass | Enable Reduce Transparency | Replacement material and hierarchy | The surface becomes more opaque as the system intends; labels, selection, and grouping remain clear |
| LG-06 | Morphing, merging, or strongly animated glass | Enable Reduce Motion, then trigger the transition | Start/end state, alternate transition, focus and tap target | The outcome is unchanged and understandable without the full morph; no jump, overlap, or stranded control |
| LG-07 | Glass appearance on iOS 26.1+ | Test the user's Clear and Tinted system choices | Legibility, colour contamination, selected/primary controls | Both choices preserve labels, icons, hierarchy, and semantic tint |
| LG-08 | Text inside a glass control | Use the largest supported accessibility Dynamic Type size | Truncation, wrapping, control growth, collisions | Essential text is available, targets do not overlap, and the glass shape grows or reflows without clipping |
| LG-09 | Interactive or selected glass | Capture normal, pressed, selected, disabled, and post-morph states | Feedback, semantic tint, icon position, shape continuity | Every state is recognisable without colour alone; release lands in the correct stable state |
| LG-10 | Widget or Lock Screen presentation | Render Home Screen and Lock Screen variants, including accented/tinted rendering where applicable | Container background, cut-outs, text/icon contrast, system tint | The widget remains readable and intentional in every supported rendering mode; no duplicate background or lost content |
| LG-11 | Glass on iPhone Duo | Capture relevant screens on outer and inner displays; add portrait/landscape and book/tabletop only when layout can change | Fold/bar avoidance, toolbar placement, content beneath floating controls | No glass control crosses a reserved region or fold, disappears off-screen, or covers pane content; hierarchy matches on each intended display |

Accessibility settings are distinct cases. Do not treat dark appearance as a substitute for
Increase Contrast, Reduce Transparency, or Reduce Motion.

### Fill-in template

```text
Design source: <Figma frame / screenshot / PRD section>
Recognised glass: <element, system or custom, screen and state>
Backgrounds: <light / dark / busy / scrolling>
Cases: <LG-01, LG-02, ...>
Device rows: <phone; Duo outer/inner + orientation/pose if relevant>
Setup per row: <appearance, content size, system accessibility setting>
Evidence: <settled screenshot names; recording for interaction/morph>
PASS: <specific readable text/icons, hierarchy, edge behaviour, final state>
Open question: <anything a static design cannot prove>
```

## Run the supported cases

The engine can apply and restore appearance and Dynamic Type variants. Its screenshot action
waits for visual stability by default. Capture before and after a swipe so the glass is judged
over different content and at the scroll edge:

```json
{
  "version": 1,
  "name": "lg-toolbar-scroll",
  "expect": "Toolbar stays legible and separated while content scrolls beneath it",
  "app": {
    "project_root": "/absolute/path/to/App",
    "bundle_id": "com.example.app",
    "simulator": "iPhone 17"
  },
  "actions": [
    {"type": "launch"},
    {"type": "wait", "label": "Library"},
    {"type": "screenshot", "name": "lg-top.png"},
    {"type": "swipe", "direction": "up"},
    {"type": "screenshot", "name": "lg-scrolled.png"}
  ]
}
```

Run one variant at a time and keep the same session for the report:

```bash
fastSimulatorTest flow.json --appearance light --session liquid-glass
fastSimulatorTest flow.json --appearance dark --session liquid-glass
fastSimulatorTest flow.json --content-size accessibility-extra-extra-extra-large --session liquid-glass
```

Use `"stable": false` only when the point of the image is an animation frame. For morphing and
pressed states, prefer `--record`; use settled screenshots for the final acceptance state.

For iPhone Duo, select the pose before the screenshot. `closed` uses the outer display; the other
poses use the inner display. Add an explicit display when evidence names must make that choice
obvious:

```json
{"actions": [
  {"type":"duo", "pose":"closed", "orientation":"portrait"},
  {"type":"screenshot", "display":"outer", "name":"lg-outer.png"},
  {"type":"duo", "pose":"open", "orientation":"landscape"},
  {"type":"screenshot", "display":"inner", "name":"lg-inner.png"}
]}
```

### Accessibility-setting limits verified on Simulator

These findings were checked on a real booted iPhone 17 Simulator running iOS 26.5 with Xcode
26.6. They describe the current engine, not a promise that private preference keys are stable:

- **Increase Contrast:** `xcrun simctl ui <udid> increase_contrast enabled|disabled` exists,
  changes the Settings state, and can be queried with the command without the final value. The
  engine does not yet expose or restore it as a flow option, so set and restore it around a run.
- **Reduce Transparency:** `simctl ui` has no option. A real simulator accepted
  `xcrun simctl spawn <udid> defaults write com.apple.Accessibility
  EnhancedBackgroundContrastEnabled -bool true|false`; after relaunching Settings, the switch
  matched the value. This is a private preference and the engine neither sets nor restores it.
- **Reduce Motion:** `simctl ui` has no option. A real simulator accepted
  `xcrun simctl spawn <udid> defaults write com.apple.Accessibility ReduceMotionEnabled -bool
  true|false`; after relaunching Settings, the switch matched the value. This is also private and
  unmanaged by the engine.
- **Clear versus Tinted glass:** no `simctl ui` option or verified `com.apple.Accessibility`
  defaults key was found. On the tested Simulator, Settings search did not expose a Liquid Glass
  choice. Treat LG-07 as a manual precondition until a public, verifiable control is available.

Because raw defaults do not have the engine's cleanup guarantee, record the original value and
restore it even after failure. Do not put these shell commands inside a flow. A future native flow
option should own setup, verification, and rollback together.

## Apple sources

This guide paraphrases the principles; follow the current Apple documentation for implementation
details:

- [Human Interface Guidelines: Materials](https://developer.apple.com/design/human-interface-guidelines/materials)
- [Adopting Liquid Glass](https://developer.apple.com/documentation/TechnologyOverviews/adopting-liquid-glass)
- [Applying Liquid Glass to custom SwiftUI views](https://developer.apple.com/documentation/swiftui/applying-liquid-glass-to-custom-views)
- [WWDC25: Meet Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/219/)
- [WWDC25: Get to know the new design system](https://developer.apple.com/videos/play/wwdc2025/356/)
- [WWDC25: Build a SwiftUI app with the new design](https://developer.apple.com/videos/play/wwdc2025/323/)
- [WWDC25: Build a UIKit app with the new design](https://developer.apple.com/videos/play/wwdc2025/284/)
- [WidgetKit: Optimizing for accented rendering and Liquid Glass](https://developer.apple.com/documentation/WidgetKit/optimizing-your-widget-for-accented-rendering-mode-and-liquid-glass)

If `apple-liquid-glass` has been exported from the local Xcode, read its framework-specific
references for code changes. Apple text stays in that local skill and is not shipped by this repo.
