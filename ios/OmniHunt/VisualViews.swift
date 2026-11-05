import SwiftUI
import WebKit

// MARK: - 广告拦截（WKContentRuleList，本地规则，无需服务器）

enum AdBlocker {
    /// 常见广告/统计/弹窗域名。命中即整域屏蔽，图片/视频页不再弹广告。
    private static let blockedHosts = [
        "doubleclick.net", "googlesyndication.com", "googleadservices.com",
        "googletagmanager.com", "google-analytics.com", "adservice.google.com",
        "adnxs.com", "criteo.com", "criteo.net", "taboola.com", "outbrain.com",
        "popads.net", "popcash.net", "propellerads.com", "onclickads.net",
        "exoclick.com", "juicyads.com", "trafficjunky.net", "adsterra.com",
        "hilltopads.net", "clickadu.com", "mgid.com", "revcontent.com",
        "zedo.com", "adcolony.com", "applovin.com", "unityads.unity3d.com",
        "umeng.com", "cnzz.com", "baidustatic.com/ad", "tanx.com",
        "mmstat.com", "pos.baidu.com", "cpro.baidu.com", "eclick.baidu.com",
        "hm.baidu.com", "sogou.com/ad", "gdt.qq.com", "e.qq.com",
        "adsmind.gdtimg.com", "veta.naver.com", "admaster.com.cn",
        "miaozhen.com", "irs01.com", "51.la", "cnzz.net",
    ]

    static func ruleList() -> String {
        let rules = blockedHosts.map { host -> String in
            """
            {"trigger":{"url-filter":".*","if-domain":["*\(host)"]},"action":{"type":"block"}}
            """
        }
        // 弹窗脚本特征 + 常见广告位选择器
        let extra = [
            #"{"trigger":{"url-filter":".*"},"action":{"type":"css-display-none","selector":".ad, .ads, .advert, .adsbygoogle, [id^='ad_'], [class*='-ad-'], .popup, .modal-ad, .interstitial"}}"#,
            #"{"trigger":{"url-filter":".*(/ad/|/ads/|/adserver|/banner|/popunder|/prebid).*"},"action":{"type":"block"}}"#
        ]
        return "[" + (rules + extra).joined(separator: ",") + "]"
    }

    static func install(_ completion: @escaping (WKContentRuleList?) -> Void) {
        let key = "OmniHuntAdBlockV1"
        WKContentRuleListStore.default().lookUpContentRuleList(forIdentifier: key) { list, _ in
            if let list = list { completion(list); return }
            WKContentRuleListStore.default().compileContentRuleList(
                forIdentifier: key, encodedContentRuleList: ruleList()) { compiled, _ in
                completion(compiled)
            }
        }
    }
}

// MARK: - 无广告内置浏览器（拦截弹窗 + 广告，不跳出 App）

struct SafeBrowser: UIViewRepresentable {
    let url: URL

    func makeCoordinator() -> Coord { Coord() }

    func makeUIView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.defaultWebpagePreferences.preferredContentMode = .desktop
        cfg.defaultWebpagePreferences.allowsContentJavaScript = true
        // 禁止自动播放（视频页自动播广告的元凶）
        cfg.mediaTypesRequiringUserActionForPlayback = .all
        cfg.allowsInlineMediaPlayback = true
        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.uiDelegate = context.coordinator       // 拦 window.open / target=_blank
        wv.navigationDelegate = context.coordinator
        wv.allowsBackForwardNavigationGestures = true
        AdBlocker.install { list in
            if let list = list { wv.configuration.userContentController.add(list) }
            wv.load(URLRequest(url: url))
        }
        return wv
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coord: NSObject, WKUIDelegate, WKNavigationDelegate {
        // 任何新窗口请求 → 吞掉（弹窗广告的入口）
        func webView(_ webView: WKWebView,
                     createWebViewWith configuration: WKWebViewConfiguration,
                     for navigationAction: WKNavigationAction,
                     windowFeatures: WKWindowFeatures) -> WKWebView? {
            return nil
        }
    }
}

struct InAppBrowser: View {
    let url: URL
    @Environment(\.dismiss) var dismiss
    @State private var current = ""

    var body: some View {
        NavigationStack {
            SafeBrowser(url: url)
                .ignoresSafeArea(edges: .bottom)
                .navigationTitle("浏览")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("完成") { dismiss() }
                    }
                    ToolbarItem(placement: .navigationBarLeading) {
                        Link(destination: url) { Image(systemName: "safari") }
                    }
                }
        }
    }
}

// MARK: - 图片网格（缩略图直接看，点开原图）

struct ImageGrid: View {
    let results: [SearchResult]
    @State private var preview: SearchResult?

    private let cols = [GridItem(.adaptive(minimum: 108), spacing: 6)]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: cols, spacing: 6) {
                ForEach(results) { r in
                    Button { preview = r } label: {
                        AsyncImage(url: URL(string: r.thumbURL ?? r.url)) { phase in
                            switch phase {
                            case .success(let img):
                                img.resizable().aspectRatio(contentMode: .fill)
                            case .failure:
                                ZStack {
                                    Theme.surface
                                    Image(systemName: "photo")
                                        .foregroundStyle(Theme.dim)
                                }
                            default:
                                ZStack { Theme.surface; ProgressView() }
                            }
                        }
                        .frame(height: 108)
                        .clipped()
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                        .overlay(alignment: .bottomLeading) {
                            Text(r.source).font(.system(size: 9))
                                .padding(.horizontal, 4).padding(.vertical, 1)
                                .background(.black.opacity(0.55))
                                .foregroundStyle(.white)
                                .clipShape(RoundedRectangle(cornerRadius: 4))
                                .padding(4)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(8)
        }
        .sheet(item: $preview) { r in
            NavigationStack {
                VStack(spacing: 10) {
                    AsyncImage(url: URL(string: r.fullURL ?? r.thumbURL ?? r.url)) { phase in
                        if case .success(let img) = phase {
                            img.resizable().aspectRatio(contentMode: .fit)
                        } else {
                            ProgressView()
                        }
                    }
                    .frame(maxHeight: .infinity)
                    Text(r.title).font(.system(size: 12))
                        .foregroundStyle(Theme.muted)
                        .padding(.horizontal)
                    HStack(spacing: 12) {
                        if let f = r.fullURL, let u = URL(string: f) {
                            Link("打开原图", destination: u)
                        }
                        Link("来源页面", destination: URL(string: r.url) ?? URL(string: "about:blank")!)
                    }
                    .font(.system(size: 12))
                    .padding(.bottom, 12)
                }
                .navigationTitle("图片")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("完成") { preview = nil }
                    }
                }
            }
        }
    }
}

// MARK: - 视频卡片（封面 + 时长，App 内无广告播放）

struct VideoList: View {
    let results: [SearchResult]
    @State private var play: SearchResult?

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                ForEach(results) { r in
                    Button { play = r } label: {
                        HStack(spacing: 10) {
                            ZStack(alignment: .bottomTrailing) {
                                AsyncImage(url: URL(string: r.thumbURL ?? "")) { phase in
                                    if case .success(let img) = phase {
                                        img.resizable().aspectRatio(contentMode: .fill)
                                    } else {
                                        ZStack { Theme.surface; Image(systemName: "play.rectangle") .foregroundStyle(Theme.dim) }
                                    }
                                }
                                .frame(width: 132, height: 78)
                                .clipped()
                                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                                if let d = r.duration, !d.isEmpty {
                                    Text(d).font(.system(size: 10, weight: .semibold))
                                        .padding(.horizontal, 4).padding(.vertical, 1)
                                        .background(.black.opacity(0.65))
                                        .foregroundStyle(.white)
                                        .clipShape(RoundedRectangle(cornerRadius: 3))
                                        .padding(4)
                                }
                            }
                            VStack(alignment: .leading, spacing: 4) {
                                Text(r.title).font(.system(size: 13, weight: .semibold))
                                    .foregroundStyle(Theme.ink)
                                    .lineLimit(2)
                                Text(r.source).font(.system(size: 11))
                                    .foregroundStyle(Theme.dim)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(10)
                        .background(Theme.surface)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(10)
        }
        .sheet(item: $play) { r in
            InAppBrowser(url: URL(string: r.url) ?? URL(string: "about:blank")!)
        }
    }
}
