// PurchaseHistoryView — Transaction history list

import SwiftUI

struct PurchaseHistoryView: View {
    @State private var transactions: [MarketplaceTransactionResponse] = []
    @State private var isLoading = false
    @State private var error: String?

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if isLoading && transactions.isEmpty {
                LoadingStateView(state: .loading)
            } else if transactions.isEmpty {
                LoadingStateView(state: .empty(message: "No purchase history yet"))
            } else {
                ScrollView {
                    LazyVStack(spacing: AGSpacing.sm) {
                        ForEach(transactions) { transaction in
                            transactionRow(transaction)
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
            }
        }
        .navigationTitle("Purchase History")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .refreshable {
            await load()
        }
        .task {
            await load()
        }
    }

    private func transactionRow(_ transaction: MarketplaceTransactionResponse) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.sm) {
                HStack {
                    Text(transaction.listingTitle)
                        .font(AGTypography.base)
                        .fontWeight(.medium)
                        .foregroundStyle(Color.agText)

                    Spacer()

                    Text(transaction.formattedAmount)
                        .font(AGTypography.base)
                        .fontWeight(.semibold)
                        .foregroundStyle(
                            transaction.amountCents == 0 ? Color.agSuccess : Color.agText
                        )
                }

                HStack {
                    Text(transaction.listingCategory.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agPrimary)
                        .padding(.horizontal, AGSpacing.sm)
                        .padding(.vertical, 2)
                        .background(
                            Capsule().fill(Color.agPrimary.opacity(0.15))
                        )

                    statusBadge(transaction.status)

                    Spacer()

                    Text(DateFormatting.relativeTime(from: transaction.createdAt))
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agMuted)
                }
            }
        }
    }

    private func statusBadge(_ status: String) -> some View {
        let color: Color = {
            switch status {
            case "completed": return .agSuccess
            case "pending": return .agWarning
            case "failed", "refunded": return .agDanger
            default: return .agMuted
            }
        }()

        return Text(status.capitalized)
            .font(AGTypography.xs)
            .foregroundStyle(color)
            .padding(.horizontal, AGSpacing.sm)
            .padding(.vertical, 2)
            .background(
                Capsule().fill(color.opacity(0.15))
            )
    }

    private func load() async {
        isLoading = true
        error = nil
        do {
            let response = try await APIService.shared.getPurchaseHistory()
            guard !Task.isCancelled else { return }
            transactions = response.transactions
        } catch {
            if !Task.isCancelled { self.error = error.localizedDescription }
        }
        isLoading = false
    }
}
