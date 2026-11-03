import SwiftUI

struct FoldAvoidingModifier: ViewModifier {
    @State private var leadingInset: CGFloat = 0

    func body(content: Content) -> some View {
        content
            .padding(.leading, leadingInset)
            .onGeometryChange(for: CGFloat.self) { proxy in
                proxy.activeVerticalFold.map { max(0, $0.maxX) } ?? 0
            } action: { inset in
                withAnimation(.smooth) { leadingInset = inset }
            }
    }
}

// MARK: - View Extension
extension View {
    /// Moves fixed controls to the trailing side of the fold while iPhone Duo is partially folded, as the system does with alerts.
    func foldAvoiding() -> some View {
        modifier(FoldAvoidingModifier())
    }
}
