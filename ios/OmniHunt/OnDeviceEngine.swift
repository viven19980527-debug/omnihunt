import Foundation

// MARK: - 手机端直连引擎（电脑没开也能搜）

/// 与后端 29 个引擎无关，纯手机网络抓。后端连不上时自动接管。
@MainActor
enum OnDeviceEngine {

    static let ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        + "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"

    static func fetch(_ url: String, timeout: TimeInterval = 12) async -> String? {
        guard let u = URL(string: url) else { return nil }
        var req = URLRequest(url: u)
        req.timeoutInterval = timeout
        req.setValue(ua, forHTTPHeaderField: "User-Agent")
        req.setValue("zh-CN,zh;q=0.9,en;q=0.8", forHTTPHeaderField: "Accept-Language")
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode) else { return nil }
            return String(data: data, encoding: .utf8)
        } catch { return nil }
    }

    static func search(query: String, kind: ResultKind?, limit: Int) async -> [SearchResult] {
        let enc = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
        let tag = query.replacingOccurrences(of: " ", with: "_")
            .addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
        let ascii = query.unicodeScalars.allSatisfy { $0.isASCII }

        var out: [SearchResult] = []

        await withTaskGroup(of: [SearchResult].self) { group in
            if kind == nil || kind == .web {
                group.addTask { await ddg(enc) }
                group.addTask { await yandex(enc) }
            }
            if kind == nil || kind == .onion {
                group.addTask { await onionIndex(enc, "https://ahmia.fi/search/?q=", "ahmia") }
                group.addTask { await onionIndex(enc, "https://onionsearchengine.com/search.php?search=", "onionse") }
            }
            if (kind == nil || kind == .torrent) {
                group.addTask { await nyaa("https://sukebei.nyaa.si", enc, "sukebei") }
                group.addTask { await nyaa("https://nyaa.si", enc, "nyaa") }
            }
            if kind == nil || kind == .image {
                group.addTask { await bingImages(enc) }
                if ascii {
                    group.addTask { await booru("https://danbooru.donmai.us/posts.json?tags=\(tag)&limit=20", "danbooru") }
                    group.addTask { await e621(tag) }
                }
            }
            if kind == nil || kind == .video {
                group.addTask { await bilibili(enc) }
            }
            for await chunk in group { out.append(contentsOf: chunk) }
        }

        // 去重
        var seen = Set<String>()
        var unique: [SearchResult] = []
        for r in out where seen.insert(r.url).inserted { unique.append(r) }
        return Array(unique.prefix(max(20, limit)))
    }

    // MARK: 各源

    private static func mk(_ title: String, _ url: String, _ src: String,
                           _ kind: ResultKind, _ snippet: String = "",
                           extra: [String: String] = [:]) -> SearchResult {
        var e: [String: JSONValue] = [:]
        for (k, v) in extra where !v.isEmpty { e[k] = .string(v) }
        return SearchResult(title: title, url: url, snippet: snippet, source: src,
                            kind: kind, score: 1.0, sources: [src], extra: e.isEmpty ? nil : e)
    }

    private static func ddg(_ q: String) async -> [SearchResult] {
        guard let html = await fetch("https://html.duckduckgo.com/html/?q=\(q)") else { return [] }
        var out: [SearchResult] = []
        for block in matches(html, "<div class=\"result[^\"]*\"[\\s\\S]*?</div>\\s*</div>") {
            var href = first(block, "href=\"([^\"]+)\"").replacingOccurrences(of: "&amp;", with: "&")
            if let r = href.range(of: "uddg=") {
                let e = String(href[r.upperBound...]).components(separatedBy: "&").first ?? ""
                href = e.removingPercentEncoding ?? e
            }
            let t = clean(first(block, "class=\"result__a[^\"]*\"[^>]*>([\\s\\S]*?)</a>"))
            let s = clean(first(block, "class=\"result__snippet[^\"]*\"[^>]*>([\\s\\S]*?)</a>"))
            guard href.hasPrefix("http"), !t.isEmpty else { continue }
            out.append(mk(t, href, "ddg", .web, s))
            if out.count >= 15 { break }
        }
        return out
    }

    private static func yandex(_ q: String) async -> [SearchResult] {
        guard let html = await fetch("https://yandex.com/search/?text=\(q)") else { return [] }
        var out: [SearchResult] = []
        for block in matches(html, "<li class=\"serp-item[\"]?[\\s\\S]*?</li>") {
            let href = first(block, "href=\"(https?://[^\"]+)\"")
            let t = clean(first(block, "<h2[^>]*>([\\s\\S]*?)</h2>"))
            guard href.hasPrefix("http"), !t.isEmpty else { continue }
            out.append(mk(t, href, "yandex", .web))
            if out.count >= 15 { break }
        }
        return out
    }

    private static func onionIndex(_ q: String, _ prefix: String, _ src: String) async -> [SearchResult] {
        guard let html = await fetch(prefix + q) else { return [] }
        var out: [SearchResult] = []
        var seen = Set<String>()
        let links = matches(html, "href=\"(https?://[a-z2-7]{12,62}\\.onion[^\"#]*)\"")
        for l in links {
            let href = first(l, "(https?://[a-z2-7]{12,62}\\.onion[^\"#]*)")
            guard !href.isEmpty, seen.insert(href).inserted else { continue }
            out.append(mk(href, href, src, .onion))
            if out.count >= 15 { break }
        }
        return out
    }

    private static func nyaa(_ base: String, _ q: String, _ src: String) async -> [SearchResult] {
        guard let xml = await fetch("\(base)/?page=rss&c=0_0&f=0&q=\(q)") else { return [] }
        var out: [SearchResult] = []
        for item in matches(xml, "<item>([\\s\\S]*?)</item>") {
            let t = clean(first(item, "<title>([\\s\\S]*?)</title>"))
            let link = clean(first(item, "<link>([\\s\\S]*?)</link>"))
            let hash = clean(first(item, "<nyaa:infoHash>([\\s\\S]*?)</nyaa:infoHash>"))
            let size = clean(first(item, "<nyaa:size>([\\s\\S]*?)</nyaa:size>"))
            let seeds = clean(first(item, "<nyaa:seeders>([\\s\\S]*?)</nyaa:seeders>"))
            var magnet = ""
            if !hash.isEmpty {
                let dn = t.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ""
                magnet = "magnet:?xt=urn:btih:\(hash)&dn=\(dn)"
            }
            guard !t.isEmpty, !(magnet.isEmpty && link.isEmpty) else { continue }
            out.append(mk(t, link.isEmpty ? magnet : link, src, .torrent,
                          size.isEmpty ? "" : "\(size) · 做种 \(seeds)",
                          extra: ["magnet": magnet, "size": size, "seeders": seeds, "duration": ""]))
            if out.count >= 15 { break }
        }
        return out
    }

    private static func bingImages(_ q: String) async -> [SearchResult] {
        guard let html = await fetch("https://www.bing.com/images/search?q=\(q)&form=HDRSC2") else { return [] }
        var out: [SearchResult] = []
        for m in matches(html, "m=\"(\\{[^\"]{20,3000}\\})\"") {
            let js = m.replacingOccurrences(of: "&quot;", with: "\"")
            guard let d = js.data(using: .utf8),
                  let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { continue }
            let full = o["murl"] as? String ?? ""
            let thumb = (o["turl"] as? String ?? "").replacingOccurrences(of: "&amp;", with: "&")
            let page = o["purl"] as? String ?? full
            guard !thumb.isEmpty else { continue }
            out.append(mk("图片", page.isEmpty ? full : page, "bingimg", .image, "",
                          extra: ["thumb": thumb, "full": full]))
            if out.count >= 24 { break }
        }
        return out
    }

    private static func booru(_ url: String, _ src: String) async -> [SearchResult] {
        guard let raw = await fetch(url), let d = raw.data(using: .utf8),
              let arr = try? JSONSerialization.jsonObject(with: d) as? [[String: Any]] else { return [] }
        var out: [SearchResult] = []
        for p in arr.prefix(20) {
            let full = p["file_url"] as? String ?? ""
            let thumb = p["preview_file_url"] as? String ?? full
            guard !full.isEmpty else { continue }
            let id = p["id"] as? Int ?? 0
            out.append(mk(String((p["tag_string"] as? String ?? "").prefix(60)),
                          "https://danbooru.donmai.us/posts/\(id)", src, .image, "",
                          extra: ["thumb": thumb, "full": full]))
        }
        return out
    }

    private static func e621(_ tag: String) async -> [SearchResult] {
        guard let raw = await fetch("https://e621.net/posts.json?tags=\(tag)&limit=20"),
              let d = raw.data(using: .utf8),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              let posts = o["posts"] as? [[String: Any]] else { return [] }
        var out: [SearchResult] = []
        for p in posts.prefix(20) {
            guard let f = p["file"] as? [String: Any], let full = f["url"] as? String else { continue }
            let thumb = (p["preview"] as? [String: Any])?["url"] as? String ?? full
            let id = p["id"] as? Int ?? 0
            out.append(mk("e621", "https://e621.net/posts/\(id)", "e621", .image, "",
                          extra: ["thumb": thumb, "full": full]))
        }
        return out
    }

    private static func bilibili(_ q: String) async -> [SearchResult] {
        guard let html = await fetch("https://search.bilibili.com/all?keyword=\(q)") else { return [] }
        var out: [SearchResult] = []
        var seen = Set<String>()
        for l in matches(html, "href=\"(//www\\.bilibili\\.com/video/BV[0-9A-Za-z]+[^\"]*)\"") {
            let href = first(l, "(//www\\.bilibili\\.com/video/BV[^\"]+)")
            guard !href.isEmpty, seen.insert(href).inserted else { continue }
            out.append(mk("B站视频", "https:" + href, "bili", .video))
            if out.count >= 12 { break }
        }
        return out
    }

    // MARK: 工具
    private static func matches(_ text: String, _ pattern: String) -> [String] {
        guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return [] }
        let ns = text as NSString
        return re.matches(in: text, range: NSRange(location: 0, length: ns.length))
            .map { ns.substring(with: $0.range) }
    }

    private static func first(_ text: String, _ pattern: String) -> String {
        guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return "" }
        let ns = text as NSString
        guard let m = re.firstMatch(in: text, range: NSRange(location: 0, length: ns.length)) else { return "" }
        if m.numberOfRanges > 1 { return ns.substring(with: m.range(at: 1)) }
        return ns.substring(with: m.range)
    }

    private static func clean(_ s: String) -> String {
        var t = s
        for (a, b) in [("<![CDATA[", ""), ("]]>", ""), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                       ("&quot;", "\""), ("&#39;", "'")] {
            t = t.replacingOccurrences(of: a, with: b)
        }
        if let re = try? NSRegularExpression(pattern: "<[^>]+>") {
            t = re.stringByReplacingMatches(in: t, range: NSRange(location: 0, length: (t as NSString).length), withTemplate: " ")
        }
        return t.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
