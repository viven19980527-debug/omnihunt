import Foundation

// MARK: - Kind

enum ResultKind: String, Codable, CaseIterable, Identifiable {
    case web
    case onion
    case adult
    case torrent
    case pattern

    var id: String { rawValue }

    var label: String {
        switch self {
        case .web: return "网页"
        case .onion: return "暗网"
        case .adult: return "成人"
        case .torrent: return "磁力"
        case .pattern: return "模式"
        }
    }

    var englishLabel: String {
        switch self {
        case .web: return "web"
        case .onion: return "onion"
        case .adult: return "adult"
        case .torrent: return "torrent"
        case .pattern: return "pattern"
        }
    }

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = ResultKind(rawValue: raw) ?? .web
    }
}

// MARK: - Loose JSON (for Result.extra)

enum JSONValue: Codable, Hashable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case array([JSONValue])
    case object([String: JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
            return
        }
        if let value = try? container.decode(Bool.self) {
            self = .bool(value)
            return
        }
        if let value = try? container.decode(Double.self) {
            self = .number(value)
            return
        }
        if let value = try? container.decode(String.self) {
            self = .string(value)
            return
        }
        if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
            return
        }
        if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
            return
        }
        self = .null
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }

    var stringValue: String? {
        if case .string(let value) = self { return value }
        return nil
    }

    var boolValue: Bool? {
        if case .bool(let value) = self { return value }
        return nil
    }
}

// MARK: - API payloads

struct SearchResult: Codable, Identifiable, Hashable {
    let title: String
    let url: String
    let snippet: String?
    let source: String
    let kind: ResultKind
    let score: Double
    let sources: [String]?
    let extra: [String: JSONValue]?

    var id: String { url }
    var magnet: String? { extra?["magnet"]?.stringValue }
    var allSources: [String] { (sources?.isEmpty == false ? sources : nil) ?? [source] }
}

struct SearchResponse: Codable {
    let query: String
    let tookMS: Int
    let cached: Bool
    let count: Int
    let stats: Stats?
    let errors: [EngineError]
    let results: [SearchResult]

    enum CodingKeys: String, CodingKey {
        case query, cached, count, stats, errors, results
        case tookMS = "took_ms"
    }

    struct Stats: Codable {
        let raw: Int?
        let unique: Int?
        let cachedEngines: Int?
        let engines: [EngineStat]?

        enum CodingKeys: String, CodingKey {
            case raw, unique, engines
            case cachedEngines = "cached_engines"
        }
    }

    struct EngineStat: Codable, Identifiable {
        let name: String
        let kind: String?
        let count: Int?
        let ms: Int?
        let cached: Bool?
        let error: String?

        var id: String { name }
    }

    struct EngineError: Codable, Identifiable, Hashable {
        let engine: String
        let message: String

        var id: String { engine + "|" + message }
    }
}

struct HealthResponse: Codable {
    let ok: Bool
    let engines: Int
}
