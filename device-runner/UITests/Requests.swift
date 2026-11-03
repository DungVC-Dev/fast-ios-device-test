import Foundation

// XCUIDevice rejects assigning `.unspecified` (raw value 0) even though it may report that
// value before a test changes appearance. Keep this logic independent of XCTest so it can be
// checked on the Mac with the rest of the runner's pure logic.
enum AppearancePolicy {
    static func requested(_ value: Any?) -> String? {
        guard let value = value as? String, value == "light" || value == "dark" else { return nil }
        return value
    }

    static func shouldRestore(previousRawValue: Int) -> Bool {
        previousRawValue != 0
    }
}

// What a `do` request needs at its end.
enum Requests {
    // A last step that reads the tree (a wait, a dump, an `expect`, a scroll that found its
    // target, a tap_nearest that waited for success) already left a fresh read: the closing
    // read, which settles up to 1.5 s with the idle wait off, adds nothing.
    static func endsWithRead(_ action: [String: Any]) -> Bool {
        if action["expect"] != nil { return true }
        switch action["type"] as? String {
        case "wait", "wait_change", "wait_absent", "assert_absent", "dump", "scroll_to": return true
        case "tap_nearest": return action["success"] != nil
        default: return false
        }
    }
}
