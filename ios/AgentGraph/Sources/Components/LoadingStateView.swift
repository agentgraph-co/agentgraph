// LoadingStateView — Loading/empty/error states

import SwiftUI

struct LoadingStateView: View {
    enum State {
        case loading
        case empty(message: String)
        case error(message: String, retry: (() async -> Void)?)
    }

    let state: State

    var body: some View {
        VStack(spacing: AGSpacing.lg) {
            switch state {
            case .loading:
                ProgressView()
                    .tint(.agPrimary)
                    .scaleEffect(1.2)
                Text("Loading...")
                    .font(AGTypography.base)
                    .foregroundStyle(Color.agMuted)

            case .empty(let message):
                Image(systemName: "tray")
                    .font(.system(size: 40))
                    .foregroundStyle(Color.agMuted)
                Text(message)
                    .font(AGTypography.base)
                    .foregroundStyle(Color.agMuted)
                    .multilineTextAlignment(.center)

            case .error(let message, let retry):
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 40))
                    .foregroundStyle(Color.agDanger)
                Text(message)
                    .font(AGTypography.base)
                    .foregroundStyle(Color.agMuted)
                    .multilineTextAlignment(.center)
                if let retry {
                    Button {
                        Task { await retry() }
                    } label: {
                        Text("Retry")
                            .font(AGTypography.sm)
                            .fontWeight(.semibold)
                            .foregroundStyle(Color.agPrimary)
                            // Ensure 44pt minimum tap target
                            .frame(minWidth: 44, minHeight: 44)
                            .contentShape(Rectangle())
                    }
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, AGSpacing.huge)
    }
}
