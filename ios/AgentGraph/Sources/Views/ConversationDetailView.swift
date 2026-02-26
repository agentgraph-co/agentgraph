// ConversationDetailView — Chat thread with message bubbles

import SwiftUI

struct ConversationDetailView: View {
    let conversationId: UUID
    let otherEntityId: UUID
    let otherEntityName: String

    @Environment(AuthViewModel.self) private var auth
    @State private var viewModel = ConversationViewModel()
    @State private var messageText = ""

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            VStack(spacing: 0) {
                if viewModel.isLoading && viewModel.messages.isEmpty {
                    Spacer()
                    LoadingStateView(state: .loading)
                    Spacer()
                } else if viewModel.messages.isEmpty && !viewModel.isLoading {
                    Spacer()
                    LoadingStateView(state: .empty(message: "No messages yet. Say hello!"))
                    Spacer()
                } else {
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(spacing: AGSpacing.sm) {
                                if viewModel.hasMore {
                                    Button {
                                        Task { await viewModel.loadOlder(conversationId: conversationId) }
                                    } label: {
                                        Text("Load older messages")
                                            .font(AGTypography.sm)
                                            .foregroundStyle(Color.agPrimary)
                                    }
                                    .padding(.vertical, AGSpacing.sm)
                                }

                                ForEach(viewModel.messages) { message in
                                    messageBubble(message)
                                        .id(message.id)
                                }
                            }
                            .padding(.horizontal, AGSpacing.base)
                            .padding(.vertical, AGSpacing.sm)
                        }
                        .onChange(of: viewModel.messages.count) {
                            if let last = viewModel.messages.last {
                                withAnimation {
                                    proxy.scrollTo(last.id, anchor: .bottom)
                                }
                            }
                        }
                    }
                }

                // Input bar
                inputBar
            }
        }
        .navigationTitle(otherEntityName)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .task {
            await viewModel.load(conversationId: conversationId)
        }
    }

    private func messageBubble(_ message: DMMessageResponse) -> some View {
        let isMine = message.senderId == auth.currentUser?.id

        return HStack {
            if isMine { Spacer(minLength: 60) }

            VStack(alignment: isMine ? .trailing : .leading, spacing: 2) {
                Text(message.content)
                    .font(AGTypography.base)
                    .foregroundStyle(isMine ? .white : Color.agText)
                    .padding(.horizontal, AGSpacing.md)
                    .padding(.vertical, AGSpacing.sm)
                    .background(
                        RoundedRectangle(cornerRadius: AGRadii.lg)
                            .fill(isMine ? Color.agPrimary : Color.agSurface)
                    )

                Text(message.createdAt.prefix(16).replacingOccurrences(of: "T", with: " "))
                    .font(AGTypography.xs)
                    .foregroundStyle(Color.agMuted)
            }
            .contextMenu {
                if isMine {
                    Button(role: .destructive) {
                        Task {
                            await viewModel.deleteMessage(
                                conversationId: conversationId,
                                messageId: message.id
                            )
                        }
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                }
            }

            if !isMine { Spacer(minLength: 60) }
        }
    }

    private var inputBar: some View {
        HStack(spacing: AGSpacing.sm) {
            TextField("Message...", text: $messageText)
                .textFieldStyle(.plain)
                .font(AGTypography.base)
                .foregroundStyle(Color.agText)
                .padding(.horizontal, AGSpacing.md)
                .padding(.vertical, AGSpacing.sm)
                .background(Color.agSurface)
                .clipShape(RoundedRectangle(cornerRadius: AGRadii.lg))
                .overlay(
                    RoundedRectangle(cornerRadius: AGRadii.lg)
                        .stroke(Color.agBorder, lineWidth: 1)
                )

            Button {
                let text = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !text.isEmpty else { return }
                let content = text
                messageText = ""
                Task {
                    _ = await viewModel.send(
                        conversationId: conversationId,
                        recipientId: otherEntityId,
                        content: content
                    )
                }
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 32))
                    .foregroundStyle(
                        messageText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            ? Color.agMuted
                            : Color.agPrimary
                    )
            }
            .disabled(messageText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isSending)
        }
        .padding(.horizontal, AGSpacing.base)
        .padding(.vertical, AGSpacing.sm)
        .background(Color.agBackground)
    }
}
