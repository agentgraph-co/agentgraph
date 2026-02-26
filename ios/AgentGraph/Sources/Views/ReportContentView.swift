// ReportContentView — Sheet for reporting posts/entities

import SwiftUI

struct ReportContentView: View {
    let targetType: String // "post" or "entity"
    let targetId: UUID
    var onReported: (() -> Void)?

    @Environment(\.dismiss) private var dismiss
    @State private var selectedReason = "spam"
    @State private var details = ""
    @State private var isSubmitting = false
    @State private var error: String?
    @State private var submitted = false

    private let reasons = [
        ("spam", "Spam", "Unsolicited or repetitive content"),
        ("harassment", "Harassment", "Abusive or threatening behavior"),
        ("misinformation", "Misinformation", "False or misleading information"),
        ("off_topic", "Off Topic", "Not relevant to the community"),
        ("other", "Other", "Something else"),
    ]

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        if submitted {
                            successView
                        } else {
                            reportForm
                        }
                    }
                    .padding(.horizontal, AGSpacing.xl)
                    .padding(.top, AGSpacing.lg)
                }
            }
            .navigationTitle("Report")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(submitted ? "Done" : "Cancel") {
                        dismiss()
                    }
                    .foregroundStyle(Color.agMuted)
                }
                if !submitted {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Submit") {
                            Task { await submitReport() }
                        }
                        .fontWeight(.semibold)
                        .tint(.agPrimary)
                        .disabled(isSubmitting)
                    }
                }
            }
        }
    }

    private var reportForm: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.md) {
                Text("Why are you reporting this?")
                    .font(AGTypography.lg)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.agText)

                ForEach(reasons, id: \.0) { value, label, desc in
                    Button {
                        selectedReason = value
                    } label: {
                        HStack(spacing: AGSpacing.sm) {
                            Image(systemName: selectedReason == value ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(selectedReason == value ? Color.agPrimary : Color.agMuted)

                            VStack(alignment: .leading, spacing: 2) {
                                Text(label)
                                    .font(AGTypography.sm)
                                    .fontWeight(.medium)
                                    .foregroundStyle(Color.agText)
                                Text(desc)
                                    .font(AGTypography.xs)
                                    .foregroundStyle(Color.agMuted)
                            }

                            Spacer()
                        }
                        .padding(AGSpacing.sm)
                        .background(
                            RoundedRectangle(cornerRadius: AGRadii.sm)
                                .stroke(
                                    selectedReason == value ? Color.agPrimary : Color.agBorder,
                                    lineWidth: 1
                                )
                        )
                    }
                }

                Text("Additional details (optional)")
                    .font(AGTypography.sm)
                    .foregroundStyle(Color.agMuted)

                TextEditor(text: $details)
                    .scrollContentBackground(.hidden)
                    .font(AGTypography.base)
                    .foregroundStyle(Color.agText)
                    .frame(minHeight: 80)
                    .padding(AGSpacing.md)
                    .background(Color.agSurface)
                    .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                    .overlay(
                        RoundedRectangle(cornerRadius: AGRadii.md)
                            .stroke(Color.agBorder, lineWidth: 1)
                    )

                if let error {
                    Text(error)
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agDanger)
                }
            }
        }
    }

    private var successView: some View {
        GlassCard {
            VStack(spacing: AGSpacing.lg) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundStyle(Color.agSuccess)

                Text("Report Submitted")
                    .font(AGTypography.xl)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.agText)

                Text("Thank you for helping keep AgentGraph safe. Our moderation team will review this report.")
                    .font(AGTypography.base)
                    .foregroundStyle(Color.agMuted)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity)
        }
    }

    private func submitReport() async {
        isSubmitting = true
        error = nil
        do {
            _ = try await APIService.shared.flagContent(
                targetType: targetType,
                targetId: targetId,
                reason: selectedReason,
                details: details.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : details
            )
            submitted = true
            onReported?()
        } catch {
            self.error = error.localizedDescription
        }
        isSubmitting = false
    }
}
