import SwiftUI

// MARK: - 直连暗面（走手机 VPN，不经 PC 后端）

/// 手机开了 VPN 时，这些源可以直连。所有请求走 URLSession，
/// 结果分三栏：磁力（真 magnet）/ 图片（booru）/ 暗网（.onion）。
@MainActor
final class DarkStore: ObservableObject {
    @Published var query = ""
    @Published var running = false
    @Published var log: [String] = []
    @Published var torrents: [DarkHit] = []
    @Published var images: [DarkHit] = []
    @Published var onions: [DarkHit] = []

    struct DarkHit: Identifiable {
        let id = UUID()
        let source: String
        let title: String
        let page: String
        var thumb: String = ""
        var full: String = ""
        var magnet: String = ""
        var size: String = ""
        var seeders: String = ""
        var isOnion: Bool { page.contains(".onion") }
    }

    private let ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        + "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"

    private func fetch(_ url: String, timeout: TimeInterval = 12) async -> String? {
        guard let u = URL(string: url) else { return nil }
        var req = URLRequest(url: u)
        req.timeoutInterval = timeout
        req.setValue(ua, forHTTPHeaderField: "User-Agent")
        req.setValue("zh-CN,zh;q=0.9,en;q=0.8", forHTTPHeaderField: "Accept-Language")
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                return nil
            }
            return String(data: data, encoding: .utf8)
        } catch {
            return nil
        }
    }

    func run() async {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty, !running else { return }
        running = true
        torrents = []; images = []; onions = []; log = []
        let enc = q.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? q
        let tag = q.replacingOccurrences(of: " ", with: "_")
            .addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? q

        await withTaskGroup(of: (String, [DarkHit]).self) { group in
            let isASCII = q.unicodeScalars.allSatisfy { $0.isASCII }
            group.addTask { ("nyaa", await self.nyaaRSS("https://nyaa.si", enc, "nyaa")) }
            group.addTask { ("sukebei", await self.nyaaRSS("https://sukebei.nyaa.si", enc, "sukebei")) }
            if isASCII {
                group.addTask {
                    let url = "https://api.rule34.xxx/index.php?page=dapi&s=post&q=index&json=1&limit=20&tags=\(tag)"
                    return ("rule34", await self.booru(url, "rule34", "rule34.xxx"))
                }
                group.addTask { ("danbooru", await self.danbooru(tag)) }
                group.addTask { ("e621", await self.e621(tag)) }
            } else {
                log.append("中文关键词已跳过 booru（只认英文标签）")
            }
            group.addTask { ("ahmia", await self.ahmia(enc)) }
            group.addTask { ("onionse", await self.onionSE(enc)) }

            for await (name, hits) in group {
                log.append("\(name): \(hits.count) 条")
                for h in hits {
                    if !h.magnet.isEmpty {
                        torrents.append(h)
                    } else if h.isOnion {
                        onions.append(h)
                    } else if !h.thumb.isEmpty || !h.full.isEmpty {
                        images.append(h)
                    }
                }
            }
        }
        torrents.sort { (Int($0.seeders) ?? 0) > (Int($1.seeders) ?? 0) }
        running = false
    }

    // ---- Nyaa / Sukebei RSS：从 infoHash 拼 magnet（RSS 本身不含 magnet 链接）----
    private func nyaaRSS(_ base: String, _ q: String, _ name: String) async -> [DarkHit] {
        guard let xml = await fetch("\(base)/?page=rss&c=0_0&f=0&q=\(q)") else { return [] }
        var out: [DarkHit] = []
        for item in matches(xml, "<item>([\\s\\S]*?)</item>") {
            let title = clean(first(item, "<title>([\\s\\S]*?)</title>"))
            let link = clean(first(item, "<link>([\\s\\S]*?)</link>"))
            let hash = clean(first(item, "<nyaa:infoHash>([\\s\\S]*?)</nyaa:infoHash>"))
            let size = clean(first(item, "<nyaa:size>([\\s\\S]*?)</nyaa:size>"))
            let seeds = clean(first(item, "<nyaa:seeders>([\\s\\S]*?)</nyaa:seeders>"))

            var magnet = first(item, "(magnet:\\?xt=urn:btih:[^\"<\\s&]+)")
            if magnet.isEmpty, !hash.isEmpty {
                let dn = title.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ""
                magnet = "magnet:?xt=urn:btih:\(hash)&dn=\(dn)"
            }
            guard !magnet.isEmpty || !link.isEmpty else { continue }
            out.append(DarkHit(source: name, title: title.isEmpty ? "(无标题)" : title,
                               page: link.isEmpty ? magnet : link,
                               magnet: magnet, size: size, seeders: seeds))
            if out.count >= 20 { break }
        }
        return out
    }

    // ---- booru JSON ----
    private func booru(_ url: String, _ name: String, _ host: String) async -> [DarkHit] {
        guard let raw = await fetch(url), let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) else { return [] }
        var posts: [[String: Any]] = []
        if let arr = obj as? [[String: Any]] { posts = arr }
        else if let dict = obj as? [String: Any], let arr = dict["post"] as? [[String: Any]] { posts = arr }
        var out: [DarkHit] = []
        for p in posts.prefix(20) {
            let full = (p["file_url"] as? String) ?? (p["sample_url"] as? String) ?? ""
            let thumb = (p["preview_url"] as? String) ?? (p["sample_url"] as? String) ?? full
            let page = (p["post_url"] as? String).map { $0.hasPrefix("/") ? "https://\(host)\($0)" : $0 } ?? full
            let tags = (p["tag_string"] as? String) ?? (p["tags"] as? String) ?? ""
            guard !full.isEmpty || !thumb.isEmpty else { continue }
            out.append(DarkHit(source: name, title: String(tags.prefix(70)), page: page,
                               thumb: thumb, full: full))
        }
        return out
    }

    private func danbooru(_ tag: String) async -> [DarkHit] {
        guard let raw = await fetch("https://danbooru.donmai.us/posts.json?tags=\(tag)&limit=20"),
              let data = raw.data(using: .utf8),
              let arr = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else { return [] }
        return arr.compactMap { p in
            let full = p["file_url"] as? String ?? ""
            let thumb = p["preview_file_url"] as? String ?? full
            let page = "https://danbooru.donmai.us/posts/\(p["id"] as? Int ?? 0)"
            guard !full.isEmpty else { return nil }
            return DarkHit(source: "danbooru", title: String((p["tag_string"] as? String ?? "").prefix(70)),
                           page: page, thumb: thumb, full: full)
        }
    }

    private func e621(_ tag: String) async -> [DarkHit] {
        guard let raw = await fetch("https://e621.net/posts.json?tags=\(tag)&limit=20"),
              let data = raw.data(using: .utf8),
              let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let posts = dict["posts"] as? [[String: Any]] else { return [] }
        return posts.compactMap { p in
            guard let file = p["file"] as? [String: Any],
                  let full = file["url"] as? String else { return nil }
            let preview = (p["preview"] as? [String: Any])?["url"] as? String ?? full
            let page = "https://e621.net/posts/\(p["id"] as? Int ?? 0)"
            let tags = (p["tags"] as? [String: Any])?["general"] as? [String] ?? []
            return DarkHit(source: "e621", title: tags.prefix(6).joined(separator: " "),
                           page: page, thumb: preview, full: full)
        }
    }

    // ---- .onion 索引（clearnet 端点）----
    // 结构常改，所以不依赖 li/h4：直接抓 .onion 链接，再取相邻文本当标题。
    private func ahmia(_ q: String) async -> [DarkHit] {
        guard let html = await fetch("https://ahmia.fi/search/?q=\(q)") else { return [] }
        return onionHits(html, source: "ahmia")
    }

    private func onionSE(_ q: String) async -> [DarkHit] {
        guard let html = await fetch("https://onionsearchengine.com/search.php?search=\(q)") else { return [] }
        return onionHits(html, source: "onionse")
    }

    private func onionHits(_ html: String, source: String) -> [DarkHit] {
        var seen = Set<String>()
        var out: [DarkHit] = []
        let pattern = "href=\"(https?://[a-z2-7]{12,62}\\.onion[^\"#]*)\""
        guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return [] }
        let ns = html as NSString
        let all = re.matches(in: html, range: NSRange(location: 0, length: ns.length))
        for m in all {
            let href = ns.substring(with: m.range(at: 1))
            let key = href.lowercased()
            guard seen.insert(key).inserted else { continue }
            // 从链接位置向前后各取 400 字符，抽标题
            let start = max(0, m.range.location - 300)
            let len = min(900, ns.length - start)
            let window = ns.substring(with: NSRange(location: start, length: len))
            let anchor = first(window, ">([^<>]{6,120})</a>")
            let title = anchor.isEmpty ? href : clean(anchor)
            out.append(DarkHit(source: source, title: title, page: href))
            if out.count >= 20 { break }
        }
        return out
    }

    // ---- 小工具 ----
    private func matches(_ text: String, _ pattern: String) -> [String] {
        guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return [] }
        let ns = text as NSString
        return re.matches(in: text, range: NSRange(location: 0, length: ns.length))
            .map { ns.substring(with: $0.range) }
    }

    private func first(_ text: String, _ pattern: String) -> String {
        guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return "" }
        let ns = text as NSString
        guard let m = re.firstMatch(in: text, range: NSRange(location: 0, length: ns.length)) else { return "" }
        if m.numberOfRanges > 1 {
            return ns.substring(with: m.range(at: 1))
        }
        return ns.substring(with: m.range)
    }

    private func clean(_ s: String) -> String {
        var t = s
        t = t.replacingOccurrences(of: "<![CDATA[", with: "")
            .replacingOccurrences(of: "]]>", with: "")
            .replacingOccurrences(of: "&amp;", with: "&")
            .replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&#39;", with: "'")
        if let re = try? NSRegularExpression(pattern: "<[^>]+>") {
            t = re.stringByReplacingMatches(in: t, range: NSRange(location: 0, length: (t as NSString).length), withTemplate: " ")
        }
        return t.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - 页面

struct DarkBoardView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var store = DarkStore()
    @State private var browser: BrowserTarget?
    @State private var copied: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    searchRow
                    if !store.log.isEmpty { logRow }
                    if store.running { ProgressView().tint(Theme.accent) }
                    if !store.torrents.isEmpty { torrentSection }
                    if !store.images.isEmpty { imageSection }
                    if !store.onions.isEmpty { onionSection }
                    if !store.running && store.log.isEmpty { hint }
                    if !store.log.isEmpty && store.torrents.isEmpty
                        && store.images.isEmpty && store.onions.isEmpty { emptyHint }
                }
                .padding(14)
            }
            .background(Theme.bg.ignoresSafeArea())
            .navigationTitle("直连暗面")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) { Button("完成") { dismiss() } }
            }
            .sheet(item: $browser) { t in InAppBrowser(url: t.url) }
        }
    }

    private var emptyHint: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("没有结果时按这三点排查：")
                .font(.system(size: 12, weight: .semibold)).foregroundStyle(Theme.ink)
            Text("1. booru 图站只认英文标签：搜 nurse / nurse_dress 而不是「护士」")
                .font(.system(size: 11)).foregroundStyle(Theme.muted)
            Text("2. nyaa 是动漫站，中文关键词通常 0 条；成人磁力用 sukebei")
                .font(.system(size: 11)).foregroundStyle(Theme.muted)
            Text("3. .onion 索引常被 Cloudflare 拦，多试几次或换关键词")
                .font(.system(size: 11)).foregroundStyle(Theme.muted)
        }
        .padding(10)
        .background(Theme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var hint: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("这个页面不经过 PC 后端，直接用手机网络抓。")
                .font(.system(size: 12)).foregroundStyle(Theme.muted)
            Text("开 VPN 后：nyaa / sukebei（磁力）、rule34 / danbooru / e621（图站）、ahmia / onionsearchengine（.onion 索引）全部直连。")
                .font(.system(size: 11)).foregroundStyle(Theme.dim)
        }
        .padding(.top, 8)
    }

    private var searchRow: some View {
        HStack(spacing: 8) {
            TextField("关键词（英文命中率更高）", text: $store.query)
                .textFieldStyle(.plain)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .padding(.horizontal, 10).padding(.vertical, 9)
                .background(Theme.panel)
                .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            Button {
                Task { await store.run() }
            } label: {
                Image(systemName: store.running ? "hourglass" : "bolt.fill")
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    .background(Theme.accent)
                    .foregroundStyle(.black)
                    .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            }
            .disabled(store.running || store.query.trimmingCharacters(in: .whitespaces).isEmpty)
        }
    }

    private var logRow: some View {
        Text(store.log.joined(separator: " · "))
            .font(.system(size: 10, design: .monospaced))
            .foregroundStyle(Theme.dim)
    }

    private var torrentSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionTitle("磁力 \(store.torrents.count)")
            ForEach(store.torrents) { h in
                VStack(alignment: .leading, spacing: 4) {
                    Text(h.title).font(.system(size: 12.5, weight: .semibold))
                        .foregroundStyle(Theme.ink).lineLimit(3)
                    HStack(spacing: 8) {
                        Text(h.source).font(.system(size: 10)).foregroundStyle(Theme.dim)
                        if !h.size.isEmpty {
                            Text(h.size).font(.system(size: 10)).foregroundStyle(Theme.muted)
                        }
                        if !h.seeders.isEmpty {
                            Text("做种 \(h.seeders)").font(.system(size: 10))
                                .foregroundStyle(Theme.accent)
                        }
                    }
                    HStack(spacing: 8) {
                        Button(copied == h.id.uuidString ? "已复制" : "复制磁力") {
                            UIPasteboard.general.string = h.magnet
                            copied = h.id.uuidString
                        }
                        .font(.system(size: 11))
                        Button("打开页面") {
                            if let u = URL(string: h.page) { browser = BrowserTarget(url: u) }
                        }
                        .font(.system(size: 11))
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        }
    }

    private var imageSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionTitle("图片 \(store.images.count)")
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 104), spacing: 6)], spacing: 6) {
                ForEach(store.images) { h in
                    AsyncImage(url: URL(string: h.thumb.isEmpty ? h.full : h.thumb)) { phase in
                        if case .success(let img) = phase {
                            img.resizable().aspectRatio(contentMode: .fill)
                        } else {
                            ZStack { Theme.surface; Image(systemName: "photo").foregroundStyle(Theme.dim) }
                        }
                    }
                    .frame(height: 104).clipped()
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .onTapGesture {
                        if let u = URL(string: h.page.isEmpty ? h.full : h.page) {
                            browser = BrowserTarget(url: u)
                        }
                    }
                }
            }
        }
    }

    private var onionSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionTitle(".onion \(store.onions.count)")
            ForEach(store.onions) { h in
                VStack(alignment: .leading, spacing: 3) {
                    Text(h.title).font(.system(size: 12.5)).foregroundStyle(Theme.ink).lineLimit(2)
                    Text(h.page).font(.system(size: 9.5, design: .monospaced))
                        .foregroundStyle(Theme.dim).lineLimit(1)
                    Button("复制地址") {
                        UIPasteboard.general.string = h.page
                        copied = h.id.uuidString
                    }
                    .font(.system(size: 11))
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
            Text("iPhone 上没有 Tor 客户端无法直接打开 .onion，复制地址到 Tor Browser。")
                .font(.system(size: 10)).foregroundStyle(Theme.dim)
        }
    }

    private func sectionTitle(_ s: String) -> some View {
        Text(s).font(.system(size: 12, weight: .bold))
            .foregroundStyle(Theme.muted).tracking(1)
    }
}
