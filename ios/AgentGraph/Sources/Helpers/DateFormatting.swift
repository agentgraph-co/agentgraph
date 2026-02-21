// DateFormatting — Relative time ("2h ago") helper

import Foundation

enum DateFormatting {
    // #32: Static cached formatter to avoid allocation per call
    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "MMM d"
        return f
    }()

    static func relativeTime(from date: Date) -> String {
        let interval = Date().timeIntervalSince(date)
        let seconds = Int(interval)

        // #31: Handle negative intervals (clock skew)
        guard seconds >= 0 else { return "just now" }

        if seconds < 60 { return "just now" }
        if seconds < 3600 { return "\(seconds / 60)m ago" }
        if seconds < 86400 { return "\(seconds / 3600)h ago" }
        if seconds < 604800 { return "\(seconds / 86400)d ago" }
        if seconds < 2592000 { return "\(seconds / 604800)w ago" }

        return dateFormatter.string(from: date)
    }
}
