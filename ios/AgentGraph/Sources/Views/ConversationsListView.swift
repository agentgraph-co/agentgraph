// ConversationsListView — List of DM conversations

import SwiftUI

struct ConversationsListView: View {
    @Environment(AuthViewModel.self) private var auth
    @State private var viewModel = MessagesViewModel()

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if viewModel.isLoading && viewModel.conversations.isEmpty {
                LoadingStateView(state: .loading)
            } else if viewModel.conversations.isEmpty {
                LoadingStateView(state: .empty(message: "No conversations yet. Send a message from someone's profile!"))
            } else {
                ScrollView {
                    LazyVStack(spacing: AGSpacing.sm) {
                        ForEach(viewModel.conversations) { conversation in
                            NavigationLink(value: conversation) {
                                conversationRow(conversation)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
            }
        }
        .navigationTitle("Messages")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .navigationDestination(for: ConversationResponse.self) { conversation in
            ConversationDetailView(
                conversationId: conversation.id,
                otherEntityId: conversation.otherEntityId,
                otherEntityName: conversation.otherEntityName
            )
        }
        .refreshable {
            await viewModel.load()
        }
        .task {
            await viewModel.load()
        }
    }

    private func conversationRow(_ conversation: ConversationResponse) -> some View {
        GlassCard {
            HStack(spacing: AGSpacing.md) {
                // Avatar
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [.agPrimary, .agAccent],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 44, height: 44)
                    .overlay(
                        Text(String(conversation.otherEntityName.prefix(1)).uppercased())
                            .font(.system(size: 18, weight: .bold))
                            .foregroundStyle(.white)
                    )

                VStack(alignment: .leading, spacing: AGSpacing.xs) {
                    HStack {
                        Text(conversation.otherEntityName)
                            .font(AGTypography.base)
                            .fontWeight(conversation.unreadCount > 0 ? .semibold : .medium)
                            .foregroundStyle(Color.agText)

                        Spacer()

                        Text(conversation.lastMessageAt.prefix(10))
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                    }

                    HStack {
                        if let preview = conversation.lastMessagePreview {
                            Text(preview)
                                .font(AGTypography.sm)
                                .foregroundStyle(Color.agMuted)
                                .lineLimit(1)
                        }

                        Spacer()

                        if conversation.unreadCount > 0 {
                            Text("\(conversation.unreadCount)")
                                .font(AGTypography.xs)
                                .fontWeight(.bold)
                                .foregroundStyle(.white)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Capsule().fill(Color.agPrimary))
                        }
                    }
                }
            }
        }
    }
}

// Conform ConversationResponse to Hashable for NavigationLink(value:)
extension ConversationResponse: Hashable {
    static func == (lhs: ConversationResponse, rhs: ConversationResponse) -> Bool {
        lhs.id == rhs.id
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }
}
