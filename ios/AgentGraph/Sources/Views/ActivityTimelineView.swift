// ActivityTimelineView — Entity activity timeline with cursor pagination

import SwiftUI

struct ActivityTimelineView: View {
    let entityId: UUID

    @State private var activities: [ActivityItemResponse] = []
    @State private var isLoading = false
    @State private var error: String?
    @State private var nextCursor: String?

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if isLoading && activities.isEmpty {
                LoadingStateView(state: .loading)
            } else if activities.isEmpty {
                LoadingStateView(state: .empty(message: "No activity yet"))
            } else {
                ScrollView {
                    LazyVStack(spacing: AGSpacing.sm) {
                        ForEach(activities) { activity in
                            activityRow(activity)
                                .onAppear {
                                    if activity.id == activities.last?.id && nextCursor != nil {
                                        Task { await loadMore() }
                                    }
                                }
                        }

                        if isLoading {
                            ProgressView()
                                .tint(.agPrimary)
                                .padding()
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
            }
        }
        .navigationTitle("Activity")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .refreshable {
            await load()
        }
        .task {
            await load()
        }
    }

    private func activityRow(_ activity: ActivityItemResponse) -> some View {
        GlassCard {
            HStack(alignment: .top, spacing: AGSpacing.md) {
                Image(systemName: activityIcon(activity.type))
                    .font(.system(size: 20))
                    .foregroundStyle(activityColor(activity.type))
                    .frame(width: 28)

                VStack(alignment: .leading, spacing: AGSpacing.xs) {
                    Text(activity.summary)
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agText)
                        .lineLimit(2)

                    HStack(spacing: AGSpacing.xs) {
                        Text(activity.type.capitalized)
                            .font(AGTypography.xs)
                            .fontWeight(.medium)
                            .foregroundStyle(activityColor(activity.type))
                            .padding(.horizontal, AGSpacing.sm)
                            .padding(.vertical, 2)
                            .background(
                                Capsule().fill(activityColor(activity.type).opacity(0.15))
                            )

                        Text(DateFormatting.relativeTime(from: activity.createdAt))
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                    }
                }

                Spacer()
            }
        }
    }

    private func activityIcon(_ type: String) -> String {
        switch type {
        case "post": return "square.and.pencil"
        case "reply": return "arrowshape.turn.up.left"
        case "vote": return "arrow.up.circle"
        case "follow": return "person.badge.plus"
        case "endorsement": return "checkmark.seal"
        case "review": return "star"
        default: return "clock"
        }
    }

    private func activityColor(_ type: String) -> Color {
        switch type {
        case "post": return .agPrimary
        case "reply": return .agAccent
        case "vote": return .agSuccess
        case "follow": return .agViolet
        case "endorsement": return .agWarning
        case "review": return .agWarning
        default: return .agMuted
        }
    }

    private func load() async {
        isLoading = true
        error = nil
        do {
            let response = try await APIService.shared.getActivity(entityId: entityId)
            guard !Task.isCancelled else { return }
            activities = response.activities
            nextCursor = response.nextCursor
        } catch {
            if !Task.isCancelled { self.error = error.localizedDescription }
        }
        isLoading = false
    }

    private func loadMore() async {
        guard !isLoading, let cursor = nextCursor else { return }
        isLoading = true
        do {
            let response = try await APIService.shared.getActivity(entityId: entityId, before: cursor)
            guard !Task.isCancelled else { return }
            activities.append(contentsOf: response.activities)
            nextCursor = response.nextCursor
        } catch {
            // Non-critical
        }
        isLoading = false
    }
}
