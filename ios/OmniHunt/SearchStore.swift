import Foundation

@MainActor
final class SearchStore: ObservableObject {
    @Published var query: String = ""
    @Published var kind: ResultKind?
    @Published var patterns: Bool = false
    @Published var limit: Int = 40

    @Published private(set) var results: [SearchResult] = []
    @Published private(set) var errors: [SearchResponse.EngineError] = []
    @Published private(set) var stats: SearchResponse.Stats?
    @Published private(set) var tookMS: Int = 0
    @Published private(set) var cached: Bool = false
    @Published private(set) var rawCount: Int = 0
    @Published private(set) var isLoading: Bool = false
    @Published var lastError: String?
    /// true = 电脑连不上，本次结果来自手机直连引擎
    @Published private(set) var localMode: Bool = false

    private var task: Task<Void, Never>?

    var hasSearched: Bool { !results.isEmpty || tookMS > 0 || lastError != nil }

    func search(baseURL: URL?) {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        guard let baseURL else {
            lastError = "服务器地址无效，去设置里填 http://<电脑IP>:7860"
            return
        }

        task?.cancel()
        let kind = self.kind
        let patterns = self.patterns
        let limit = self.limit

        isLoading = true
        lastError = nil

        task = Task { [weak self] in
            do {
                let response = try await APIClient(baseURL: baseURL)
                    .search(query: trimmed, kind: kind, patterns: patterns, limit: limit)
                guard let self else { return }
                guard !Task.isCancelled else {
                    self.isLoading = false
                    return
                }
                self.localMode = false
                self.apply(response)
                self.isLoading = false
            } catch {
                guard let self else { return }
                if Task.isCancelled {
                    self.isLoading = false
                    return
                }
                // 电脑连不上：自动改用手机直连引擎，不再显示「连不上服务器」
                let local = await OnDeviceEngine.search(query: trimmed, kind: kind, limit: limit)
                if !local.isEmpty {
                    self.results = local
                    self.errors = []
                    self.stats = nil
                    self.tookMS = 0
                    self.cached = false
                    self.rawCount = local.count
                    self.localMode = true
                    self.lastError = nil
                    self.isLoading = false
                    return
                }
                self.localMode = true
                self.lastError = "电脑未连接，手机直连也没抓到结果。检查 VPN 或换英文关键词。"
                self.results = []
                self.errors = []
                self.stats = nil
                self.isLoading = false
            }
        }
    }

    func cancel() {
        task?.cancel()
        isLoading = false
    }

    func clear() {
        task?.cancel()
        query = ""
        results = []
        errors = []
        stats = nil
        lastError = nil
        tookMS = 0
        cached = false
        rawCount = 0
        isLoading = false
    }

    private func apply(_ response: SearchResponse) {
        results = response.results
        errors = response.errors
        stats = response.stats
        tookMS = response.tookMS
        cached = response.cached
        rawCount = response.stats?.raw ?? response.results.count
    }
}
