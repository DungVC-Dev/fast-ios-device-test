import Foundation

// With XCUITest's idle wait switched off nothing waits for a push, a sheet or a launch to
// finish animating, so the runner reads the screen until two reads in a row agree.
enum Settle {
    // Reads until a read agrees with the one before it (the first read is compared with
    // `first`), or until `timeout` passes; returns the last value read.
    static func stable<T>(
        first: T,
        timeout: Double,
        interval: Double = 0.1,
        read: () -> T,
        same: (T, T) -> Bool,
        now: () -> Double = { Date().timeIntervalSinceReferenceDate },
        sleep: (Double) -> Void = { Thread.sleep(forTimeInterval: $0) }
    ) -> T {
        let deadline = now() + timeout
        var previous = first
        while true {
            let current = read()
            if same(previous, current) || now() >= deadline { return current }
            previous = current
            sleep(interval)
        }
    }
}
