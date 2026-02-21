// PostCard — Extracted, interactive post card with vote, bookmark, time-ago

import SwiftUI

struct PostCard: View {
    let post: PostResponse
    var lineLimit: Int? = 12
    var onVote: ((String) -> Void)?
    var onBookmark: (() -> Void)?

    // #31: Fallback for empty displayName
    private var authorName: String {
        post.author.displayName.isEmpty ? "Unknown" : post.author.displayName
    }

    var body: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                // Author row
                HStack {
                    Circle()
                        .fill(
                            LinearGradient(
                                colors: [.agPrimary, .agAccent],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 36, height: 36)
                        .overlay(
                            Text(String(authorName.prefix(1)).uppercased())
                                .font(AGTypography.sm)
                                .fontWeight(.bold)
                                .foregroundStyle(.white)
                        )

                    VStack(alignment: .leading, spacing: 2) {
                        Text(authorName)
                            .font(AGTypography.sm)
                            .fontWeight(.medium)
                            .foregroundStyle(Color.agText)
                        HStack(spacing: AGSpacing.xs) {
                            Text(post.author.type.capitalized)
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agMuted)
                            Text(DateFormatting.relativeTime(from: post.createdAt))
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agMuted)
                        }
                    }

                    Spacer()

                    if let trustScore = post.authorTrustScore {
                        TrustBadge(score: trustScore)
                    }
                }

                // Content — #27: Line limit in feed, unlimited in detail
                if let limit = lineLimit {
                    Text(post.content)
                        .font(AGTypography.base)
                        .foregroundStyle(Color.agText)
                        .lineSpacing(4)
                        .lineLimit(limit)
                } else {
                    Text(post.content)
                        .font(AGTypography.base)
                        .foregroundStyle(Color.agText)
                        .lineSpacing(4)
                }

                // Flair
                if let flair = post.flair {
                    Text(flair)
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agAccent)
                        .padding(.horizontal, AGSpacing.sm)
                        .padding(.vertical, 2)
                        .background(
                            Capsule().fill(Color.agAccent.opacity(0.15))
                        )
                }

                // Actions row
                HStack(spacing: AGSpacing.lg) {
                    // Vote — #15: 44pt minimum tap targets
                    HStack(spacing: AGSpacing.xs) {
                        Button {
                            onVote?("up")
                        } label: {
                            Image(systemName: post.userVote == "up" ? "arrow.up.circle.fill" : "arrow.up")
                                .foregroundStyle(post.userVote == "up" ? Color.agSuccess : Color.agMuted)
                                .frame(minWidth: 44, minHeight: 44)
                                .contentShape(Rectangle())
                        }

                        Text("\(post.voteCount)")
                            .font(AGTypography.sm)
                            .foregroundStyle(Color.agMuted)

                        Button {
                            onVote?("down")
                        } label: {
                            Image(systemName: post.userVote == "down" ? "arrow.down.circle.fill" : "arrow.down")
                                .foregroundStyle(post.userVote == "down" ? Color.agDanger : Color.agMuted)
                                .frame(minWidth: 44, minHeight: 44)
                                .contentShape(Rectangle())
                        }
                    }

                    // Replies
                    Label("\(post.replyCount)", systemImage: "bubble.left")
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)

                    Spacer()

                    // Bookmark — #15: 44pt tap target
                    Button {
                        onBookmark?()
                    } label: {
                        Image(systemName: post.isBookmarked ? "bookmark.fill" : "bookmark")
                            .foregroundStyle(post.isBookmarked ? Color.agAccent : Color.agMuted)
                            .frame(minWidth: 44, minHeight: 44)
                            .contentShape(Rectangle())
                    }

                    // Pinned indicator
                    if post.isPinned {
                        Image(systemName: "pin.fill")
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agWarning)
                    }

                    // Edited indicator
                    if post.isEdited {
                        Text("edited")
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                    }
                }
                .font(AGTypography.sm)
            }
        }
    }
}
