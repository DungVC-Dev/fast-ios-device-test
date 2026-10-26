import Foundation

// Which button the runner taps on a permission prompt. `optional_permission_labels` holds
// bare button labels and rules {"title_contains": …, "tap": …}. A rule whose title matches
// owns the prompt: when its button is missing nothing is tapped, so a bare "Don’t Allow"
// never answers a prompt a rule was written for. Bare labels answer in the order they are
// declared. Mirrors prompt_choice in the Simulator engine (fast_ui.py).
enum PromptRules {
    static func choice(title: String, buttons: [String], entries: [Any]) -> String? {
        var owned = false
        for case let rule as [String: Any] in entries {
            guard let fragment = rule["title_contains"] as? String,
                  title.range(of: fragment, options: .caseInsensitive) != nil else { continue }
            owned = true
            if let tap = rule["tap"] as? String, buttons.contains(tap) { return tap }
        }
        if owned { return nil }
        for case let label as String in entries where buttons.contains(label) {
            return label
        }
        return nil
    }
}
