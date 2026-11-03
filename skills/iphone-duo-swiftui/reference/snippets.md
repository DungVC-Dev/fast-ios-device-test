# Snippets

Patterns that don't deserve a component but recur on every project.

Component dependencies:
- `AdaptiveBarModifier` needs `VerticalBarReader`.
- `FoldSplitLayout` and `FoldAvoidingModifier` need `GeometryProxy+Duo`.

## Full-screen cover that should use the vertical bar

A toolbar needs a navigation container. Covers usually have none.

```swift
.fullScreenCover(item: $editor) { editor in
    NavigationStack {
        EditorView(editor: editor)   // uses .adaptiveBar(...) inside
    }
}
```

## Custom toolbar switch with the back-button settle fix

Use this when you can't use `adaptiveBar` (e.g. a view that already owns a `.toolbar`).

```swift
@State private var hasSettled = false

VerticalBarReader { hasVerticalBar in
    content
        .navigationBarBackButtonHidden(true)
        .toolbar {
            if hasVerticalBar {
                if hasSettled { verticalBarItems }
            } else {
                phoneItems
            }
        }
}
// iOS 27.1 ignores a hidden back button on a view pushed as a sheet dismisses, until its items change.
.task { hasSettled = true }
```

## Centered tab title (design centers it, the vertical-bar layout draws it leading)

```swift
VerticalBarReader { hasVerticalBar in
    TabView(selection: $tab) { … }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if hasVerticalBar, !isSplitPane {
                ToolbarItem(placement: .principal) {
                    Text(title).font(.headline)
                }
            }
        }
}
```

## Two columns on the inner display (scroll content)

```swift
@Environment(\.horizontalSizeClass) private var sizeClass

if sizeClass == .regular {
    HStack(alignment: .top, spacing: 20) {
        primaryColumn.frame(maxWidth: .infinity)
        secondaryColumn.frame(maxWidth: .infinity)
    }
    .frame(maxWidth: 720)          // readable width, centered
    .frame(maxWidth: .infinity)
} else {
    VStack(spacing: 24) { primaryColumn; secondaryColumn }
}
```

Use `FoldSplitLayout` instead when the panes are independent and must not scroll together.

## Fixed CTA bar with a full-width background

```swift
AppButton("Continue") { … }
    .padding(16)
    .frame(maxWidth: .infinity)
    .foldAvoiding()                 // the button moves…
    .background(.bar)               // …the bar stays full width
```

## Bar-side margin for lists that are not inset-grouped by the system

```swift
VerticalBarReader { hasVerticalBar in
    List { … }
        .contentMargins(.horizontal, hasVerticalBar ? 0 : 16, for: .scrollContent)
        .verticalBarClearance()
}
```

## Document page canvas on a landscape viewport

```swift
let fitsPage = viewport.width > viewport.height   // fill width only in portrait
```

## AdMob adaptive banner on the inner display

```swift
func bannerView(_ bannerView: BannerView, didFailToReceiveAdWithError error: any Error) {
    // AdMob checks the main screen, which on iPhone Duo is the outer display even on the inner one.
    if !isAdSizeEqualToSize(size1: bannerView.adSize, size2: AdSizeBanner) {
        bannerView.adSize = AdSizeBanner
        bannerView.load(Request())
        return
    }
    onAdFailed?()                   // collapse the reserved slot to 0
}
```

On Duo, let the banner's background ignore the bottom safe area (no tab bar there): `.background(color, ignoresSafeAreaEdges: hasVerticalBar ? .bottom : [])`.

## Camera / art under the outer camera

```swift
GeometryReader { proxy in
    art.padding(.trailing, proxy.trailingOcclusionWidth)
}
```

## Debug-only premium (to walk screens without paywalls/ads)

Put this in the live entitlement resolver, never in Release, and keep analytics on the real value:

```swift
#if DEBUG
return true
#else
return resolvedPremium(storeKit: storeKit)
#endif
```
