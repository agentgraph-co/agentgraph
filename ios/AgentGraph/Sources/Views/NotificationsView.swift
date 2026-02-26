// NotificationsView — Notification list with tap-to-navigate routing

import SwiftUI

struct NotificationsView: View {
    @State private var viewModel = NotificationsViewModel()

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if viewModel.isLoading && viewModel.notifications.isEmpty {
                LoadingStateView(state: .loading)
            } else if viewModel.notifications.isEmpty {
                LoadingStateView(state: .empty(message: "No notifications yet"))
            } else {
                ScrollView {
                    LazyVStack(spacing: AGSpacing.sm) {
                        ForEach(viewModel.notifications) { notification in
                            notificationButton(notification)
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
            }
        }
        .navigationTitle("Notifications")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            if viewModel.unreadCount > 0 {
                ToolbarItem(placement: .primaryAction) {
                    Button("Read All") {
                        Task { await viewModel.markAllRead() }
                    }
                    .font(AGTypography.sm)
                    .tint(.agPrimary)
                }
            }
        }
        .navigationDestination(for: PostNavigation.self) { nav in
            PostDetailView(postId: nav.postId)
        }
        .navigationDestination(for: EntityNavigation.self) { nav in
            ProfileDetailView(entityId: nav.entityId)
        }
        .navigationDestination(for: ConversationNavigation.self) { nav in
            // Navigate to conversations list when tapping a message notification
            ConversationsListView()
        }
        .refreshable {
            await viewModel.loadNotifications()
        }
        .task {
            await viewModel.loadNotifications()
        }
    }

    @ViewBuilder
    private func notificationButton(_ notification: NotificationResponse) -> some View {
        if let destination = notificationDestination(notification) {
            switch destination {
            case .post(let postId):
                NavigationLink(value: PostNavigation(postId: postId)) {
                    notificationRow(notification)
                }
                .buttonStyle(.plain)
                .simultaneousGesture(TapGesture().onEnded {
                    if !notification.isRead {
                        Task { await viewModel.markRead(id: notification.id) }
                    }
                })
            case .entity(let entityId):
                NavigationLink(value: EntityNavigation(entityId: entityId)) {
                    notificationRow(notification)
                }
                .buttonStyle(.plain)
                .simultaneousGesture(TapGesture().onEnded {
                    if !notification.isRead {
                        Task { await viewModel.markRead(id: notification.id) }
                    }
                })
            case .conversation:
                NavigationLink(value: ConversationNavigation(conversationId: UUID())) {
                    notificationRow(notification)
                }
                .buttonStyle(.plain)
                .simultaneousGesture(TapGesture().onEnded {
                    if !notification.isRead {
                        Task { await viewModel.markRead(id: notification.id) }
                    }
                })
            }
        } else {
            // No destination — just mark read on tap
            Button {
                if !notification.isRead {
                    Task { await viewModel.markRead(id: notification.id) }
                }
            } label: {
                notificationRow(notification)
            }
            .buttonStyle(.plain)
        }
    }

    private enum NotificationDestination {
        case post(UUID)
        case entity(UUID)
        case conversation
    }

    private func notificationDestination(_ notification: NotificationResponse) -> NotificationDestination? {
        guard let refId = notification.referenceId, let uuid = UUID(uuidString: refId) else {
            return nil
        }

        switch notification.kind {
        case "reply", "vote", "mention":
            return .post(uuid)
        case "follow", "endorsement", "review":
            return .entity(uuid)
        case "message":
            return .conversation
        default:
            return nil
        }
    }

    private func notificationRow(_ notification: NotificationResponse) -> some View {
        GlassCard {
            HStack(alignment: .top, spacing: AGSpacing.md) {
                Image(systemName: notificationIcon(notification.kind))
                    .font(.system(size: 20))
                    .foregroundStyle(notification.isRead ? Color.agMuted : Color.agPrimary)
                    .frame(width: 28)

                VStack(alignment: .leading, spacing: AGSpacing.xs) {
                    Text(notification.title)
                        .font(AGTypography.sm)
                        .fontWeight(notification.isRead ? .regular : .semibold)
                        .foregroundStyle(Color.agText)

                    Text(notification.body)
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)

                    Text(DateFormatting.relativeTime(from: notification.createdAt))
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agMuted)
                }

                Spacer()

                if !notification.isRead {
                    Circle()
                        .fill(Color.agPrimary)
                        .frame(width: 8, height: 8)
                }
            }
        }
    }

    private func notificationIcon(_ kind: String) -> String {
        switch kind {
        case "follow": return "person.badge.plus"
        case "reply": return "arrowshape.turn.up.left"
        case "vote": return "arrow.up.circle"
        case "mention": return "at"
        case "endorsement": return "checkmark.seal"
        case "review": return "star"
        case "moderation": return "shield"
        case "message": return "envelope"
        default: return "bell"
        }
    }
}
