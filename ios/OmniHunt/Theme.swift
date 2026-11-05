import SwiftUI

enum Theme {
    static let bg = Color(hex: 0x0A0C10)
    static let panel = Color(hex: 0x11151C)
    static let card = Color(hex: 0x12161E)
    static let line = Color(hex: 0x232B38)
    static let ink = Color(hex: 0xE8EDF5)
    static let muted = Color(hex: 0x8B97A8)
    static let dim = Color(hex: 0x5C6675)

    static let accent = Color(hex: 0x5EF2B0)
    static let accentDeep = Color(hex: 0x39C98D)
    static let web = Color(hex: 0x5CC8FF)
    static let onion = Color(hex: 0xC48BFF)
    static let adult = Color(hex: 0xFF85C0)
    static let torrent = Color(hex: 0xFFCC66)
    static let pattern = Color(hex: 0x8B97A8)

    static func color(for kind: ResultKind) -> Color {
        switch kind {
        case .web: return web
        case .onion: return onion
        case .adult: return adult
        case .torrent: return torrent
        case .pattern: return pattern
        }
    }
}

extension Color {
    init(hex: UInt32, alpha: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: alpha
        )
    }
}

/// The rounded gradient mark used in the header, mirrors the web UI logo.
struct BrandMark: View {
    var size: CGFloat = 38

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.29, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [Theme.accent, Theme.web, Theme.onion],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
            RoundedRectangle(cornerRadius: size * 0.17, style: .continuous)
                .fill(Theme.bg)
                .padding(size * 0.24)
        }
        .frame(width: size, height: size)
    }
}
