import Foundation

// Checks for the device runner's pure logic (PromptRules.swift, Settle.swift). The runner
// itself only runs on an iPhone, so test_fast_ui.RunnerLogicTests compiles these two files
// with this one for the Mac and runs the result.
@main
struct RunnerLogicChecks {
    static var failures = 0

    static func check(_ condition: Bool, _ name: String) {
        if !condition {
            failures += 1
            print("FAIL \(name)")
        }
    }

    static func main() {
        checkPromptRules()
        checkSettle()
        if failures > 0 { exit(1) }
        print("OK")
    }

    static func checkPromptRules() {
        let tracking = "Allow “App” to track your activity across other companies’ apps and websites?"
        let notifications = "“App” Would Like to Send You Notifications"
        let location = "Allow “App” to use your location?"
        let rules: [Any] = [
            ["title_contains": "notifications", "tap": "Allow"],
            ["title_contains": "track", "tap": "Ask App Not to Track"],
        ]
        check(PromptRules.choice(title: tracking, buttons: ["Ask App Not to Track", "Allow"], entries: rules)
              == "Ask App Not to Track", "a button name shared by two prompts follows the tracking rule")
        check(PromptRules.choice(title: notifications, buttons: ["Don’t Allow", "Allow"], entries: rules)
              == "Allow", "the notifications rule picks Allow")
        check(PromptRules.choice(title: location, buttons: ["Allow Once", "Allow While Using App", "Don’t Allow"],
                                 entries: [["title_contains": "Location", "tap": "Always Allow"], "Don’t Allow"])
              == nil, "a bare label never answers a prompt a rule was written for")
        check(PromptRules.choice(title: notifications, buttons: ["Don’t Allow", "Allow"], entries: ["Allow", "Don’t Allow"])
              == "Allow", "bare labels answer in the order they are declared")
        check(PromptRules.choice(title: notifications, buttons: ["Don’t Allow", "Allow"], entries: [])
              == nil, "nothing declared taps nothing")
    }

    static func checkSettle() {
        var clock = 0.0
        var reads = [1, 2, 2, 3]
        let settled = Settle.stable(first: 0, timeout: 5, read: { reads.removeFirst() }, same: ==,
                                    now: { clock }, sleep: { clock += $0 })
        check(settled == 2 && reads == [3], "settles on the first value read twice in a row")

        reads = [5, 9]
        let unchanged = Settle.stable(first: 5, timeout: 5, read: { reads.removeFirst() }, same: ==,
                                      now: { clock }, sleep: { clock += $0 })
        check(unchanged == 5 && reads == [9], "one read is enough when it agrees with the first value")

        clock = 0
        var count = 0
        let moving = Settle.stable(first: 0, timeout: 1, interval: 0.1, read: { count += 1; return count }, same: ==,
                                   now: { clock }, sleep: { clock += $0 })
        check(moving == count && (10...12).contains(count), "a value that never settles stops at the timeout")
    }
}
