// ConversationViewModel — Messages for a single conversation

import Foundation
import Observation

@Observable @MainActor
final class ConversationViewModel {
    var messages: [DMMessageResponse] = []
    var isLoading = false
    var isSending = false
    var error: String?
    var hasMore = false

    func load(conversationId: UUID) async {
        isLoading = true
        error = nil
        do {
            let response = try await APIService.shared.getConversationMessages(conversationId: conversationId)
            guard !Task.isCancelled else { return }
            // API returns newest first; reverse for chat order (oldest at top)
            messages = response.messages.reversed()
            hasMore = response.hasMore
        } catch {
            if !Task.isCancelled { self.error = error.localizedDescription }
        }
        isLoading = false
    }

    func loadOlder(conversationId: UUID) async {
        guard hasMore, !isLoading, let oldest = messages.first else { return }
        isLoading = true
        do {
            let response = try await APIService.shared.getConversationMessages(
                conversationId: conversationId,
                before: oldest.id
            )
            guard !Task.isCancelled else { return }
            messages.insert(contentsOf: response.messages.reversed(), at: 0)
            hasMore = response.hasMore
        } catch {
            // Non-critical
        }
        isLoading = false
    }

    func send(conversationId: UUID, recipientId: UUID, content: String) async -> Bool {
        isSending = true
        defer { isSending = false }
        do {
            let msg = try await APIService.shared.sendMessage(recipientId: recipientId, content: content)
            guard !Task.isCancelled else { return false }
            messages.append(msg)
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func deleteMessage(conversationId: UUID, messageId: UUID) async {
        do {
            try await APIService.shared.deleteMessage(conversationId: conversationId, messageId: messageId)
            messages.removeAll { $0.id == messageId }
        } catch {
            self.error = error.localizedDescription
        }
    }
}
