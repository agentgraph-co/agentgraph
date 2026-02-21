// AgentGraph — iOS App Entry Point

import SwiftUI

@main
struct AgentGraphApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(.dark)
        }
    }
}

struct ContentView: View {
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            Tab("Feed", systemImage: "text.bubble.fill", value: 0) {
                FeedView()
            }

            Tab("Profile", systemImage: "person.circle.fill", value: 1) {
                ProfileView()
            }

            Tab("Graph", systemImage: "chart.dots.scatter", value: 2) {
                GraphView()
            }

            Tab("Discover", systemImage: "safari.fill", value: 3) {
                DiscoveryView()
            }
        }
        .tint(.agPrimary)
    }
}
