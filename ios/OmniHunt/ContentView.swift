import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var settings: AppSettings
    @StateObject private var store = SearchStore()
    @State private var showSettings = false
    @State private var showDark = false
    @FocusState private var searchFocused: Bool

    private let examples = ["frida hook", "吃瓜", "urn:btih", "index of archives"]

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    header
                    searchBar
                    chips
                    metaBar
                    errorPanel
                    results
                }
                .padding(.horizontal, 16)
                .padding(.top, 10)
                .padding(.bottom, 44)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .sheet(isPresented: $showDark) { DarkBoardView() }
        .sheet(isPresented: $showSettings, onDismiss: applyDefaults) {
            SettingsView().environmentObject(settings)
        }
        .onAppear(perform: applyDefaults)
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 11) {
            BrandMark(size: 36)
            VStack(alignment: .leading, spacing: 1) {
                Text("OMNIHUNT")
                    .font(.system(size: 14, weight: .bold))
                    .tracking(2.2)
                    .foregroundStyle(Theme.ink)
                Text("clearnet · onion · catalog · magnet")
                    .font(.system(size: 10.5))
                    .foregroundStyle(Theme.muted)
            }
            Spacer()
            Button { showDark = true } label: {
                Image(systemName: "moon.stars.fill")
                    .font(.system(size: 16))
                    .foregroundStyle(Theme.onion)
            }
            .accessibilityLabel("直连暗面")
            Button { showSettings = true } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.muted)
            }
            .accessibilityLabel("设置")
        }
    }

    // MARK: - Search field

    private var searchBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(Theme.dim)

            TextField("搜任意关键词：番号、标签、站点、infohash…", text: $store.query)
                .focused($searchFocused)
                .submitLabel(.search)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .onSubmit(runSearch)
                .font(.system(size: 16))
                .foregroundStyle(Theme.ink)

            if !store.query.isEmpty {
                Button {
                    store.clear()
                    searchFocused = true
                } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.dim)
                }
                .accessibilityLabel("清空")
            }

            Button(action: runSearch) {
                Text("搜索")
                    .font(.system(size: 13.5, weight: .semibold))
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(
                        LinearGradient(colors: [Theme.accent, Theme.accentDeep],
                                       startPoint: .top, endPoint: .bottom)
                    )
                    .foregroundStyle(Color(hex: 0x04150F))
                    .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            }
            .disabled(store.isLoading || store.query.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .padding(.horizontal, 13)
        .padding(.vertical, 10)
        .background(Theme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .stroke(Theme.line, lineWidth: 1)
        )
    }

    // MARK: - Kind chips

    private var chips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                chip(title: "全部", kind: nil)
                ForEach(ResultKind.allCases) { kind in
                    chip(title: kind.label, kind: kind)
                }
            }
            .padding(.vertical, 1)
        }
    }

    private func chip(title: String, kind: ResultKind?) -> some View {
        let selected = store.kind == kind
        return Button {
            store.kind = kind
            if !store.query.trimmingCharacters(in: .whitespaces).isEmpty {
                runSearch()
            }
        } label: {
            Text(title)
                .font(.system(size: 12.5, weight: selected ? .semibold : .regular))
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(selected ? Theme.accent : Theme.panel)
                .foregroundStyle(selected ? Color(hex: 0x08110D) : Theme.muted)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(selected ? Theme.accent : Theme.line, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    // MARK: - Status

    private var metaBar: some View {
        HStack(spacing: 10) {
            if store.hasSearched {
                Text("结果 \(store.results.count)")
                Text("耗时 \(store.tookMS) ms")
                if store.cached { Text("缓存") }
                Text("引擎 \(store.stats?.engines?.count ?? 0)")
            } else {
                Text("输入关键词开始")
            }
            Spacer(minLength: 6)
            Toggle(isOn: $store.patterns) {
                Text("深度模式")
            }
            .toggleStyle(.switch)
            .controlSize(.mini)
            .font(.system(size: 11.5))
            .foregroundStyle(Theme.muted)
            .fixedSize()
        }
        .font(.system(size: 11.5))
        .foregroundStyle(Theme.dim)
    }

    @ViewBuilder
    private var errorPanel: some View {
        if let error = store.lastError {
            Text(error)
                .font(.system(size: 12))
                .foregroundStyle(Color(hex: 0xFF6B81))
                .padding(11)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(hex: 0x1B1114))
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        } else if !store.errors.isEmpty {
            DisclosureGroup {
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(store.errors) { item in
                        Text("\(item.engine)：\(item.message)")
                            .font(.system(size: 11.5))
                            .foregroundStyle(Theme.muted)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                .padding(.top, 6)
            } label: {
                Text("\(store.errors.count) 个引擎失败")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Color(hex: 0xFFB86B))
            }
            .tint(Color(hex: 0xFFB86B))
            .padding(11)
            .background(Color(hex: 0x1B1410))
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
    }

    // MARK: - Results

    @ViewBuilder
    private var results: some View {
        if store.isLoading {
            VStack(spacing: 10) {
                ProgressView().tint(Theme.accent)
                Text("并行查询所有源…")
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.dim)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 50)
        } else if store.results.isEmpty {
            emptyState
        } else if store.kind == .image {
            ImageGrid(results: store.results)
        } else if store.kind == .video {
            VideoList(results: store.results)
        } else {
            LazyVStack(spacing: 10) {
                ForEach(store.results) { result in
                    ResultRow(result: result)
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            BrandMark(size: 46)
                .opacity(0.9)
            Text(store.hasSearched ? "没有结果" : "输入关键词开始")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.ink)
            Text(store.hasSearched
                 ? "换个关键词，或切回「全部」；暗网索引对中文关键词覆盖很差。"
                 : "一次查询同时打 clearnet 引擎、.onion 索引、成人站目录与磁力索引。")
                .font(.system(size: 12.5))
                .foregroundStyle(Theme.muted)
                .multilineTextAlignment(.center)

            if !store.hasSearched {
                HStack(spacing: 8) {
                    ForEach(examples, id: \.self) { example in
                        Button(example) {
                            store.query = example
                            runSearch()
                        }
                        .font(.system(size: 12))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Theme.panel)
                        .foregroundStyle(Theme.muted)
                        .clipShape(Capsule())
                        .overlay(Capsule().stroke(Theme.line, lineWidth: 1))
                    }
                }
                .padding(.top, 4)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 48)
        .padding(.horizontal, 12)
    }

    // MARK: - Actions

    private func runSearch() {
        searchFocused = false
        store.search(baseURL: settings.baseURL)
    }

    private func applyDefaults() {
        store.patterns = settings.patternsDefault
        store.limit = settings.limit
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView().environmentObject(AppSettings())
    }
}
