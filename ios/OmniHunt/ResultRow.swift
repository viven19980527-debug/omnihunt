import SwiftUI
import UIKit

struct KindBadge: View {
    let kind: ResultKind

    var body: some View {
        Text(kind.englishLabel.uppercased())
            .font(.system(size: 9.5, weight: .semibold, design: .monospaced))
            .tracking(0.8)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .foregroundStyle(Theme.color(for: kind))
            .overlay(
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .stroke(Theme.color(for: kind).opacity(0.85), lineWidth: 1)
            )
    }
}

struct ResultRow: View {
    let result: SearchResult

    @State private var browser: URL?
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                KindBadge(kind: result.kind)
                Text(result.title.isEmpty ? result.url : result.title)
                    .font(.system(size: 15.5, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Text(result.url)
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(Color(hex: 0x6F8BA8))
                .lineLimit(2)
                .truncationMode(.middle)

            if let snippet = result.snippet, !snippet.isEmpty {
                Text(snippet)
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.muted)
                    .lineLimit(3)
            }

            HStack(spacing: 10) {
                Text(result.allSources.joined(separator: " · "))
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.dim)
                    .lineLimit(1)

                Text(String(format: "%.2f", result.score))
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Theme.dim)

                Spacer(minLength: 4)

                Button { copy(result.magnet ?? result.url) } label: {
                    Label(result.magnet == nil ? "复制" : "磁力",
                          systemImage: copied ? "checkmark" : "doc.on.doc")
                        .font(.system(size: 11, weight: .medium))
                }
                .buttonStyle(.bordered)
                .controlSize(.mini)
                .tint(Theme.line)

                Button { open(result.url) } label: {
                    Label("打开", systemImage: "arrow.up.right")
                        .font(.system(size: 11, weight: .medium))
                }
                .buttonStyle(.bordered)
                .controlSize(.mini)
                .tint(Theme.accentDeep)
            }
        }
        .padding(13)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.card)
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .stroke(Theme.line, lineWidth: 1)
        )
        .contextMenu {
            Button { copy(result.url) } label: { Label("复制链接", systemImage: "link") }
            if let magnet = result.magnet {
                Button { copy(magnet) } label: {
                    Label("复制磁力", systemImage: "dot.radiowaves.left.and.right")
                }
            }
            if let url = URL(string: result.url) {
                ShareLink(item: url)
            }
        }
        .sheet(item: $browser) { url in InAppBrowser(url: url) }
    }

    private func copy(_ text: String) {
        UIPasteboard.general.string = text
        copied = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
            copied = false
        }
    }

    private func open(_ string: String) {
        guard let url = URL(string: string), url.scheme?.hasPrefix("http") == true else { return }
        browser = url          // 走 App 内拦截广告的浏览器
    }
}
