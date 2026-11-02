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

// Two fingers dragging side by side (tilts an Apple Maps map): XCUITest's public API has no such
// gesture, so the events come from the private XCTest classes the way WebDriverAgent builds them.
// Looked up at runtime: an Xcode that renames them makes `drag` return a reason and nothing else changes.
enum MultiTouch {
    private typealias InitTouch = @convention(c) (AnyObject, Selector, CGPoint, Double) -> Unmanaged<AnyObject>
    private typealias MoveTo = @convention(c) (AnyObject, Selector, CGPoint, Double) -> Void
    private typealias LiftUp = @convention(c) (AnyObject, Selector, Double) -> Void
    private typealias InitRecord = @convention(c) (AnyObject, Selector, NSString, Int) -> Unmanaged<AnyObject>
    private typealias Synthesize = @convention(c) (AnyObject, Selector, AnyObject, @escaping @convention(block) (UnsafeRawPointer?, UnsafeRawPointer?) -> Void) -> Void

    // Each finger goes from `from` to `to` over `duration` seconds. Nil on success, else why not.
    static func drag(fingers: [(from: CGPoint, to: CGPoint)], duration: Double) -> String? {
        guard let pathClass = NSClassFromString("XCPointerEventPath") as? NSObject.Type,
              let recordClass = NSClassFromString("XCSynthesizedEventRecord") as? NSObject.Type,
              let sessionClass = NSClassFromString("XCTRunnerDaemonSession") as? NSObject.Type else {
            return "this Xcode has no XCPointerEventPath / XCSynthesizedEventRecord / XCTRunnerDaemonSession"
        }
        let initTouch = NSSelectorFromString("initForTouchAtPoint:offset:")
        let moveTo = NSSelectorFromString("moveToPoint:atOffset:")
        let liftUp = NSSelectorFromString("liftUpAtOffset:")
        let initRecord = NSSelectorFromString("initWithName:interfaceOrientation:")
        let addPath = NSSelectorFromString("addPointerEventPath:")
        let synthesize = NSSelectorFromString("synthesizeEvent:completion:")
        let shared = NSSelectorFromString("sharedSession")
        guard pathClass.instancesRespond(to: initTouch), pathClass.instancesRespond(to: moveTo),
              pathClass.instancesRespond(to: liftUp), recordClass.instancesRespond(to: initRecord),
              recordClass.instancesRespond(to: addPath), sessionClass.instancesRespond(to: synthesize),
              sessionClass.responds(to: shared) else {
            return "the private multi-touch selectors are missing on this Xcode"
        }
        func call<T>(_ object: AnyObject, _ selector: Selector, as _: T.Type) -> T {
            unsafeBitCast(class_getMethodImplementation(type(of: object), selector), to: T.self)
        }
        guard let recordAlloc = recordClass.perform(NSSelectorFromString("alloc"))?.takeUnretainedValue() else {
            return "XCSynthesizedEventRecord could not be allocated"
        }
        let record = call(recordAlloc, initRecord, as: InitRecord.self)(recordAlloc, initRecord, "two-finger drag", 1)
            .takeUnretainedValue()
        let steps = 12
        for finger in fingers {
            guard let alloc = pathClass.perform(NSSelectorFromString("alloc"))?.takeUnretainedValue() else {
                return "XCPointerEventPath could not be allocated"
            }
            let path = call(alloc, initTouch, as: InitTouch.self)(alloc, initTouch, finger.from, 0).takeUnretainedValue()
            for step in 1...steps {
                let fraction = Double(step) / Double(steps)
                let point = CGPoint(x: finger.from.x + (finger.to.x - finger.from.x) * fraction,
                                    y: finger.from.y + (finger.to.y - finger.from.y) * fraction)
                call(path, moveTo, as: MoveTo.self)(path, moveTo, point, duration * fraction)
            }
            call(path, liftUp, as: LiftUp.self)(path, liftUp, duration + 0.05)
            _ = record.perform(addPath, with: path)
        }
        guard let session = sessionClass.perform(shared)?.takeUnretainedValue() else {
            return "XCTRunnerDaemonSession.sharedSession is nil"
        }
        let done = DispatchSemaphore(value: 0)
        call(session, synthesize, as: Synthesize.self)(session, synthesize, record, { _, _ in done.signal() })
        guard done.wait(timeout: .now() + duration + 10) == .success else { return "the event was never acknowledged" }
        return nil
    }
}
