import Network
import XCTest

// Runs fastDeviceTest flows on a physical device. `testFlow` runs one flow passed as
// base64 JSON in FAST_FLOW; `testServe` stays alive and takes newline-delimited JSON
// requests on FAST_PORT so later flows and single actions skip the xcodebuild launch.
// Selectors and action names mirror the Simulator engine so one flow runs on both.
final class FlowRunner: XCTestCase {
    struct Failure: Error { let message: String }

    struct Node {
        let label: String
        let type: String
        let frame: CGRect
        // Frame of the nearest enclosing cell; nil outside lists.
        let cell: CGRect?
    }

    private var apps: [String: XCUIApplication] = [:]
    private var current: XCUIApplication?
    private var promptLabels: [String] = []
    private var lastLabels: [String] = []
    private var screenBounds = CGRect.infinite
    private var inlineScreenshots = false
    private var screenshots: [[String: String]] = []
    private let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")

    func testFlow() throws {
        continueAfterFailure = false
        let report: [String: Any]
        do {
            report = runFlow(try decode(ProcessInfo.processInfo.environment["FAST_FLOW"]))
        } catch {
            report = ["status": "fail", "step": "prepare", "error": message(error)]
        }
        attachText("zz_result.json", json(report))
    }

    func testServe() throws {
        continueAfterFailure = true
        inlineScreenshots = true
        let environment = ProcessInfo.processInfo.environment
        let port = NWEndpoint.Port(rawValue: UInt16(environment["FAST_PORT"] ?? "") ?? 8765) ?? 8765
        let idleLimit = Double(environment["FAST_IDLE"] ?? "1800") ?? 1800
        let server = try RequestServer(port: port)
        server.start()
        var lastRequest = Date()
        var isStopped = false
        while !isStopped && Date().timeIntervalSince(lastRequest) < idleLimit {
            guard let request = server.next() else {
                RunLoop.current.run(until: Date().addingTimeInterval(0.05))
                continue
            }
            lastRequest = Date()
            screenshots = []
            var response = handle(request.body, isStopped: &isStopped)
            response["screenshots"] = screenshots
            request.reply(json(response, pretty: false))
        }
        server.stop()
    }
}

// MARK: - Requests
private extension FlowRunner {
    func handle(_ body: Data, isStopped: inout Bool) -> [String: Any] {
        do {
            guard let request = try JSONSerialization.jsonObject(with: body) as? [String: Any],
                  let operation = request["op"] as? String else {
                throw Failure(message: "request needs an op")
            }
            switch operation {
            case "ping":
                return ["status": "pass", "pong": true]
            case "stop":
                isStopped = true
                return ["status": "pass"]
            case "flow":
                return runFlow(request["flow"] as? [String: Any] ?? [:])
            case "action":
                let action = request["action"] as? [String: Any] ?? [:]
                if let bundleID = action["app"] as? String { current = application(bundleID) }
                guard current != nil else { throw Failure(message: "no current app: add \"app\" to the action") }
                let result = try execute(action, index: 1) ?? [:]
                _ = snapshotNodes()
                return ["status": "pass", "result": result, "labels": lastLabels]
            case "actions":
                return runActions(request["actions"] as? [[String: Any]] ?? [])
            default:
                throw Failure(message: "unknown op '\(operation)'")
            }
        } catch {
            if current != nil { _ = snapshotNodes() }
            return ["status": "fail", "error": message(error), "labels": lastLabels]
        }
    }

    // Stops at the first failing step, like a flow, but keeps the app state it found.
    func runActions(_ actions: [[String: Any]]) -> [String: Any] {
        var results: [[String: Any]] = []
        for (offset, action) in actions.enumerated() {
            let index = offset + 1
            do {
                if let result = try execute(action, index: index) {
                    results.append(["step": index].merging(result) { first, _ in first })
                }
            } catch {
                if current != nil { _ = snapshotNodes() }
                return ["status": "fail", "step": index, "error": message(error), "results": results, "labels": lastLabels]
            }
        }
        _ = snapshotNodes()
        return ["status": "pass", "results": results, "labels": lastLabels]
    }

    func runFlow(_ flow: [String: Any]) -> [String: Any] {
        var results: [[String: Any]] = []
        var step = "launch"
        let setup = flow["setup"] as? [String: Any] ?? [:]
        let previousAppearance = XCUIDevice.shared.appearance
        defer { XCUIDevice.shared.appearance = previousAppearance }
        do {
            let app = flow["app"] as? [String: Any] ?? [:]
            guard let bundleID = app["bundle_id"] as? String else { throw Failure(message: "missing app.bundle_id") }
            promptLabels = setup["optional_permission_labels"] as? [String] ?? []
            switch setup["appearance"] as? String {
            case "dark": XCUIDevice.shared.appearance = .dark
            case "light": XCUIDevice.shared.appearance = .light
            default: break
            }

            let target = application(bundleID)
            current = target
            target.launchArguments = setup["launch_arguments"] as? [String] ?? []
            if setup["launch"] as? Bool ?? true {
                target.launch()
            } else {
                target.activate()
            }

            let actions = flow["actions"] as? [[String: Any]] ?? []
            for (offset, action) in actions.enumerated() {
                let index = offset + 1
                step = String(format: "%02d_%@", index, action["type"] as? String ?? "unknown")
                if let result = try execute(action, index: index) {
                    results.append(["step": index].merging(result) { first, _ in first })
                }
            }
            return ["status": "pass", "results": results, "labels": lastLabels]
        } catch {
            capture("failure")
            if let current { attachText("failure-ui.txt", current.debugDescription) }
            return ["status": "fail", "step": step, "error": message(error), "results": results, "labels": lastLabels]
        }
    }
}

// MARK: - Actions
private extension FlowRunner {
    func execute(_ action: [String: Any], index: Int) throws -> [String: Any]? {
        guard let kind = action["type"] as? String else { throw Failure(message: "action \(index) has no type") }
        if let bundleID = action["app"] as? String { current = application(bundleID) }
        guard let app = current else { throw Failure(message: "no current app") }
        let timeout = number(action["timeout"]) ?? 6
        let postDelay = number(action["post_delay"]) ?? 0.15

        switch kind {
        case "activate":
            app.activate()
        case "launch":
            if let arguments = action["launch_arguments"] as? [String] { app.launchArguments = arguments }
            app.launch()
        case "terminate":
            app.terminate()
        case "wait":
            _ = try waitNodes(timeout) { nodes in nodes.contains { self.matches($0, action) } }
        case "wait_absent":
            do {
                _ = try waitNodes(timeout) { nodes in !nodes.contains { self.matches($0, action) } }
            } catch {
                throw Failure(message: "'\(action["label"] ?? "selector")' is still on screen after \(timeout)s; visible labels: \(lastLabels)")
            }
        case "assert_absent":
            let deadline = Date().addingTimeInterval(number(action["seconds"]) ?? 3)
            repeat {
                let nodes = try waitNodes(timeout) { _ in true }
                if nodes.contains(where: { matches($0, action) }) {
                    throw Failure(message: "'\(action["label"] ?? "selector")' appeared while asserting absence; visible labels: \(lastLabels)")
                }
                Thread.sleep(forTimeInterval: 0.3)
            } while Date() < deadline
        case "tap_label":
            guard let label = action["label"] as? String else { throw Failure(message: "tap_label needs label") }
            var selector: [String: Any] = ["label": label, "element_type": action["element_type"] ?? "Button"]
            selector["frame"] = action["frame"]
            let nodes: [Node]
            if action["optional"] as? Bool ?? false {
                nodes = snapshotNodes()
            } else {
                nodes = try waitNodes(timeout) { nodes in nodes.contains { self.matches($0, selector) } }
            }
            if let node = sorted(nodes.filter { matches($0, selector) }, by: ["y", "x"]).first {
                tap(node.frame.midX, node.frame.midY, postDelay)
            }
        case "tap_first":
            let nodes = try waitNodes(timeout) { nodes in nodes.contains { self.matches($0, action) } }
            let keys = action["sort"] as? [String] ?? ["y", "x"]
            guard let node = sorted(nodes.filter { matches($0, action) }, by: keys).first else {
                throw Failure(message: "no node matched tap_first at action \(index)")
            }
            tap(node.frame.midX, node.frame.midY, postDelay)
        case "tap_nearest":
            try tapNearest(action, timeout: timeout, postDelay: postDelay)
        case "tap_point":
            tap(number(action["x"]) ?? 0, number(action["y"]) ?? 0, postDelay)
        case "swipe":
            try swipe(action)
            Thread.sleep(forTimeInterval: postDelay)
        case "scroll_to":
            let limit = Int(number(action["max_swipes"]) ?? 6)
            var swipes = 0
            while !snapshotNodes().contains(where: { matches($0, action) }) {
                guard swipes < limit else {
                    throw Failure(message: "'\(action["label"] ?? action["label_contains"] ?? "selector")' not found after \(limit) swipes; visible labels: \(lastLabels)")
                }
                try swipe(["direction": action["direction"] ?? "up"])
                Thread.sleep(forTimeInterval: 0.4)
                swipes += 1
            }
        case "type_text":
            guard let text = action["text"] as? String else { throw Failure(message: "type_text needs text") }
            app.typeText(text)
            Thread.sleep(forTimeInterval: postDelay)
        case "pause":
            Thread.sleep(forTimeInterval: number(action["seconds"]) ?? 1)
        case "screenshot":
            let name = action["name"] as? String ?? String(format: "step-%02d", index)
            capture(name)
            return ["screenshot": name]
        case "dump":
            let nodes = try waitNodes(timeout) { _ in true }
            let name = action["name"] as? String ?? String(format: "step-%02d", index)
            attachText("\(name)-ui.txt", app.debugDescription)
            return ["name": name, "labels": visibleLabels(nodes), "nodes": visibleNodes(nodes)]
        default:
            throw Failure(message: "unsupported action type '\(kind)' on device")
        }
        return nil
    }
}

// MARK: - Gestures
private extension FlowRunner {
    // Port of the Simulator engine's tap_nearest: pick the target closest to one anchor
    // along `axis`, so a row's trailing button (an ⓘ, a Delete) is found by the row's text.
    func tapNearest(_ action: [String: Any], timeout: Double, postDelay: Double) throws {
        guard let target = action["target"] as? [String: Any], let anchor = action["anchor"] as? [String: Any] else {
            throw Failure(message: "tap_nearest needs target and anchor selectors")
        }
        let axis = action["axis"] as? String ?? "y"
        func resolveAndTap() throws {
            let nodes = try waitNodes(timeout) { nodes in
                nodes.contains { self.matches($0, target) } && nodes.contains { self.matches($0, anchor) }
            }
            let targets = nodes.filter { matches($0, target) }
            // XCUITest nests a text in containers with the same label and frame; those are one anchor.
            let anchorValues = Set(nodes.filter { matches($0, anchor) }.map { value($0, axis).rounded() })
            guard anchorValues.count == 1, let anchorValue = anchorValues.first else {
                throw Failure(message: "tap_nearest requires one anchor and at least one target; got \(anchorValues.count)/\(targets.count)")
            }
            guard let nearest = targets.min(by: { abs(value($0, axis) - anchorValue) < abs(value($1, axis) - anchorValue) }) else {
                throw Failure(message: "tap_nearest found no target")
            }
            tap(nearest.frame.midX, nearest.frame.midY, postDelay)
        }

        try resolveAndTap()
        guard let success = action["success"] as? [String: Any] else { return }
        let dismissals = action["dismiss"] as? [[String: Any]]
            ?? (action["dismiss"] as? [String: Any]).map { [$0] } ?? []
        let nodes = try waitNodes(timeout) { nodes in
            nodes.contains { self.matches($0, success) }
                || dismissals.contains { selector in nodes.contains { self.matches($0, selector) } }
        }
        if nodes.contains(where: { matches($0, success) }) { return }
        let blockers = dismissals.flatMap { selector in nodes.filter { matches($0, selector) } }
        guard let blocker = sorted(blockers, by: ["y", "x"]).first else {
            throw Failure(message: "tap_nearest reached neither success nor dismiss selector")
        }
        tap(blocker.frame.midX, blocker.frame.midY, postDelay)
        try resolveAndTap()
        _ = try waitNodes(timeout) { nodes in nodes.contains { self.matches($0, success) } }
    }

    // `from`/`to` points, or a `direction` the finger moves in ("up" scrolls content down).
    func swipe(_ action: [String: Any]) throws {
        if let from = action["from"] as? [Any], let to = action["to"] as? [Any],
           let fromX = number(from.first), let fromY = number(from.last),
           let toX = number(to.first), let toY = number(to.last) {
            point(fromX, fromY).press(forDuration: 0.05, thenDragTo: point(toX, toY))
            return
        }
        if screenBounds.isInfinite { _ = snapshotNodes() }
        let bounds = screenBounds
        let x = Double(bounds.midX), y = Double(bounds.midY)
        let top = Double(bounds.minY + bounds.height * 0.3), bottom = Double(bounds.minY + bounds.height * 0.7)
        let left = Double(bounds.minX + bounds.width * 0.2), right = Double(bounds.minX + bounds.width * 0.8)
        let points: (Double, Double, Double, Double)
        switch action["direction"] as? String {
        case "up": points = (x, bottom, x, top)
        case "down": points = (x, top, x, bottom)
        case "left": points = (right, y, left, y)
        case "right": points = (left, y, right, y)
        default: throw Failure(message: "swipe needs from/to [x, y] or direction up|down|left|right")
        }
        point(points.0, points.1).press(forDuration: 0.05, thenDragTo: point(points.2, points.3))
    }
}

// MARK: - Hierarchy
private extension FlowRunner {
    func application(_ bundleID: String) -> XCUIApplication {
        if let app = apps[bundleID] { return app }
        let app = XCUIApplication(bundleIdentifier: bundleID)
        apps[bundleID] = app
        return app
    }

    func snapshotNodes() -> [Node] {
        guard let root = try? current?.snapshot() else { return [] }
        screenBounds = root.frame
        var nodes: [Node] = []
        func walk(_ element: XCUIElementSnapshot, cell: CGRect?) {
            nodes.append(Node(label: element.label, type: typeName(element.elementType), frame: element.frame, cell: cell))
            let childCell = element.elementType == .cell ? element.frame : cell
            element.children.forEach { walk($0, cell: childCell) }
        }
        walk(root, cell: nil)
        lastLabels = visibleLabels(nodes)
        return nodes
    }

    func waitNodes(_ timeout: Double, until predicate: ([Node]) -> Bool) throws -> [Node] {
        let deadline = Date().addingTimeInterval(timeout)
        var nodes: [Node] = []
        repeat {
            if dismissPrompt() { continue }
            nodes = snapshotNodes()
            if predicate(nodes) { return nodes }
            Thread.sleep(forTimeInterval: 0.2)
        } while Date() < deadline
        throw Failure(message: "timed out waiting for UI selector; visible labels: \(lastLabels)")
    }

    // Permission alerts on a device belong to SpringBoard, not the app under test.
    func dismissPrompt() -> Bool {
        guard !promptLabels.isEmpty else { return false }
        for owner in [springboard] + [current].compactMap({ $0 }) {
            for label in promptLabels {
                let button = owner.alerts.buttons[label]
                if button.exists {
                    button.tap()
                    Thread.sleep(forTimeInterval: 0.3)
                    return true
                }
            }
        }
        return false
    }

    func matches(_ node: Node, _ selector: [String: Any]) -> Bool {
        if let label = selector["label"] as? String, node.label != label { return false }
        if let fragment = selector["label_contains"] as? String, !node.label.contains(fragment) { return false }
        if selector["label_is_empty"] as? Bool ?? false, !node.label.isEmpty { return false }
        if let type = selector["element_type"] as? String, !typeMatches(node.type, type) { return false }
        let limits = selector["frame"] as? [String: Any] ?? [:]
        let values: [String: Double] = [
            "x": node.frame.minX, "y": node.frame.minY,
            "width": node.frame.width, "height": node.frame.height,
        ]
        for (name, actual) in values {
            if let minimum = number(limits["min_\(name)"]), actual < minimum { return false }
            if let maximum = number(limits["max_\(name)"]), actual > maximum { return false }
        }
        return node.frame.width > 0 && node.frame.height > 0 && isOnScreen(node)
    }

    // SwiftUI keeps hidden tabs and off-screen pages in the tree; only a node whose centre is
    // on screen can receive the tap. Text in a list row that is scrolled away reports a made-up
    // frame near the top of the list, so it also has to sit inside its own cell.
    func isOnScreen(_ node: Node) -> Bool {
        let centre = CGPoint(x: node.frame.midX, y: node.frame.midY)
        guard screenBounds.contains(centre) else { return false }
        return node.cell.map { $0.insetBy(dx: -8, dy: -8).contains(centre) } ?? true
    }

    // AXe names (Simulator flows) mapped onto XCUIElement types.
    func typeMatches(_ actual: String, _ expected: String) -> Bool {
        switch expected {
        case "RadioButton": return ["Button", "RadioButton"].contains(actual)
        case "Heading": return ["StaticText", "Other"].contains(actual)
        case "TextField": return ["TextField", "SecureTextField", "TextView"].contains(actual)
        default: return actual == expected
        }
    }

    func typeName(_ type: XCUIElement.ElementType) -> String {
        switch type {
        case .button: return "Button"
        case .staticText: return "StaticText"
        case .textField: return "TextField"
        case .secureTextField: return "SecureTextField"
        case .textView: return "TextView"
        case .image: return "Image"
        case .cell: return "Cell"
        case .switch: return "Switch"
        case .radioButton: return "RadioButton"
        case .link: return "Link"
        case .tab: return "Tab"
        case .alert: return "Alert"
        default: return "Other"
        }
    }

    func visibleLabels(_ nodes: [Node], limit: Int = 40) -> [String] {
        var seen = Set<String>()
        var labels: [String] = []
        for node in sorted(nodes, by: ["y", "x"])
        where !node.label.isEmpty && isOnScreen(node) {
            if seen.insert(node.label).inserted { labels.append(node.label) }
            if labels.count == limit { break }
        }
        return labels
    }

    // Frames use the selector keys (x, y, width, height), so a dump feeds `frame` bounds,
    // `tap_point` and `tap_nearest` directly.
    func visibleNodes(_ nodes: [Node], limit: Int = 200) -> [[String: Any]] {
        sorted(nodes, by: ["y", "x"])
            .filter { node in
                (!node.label.isEmpty || node.type != "Other") && node.frame.width > 0 && node.frame.height > 0
                    && isOnScreen(node)
            }
            .prefix(limit)
            .map { node in
                [
                    "label": node.label, "type": node.type,
                    "frame": [
                        "x": Double(node.frame.minX.rounded()), "y": Double(node.frame.minY.rounded()),
                        "width": Double(node.frame.width.rounded()), "height": Double(node.frame.height.rounded()),
                    ],
                ] as [String: Any]
            }
    }

    func sorted(_ nodes: [Node], by keys: [String]) -> [Node] {
        nodes.sorted { lhs, rhs in
            for key in keys {
                let left = value(lhs, key)
                let right = value(rhs, key)
                if left != right { return left < right }
            }
            return false
        }
    }

    func value(_ node: Node, _ key: String) -> Double {
        switch key {
        case "x": return node.frame.minX
        case "width": return node.frame.width
        case "height": return node.frame.height
        default: return node.frame.minY
        }
    }
}

// MARK: - Input and Output
private extension FlowRunner {
    func decode(_ encoded: String?) throws -> [String: Any] {
        guard let encoded, let data = Data(base64Encoded: encoded),
              let flow = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw Failure(message: "FAST_FLOW is missing or not base64 JSON")
        }
        return flow
    }

    func point(_ x: Double, _ y: Double) -> XCUICoordinate {
        let app = current ?? springboard
        return app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: x, dy: y))
    }

    func tap(_ x: Double, _ y: Double, _ postDelay: Double) {
        point(x, y).tap()
        Thread.sleep(forTimeInterval: postDelay)
    }

    func number(_ value: Any?) -> Double? {
        (value as? NSNumber)?.doubleValue
    }

    func message(_ error: Error) -> String {
        (error as? Failure)?.message ?? "\(error)"
    }

    // Server mode returns PNGs in the reply; one-shot mode leaves them in the xcresult.
    func capture(_ name: String) {
        let screenshot = XCUIScreen.main.screenshot()
        if inlineScreenshots {
            screenshots.append(["name": name, "png": screenshot.pngRepresentation.base64EncodedString()])
            return
        }
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    func attachText(_ name: String, _ text: String) {
        guard !inlineScreenshots else { return }
        let attachment = XCTAttachment(string: text)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    func json(_ object: [String: Any], pretty: Bool = true) -> String {
        let options: JSONSerialization.WritingOptions = pretty ? [.prettyPrinted] : []
        guard let data = try? JSONSerialization.data(withJSONObject: object, options: options) else { return "{}" }
        return String(decoding: data, as: UTF8.self)
    }
}
