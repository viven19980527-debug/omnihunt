import Foundation

/// Small persisted settings store. UserDefaults keys keep iOS and the CLI docs
/// pointing at the same idea: one base URL, one default result budget.
final class AppSettings: ObservableObject {
    private let defaults = UserDefaults.standard

    @Published var baseURLString: String {
        didSet { defaults.set(baseURLString, forKey: Keys.baseURL) }
    }

    @Published var patternsDefault: Bool {
        didSet { defaults.set(patternsDefault, forKey: Keys.patterns) }
    }

    @Published var limit: Int {
        didSet { defaults.set(limit, forKey: Keys.limit) }
    }

    init() {
        baseURLString = defaults.string(forKey: Keys.baseURL) ?? "http://192.168.3.2:7860"
        patternsDefault = defaults.bool(forKey: Keys.patterns)
        let storedLimit = defaults.integer(forKey: Keys.limit)
        limit = storedLimit == 0 ? 40 : storedLimit
    }

    var baseURL: URL? {
        let trimmed = baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let url = URL(string: trimmed), url.scheme != nil else { return nil }
        return url
    }

    private enum Keys {
        static let baseURL = "omnihunt.baseURL"
        static let patterns = "omnihunt.patternsDefault"
        static let limit = "omnihunt.limit"
    }
}
