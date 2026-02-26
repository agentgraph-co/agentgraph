// EditPostView — Edit an existing post's content

import SwiftUI

struct EditPostView: View {
    let postId: UUID
    let currentContent: String
    var onEdited: ((PostResponse) -> Void)?

    @Environment(\.dismiss) private var dismiss
    @State private var content: String
    @State private var isSubmitting = false
    @State private var error: String?

    private let maxLength = 10000

    init(postId: UUID, currentContent: String, onEdited: ((PostResponse) -> Void)? = nil) {
        self.postId = postId
        self.currentContent = currentContent
        self.onEdited = onEdited
        self._content = State(initialValue: currentContent)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                VStack(spacing: 0) {
                    ZStack(alignment: .topLeading) {
                        TextEditor(text: $content)
                            .scrollContentBackground(.hidden)
                            .font(AGTypography.base)
                            .foregroundStyle(Color.agText)
                            .padding(AGSpacing.base)
                    }
                    .background(Color.agSurface)

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
            .navigationTitle("Edit Post")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .foregroundStyle(Color.agMuted)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        Task { await save() }
                    } label: {
                        if isSubmitting {
                            ProgressView()
                                .tint(.agPrimary)
                        } else {
                            Text("Save")
                                .fontWeight(.semibold)
                        }
                    }
                    .tint(.agPrimary)
                    .disabled(
                        content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        || content == currentContent
                        || content.count > maxLength
                        || isSubmitting
                    )
                }
            }
        }
    }

    private func save() async {
        isSubmitting = true
        error = nil
        do {
            let sanitized = sanitize(content)
            let updated = try await APIService.shared.editPost(postId: postId, content: sanitized)
            onEdited?(updated)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
        isSubmitting = false
    }

    private func sanitize(_ text: String) -> String {
        var s = text.trimmingCharacters(in: .whitespacesAndNewlines)
        s = s.replacingOccurrences(of: "\0", with: "")
        s = s.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
        return s
    }
}
