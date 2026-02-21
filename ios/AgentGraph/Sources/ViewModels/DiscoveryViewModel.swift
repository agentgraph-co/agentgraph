// DiscoveryViewModel — Debounced search

import Foundation
import Observation

@Observable @MainActor
final class DiscoveryViewModel {
    var searchText = ""
    var searchResults: SearchResponse?
    var isSearching = false
    var error: String?
    private var searchTask: Task<Void, Never>?

    func onSearchTextChanged(_ text: String) {
        searchText = text
        searchTask?.cancel()

        guard !text.trimmingCharacters(in: .whitespaces).isEmpty else {
            searchResults = nil
            isSearching = false
            error = nil
            return
        }

        searchTask = Task {
            // 300ms debounce
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            await performSearch(query: text)
        }
    }

    func performSearch(query: String) async {
        isSearching = true
        error = nil

        do {
            let results = try await APIService.shared.search(query: query)
            if !Task.isCancelled {
                searchResults = results
            }
        } catch {
            if !Task.isCancelled {
                self.error = error.localizedDescription
            }
        }

        // #3 (DiscoveryVM): Only clear loading if not cancelled
        if !Task.isCancelled {
            isSearching = false
        }
    }
}
