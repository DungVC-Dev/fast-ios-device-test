import Foundation

// What a `do` request needs at its end.
enum Requests {
    // A last step that reads the tree (a wait, a dump, an `expect`, a scroll that found its
    // target, a tap_nearest that waited for success) already left a fresh read: the closing
    // read, which settles up to 1.5 s with the idle wait off, adds nothing.
    static func endsWithRead(_ action: [String: Any]) -> Bool {
        if action["expect"] != nil { return true }
        switch action["type"] as? String {
        case "wait", "wait_absent", "assert_absent", "dump", "scroll_to": return true
        case "tap_nearest": return action["success"] != nil
        default: return false
        }
    }
}
