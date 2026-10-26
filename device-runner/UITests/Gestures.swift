import CoreGraphics
import Foundation

// Geometry for gestures that XCUICoordinate makes from screen points; mirrors
// fast_ui.edge_points on the Simulator.
enum Gestures {
    // A swipe that starts one point inside `edge`, `at` (0-1) along it, and travels `distance`
    // (0-1) of the screen inward: the back swipe, Control Center (top, at 0.9), going home
    // (bottom). Nil for an unknown edge.
    static func edgePoints(edge: String, at: Double, distance: Double, screen: CGRect) -> (start: CGPoint, end: CGPoint)? {
        let x0 = Double(screen.minX), y0 = Double(screen.minY)
        let width = Double(screen.width), height = Double(screen.height)
        let alongX = x0 + width * at, alongY = y0 + height * at
        switch edge {
        case "left": return (CGPoint(x: x0 + 1, y: alongY), CGPoint(x: x0 + width * distance, y: alongY))
        case "right": return (CGPoint(x: x0 + width - 1, y: alongY), CGPoint(x: x0 + width * (1 - distance), y: alongY))
        case "top": return (CGPoint(x: alongX, y: y0 + 1), CGPoint(x: alongX, y: y0 + height * distance))
        case "bottom": return (CGPoint(x: alongX, y: y0 + height - 1), CGPoint(x: alongX, y: y0 + height * (1 - distance)))
        default: return nil
        }
    }
}
