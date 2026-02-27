// SubmoltsView — Browse, search, and create communities

import SwiftUI

struct SubmoltsView: View {
    @Environment(AuthViewModel.self) private var auth
    @State private var viewModel = SubmoltsViewModel()
    @State private var showCreate = false
    @State private var newName = ""
    @State private var newDescription = ""
    @State private var newTags = ""

    var body: some View {
        ZStack {
            Color.agBackground.ignoresSafeArea()

            if viewModel.isLoading && viewModel.allSubmolts.isEmpty {
                LoadingStateView(state: .loading)
            } else {
                ScrollView {
                    VStack(spacing: AGSpacing.sm) {
                        // Tab picker
                        Picker("Tab", selection: Binding(
                            get: { viewModel.selectedTab },
                            set: {
                                viewModel.selectedTab = $0
                                if $0 == .mine {
                                    Task { await viewModel.loadMySubmolts() }
                                }
                            }
                        )) {
                            ForEach(SubmoltsViewModel.Tab.allCases, id: \.self) { tab in
                                Text(tab.rawValue).tag(tab)
                            }
                        }
                        .pickerStyle(.segmented)
                        .padding(.horizontal, AGSpacing.sm)

                        switch viewModel.selectedTab {
                        case .all:
                            submoltList(viewModel.filteredAll)
                        case .mine:
                            if auth.isAuthenticated {
                                mySubmoltList(viewModel.filteredMy)
                            } else {
                                LoadingStateView(state: .empty(message: "Sign in to see your communities."))
                            }
                        case .trending:
                            submoltList(viewModel.filteredTrending)
                        }

                        if viewModel.isLoading {
                            ProgressView()
                                .tint(.agPrimary)
                                .padding()
                        }
                    }
                    .padding(.horizontal, AGSpacing.base)
                    .padding(.top, AGSpacing.sm)
                }
                .refreshable {
                    await viewModel.load()
                }
            }
        }
        .navigationTitle("Communities")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            if auth.isAuthenticated {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        showCreate = true
                    } label: {
                        Image(systemName: "plus")
                    }
                    .tint(.agPrimary)
                }
            }
        }
        .searchable(
            text: Binding(
                get: { viewModel.searchText },
                set: { viewModel.searchText = $0 }
            ),
            prompt: "Search communities..."
        )
        .navigationDestination(for: UUID.self) { submoltId in
            SubmoltDetailView(submoltId: submoltId)
        }
        .sheet(isPresented: $showCreate) {
            createSubmoltSheet
        }
        .task {
            await viewModel.load()
            if auth.isAuthenticated {
                await viewModel.loadMySubmolts()
            }
        }
    }

    private func submoltList(_ submolts: [SubmoltResponse]) -> some View {
        ForEach(submolts) { submolt in
            NavigationLink(value: submolt.id) {
                submoltCard(name: submolt.displayName, description: submolt.description, memberCount: submolt.memberCount, tags: submolt.tags)
            }
            .buttonStyle(.plain)
        }
    }

    private func mySubmoltList(_ submolts: [MySubmoltItem]) -> some View {
        Group {
            if submolts.isEmpty {
                LoadingStateView(state: .empty(message: "You haven't joined any communities yet."))
            } else {
                ForEach(submolts) { submolt in
                    NavigationLink(value: submolt.id) {
                        submoltCard(name: submolt.displayName, description: submolt.description, memberCount: submolt.memberCount, tags: [])
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func submoltCard(name: String, description: String?, memberCount: Int, tags: [String]) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: AGSpacing.sm) {
                HStack {
                    Image(systemName: "person.3.fill")
                        .foregroundStyle(Color.agPrimary)

                    Text(name)
                        .font(AGTypography.base)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.agText)

                    Spacer()

                    Text("\(memberCount) members")
                        .font(AGTypography.xs)
                        .foregroundStyle(Color.agMuted)
                }

                if let description, !description.isEmpty {
                    Text(description)
                        .font(AGTypography.sm)
                        .foregroundStyle(Color.agMuted)
                        .lineLimit(2)
                }

                if !tags.isEmpty {
                    HStack(spacing: AGSpacing.xs) {
                        ForEach(tags.prefix(3), id: \.self) { tag in
                            Text(tag)
                                .font(AGTypography.xs)
                                .foregroundStyle(Color.agAccent)
                                .padding(.horizontal, AGSpacing.sm)
                                .padding(.vertical, 2)
                                .background(
                                    Capsule()
                                        .fill(Color.agAccent.opacity(0.15))
                                )
                        }
                    }
                }
            }
        }
    }

    private var createSubmoltSheet: some View {
        NavigationStack {
            ZStack {
                Color.agBackground.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AGSpacing.lg) {
                        GlassCard {
                            VStack(alignment: .leading, spacing: AGSpacing.md) {
                                Text("Name")
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)
                                TextField("Community name", text: $newName)
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

                                Text("Description")
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)
                                TextEditor(text: $newDescription)
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

                                Text("Tags (comma-separated)")
                                    .font(AGTypography.sm)
                                    .foregroundStyle(Color.agMuted)
                                TextField("ai, agents, research", text: $newTags)
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
                    }
                    .padding(.horizontal, AGSpacing.xl)
                    .padding(.top, AGSpacing.lg)
                }
            }
            .navigationTitle("New Community")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showCreate = false }
                        .foregroundStyle(Color.agMuted)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        Task {
                            let tags = newTags.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
                            let success = await viewModel.createSubmolt(
                                name: newName,
                                description: newDescription,
                                tags: tags
                            )
                            if success {
                                newName = ""
                                newDescription = ""
                                newTags = ""
                                showCreate = false
                            }
                        }
                    }
                    .fontWeight(.semibold)
                    .tint(.agPrimary)
                    .disabled(newName.isEmpty || newDescription.isEmpty)
                }
            }
        }
    }
}
