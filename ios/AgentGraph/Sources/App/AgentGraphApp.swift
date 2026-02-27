// AgentGraph — iOS App Entry Point with Auth Gate + Splash Screen

import SwiftUI

enum DeepLinkDestination: Equatable {
    case resetPassword(token: String)
    case verifyEmail(token: String)
}

struct DeepLinkWrapper: Identifiable {
    let id = UUID()
    let destination: DeepLinkDestination
}

@main @MainActor
struct AgentGraphApp: App {
    @State private var auth = AuthViewModel()
    @State private var envManager = EnvironmentManager()
    @State private var deepLinkDestination: DeepLinkDestination?
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            Group {
                if auth.isCheckingSession {
                    // #14: Splash screen prevents login flash on cold launch
                    splashScreen
                } else if auth.canAccessApp {
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
            .onChange(of: scenePhase) { _, newPhase in
                Task {
                    switch newPhase {
                    case .background:
                        await auth.disconnectWebSocket()
                    case .active:
                        if auth.isAuthenticated {
                            await auth.reconnectWebSocket()
                        }
                    default:
                        break
                    }
                }
            }
            .onOpenURL { url in
                handleDeepLink(url)
            }
            .sheet(item: Binding(
                get: { deepLinkDestination.map { DeepLinkWrapper(destination: $0) } },
                set: { _ in deepLinkDestination = nil }
            )) { wrapper in
                switch wrapper.destination {
                case .resetPassword(let token):
                    ResetPasswordView(token: token)
                case .verifyEmail(let token):
                    VerifyEmailView(token: token)
                }
            }
        }
    }

    private func handleDeepLink(_ url: URL) {
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let host = url.host else { return }

        let queryItems = components.queryItems ?? []
        let token = queryItems.first(where: { $0.name == "token" })?.value

        switch host {
        case "reset-password":
            if let token {
                deepLinkDestination = .resetPassword(token: token)
            }
        case "verify-email":
            if let token {
                deepLinkDestination = .verifyEmail(token: token)
            }
        default:
            break
        }
    }

    private var splashScreen: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()
            VStack(spacing: AGSpacing.lg) {
                Image("AppLogo")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 80, height: 80)
                    .clipShape(RoundedRectangle(cornerRadius: AGRadii.lg))
                Text("AgentGraph")
                    .font(AGTypography.hero)
                    .foregroundStyle(Color.agText)
                ProgressView()
                    .tint(.agPrimary)
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

            Tab("Graph", systemImage: "point.3.connected.trianglepath.dotted", value: 2) {
                GraphView()
            }

            Tab("Profile", systemImage: "person.circle.fill", value: 3) {
                ProfileView()
            }
        }
        .tint(.agPrimary)
    }
}
