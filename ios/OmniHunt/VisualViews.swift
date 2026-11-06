import SwiftUI
import WebKit

// MARK: - 广告拦截（本地 WKContentRuleList，无需服务器）

enum AdBlocker {
    private static let blockedHosts = [
        "doubleclick.net", "googlesyndication.com", "googleadservices.com",
        "googletagmanager.com", "google-analytics.com", "adservice.google.com",
        "adnxs.com", "criteo.com", "criteo.net", "taboola.com", "outbrain.com",
        "popads.net", "popcash.net", "propellerads.com", "onclickads.net",
        "exoclick.com", "juicyads.com", "trafficjunky.net", "adsterra.com",
        "hilltopads.net", "clickadu.com", "mgid.com", "revcontent.com",
        "zedo.com", "adcolony.com", "applovin.com", "umeng.com", "cnzz.com",
        "tanx.com", "mmstat.com", "pos.baidu.com", "cpro.baidu.com",
        "eclick.baidu.com", "hm.baidu.com", "gdt.qq.com", "e.qq.com",
        "adsmind.gdtimg.com", "admaster.com.cn", "miaozhen.com", "irs01.com",
        "51.la", "cnzz.net", "popin.cc", "hadronid.net",
    ]

    static func ruleList() -> String {
        var rules: [String] = []
        for host in blockedHosts {
            rules.append("""
            {"trigger":{"url-filter":".*","if-domain":["*\(host)"]},"action":{"type":"block"}}
            """)
        }
        rules.append("""
        {"trigger":{"url-filter":".*(/ad/|/ads/|/adserver|/popunder|/prebid|/banner_ad).*"},"action":{"type":"block"}}
        """)
        rules.append("""
        {"trigger":{"url-filter":".*"},"action":{"type":"css-display-none","selector":".ad,.ads,.advert,.adsbygoogle,[id^='ad_'],[class*='-ad-'],.popup-ad,.interstitial"}}
        """)
        return "[" + rules.joined(separator: ",") + "]"
    }

    static func install(_ completion: @escaping (WKContentRuleList?) -> Void) {
        let key = "OmniHuntAdBlockV2"
        WKContentRuleListStore.default().lookUpContentRuleList(forIdentifier: key) { list, _ in
            if let list = list { completion(list); return }
            WKContentRuleListStore.default().compileContentRuleList(
                forIdentifier: key, encodedContentRuleList: ruleList()) { compiled, _ in
                completion(compiled)
            }
        }
    }
}

extension Notification.Name {
    static let omniWebBack = Notification.Name("omni.web.back")
    static let omniWebForward = Notification.Name("omni.web.forward")
    static let omniWebReload = Notification.Name("omni.web.reload")
}

// MARK: - 无广告内置浏览器

struct BrowserTarget: Identifiable {
    let id = UUID()
    let url: URL
}

final class WebRef: ObservableObject {
    weak var view: WKWebView?
    func goBack() { if view?.canGoBack == true { view?.goBack() } }
    func goForward() { if view?.canGoForward == true { view?.goForward() } }
    func reload() { view?.reload() }
}

struct SafeBrowser: UIViewRepresentable {
    let url: URL
    var ref: WebRef? = nil
    /// 手机版排版更适合窄屏；登录页仍用桌面版
    var desktop: Bool = false

    func makeCoordinator() -> Coord { Coord() }

    func makeUIView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.defaultWebpagePreferences.preferredContentMode = desktop ? .desktop : .mobile
        cfg.defaultWebpagePreferences.allowsContentJavaScript = true
        cfg.mediaTypesRequiringUserActionForPlayback = .all
        cfg.allowsInlineMediaPlayback = true
        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.customUserAgent = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            + "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
        wv.uiDelegate = context.coordinator
        wv.navigationDelegate = context.coordinator
        wv.allowsBackForwardNavigationGestures = true
        wv.allowsLinkPreview = true
        wv.scrollView.minimumZoomScale = 0.5
        wv.scrollView.maximumZoomScale = 4.0
        wv.scrollView.bouncesZoom = true
        ref?.view = wv
        AdBlocker.install { list in
            if let list = list {
                wv.configuration.userContentController.add(list)
            }
            wv.load(URLRequest(url: url))
        }
        return wv
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    static let backNote = Notification.Name.omniWebBack

    final class Coord: NSObject, WKUIDelegate, WKNavigationDelegate {
        /// 站点大量链接是 target=_blank。以前直接 return nil → 点了没反应。
        /// 现在：广告弹窗仍拦（about:blank/无 URL），正常链接改在同窗打开。
        func webView(_ webView: WKWebView,
                     createWebViewWith configuration: WKWebViewConfiguration,
                     for navigationAction: WKNavigationAction,
                     windowFeatures: WKWindowFeatures) -> WKWebView? {
            guard let url = navigationAction.request.url,
                  let scheme = url.scheme?.lowercased(),
                  scheme == "http" || scheme == "https",
                  url.absoluteString != "about:blank" else {
                return nil
            }
            webView.load(URLRequest(url: url))
            return nil
        }
    }
}

struct InAppBrowser: View {
    let url: URL
    @Environment(\.dismiss) var dismiss
    @State private var webRef = WebRef()

    var body: some View {
        NavigationStack {
            SafeBrowser(url: url, ref: webRef)
                .ignoresSafeArea(edges: .bottom)
                .onReceive(NotificationCenter.default.publisher(for: .omniWebBack)) { _ in
                    webRef.goBack()
                }
                .onReceive(NotificationCenter.default.publisher(for: .omniWebForward)) { _ in
                    webRef.goForward()
                }
                .onReceive(NotificationCenter.default.publisher(for: .omniWebReload)) { _ in
                    webRef.reload()
                }
                .navigationTitle("浏览")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("完成") { dismiss() }
                    }
                    ToolbarItem(placement: .navigationBarLeading) {
                        HStack(spacing: 14) {
                            Button { NotificationCenter.default.post(name: .omniWebBack, object: nil) } label: {
                                Image(systemName: "chevron.backward")
                            }
                            Button { NotificationCenter.default.post(name: .omniWebForward, object: nil) } label: {
                                Image(systemName: "chevron.forward")
                            }
                            Button { NotificationCenter.default.post(name: .omniWebReload, object: nil) } label: {
                                Image(systemName: "arrow.clockwise")
                            }
                        }
                    }
                }
        }
    }
}

// MARK: - 图片网格

struct ImageGrid: View {
    let results: [SearchResult]
    @State private var preview: SearchResult?

    private let cols = [GridItem(.adaptive(minimum: 108), spacing: 6)]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: cols, spacing: 6) {
                ForEach(results) { r in
                    ImageCell(result: r)
                        .onTapGesture { preview = r }
                }
            }
            .padding(8)
        }
        .sheet(item: $preview) { r in
            ImagePreview(result: r)
        }
    }
}

private struct ImageCell: View {
    let result: SearchResult

    var body: some View {
        AsyncImage(url: URL(string: result.thumbURL ?? result.url)) { phase in
            switch phase {
            case .success(let img):
                img.resizable().aspectRatio(contentMode: .fill)
            case .failure:
                ZStack {
                    Theme.surface
                    Image(systemName: "photo").foregroundStyle(Theme.dim)
                }
            default:
                ZStack { Theme.surface; ProgressView() }
            }
        }
        .frame(height: 108)
        .clipped()
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(alignment: .bottomLeading) {
            Text(result.source)
                .font(.system(size: 9))
                .padding(.horizontal, 4).padding(.vertical, 1)
                .background(Color.black.opacity(0.55))
                .foregroundStyle(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 4))
                .padding(4)
        }
    }
}

private struct ImagePreview: View {
    let result: SearchResult
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 10) {
                AsyncImage(url: URL(string: result.fullURL ?? result.thumbURL ?? result.url)) { phase in
                    if case .success(let img) = phase {
                        img.resizable().aspectRatio(contentMode: .fit)
                    } else {
                        ProgressView()
                    }
                }
                .frame(maxHeight: .infinity)
                Text(result.title)
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.muted)
                    .padding(.horizontal)
                HStack(spacing: 14) {
                    if let f = result.fullURL, let u = URL(string: f) {
                        Link("打开原图", destination: u)
                    }
                    if let u = URL(string: result.url) {
                        Link("来源页面", destination: u)
                    }
                }
                .font(.system(size: 12))
                .padding(.bottom, 12)
            }
            .navigationTitle("图片")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("完成") { dismiss() }
                }
            }
        }
    }
}

// MARK: - 视频列表

struct VideoList: View {
    let results: [SearchResult]
    @State private var playing: BrowserTarget?

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                ForEach(results) { r in
                    VideoCardRow(result: r)
                        .onTapGesture {
                            if let u = URL(string: r.url) {
                                playing = BrowserTarget(url: u)
                            }
                        }
                }
            }
            .padding(10)
        }
        .fullScreenCover(item: $playing) { t in
            StreamSnifferView(url: t.url)   // 视频走嗅探 + 原生播放
        }
    }
}

struct VideoCardRow: View {
    let result: SearchResult

    private var thumb: some View {
        AsyncImage(url: URL(string: result.thumbURL ?? "")) { phase in
            if case .success(let img) = phase {
                img.resizable().aspectRatio(contentMode: .fill)
            } else {
                ZStack {
                    Theme.surface
                    Image(systemName: "play.rectangle").foregroundStyle(Theme.dim)
                }
            }
        }
        .frame(width: 132, height: 78)
        .clipped()
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private var durationBadge: some View {
        Group {
            if let d = result.duration, !d.isEmpty {
                Text(d)
                    .font(.system(size: 10, weight: .semibold))
                    .padding(.horizontal, 4).padding(.vertical, 1)
                    .background(Color.black.opacity(0.65))
                    .foregroundStyle(Color.white)
                    .clipShape(RoundedRectangle(cornerRadius: 3))
                    .padding(4)
            }
        }
    }

    var body: some View {
        HStack(spacing: 10) {
            ZStack(alignment: .bottomTrailing) {
                thumb
                durationBadge
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(result.title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2)
                Text(result.source)
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.dim)
            }
            Spacer(minLength: 0)
        }
        .padding(10)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}
