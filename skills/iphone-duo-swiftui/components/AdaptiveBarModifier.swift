import SwiftUI

struct AdaptiveBarModifier<Header: View, Footer: View, Items: ToolbarContent>: ViewModifier {
    @ViewBuilder let header: () -> Header
    @ViewBuilder let footer: () -> Footer
    @ToolbarContentBuilder let items: () -> Items

    @State private var hasSettled = false

    func body(content: Content) -> some View {
        VerticalBarReader { hasVerticalBar in
            content
                .safeAreaInset(edge: .top, spacing: 0) {
                    if !hasVerticalBar {
                        header()
                    }
                }
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    if !hasVerticalBar {
                        footer()
                    }
                }
                .toolbar(hasVerticalBar ? .visible : .hidden, for: .navigationBar)
                .toolbar {
                    if hasVerticalBar, hasSettled {
                        items()
                    }
                }
        }
        // iOS 27.1 ignores a hidden back button on a view pushed as a sheet dismisses, until its items change.
        .task { hasSettled = true }
    }
}

// MARK: - View Extension
extension View {
    /// Shows the hand-built `header` and `footer` with horizontal bars, and `items` in iPhone Duo's vertical bar instead.
    func adaptiveBar(
        @ViewBuilder header: @escaping () -> some View,
        @ViewBuilder footer: @escaping () -> some View,
        @ToolbarContentBuilder items: @escaping () -> some ToolbarContent
    ) -> some View {
        modifier(AdaptiveBarModifier(header: header, footer: footer, items: items))
    }

    func adaptiveBar(
        @ViewBuilder header: @escaping () -> some View,
        @ToolbarContentBuilder items: @escaping () -> some ToolbarContent
    ) -> some View {
        modifier(AdaptiveBarModifier(header: header, footer: { EmptyView() }, items: items))
    }
}
