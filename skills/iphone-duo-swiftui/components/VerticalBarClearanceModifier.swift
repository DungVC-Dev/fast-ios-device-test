import SwiftUI

struct VerticalBarClearanceModifier: ViewModifier {
    let length: CGFloat

    func body(content: Content) -> some View {
        #if compiler(>=6.4)
        if #available(iOS 27.1, *) {
            VerticalBarEdgeClearance(length: length, content: content)
        } else {
            content
        }
        #else
        content
        #endif
    }
}

#if compiler(>=6.4)
@available(iOS 27.1, *)
private struct VerticalBarEdgeClearance<Content: View>: View {
    let length: CGFloat
    let content: Content

    @Environment(\.toolbarVerticalEdge)
    private var toolbarVerticalEdge

    var body: some View {
        content
            .safeAreaPadding(edge, toolbarVerticalEdge == nil ? 0 : length)
    }

    var edge: Edge.Set {
        toolbarVerticalEdge == .leading ? .leading : .trailing
    }
}
#endif

// MARK: - View Extension
extension View {
    /// Keeps inset-grouped list content clear of iPhone Duo's vertical bar, which a list otherwise sits flush against.
    func verticalBarClearance(_ length: CGFloat = 16) -> some View {
        modifier(VerticalBarClearanceModifier(length: length))
    }
}
