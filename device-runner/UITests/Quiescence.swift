import ObjectiveC
import XCTest

// XCUITest waits for the app to go idle before and after every event; a screen that
// animates forever (a GIF, a ticking clock) makes each tap pay the whole idle timeout,
// measured at 2.4 s per tap on an app with an animated dashboard. WebDriverAgent avoids this by swizzling the
// private wait on XCUIApplicationProcess; flows opt in with `setup.wait_for_idle: false`
// (or `--no-idle-wait` on `fastDeviceTest do`) and rely on their own selector waits.
// The selectors are looked up at runtime, so an Xcode that renames them simply keeps
// waiting: `disable()` then returns false and nothing else changes.
enum Quiescence {
    private static var originals: [(Method, IMP)] = []

    @discardableResult
    static func disable() -> Bool {
        guard originals.isEmpty else { return true }
        guard let processClass = NSClassFromString("XCUIApplicationProcess") else { return false }
        let single = NSSelectorFromString("waitForQuiescenceIncludingAnimationsIdle:")
        if let method = class_getInstanceMethod(processClass, single) {
            let block: @convention(block) (AnyObject, Bool) -> Void = { _, _ in }
            originals.append((method, method_setImplementation(method, imp_implementationWithBlock(block))))
        }
        let preEvent = NSSelectorFromString("waitForQuiescenceIncludingAnimationsIdle:isPreEvent:")
        if let method = class_getInstanceMethod(processClass, preEvent) {
            let block: @convention(block) (AnyObject, Bool, Bool) -> Void = { _, _, _ in }
            originals.append((method, method_setImplementation(method, imp_implementationWithBlock(block))))
        }
        return !originals.isEmpty
    }

    static func restore() {
        for (method, original) in originals {
            method_setImplementation(method, original)
        }
        originals = []
    }
}
