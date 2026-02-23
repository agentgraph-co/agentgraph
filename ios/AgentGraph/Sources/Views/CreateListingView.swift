// CreateListingView -- Create a new marketplace listing

import SwiftUI

struct CreateListingView: View {
    var onCreated: (() async -> Void)?
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var description = ""
    @State private var selectedCategory = "service"
    @State private var selectedPricingModel = "free"
    @State private var priceText = ""
    @State private var tagsText = ""
    @State private var isSubmitting = false
    @State private var error: String?

    private let categories = [
        ("service", "Service"),
        ("skill", "Skill"),
        ("integration", "Integration"),
        ("tool", "Tool"),
        ("data", "Data"),
    ]

    private let pricingModels = [
        ("free", "Free"),
        ("one_time", "One-time"),
        ("subscription", "Subscription"),
    ]
    private var priceCents: Int {
        guard selectedPricingModel != "free" else { return 0 }
        return Int((Double(priceText) ?? 0) * 100)
    }

    private var isValid: Bool {
        !title.trimmingCharacters(in: .whitespaces).isEmpty
        && !description.trimmingCharacters(in: .whitespaces).isEmpty
        && (selectedPricingModel == "free" || priceCents > 0)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        GlassCard {
                            VStack(alignment: .leading, spacing: AGSpacing.md) {
                                formLabel("Title")
                                TextField("What are you offering?", text: $title)
                                    .textFieldStyle(.plain)
                                    .font(AGTypography.base)
                                    .foregroundStyle(Color.agText)
                                    .padding(AGSpacing.md)
                                    .background(Color.agSurface)
                                    .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: AGRadii.md)
                                            .stroke(Color.agBorder, lineWidth: 1)
                                    )

                                formLabel("Description")
                                TextEditor(text: $description)
                                    .scrollContentBackground(.hidden)
                                    .font(AGTypography.base)
                                    .foregroundStyle(Color.agText)
                                    .frame(minHeight: 120)
                                    .padding(AGSpacing.md)
                                    .background(Color.agSurface)
                                    .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: AGRadii.md)
                                            .stroke(Color.agBorder, lineWidth: 1)
                                    )

                                formLabel("Category")
                                Picker("Category", selection: $selectedCategory) {
                                    ForEach(categories, id: \.0) { value, label in
                                        Text(label).tag(value)
                                    }
                                }
                                .pickerStyle(.segmented)

                                formLabel("Pricing")
                                Picker("Pricing", selection: $selectedPricingModel) {
                                    ForEach(pricingModels, id: \.0) { value, label in
                                        Text(label).tag(value)
                                    }
                                }
                                .pickerStyle(.segmented)

                                if selectedPricingModel != "free" {
                                    formLabel("Price (USD)")
                                    TextField("0.00", text: $priceText)
                                        .textFieldStyle(.plain)
                                        .font(AGTypography.base)
                                        .foregroundStyle(Color.agText)
                                        .keyboardType(.decimalPad)
                                        .padding(AGSpacing.md)
                                        .background(Color.agSurface)
                                        .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                        .overlay(
                                            RoundedRectangle(cornerRadius: AGRadii.md)
                                                .stroke(Color.agBorder, lineWidth: 1)
                                        )
                                }

                                formLabel("Tags (comma-separated)")
                                TextField("ai, tools, automation", text: $tagsText)
                                    .textFieldStyle(.plain)
                                    .font(AGTypography.base)
                                    .foregroundStyle(Color.agText)
                                    .padding(AGSpacing.md)
                                    .background(Color.agSurface)
                                    .clipShape(RoundedRectangle(cornerRadius: AGRadii.md))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: AGRadii.md)
                                            .stroke(Color.agBorder, lineWidth: 1)
                                    )
                            }
                        }

                        if let error {
                            Text(error)
                                .font(AGTypography.sm)
                                .foregroundStyle(Color.agDanger)
                                .multilineTextAlignment(.center)
                        }
                    }
                    .padding(.horizontal, AGSpacing.xl)
                    .padding(.top, AGSpacing.lg)
                }
            }
            .navigationTitle("New Listing")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .foregroundStyle(Color.agMuted)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        isSubmitting = true
                        error = nil
                        Task {
                            await createListing()
                            isSubmitting = false
                        }
                    }
                    .fontWeight(.semibold)
                    .tint(.agPrimary)
                    .disabled(!isValid || isSubmitting)
                }
            }
        }
    }

    private func formLabel(_ text: String) -> some View {
        Text(text)
            .font(AGTypography.sm)
            .foregroundStyle(Color.agMuted)
    }

    private func createListing() async {
        let tags = tagsText
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }

        do {
            _ = try await APIService.shared.createMarketplaceListing(
                title: title.trimmingCharacters(in: .whitespacesAndNewlines),
                description: description.trimmingCharacters(in: .whitespacesAndNewlines),
                category: selectedCategory,
                tags: tags,
                pricingModel: selectedPricingModel,
                priceCents: priceCents
            )
            await onCreated?()
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
