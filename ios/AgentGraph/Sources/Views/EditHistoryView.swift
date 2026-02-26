// EditHistoryView — Shows the edit history for a post

import SwiftUI

struct EditHistoryView: View {
    let postId: UUID

    @State private var edits: [PostEditEntry] = []
    @State private var isLoading = false
    @State private var error: String?

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if isLoading && edits.isEmpty {
                LoadingStateView(state: .loading)
            } else if edits.isEmpty {
                LoadingStateView(state: .empty(message: "No edit history"))
            } else {
                ScrollView {
                    LazyVStack(spacing: AGSpacing.md) {
                        ForEach(edits) { edit in
                            GlassCard {
                                VStack(alignment: .leading, spacing: AGSpacing.sm) {
                                    HStack {
                                        Text("Edited")
                                            .font(AGTypography.sm)
                                            .fontWeight(.semibold)
                                            .foregroundStyle(Color.agText)
                                        Spacer()
                                        Text(DateFormatting.relativeTime(from: edit.editedAt))
                                            .font(AGTypography.xs)
                                            .foregroundStyle(Color.agMuted)
                                    }

                                    VStack(alignment: .leading, spacing: AGSpacing.xs) {
                                        Text("Before:")
                                            .font(AGTypography.xs)
                                            .fontWeight(.medium)
                                            .foregroundStyle(Color.agDanger)
                                        Text(edit.previousContent)
                                            .font(AGTypography.sm)
                                            .foregroundStyle(Color.agMuted)
                                            .lineLimit(5)
                                    }

                                    Divider().background(Color.agBorder)

                                    VStack(alignment: .leading, spacing: AGSpacing.xs) {
                                        Text("After:")
                                            .font(AGTypography.xs)
                                            .fontWeight(.medium)
                                            .foregroundStyle(Color.agSuccess)
                                        Text(edit.newContent)
                                            .font(AGTypography.sm)
                                            .foregroundStyle(Color.agText)
                                            .lineLimit(5)
                                    }
                                }
                            }
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
            }
        }
        .navigationTitle("Edit History")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .task {
            await load()
        }
    }

    private func load() async {
        isLoading = true
        error = nil
        do {
            let response = try await APIService.shared.getPostEditHistory(postId: postId)
            guard !Task.isCancelled else { return }
            edits = response.edits
        } catch {
            if !Task.isCancelled { self.error = error.localizedDescription }
        }
        isLoading = false
    }
}
