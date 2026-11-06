import SwiftUI
import WebKit
import AVKit

// MARK: - 视频流嗅探 + 播放（点开就能看，不用下载种子）

/// 嗅探 WKWebView 里的 m3u8 / mp4 请求，拿到地址后用 AVPlayer 直接播。
struct StreamSnifferView: View {
    let url: URL
    @Environment(\.dismiss) private var dismiss
    @State private var stream: URL?
    @State private var playURL: URL?
    @State private var hint = "正在加载页面…"

    var body: some View {
        NavigationStack {
            ZStack(alignment: .bottom) {
                SnifferWeb(url: url, onStream: { found in
                    stream = found
                    hint = "已抓到播放地址"
                }, onStatus: { s in hint = s })

                VStack(spacing: 8) {
                    Text(hint).font(.system(size: 11)).foregroundStyle(.white.opacity(0.8))
                    Button {
                        playURL = stream
                    } label: {
                        Label(stream == nil ? "正在嗅探播放地址…" : "▶ 立即播放",
                              systemImage: "play.fill")
                            .font(.system(size: 15, weight: .bold))
                            .padding(.horizontal, 22).padding(.vertical, 12)
                            .background(stream == nil ? Color.gray : Color.green)
                            .foregroundStyle(.black)
                            .clipShape(Capsule())
                    }
                    .disabled(stream == nil)
                }
                .padding(.bottom, 18)
            }
            .ignoresSafeArea(edges: .bottom)
            .navigationTitle("嗅探播放")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) { Button("完成") { dismiss() } }
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("刷新") { stream = nil; hint = "重新嗅探…" }
                }
            }
            .fullScreenCover(item: $playURL) { u in VideoPlayerView(url: u) }
        }
    }
}

struct VideoPlayerView: View {
    let url: URL
    @Environment(\.dismiss) private var dismiss
    @State private var player: AVPlayer?
    @State private var failed = false

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if let p = player {
                VideoPlayer(player: p)
                    .ignoresSafeArea()
                    .onAppear { p.play() }
            } else {
                ProgressView().tint(.white)
            }
            VStack {
                HStack {
                    Spacer()
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 16, weight: .bold))
                            .padding(10)
                            .background(.black.opacity(0.55))
                            .foregroundStyle(.white)
                            .clipShape(Circle())
                    }
                    .padding(14)
                }
                Spacer()
                if failed {
                    VStack(spacing: 8) {
                        Text("这个地址播不了（可能需要 Referer 或已过期）")
                            .font(.system(size: 12)).foregroundStyle(.white)
                        Button("复制地址，用其他播放器") {
                            UIPasteboard.general.string = url.absoluteString
                        }
                        .font(.system(size: 12, weight: .semibold))
                        .padding(.horizontal, 14).padding(.vertical, 8)
                        .background(.white.opacity(0.2))
                        .foregroundStyle(.white)
                        .clipShape(Capsule())
                    }
                    .padding(.bottom, 40)
                }
            }
        }
        .onAppear {
            let asset = AVURLAsset(url: url)
            let item = AVPlayerItem(asset: asset)
            player = AVPlayer(playerItem: item)
            NotificationCenter.default.addObserver(
                forName: .AVPlayerItemFailedToPlayToEndTime, object: item, queue: .main) { _ in
                failed = true
            }
        }
        .onDisappear { player?.pause() }
    }
}

private struct SnifferWeb: UIViewRepresentable {
    let url: URL
    let onStream: (URL) -> Void
    let onStatus: (String) -> Void

    func makeCoordinator() -> Coord { Coord(self) }

    func makeUIView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.allowsInlineMediaPlayback = true
        cfg.mediaTypesRequiringUserActionForPlayback = .all
        cfg.defaultWebpagePreferences.preferredContentMode = .desktop
        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.navigationDelegate = context.coordinator
        wv.uiDelegate = context.coordinator
        AdBlocker.install { list in
            if let list = list { wv.configuration.userContentController.add(list) }
            wv.load(URLRequest(url: url))
        }
        context.coordinator.startSniffing(wv)
        return wv
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coord: NSObject, WKNavigationDelegate, WKUIDelegate {
        let parent: SnifferWeb
        private var timer: Timer?
        private var found = false

        init(_ p: SnifferWeb) { parent = p }

        func startSniffing(_ wv: WKWebView) {
            timer?.invalidate()
            timer = Timer.scheduledTimer(withTimeInterval: 1.2, repeats: true) { [weak self] _ in
                guard let self, !self.found else { return }
                self.scan(wv)
            }
        }

        private func scan(_ wv: WKWebView) {
            let js = """
            (function(){
              // 1) 页面里的 video 元素
              var vids = document.querySelectorAll('video, source');
              for (var i=0;i<vids.length;i++){
                var s = vids[i].src || vids[i].currentSrc || vids[i].getAttribute('src');
                if (s && (s.indexOf('.m3u8')>=0 || s.indexOf('.mp4')>=0)) return s;
              }
              // 2) 资源时间线（真正的流地址常在这里）
              var es = performance.getEntriesByType('resource') || [];
              for (var j=es.length-1;j>=0;j--){
                var n = es[j].name || '';
                if (n.indexOf('.m3u8')>=0) return n;
              }
              for (var k=es.length-1;k>=0;k--){
                var m = es[k].name || '';
                if (m.indexOf('.mp4')>=0) return m;
              }
              return '';
            })();
            """
            wv.evaluateJavaScript(js) { result, _ in
                guard let s = result as? String, !s.isEmpty,
                      let u = URL(string: s) else { return }
                self.found = true
                self.timer?.invalidate()
                self.timer = nil
                self.parent.onStream(u)
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            parent.onStatus("页面已加载，等待播放器请求…")
        }

        func webView(_ webView: WKWebView,
                     createWebViewWith configuration: WKWebViewConfiguration,
                     for navigationAction: WKNavigationAction,
                     windowFeatures: WKWindowFeatures) -> WKWebView? {
            // 页面内点播放常走新窗口：改在同一个 webview 里加载
            if let u = navigationAction.request.url { webView.load(URLRequest(url: u)) }
            return nil
        }
    }
}


extension URL: Identifiable {
    public var id: String { absoluteString }
}
