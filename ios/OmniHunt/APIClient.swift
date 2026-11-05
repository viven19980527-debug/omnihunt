import Foundation

enum APIError: LocalizedError {
    case badURL
    case badResponse
    case http(Int, String)
    case decoding(String)
    case transport(String)

    var errorDescription: String? {
        switch self {
        case .badURL:
            return "服务器地址无效，去设置里检查一下（形如 http://192.168.3.2:7860）"
        case .badResponse:
            return "服务端返回了无法识别的响应"
        case .http(let code, let body):
            let trimmed = body.trimmingCharacters(in: .whitespacesAndNewlines)
            let hint = trimmed.isEmpty ? "" : "：" + String(trimmed.prefix(160))
            return "HTTP \(code)\(hint)"
        case .decoding(let detail):
            return "解析响应失败：\(detail)"
        case .transport(let detail):
            return "连不上服务器（\(detail)）。确认 OmniHunt 用 --host 0.0.0.0 启动、手机和电脑在同一网段。"
        }
    }
}

struct APIClient {
    let baseURL: URL

    private var session: URLSession {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 35
        config.timeoutIntervalForResource = 60
        config.waitsForConnectivity = false
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: config)
    }

    func search(query: String, kind: ResultKind?, patterns: Bool, limit: Int) async throws -> SearchResponse {
        var items: [URLQueryItem] = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "per_engine", value: "10")
        ]
        if let kind {
            items.append(URLQueryItem(name: "kinds", value: kind.rawValue))
        }
        if patterns {
            items.append(URLQueryItem(name: "patterns", value: "1"))
        }
        return try await get("api/search", items: items)
    }

    func health() async throws -> HealthResponse {
        try await get("health", items: [])
    }

    func engines() async throws -> EnginesResponse {
        try await get("api/engines", items: [])
    }

    private func get<T: Decodable>(_ path: String, items: [URLQueryItem]) async throws -> T {
        guard var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false) else {
            throw APIError.badURL
        }
        components.queryItems = items.isEmpty ? nil : items
        guard let url = components.url else { throw APIError.badURL }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else { throw APIError.badResponse }
            guard (200..<300).contains(http.statusCode) else {
                throw APIError.http(http.statusCode, String(data: data, encoding: .utf8) ?? "")
            }
            do {
                return try JSONDecoder().decode(T.self, from: data)
            } catch {
                throw APIError.decoding(error.localizedDescription)
            }
        } catch let error as APIError {
            throw error
        } catch {
            throw APIError.transport(error.localizedDescription)
        }
    }
}

struct EnginesResponse: Codable {
    let engines: [SearchResponse.EngineStat]
}
