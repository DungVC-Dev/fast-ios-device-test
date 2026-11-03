import SwiftUI

/// Places `leading` and `trailing` on either side of a vertical fold, and falls back to `stacked` wherever there is none.
struct FoldSplitLayout<Leading: View, Trailing: View, Stacked: View>: View {
    @ViewBuilder let leading: () -> Leading
    @ViewBuilder let trailing: () -> Trailing
    @ViewBuilder let stacked: () -> Stacked

    var body: some View {
        #if compiler(>=6.4)
        if #available(iOS 27.1, *) {
            FoldSplitReader(leading: leading, trailing: trailing, stacked: stacked)
        } else {
            stacked()
        }
        #else
        stacked()
        #endif
    }
}

#if compiler(>=6.4)
@available(iOS 27.1, *)
private struct FoldSplitReader<Leading: View, Trailing: View, Stacked: View>: View {
    let leading: () -> Leading
    let trailing: () -> Trailing
    let stacked: () -> Stacked

    var body: some View {
        GeometryReader { proxy in
            if let fold = proxy.verticalFold {
                HStack(spacing: 0) {
                    leading()
                        .frame(width: max(0, fold.minX))
                    Color.clear
                        .frame(width: fold.width)
                    trailing()
                        .frame(maxWidth: .infinity)
                }
            } else {
                stacked()
            }
        }
    }
}
#endif
