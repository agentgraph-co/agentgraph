// AgentManagementView — Register, list, and delete own agents

import SwiftUI

struct AgentManagementView: View {
    @State private var agents: [AgentResponse] = []
    @State private var isLoading = false
    @State private var error: String?
    @State private var showCreate = false
    @State private var apiKeyToShow: String?

    // Create form state
    @State private var newName = ""
    @State private var newBio = ""
    @State private var newCapabilities = ""
    @State private var newAutonomy = 3

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if isLoading && agents.isEmpty {
                LoadingStateView(state: .loading)
            } else if agents.isEmpty {
                LoadingStateView(state: .empty(message: "No agents registered yet. Create your first agent!"))
            } else {
                ScrollView {
                    LazyVStack(spacing: AGSpacing.sm) {
                        ForEach(agents) { agent in
                            agentRow(agent)
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
            }
        }
        .navigationTitle("My Agents")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showCreate = true
                } label: {
                    Image(systemName: "plus")
                }
                .tint(.agPrimary)
            }
        }
        .sheet(isPresented: $showCreate) {
            createAgentSheet
        }
        .alert("API Key Created", isPresented: Binding(
            get: { apiKeyToShow != nil },
            set: { if !$0 { apiKeyToShow = nil } }
        )) {
            Button("Copy") {
                if let key = apiKeyToShow {
                    UIPasteboard.general.string = key
                }
            }
            Button("OK") { }
        } message: {
            Text("Save this key — it won't be shown again:\n\(apiKeyToShow ?? "")")
        }
        .refreshable {
            await load()
        }
        .task {
            await load()
        }
    }

    private var agentInitialCircle: some View {
        Circle()
            .fill(
                LinearGradient(
                    colors: [.agViolet, .agAccent],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .frame(width: 36, height: 36)
            .overlay(
                Image(systemName: "cpu")
                    .font(AGTypography.sm)
                    .foregroundStyle(.white)
            )
    }

    private func agentRow(_ agent: AgentResponse) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.sm) {
                HStack {
                    if let avatarUrlStr = agent.avatarUrl,
                       let url = URL(string: avatarUrlStr) {
                        AsyncImage(url: url) { image in
                            image
                                .resizable()
                                .scaledToFill()
                        } placeholder: {
                            agentInitialCircle
                        }
                        .frame(width: 36, height: 36)
                        .clipShape(Circle())
                    } else {
                        agentInitialCircle
                    }

                    VStack(alignment: .leading, spacing: 2) {
                        Text(agent.displayName)
                            .font(AGTypography.base)
                            .fontWeight(.medium)
                            .foregroundStyle(Color.agText)
                        Text(agent.didWeb)
                            .font(AGTypography.xs)
                            .foregroundStyle(Color.agMuted)
                    }

                    Spacer()

                    if agent.isActive {
                        Circle()
                            .fill(Color.agSuccess)
                            .frame(width: 8, height: 8)
                    }
                }

                if !agent.bioMarkdown.isEmpty {
                    Text(agent.bioMarkdown)
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)
                        .lineLimit(2)
                }

                if !agent.capabilities.isEmpty {
                    HStack(spacing: AGSpacing.xs) {
                        ForEach(agent.capabilities.prefix(3), id: \.self) { cap in
                            Text(cap)
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agAccent)
                                .padding(.horizontal, AGSpacing.sm)
                                .padding(.vertical, 2)
                                .background(
                                    Capsule().fill(Color.agAccent.opacity(0.15))
                                )
                        }
                    }
                }
            }
        }
        .contextMenu {
            Button(role: .destructive) {
                Task { await deleteAgent(agent.id) }
            } label: {
                Label("Delete Agent", systemImage: "trash")
            }
        }
    }

    private var createAgentSheet: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        GlassCard {
                            VStack(alignment: .leading, spacing: AGSpacing.md) {
                                formLabel("Display Name")
                                TextField("Agent name", text: $newName)
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

                                formLabel("Bio")
                                TextEditor(text: $newBio)
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

                                formLabel("Capabilities (comma-separated)")
                                TextField("reasoning, code_generation", text: $newCapabilities)
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

                                formLabel("Autonomy Level (1-5)")
                                Picker("Autonomy", selection: $newAutonomy) {
                                    ForEach(1...5, id: \.self) { level in
                                        Text("\(level)").tag(level)
                                    }
                                }
                                .pickerStyle(.segmented)
                            }
                        }

                        if let error {
                            Text(error)
                                .font(AGTypography.sm)
                                .foregroundStyle(Color.agDanger)
                        }
                    }
                    .padding(.horizontal, AGSpacing.xl)
                    .padding(.top, AGSpacing.lg)
                }
            }
            .navigationTitle("Register Agent")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showCreate = false }
                        .foregroundStyle(Color.agMuted)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        Task { await createAgent() }
                    }
                    .fontWeight(.semibold)
                    .tint(.agPrimary)
                    .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
    }

    private func formLabel(_ text: String) -> some View {
        Text(text)
            .font(AGTypography.sm)
            .foregroundStyle(Color.agMuted)
    }

    private func load() async {
        isLoading = true
        error = nil
        do {
            let response = try await APIService.shared.getMyAgents()
            guard !Task.isCancelled else { return }
            agents = response.agents
        } catch {
            if !Task.isCancelled { self.error = error.localizedDescription }
        }
        isLoading = false
    }

    private func createAgent() async {
        let caps = newCapabilities.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        do {
            let response = try await APIService.shared.createAgent(
                displayName: newName.trimmingCharacters(in: .whitespacesAndNewlines),
                capabilities: caps,
                autonomyLevel: newAutonomy,
                bioMarkdown: newBio.trimmingCharacters(in: .whitespacesAndNewlines)
            )
            agents.insert(response.agent, at: 0)
            apiKeyToShow = response.apiKey
            newName = ""
            newBio = ""
            newCapabilities = ""
            newAutonomy = 3
            showCreate = false
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func deleteAgent(_ id: UUID) async {
        do {
            _ = try await APIService.shared.deleteAgent(agentId: id)
            agents.removeAll { $0.id == id }
        } catch {
            self.error = error.localizedDescription
        }
    }
}
