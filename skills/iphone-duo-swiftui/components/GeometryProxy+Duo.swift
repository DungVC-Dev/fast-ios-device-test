import SwiftUI

extension GeometryProxy {
    /// Width that an active hardware occlusion on the trailing half, such as iPhone Duo's outer camera, takes from the trailing edge.
    var trailingOcclusionWidth: CGFloat {
        #if compiler(>=6.4)
        if #available(iOS 27.1, *) {
            let width = size.width
            return reservedRegions(kind: .occlusion)
                .filter { $0.isActive && $0.frame.minX > width / 2 }
                .map { width - $0.frame.minX }
                .max() ?? 0
        }
        #endif
        return 0
    }

    /// The vertical fold crossing this view, as a zero-width line while the device lies flat so layouts keep their halves.
    var verticalFold: CGRect? {
        #if compiler(>=6.4)
        if #available(iOS 27.1, *) {
            let width = size.width
            return reservedRegions(kind: .division, options: .includeInactive)
                .first { $0.frame.height > $0.frame.width && $0.frame.midX > 0 && $0.frame.midX < width }
                .map { region in
                    region.isActive ? region.frame : CGRect(x: region.frame.midX, y: 0, width: 0, height: 0)
                }
        }
        #endif
        return nil
    }

    /// The vertical fold crossing this view while the device is partially folded.
    var activeVerticalFold: CGRect? {
        verticalFold.flatMap { $0.width > 0 ? $0 : nil }
    }
}
