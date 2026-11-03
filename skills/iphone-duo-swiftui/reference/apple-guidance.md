# iPhone Duo — digest of Apple's official developer material

Compiled 3 Oct 2026 from Apple pages read live (DocC JSON for docs/HIG, HTML transcripts for talks). Paraphrased; only API names are quoted. Written for a SwiftUI app with an older deployment target, a home grid, a tab bar and navigation titles.

**Sources read:** HIG "Designing for iPhone Duo" (new page, 9 Sep 2026). Technology overview "Preparing your app for iPhone Duo". About 90 SwiftUI/UIKit symbol pages, covering every API the overview links plus their child symbols. AVKit "Choosing a camera by the direction it faces". All six tech talks (111461–111466), full transcripts. App Store Connect screenshot specifications. Group Lab Q&A (forum thread 847644).

**Sources with limits:**
- **Group Lab Q&A.** apple.co redirects to developer.apple.com/forums/thread/847644, which sits behind a "verify human" gate when fetched with curl. I could read it only through WebFetch's summarizer, so treat Q&A items as paraphrase-of-paraphrase. They are marked **[Q&A]** below.
- **AVFoundation article.** "Registering a camera capture accessory on iPhone Duo" was downloaded but only skimmed, because it is not relevant to this app.
- **TN3210.** Downloaded but not read in depth.
- **Not on my list.** I did not read the apple.com marketing tech-specs page or Apple Design Resources (Figma/Sketch templates).

---

## 1. Device facts

### Displays
- **Two displays, each with its own front camera.**
  - The outer display is compact width. It is wider and shorter than a regular iPhone screen.
  - The inner display is large and regular width.
  - A centre hinge joins them.
  - (HIG Anatomy; overview.)
- **Pixel sizes** (App Store Connect screenshot specifications, the only Apple page I read that gives numbers):
  - Outer display: 1398 × 2034 px, or 2034 × 1398 px.
  - Inner display: 2007 × 2853 px, or 2853 × 2007 px.
  - App Store Connect notes that uploading Duo screenshots will be supported "later this year".
- **Point sizes:** none of the Apple pages I read state a point size, a scale factor, a safe-area value or a bar width. Any pt figures (466×678, 951×669, the 84 pt bar, 20 pt margins) come from elsewhere. See §6.
- **Size classes** (talk 111461; [Q&A]):

  | Display | Portrait (horizontal × vertical) | Landscape (horizontal × vertical) |
  |---|---|---|
  | Outer | compact × regular | compact × compact |
  | Inner | regular × regular | regular × regular |

  - The outer display behaves like any other iPhone, orientation included.
  - The inner display ignores the app's supported interface orientations. It always rotates, and the app scales there, including in Split View.
  - `UIRequiresFullScreen` is honoured, but the app still resizes when the device opens or closes.

### Poses
- **Six poses.** The overview's image caption lists them left to right: closed, tent, open wide, partially folded, open tall, laptop (tabletop). The HIG prose describes them as "like a book", "on a surface" and "standing on its edges".
- **Apple tells you not to design per pose.**
  - Design for two size classes: compact width (outer) and regular width (inner).
  - Avoid fixed widths and breakpoints (talk 111466, explicitly).
  - One optional bespoke layout is acceptable: tabletop, with media on top and controls on the stable bottom half. It must keep the same controls and the same hierarchy as the other poses.
- **Split View multitasking.**
  - New on iPhone Duo: drag an app to one side with the home gesture to get a 50/50 split.
  - Each app's bar sits on its own outer edge, so the left app has its controls on the left.
- **Picture in Picture.**
  - PiP can be pinned to the top of the screen; the app below shrinks vertically.
  - When partially folded, the video takes half the screen.
- **Multiple windows.**
  - iPhone Duo is the first iPhone with multiple scenes.
  - New windows can be created only on the inner display.
  - Handle failures when requesting a new scene.

### Reserved regions (HIG; talk 111463)
iOS models hardware intrusions as reserved regions:

| Region | Kind | When it is present |
|---|---|---|
| Outer front camera | occlusion | Always. It sits in a corner, vertically in line with the side controls, and grows into the Dynamic Island for Live Activities. |
| Inner front camera (under the display) | occlusion | Active only while the camera runs. The UI moves aside when it activates. |
| Folding region | division | Active only when partially open. Inactive when flat, with zero width. |

- Each region has `frame`, `isActive`, `kind`, `id` and `margins`. `margins` is described as the margins included in the frame around the area for interactive content.
- **Conflict in Apple's own material about the default query:**
  - The talk (and its chapter text) says only active regions come back by default, and `.includeInactive` adds the rest.
  - The `ReservedRegion` and `reservedRegions(...)` doc pages say the call returns every intersecting region whether or not it is active.
  - **Practical rule:** always filter on `isActive` for current-state decisions.
- Inactive regions are useful for stable decisions. Apple's example: prefer an even column count whenever a fold exists.
- System components adapt automatically: alerts, context menus, sheets, popovers, split views, navigation and content containers. In a partially folded split view, the columns rebalance to an even 50/50 split.
- [Q&A] Touches on custom UI drawn over the camera's reserved region may be suppressed.

---

## 2. SDK tiers and deployment target

| Built with | What the app gets on iPhone Duo |
|---|---|
| iOS 26 SDK / Xcode 26 or older | Runs and resizes. Closed: it uses the area left of the status bar and camera. Open: familiar iPhone size and aspect ratio. Does not extend under the status bar or camera. [Q&A] calls this compatibility mode with letterboxing. |
| iOS 27 SDK | Existing iPhone-resizing work pays off. On the inner display the app extends to the left of the status-bar area. |
| **iOS 27.1 SDK / Xcode 27.1** | Full screen, edge to edge. Standard navigation buttons and toolbar buttons lay out vertically under the status bar. This is required for the vertical-bar behaviour. |

The table is from talk 111461. The overview only says that building with Xcode 26 or earlier leaves the app short of the status bar and camera, and to use the latest Xcode.

**Availability as documented** (the DocC pages list iOS/iPadOS as "beta" at 27.1):
- **iOS 27.1:**
  - `ArrangementView` and its style/modifier family, `overlayArrangementZIndex`
  - `ReservedRegion`, `GeometryProxy.reservedRegions`
  - `DeviceHinge`, `DeviceHingeContext`, `onHingeChange`
  - `toolbarVerticalEdge`, `toolbarVerticalBehavior`, `ToolbarVerticalCompressionBehavior`
  - `ToolbarItemAxisBehavior` / `axisBehavior(_:)`
  - `CameraCaptureAccessory`
  - All UIKit equivalents: `UIHinge*`, `UIArrangementViewController`, `UIView.ReservedRegion`, `verticalBarEdge`, `preferredVerticalBarBehavior`, `UIVerticalBarCompressionBehavior`, `UIBarButtonItem.AxisBehavior`
- **iOS 27.0:**
  - `ToolbarItemVisibilityPriority`, `visibilityPriority(_:)`
  - `ToolbarOverflowMenu`, `toolbarOverflowMenu(content:)`
  - `topBarPinnedTrailing`
  - `presentationPlacement(_:)` / `PresentationPlacement`
  - `defaultTabBarPlacement(_:)`
  - `sceneAccessory(content:)`
  - `UIBarButtonItemVisibilityPriority`, `UISheetPresentationController.preferredPlacement`
- **iOS 26.0:** `backgroundExtensionEffect()`, plus the concentricity APIs `ConcentricRectangle` and `UICornerConfiguration`.

**For an iOS 17 deployment target:**
- [Q&A] Apple says to gate the 27.1 APIs behind availability checks and build the baseline on size classes and safe areas, which predate iOS 17, so older OS versions degrade gracefully.
- `ArrangementView` will not be back-ported (iOS 27.1 and later only).
- The vertical-bar behaviour is driven by the system plus the SDK. It needs no API calls, so a deployment target of 17 with the 27.1 SDK gets it automatically.
- **Not documented:** whether `ToolbarContentBuilder` accepts `if #available` inside `.toolbar { }`. Check this before relying on `.axisBehavior` or `.visibilityPriority` under an iOS 17 target.

**Tooling:**
- Xcode 27.1 adds an iPhone Duo simulator in **Device Hub**, with buttons to open, close, rotate and fold.
- The Xcode "App Resizability" skill (renamed from the app modernization skill) now covers SwiftUI and iPhone Duo.

---

## 3. API reference (exact declarations from the doc pages)

### SwiftUI
| API | Declaration | Avail. | Purpose |
|---|---|---|---|
| `DeviceHinge` | `struct DeviceHinge` with `var angle: Angle` and `var status: DeviceHinge.Status` | 27.1 | State of one hinge. |
| `DeviceHinge.Status` | `struct Status`, static members `.closed`, `.partiallyOpen`, `.fullyOpen` | 27.1 | Discrete status that the system derives from angle plus device orientation. |
| `DeviceHingeContext` | `struct DeviceHingeContext` with `hinge: DeviceHinge?` (nil means no hinge) | 27.1 | Context passed to the hinge callback. |
| `onHingeChange` | `nonisolated func onHingeChange(isEnabled: Bool = true, _ action: @escaping (DeviceHingeContext, DeviceHingeContext) -> Void) -> some View` | 27.1 | (old, new) callback. Use it for effects and interactions, never for layout. |
| `ArrangementView` | `nonisolated struct ArrangementView<Primary: View, Secondary: View>` with `init(primary:secondary:)` and `init(_ configuration: ArrangementViewStyleConfiguration)` | 27.1 | Layout container that places a primary and a secondary view according to size, size class and hardware. |
| `arrangementViewStyle(_:)` | `nonisolated func arrangementViewStyle(_ style: some ArrangementViewStyle) -> some View`. Styles are `.automatic` (resolves to split), `.split` and `.overlay`, each with `.axes(_:)`. | 27.1 | Picks the arrangement. |
| Split tuning | `splitArrangementLayoutRatio(_ ratio: CGFloat?)`, `splitArrangementLayoutRatio(minHorizontal:idealHorizontal:maxHorizontal:minVertical:idealVertical:maxVertical:)`, `splitArrangementLayoutSize(minWidth:…maxHeight:)`, `splitArrangementFixedLayoutSize(horizontal: Bool = true, vertical: Bool = true)` | 27.1 | Preferred size, ratio or fixed size of a pane. |
| `overlayArrangementEdge(_:)` | `nonisolated func overlayArrangementEdge(_ edge: HorizontalEdge?) -> some View` | 27.1 | Which side a view moves to when an overlay becomes side-by-side. |
| `overlayArrangementZIndex` | `EnvironmentValues`, `var overlayArrangementZIndex: Int` | 27.1 | Lets a view know whether it is layered on top, for example to collapse it. |
| `ReservedRegion` | `struct ReservedRegion` (Identifiable, Hashable, Sendable) with `frame: CGRect`, `margins: EdgeInsets`, `isActive: Bool`, `kind: Kind`, `id`. `Kind` is `.division` / `.occlusion`; `QueryOptions` is `.includeInactive`. | 27.1 | An area reserved by hardware. |
| `GeometryProxy.reservedRegions` | `func reservedRegions(kind: ReservedRegion.Kind, options: ReservedRegion.QueryOptions = [], layoutDirectionBehavior: LayoutDirectionBehavior = .mirrors) -> [ReservedRegion]` | 27.1 | Query regions inside a `GeometryReader` or `onGeometryChange`. Mirrored for RTL by default; pass `.fixed` for physical frames. |
| `toolbarVerticalEdge` | `EnvironmentValues`, `var toolbarVerticalEdge: HorizontalEdge? { get }` | 27.1 | The edge the system prefers for the vertical bar, whether or not a bar is visible. nil where the system never uses a vertical bar. |
| `toolbarVerticalBehavior(_:)` | `nonisolated func toolbarVerticalBehavior(_ behavior: ToolbarVerticalBehavior) -> some View`, with `.automatic` / `.disabled` | 27.1 | Opt out of the vertical bar. Resolution rules: in a NavigationStack the topmost view decides; in a TabView the selected tab decides; in a NavigationSplitView the trailing-most column decides. |
| `toolbarVerticalCompressionBehavior(_:)` | `ToolbarVerticalCompressionBehavior` with `.automatic`, `.prefersTabBar`, `.prefersToolbarItems` | 27.1 | Chooses whether the toolbar or the tab bar compresses first when they share the vertical bar. |
| `axisBehavior(_:)` (on `ToolbarContent`) | `nonisolated func axisBehavior(_ behavior: ToolbarItemAxisBehavior) -> some ToolbarContent`, with `.automatic`, `.horizontalOnly`, `.verticalPreferred` | 27.1 | Overrides which bar axis an item may use. |
| `ToolbarItemVisibilityPriority` | `struct`, with `.automatic`, `.low`, `.high`, `init(higherThan:)`, `init(lowerThan:)`. Applied via `visibilityPriority(_:) -> some ToolbarContent`. | 27.0 | Order in which items move to the overflow menu; lower priority goes first. |
| `ToolbarOverflowMenu` | `nonisolated struct ToolbarOverflowMenu<Content: View>` with `init(content:)`; also `View.toolbarOverflowMenu(content:)` | 27.0 | Items that always live in the system overflow menu. |
| `topBarPinnedTrailing` | `static let topBarPinnedTrailing: ToolbarItemPlacement` | 27.0 | Pinned prominent action, such as Done. |
| `presentationPlacement(_:)` | `PresentationPlacement` with `.automatic`, `.center`, `.leading`, `.trailing` (sheets only) | 27.0 | On the inner display, a trailing sheet gets a vertical bar and a centered or leading sheet does not. |
| `backgroundExtensionEffect()` | `func backgroundExtensionEffect() -> some View` | 26.0 | Extends hero or background art under the vertical bar. |
| `defaultTabBarPlacement(_:)` | takes `AdaptableTabBarPlacement` | 27.0 | `.sidebar` shows tabs as a sidebar on the inner display. |
| `sceneAccessory(content:)` / `CameraCaptureAccessory` | `CameraCaptureAccessory` is 27.1 | 27.0 / 27.1 | Content on the outer display during camera capture. |

### UIKit
| API | Declaration | Avail. | Purpose |
|---|---|---|---|
| `UIHinge` | `@MainActor class UIHinge` with `angle: CGFloat` (**radians**) and `status: UIHinge.Status` | 27.1 | Hinge state. |
| `UIHinge.Status` | `enum`: `.closed`, `.partiallyOpen`, `.fullyOpen`, `.unknown` | 27.1 | |
| `UIHingeInteraction` | `@MainActor class`, `init(updateHandler: @escaping (UIHingeInteraction, UIHingeInteraction.Update) -> Void)`, `isEnabled`; `Update.hinge: UIHinge?` | 27.1 | Add it to a view. `hinge` is nil when the view leaves a hierarchy that provides hinge updates. |
| `UIArrangementViewController` | `@MainActor class`. Methods: `setViewController(_:for:animated:)`, `viewController(for:)`, `placement(for:)`, `updateArrangement(_:animated:)` with `UISplitArrangement` / `UIOverlayArrangement` (`.axes(_:)`), `state(for:) -> ViewState?` (`isHidden`, `splitAxis`, `zIndex`). `ViewPlacement` is `.primary` / `.secondary`. | 27.1 | UIKit arrangement. |
| `UIView.reservedRegions` | `@MainActor func reservedRegions(kind: UIView.ReservedRegion.Kind, options: UIView.ReservedRegion.QueryOptions = []) -> [UIView.ReservedRegion]` | 27.1 | `UIView.ReservedRegion` has `frame`, `margins: UIEdgeInsets`, `isActive` and `kind`. |
| `verticalBarEdge` | `UITraitCollection`, `var verticalBarEdge: UIVerticalBarEdge` (`.leading` / `.trailing` / `.unspecified`) | 27.1 | Same as `toolbarVerticalEdge`. |
| `preferredVerticalBarBehavior` | `UIViewController`, `var preferredVerticalBarBehavior: UIVerticalBarBehavior` (`.automatic` / `.disabled`); plus `childForPreferredVerticalBarBehavior` and `setNeedsUpdateOfVerticalBarConfiguration()` | 27.1 | Opt out of the vertical bar. |
| `verticalBarCompressionBehavior` | `UINavigationItem`, `UIVerticalBarCompressionBehavior` (`.automatic` / `.prefersBarItems` / `.prefersTabBar`) | 27.1 | |
| `UIBarButtonItem.axisBehavior` | `UIBarButtonItem.AxisBehavior` (`.automatic` / `.horizontalOnly` / `.verticalPreferred`) | 27.1 | |
| `UIBarButtonItem.visibilityPriority` | `UIBarButtonItemVisibilityPriority` (`.standard` / `.low` / `.high`, plus `init(higherThan:)` and `init(lowerThan:)`) | 27.0 | |
| `UINavigationItem.additionalOverflowItems` | `UIDeferredMenuElement?` | 16.0 | |

---

## 4. Layout guidance for a home grid, a tab bar and navigation titles

### Where the bars go
- **The rule.** The system moves navigation-bar buttons, toolbar items and the tab bar into one vertical strip on the side, together with the Dynamic Island and status bar (top to bottom: Dynamic Island → status bar → toolbar → tab bar).
- **Where this happens:**
  - The outer display, in both orientations.
  - The inner display in landscape.
  - The one exception is the inner display in portrait, which keeps normal horizontal bars.
- **Which side.** The strip is tied to the hardware: normally trailing, in line with the outer camera. It does not flip in RTL languages. In Split View each app's strip sits on its outer edge.

### Requirements for the vertical bar
- Build with the iOS 27.1 SDK.
- Use container-provided bars: `.toolbar` on content inside `NavigationStack` or `NavigationSplitView`, and `TabView`.
- Hand-built bars and standalone `UITabBar`, `UIToolbar` or `UINavigationBar` instances are ignored.
- **Implication:** one `NavigationStack` with a `TabView` inside is the right shape. Any custom tab bar or custom header row will not adapt.

### Tab bar
- The tab bar stays at the bottom of the vertical strip.
- Every tab needs an icon. A tab with only a title is not shown vertically; give every tab both a title and an icon.
- On the inner display you may opt into a sidebar with `.defaultTabBarPlacement(.sidebar)` (iOS 27.0). Apple suggests this only for information-dense apps.
- **When space runs out:**
  - By default the toolbar compresses first, so the tab bar stays visible; Apple calls this right for navigation-focused screens.
  - Task-oriented screens may set `.toolbarVerticalCompressionBehavior(.prefersToolbarItems)` so the tab bar minimizes instead.

### Toolbar items
- **Order** (top to bottom): Back/Close first (`cancellationAction`), then prominent actions (`topBarPinnedTrailing`), then the remaining groups in their original grouping. The system puts a gap between items that came from the top bar and items that came from the bottom bar.
- **What goes vertical:**
  - Items with an icon go vertical.
  - Text-only items, wide custom views and segmented controls stay in a horizontal bar.
  - Give every item both a title and a symbol (use `Label`).
  - Badges help turn a text-plus-icon item into an icon-only one.
- **Spacing and groups.**
  - Flexible spacers collapse to zero vertically.
  - Use `ToolbarItemGroup` rather than manual spacing.
- **Overflow:**
  - Items overflow bottom to top by default.
  - Set priorities with `.visibilityPriority`.
  - Move any custom "…" menu into `ToolbarOverflowMenu`, and keep the ellipsis symbol for overflow only.
- **Placement next to content.** Controls that act on a pane other than the trailing one should stay with that pane (Mail's list controls are the example).

### Navigation title
- **No Apple source I read says how the navigation title (inline or large) is drawn when bars go vertical.**
  - The anatomy diagrams label only the Dynamic Island, the status bar, the toolbar and the tab bar.
  - The talks say only that top toolbar buttons move to the top of the strip.
- **Treat this as unknown.** Verify in Device Hub, especially large titles on the outer display in landscape (compact × compact).

### Safe area and asymmetry
- Bars sit outside the safe area. Horizontal bars contribute top and bottom insets; vertical bars contribute leading or trailing insets.
- Layout margins are asymmetric too.
- Never compute width as bounds minus twice one side.
- Interactive content stays inside the safe area; backgrounds may extend past it (`.ignoresSafeArea()` or `backgroundExtensionEffect()`).

### Home grid
- **Column count.** Apple gives only one rule: prefer an even number of columns, so the grid divides cleanly at the fold. It allows using `.includeInactive` to keep that decision stable whenever a fold exists.
- **No breakpoints, widths or column counts are published.** Talk 111466 explicitly says to avoid breakpoints and screen-tied metrics and to rely on size classes.
- **When folded.** Apple's example keeps the outer margins and widens the gap at the hinge, so every cell stays inside one region.
- **Scrolling grids** do not need to avoid the fold; only fixed interactive elements do.
- [Q&A] When `LazyVGrid` columns change, you do not need to manage `scrollPosition` manually.

### Inner display
- Don't simply stretch the phone layout. Choose one of:
  - a split view (one more level of hierarchy, same hierarchy);
  - reflowing to two columns;
  - a tab sidebar.

### Telling outer portrait from outer landscape
- [Q&A] Size classes don't separate the two (both are compact width). Apple suggests `toolbarVerticalEdge` as the signal.
- But the doc says it reports the preferred edge whether or not a bar is visible, and is nil only where a vertical bar is never used.

### Sheets
- **Outer display:** sheets show their toolbar vertically by default. Opt out with `toolbarVerticalBehavior(.disabled)`; this suits a sheet with a single button. The sheet then stops just short of the camera.
- **Inner display:** a centered or leading sheet uses horizontal bars; a trailing sheet uses vertical bars.
- **Partially folded:** sheets slide aside to stay out of the fold.

---

## 5. Tech talk takeaways

### 111466 — Design for iPhone Duo
1. The design target is one app that adapts across poses, not a layout per pose. Design to compact width (outer) and regular width (inner), with no breakpoints.
2. When closed, controls move to the right side; the area to their left is comparable to a regular iPhone screen. The Dynamic Island grows vertically there.
3. Only the inner display in portrait keeps horizontal bars. When room runs out, bar items collapse into an overflow menu.
4. Mapping from a normal iPhone layout: top toolbar → top of the strip, bottom toolbar → bottom of the strip, tab bar → stays at the bottom. Text buttons and segmented controls stay in the nav bar.
5. Content needs an offset from the strip, which safe-area insets give you automatically. Centering on the full display suits only immersive, non-scrolling UI. A mix is also fine: full-width background with inset foreground.
6. Inner display options: a split view, a two-column reflow, or a tab sidebar (for information-dense apps). Never change the hierarchy between displays.
7. Sheets: vertical bars on the outer display by default (can be disabled); horizontal on the inner display; they slide out of the fold.
8. System components nudge interactive elements out of the fold. Scrollable content is exempt.

### 111461 — Prepare your app
1. Three SDK tiers (iOS 26, 27, 27.1); the full-screen experience needs the 27.1 SDK and Xcode 27.1.
2. Device Hub simulator; the App Resizability skill.
3. Use size classes, not idiom or orientation; the inner display ignores the supported orientations.
4. Avoid `UIScreen.main`, which will be deprecated. Use the environment, traits or scene bounds, and `traitCollection.displayScale`.
5. Use the concentricity APIs to match the screen corners.
6. NavigationSplitView and TabView adapt to every pose; a tab sidebar is available on the inner display.
7. Safe areas and margins are asymmetric; test Split View on both sides.
8. Use ReservedRegion (27.1) for custom bars and edge-to-edge UI.

### 111462 — Raise the bar
1. Opt in by rebuilding with the latest SDK and using container-provided bars; custom bar instances are ignored.
2. Bars share one vertical region. In a split view only the detail column takes part, and inspectors get no bar of their own.
3. Order: Back/Close (`cancellationAction`), then the pinned prominent action (`topBarPinnedTrailing`), then the remaining groups.
4. Vertical bars have a fixed width and flexible height. Icons go vertical and text stays horizontal; always supply a title.
5. `.axisBehavior(.horizontalOnly)` for items that switch between symbol and text; `.verticalPreferred` for capable custom views. Badges help reduce text.
6. Use `toolbarVerticalEdge` / `verticalBarEdge` to adapt custom views. No scroll-edge effect by default; the bar gets a background under Reduce Transparency; flexible spacers become zero height.
7. Compression: the toolbar collapses first by default; task-oriented screens can choose the other way.
8. Overflow and opt-out: use `ToolbarOverflowMenu` and `visibilityPriority`. Opt out only for calculator-like, bottom-heavy single pages or one-button sheets.

### 111463 — Strike a pose (adaptive layouts)
1. Reserved regions: the fold is a division region, the cameras are occlusion regions, and each is active or inactive.
2. Displacement pattern: move an element into the region that suits its purpose. Choose the scope (one element or a group), avoid moving it far, and don't displace scrolling content.
3. Book pose: alerts move to the trailing side. Tabletop: content on top, controls on the bottom. Search stays over the view it searches.
4. Even 50/50 split columns when folded; grids widen the gap at the hinge.
5. Query regions via `GeometryProxy` or `UIView`, with the `.includeInactive` option.
6. Arrangements: the inputs are size classes, aspect ratio and active divisions; the outputs are visibility and frame. Split (the default) versus overlay; restrict with `.axes`; if the primary axis can't split, only one view is shown.
7. Read `overlayArrangementZIndex` / `state(for:).zIndex` to collapse or expand a view.
8. Don't put navigation containers inside an arrangement, and don't put an arrangement inside List or ScrollView. Audit centered layouts.

### 111464 — Multiple displays and scenes
1. `onHingeChange` / `UIHingeInteraction` give the discrete status plus a live angle. A nil hinge means the device has none.
2. Filter on `.partiallyOpen` and reset in the else branch.
3. The hinge is for effects and interactions; use arrangements and reserved regions for layout.
4. Every app takes part in side-by-side multitasking and in the video-plus-app stacking layout. Use size classes and scene geometry.
5. First iPhone with multiple scenes: new windows only on the inner display. Handle errors; `UIWindowSceneActivationAction` hides itself when unavailable.
6. Scene accessories: system-controlled and toggled at any time; observe availability.
7. `CameraCaptureAccessory` shows UI on the outer display while the app is full screen on the inner display with an active capture session.

### 111465 — Camera
1. Two square, ultra-wide front cameras: the outer one, and an inner under-display one (the first on iPhone).
2. The virtual front camera (front-position discovery) switches automatically between them. It offers only shared capabilities (1080p60) and no depth.
3. The individual devices are the outer ultra-wide (up to 4K120) and the inner ultra-wide (1080p60), with depth.
4. `position == .front` no longer means "facing the user". Use `AVCaptureDeviceDirectionCoordinator` (AVKit, main actor), one per view.
5. The handler gets a direction map of forward- and backward-facing device descriptors (sendable); reconfigure the session off the main actor.
6. Mirror the preview based on the direction a camera faces, not its position.
7. Use `videoGravity` and `dynamicAspectRatio` to fill the display; `AVCaptureDeviceRotationCoordinator`, then turn off sensor-orientation compensation.

---
