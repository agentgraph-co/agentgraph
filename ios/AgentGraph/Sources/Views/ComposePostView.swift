// ComposePostView — Create post / reply

import SwiftUI

struct ComposePostView: View {
    var parentPostId: UUID?
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
                    // Text editor
                    TextEditor(text: $content)
                        .scrollContentBackground(.hidden)
                        .font(AGTypography.base)
                        .foregroundStyle(Color.agText)
                        .padding(AGSpacing.base)
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
                    .disabled(content.trimmingCharacters(in: .whitespaces).isEmpty || content.count > maxLength || isPosting)
                }
            }
        }
    }

    private func postContent() async {
        isPosting = true
        error = nil

        do {
            _ = try await APIService.shared.createPost(content: content, parentPostId: parentPostId)
            await onPost?()
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }

        isPosting = false
    }
}
