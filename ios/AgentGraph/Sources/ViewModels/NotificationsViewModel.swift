// NotificationsViewModel — Unread count, mark read, periodic polling

import Foundation
import Observation

@Observable @MainActor
final class NotificationsViewModel {
    var notifications: [NotificationResponse] = []
    var unreadCount = 0
    var isLoading = false
    var error: String?

    func loadNotifications() async {
        isLoading = true
        error = nil

        do {
            let response = try await APIService.shared.getNotifications()
            notifications = response.notifications
            unreadCount = response.unreadCount
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    func markRead(id: UUID) async {
        do {
            _ = try await APIService.shared.markNotificationRead(id: id)
            if let index = notifications.firstIndex(where: { $0.id == id }) {
                let old = notifications[index]
                notifications[index] = NotificationResponse(
                    id: old.id,
                    kind: old.kind,
                    title: old.title,
                    body: old.body,
                    referenceId: old.referenceId,
                    isRead: true,
                    createdAt: old.createdAt
                )
                unreadCount = max(0, unreadCount - 1)
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func markAllRead() async {
        do {
            _ = try await APIService.shared.markAllNotificationsRead()
            notifications = notifications.map {
                NotificationResponse(
                    id: $0.id, kind: $0.kind, title: $0.title,
                    body: $0.body, referenceId: $0.referenceId,
                    isRead: true, createdAt: $0.createdAt
                )
            }
            unreadCount = 0
        } catch {
            self.error = error.localizedDescription
        }
    }

    // #21: Periodic polling every 30s
    func startPolling() async {
        while !Task.isCancelled {
            do {
                unreadCount = try await APIService.shared.getUnreadCount()
            } catch {
                // Silently fail for polling
            }
            try? await Task.sleep(for: .seconds(30))
        }
    }

    func pollUnreadCount() async {
        do {
            unreadCount = try await APIService.shared.getUnreadCount()
        } catch {
            // Silently fail for polling
        }
    }
}
