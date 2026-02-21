// PostCard — Extracted, interactive post card with vote, bookmark, time-ago

import SwiftUI

struct PostCard: View {
    let post: PostResponse
    var onVote: ((String) -> Void)?
    var onBookmark: (() -> Void)?

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
                            Text(String(post.author.displayName.prefix(1)).uppercased())
                                .font(AGTypography.sm)
                                .fontWeight(.bold)
                                .foregroundStyle(.white)
                        )

                    VStack(alignment: .leading, spacing: 2) {
                        Text(post.author.displayName)
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

                // Content
                Text(post.content)
                    .font(AGTypography.base)
                    .foregroundStyle(Color.agText)
                    .lineSpacing(4)

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
                    // Vote
                    HStack(spacing: AGSpacing.xs) {
                        Button {
                            onVote?("up")
                        } label: {
                            Image(systemName: post.userVote == "up" ? "arrow.up.circle.fill" : "arrow.up")
                                .foregroundStyle(post.userVote == "up" ? Color.agSuccess : Color.agMuted)
                        }

                        Text("\(post.voteCount)")
                            .font(AGTypography.sm)
                            .foregroundStyle(Color.agMuted)

                        Button {
                            onVote?("down")
                        } label: {
                            Image(systemName: post.userVote == "down" ? "arrow.down.circle.fill" : "arrow.down")
                                .foregroundStyle(post.userVote == "down" ? Color.agDanger : Color.agMuted)
                        }
                    }

                    // Replies
                    Label("\(post.replyCount)", systemImage: "bubble.left")
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)

                    Spacer()

                    // Bookmark
                    Button {
                        onBookmark?()
                    } label: {
                        Image(systemName: post.isBookmarked ? "bookmark.fill" : "bookmark")
                            .foregroundStyle(post.isBookmarked ? Color.agAccent : Color.agMuted)
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
