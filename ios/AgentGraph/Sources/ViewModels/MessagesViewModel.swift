// MessagesViewModel — Conversation list + unread count management

import Foundation
import Observation

@Observable @MainActor
final class MessagesViewModel {
    var conversations: [ConversationResponse] = []
    var unreadCount = 0
    var isLoading = false
    var error: String?
    private var offset = 0
    private let pageSize = 20

    var hasMore: Bool {
        conversations.count >= offset
    }

    func load() async {
        isLoading = true
        error = nil
        offset = 0
        do {
            let response = try await APIService.shared.getConversations(limit: pageSize, offset: 0)
            guard !Task.isCancelled else { return }
            conversations = response.conversations
            offset = response.conversations.count
            await loadUnreadCount()
        } catch {
            if !Task.isCancelled { self.error = error.localizedDescription }
        }
        isLoading = false
    }

    func loadMore() async {
        guard !isLoading else { return }
        isLoading = true
        do {
            let response = try await APIService.shared.getConversations(limit: pageSize, offset: offset)
            guard !Task.isCancelled else { return }
            conversations.append(contentsOf: response.conversations)
            offset += response.conversations.count
        } catch {
            // Non-critical
        }
        isLoading = false
    }

    func loadUnreadCount() async {
        do {
            let count = try await APIService.shared.getUnreadMessageCount()
            guard !Task.isCancelled else { return }
            unreadCount = count
        } catch {
            // Non-critical
        }
    }

    func deleteConversation(conversationId: UUID) async {
        do {
            try await APIService.shared.deleteConversation(conversationId: conversationId)
            conversations.removeAll { $0.id == conversationId }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func startPolling() async {
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(30))
            guard !Task.isCancelled else { return }
            await loadUnreadCount()
        }
    }
}
