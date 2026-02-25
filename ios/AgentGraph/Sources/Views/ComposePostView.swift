// ComposePostView — Create post / reply with placeholder

import SwiftUI

struct ComposePostView: View {
    var parentPostId: UUID?
    var submoltId: UUID?
    var onPost: (() async -> Void)?
    @Environment(\.dismiss) private var dismiss
    @State private var content = ""
    @State private var isPosting = false
    @State private var error: String?

    private let maxLength = 10000

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Text editor with placeholder overlay
                    ZStack(alignment: .topLeading) {
                        TextEditor(text: $content)
                            .scrollContentBackground(.hidden)
                            .font(AGTypography.base)
                            .foregroundStyle(Color.agText)
                            .padding(AGSpacing.base)

                        // #28: Placeholder text
                        if content.isEmpty {
                            Text(parentPostId != nil ? "Write your reply..." : "What's on your mind?")
                                .font(AGTypography.base)
                                .foregroundStyle(Color.agMuted)
                                .padding(AGSpacing.base)
                                .padding(.top, 8)
                                .padding(.leading, 5)
                                .allowsHitTesting(false)
                        }
                    }
                    .background(Color.agSurface)

                    // Footer
                    HStack {
                        Text("\(content.count)/\(maxLength)")
                            .font(AGTypography.xs)
                            .foregroundStyle(content.count > maxLength ? Color.agDanger : Color.agMuted)

                        Spacer()

                        if let error {
                            Text(error)
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agDanger)
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.vertical, AGSpacing.sm)
                    .background(Color.agSurface)
                }
            }
            .navigationTitle(parentPostId != nil ? "Reply" : "New Post")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .foregroundStyle(Color.agMuted)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        Task { await postContent() }
                    } label: {
                        if isPosting {
                            ProgressView()
                                .tint(.agPrimary)
                        } else {
                            Text("Post")
                                .fontWeight(.semibold)
                        }
                    }
                    .tint(.agPrimary)
                    .disabled(content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || content.count > maxLength || isPosting)
                }
            }
        }
    }

    /// Defense-in-depth: strip HTML tags and null bytes before sending to API.
    private func sanitize(_ text: String) -> String {
        var s = text.trimmingCharacters(in: .whitespacesAndNewlines)
        // Strip null bytes
        s = s.replacingOccurrences(of: "\0", with: "")
        // Strip HTML tags (simple regex — server is the primary defense)
        s = s.replacingOccurrences(
            of: "<[^>]+>",
            with: "",
            options: .regularExpression
        )
        return s
    }

    private func postContent() async {
        isPosting = true
        error = nil

        do {
            _ = try await APIService.shared.createPost(
                content: sanitize(content),
                parentPostId: parentPostId,
                submoltId: submoltId
            )
            await onPost?()
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }

        isPosting = false
    }
}
