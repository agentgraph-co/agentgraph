// AgentGraph — iOS App Entry Point with Auth Gate

import SwiftUI

@main @MainActor
struct AgentGraphApp: App {
    @State private var auth = AuthViewModel()
    @State private var envManager = EnvironmentManager()

    var body: some Scene {
        WindowGroup {
            Group {
                if auth.canAccessApp {
                    ContentView()
                } else {
                    LoginView()
                }
            }
            .environment(auth)
            .environment(envManager)
            .preferredColorScheme(.dark)
            .task {
                await auth.checkExistingSession()
            }
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

            Tab("Discover", systemImage: "magnifyingglass", value: 1) {
                DiscoveryView()
            }

            Tab("Graph", systemImage: "chart.dots.scatter", value: 2) {
                GraphView()
            }

            Tab("Profile", systemImage: "person.circle.fill", value: 3) {
                ProfileView()
            }
        }
        .tint(.agPrimary)
    }
}
