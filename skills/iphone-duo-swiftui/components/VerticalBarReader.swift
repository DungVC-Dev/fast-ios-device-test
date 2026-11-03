import SwiftUI

/// Hands `content` whether the system lays bars out vertically here, as on iPhone Duo.
struct VerticalBarReader<Content: View>: View {
    @ViewBuilder let content: (_ hasVerticalBar: Bool) -> Content

    var body: some View {
        #if compiler(>=6.4)
        if #available(iOS 27.1, *) {
            VerticalBarEdgeReader(content: content)
        } else {
            content(false)
        }
        #else
        content(false)
        #endif
    }
}

#if compiler(>=6.4)
@available(iOS 27.1, *)
private struct VerticalBarEdgeReader<Content: View>: View {
    let content: (Bool) -> Content

    @Environment(\.toolbarVerticalEdge)
    private var toolbarVerticalEdge

    var body: some View {
        content(toolbarVerticalEdge != nil)
    }
}
#endif
