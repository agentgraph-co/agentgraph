// PasswordStrengthView — Shared password strength indicator

import SwiftUI

enum PasswordStrength {
    case none, weak, medium, strong

    var bars: Int {
        switch self {
        case .none: return 0
        case .weak: return 1
        case .medium: return 2
        case .strong: return 3
        }
    }

    var label: String {
        switch self {
        case .none: return ""
        case .weak: return "Weak"
        case .medium: return "Fair"
        case .strong: return "Strong"
        }
    }

    var color: Color {
        switch self {
        case .none: return .agMuted
        case .weak: return .agDanger
        case .medium: return .agWarning
        case .strong: return .agSuccess
        }
    }
}

struct PasswordStrengthView: View {
    let strength: PasswordStrength

    var body: some View {
        HStack(spacing: AGSpacing.xs) {
            ForEach(0..<3, id: \.self) { i in
                RoundedRectangle(cornerRadius: 2)
                    .fill(i < strength.bars ? strength.color : Color.agMuted.opacity(0.3))
                    .frame(height: 4)
            }
            if !strength.label.isEmpty {
                Text(strength.label)
                    .font(AGTypography.xs)
                    .foregroundStyle(strength.color)
            }
        }
    }
}
