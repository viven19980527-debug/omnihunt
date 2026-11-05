import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var settings: AppSettings
    @Environment(\.dismiss) private var dismiss

    @State private var testState: TestState = .idle

    enum TestState: Equatable {
        case idle
        case running
        case ok(String)
        case failed(String)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("http://192.168.3.2:7860", text: $settings.baseURLString)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Button {
                        Task { await runTest() }
                    } label: {
                        HStack {
                            Text("测试连接")
                            Spacer()
                            if testState == .running {
                                ProgressView()
                            }
                        }
                    }

                    testStatus
                } header: {
                    Text("服务器")
                } footer: {
                    Text("电脑上运行：python -m omnihunt serve --host 0.0.0.0 --port 7860；手机与电脑需在同一 Wi-Fi，Windows 防火墙需放行该端口。")
                }

                Section {
                    Toggle("默认附加查询模式", isOn: $settings.patternsDefault)
                    Stepper(value: $settings.limit, in: 10...100, step: 10) {
                        Text("结果上限 \(settings.limit)")
                    }
                } header: {
                    Text("搜索默认值")
                }

                Section {
                    Label(".onion 结果需要用 Tor 浏览器打开", systemImage: "shield.lefthalf.filled")
                    Label("本 App 只做聚合与跳转，不代理任何内容", systemImage: "arrow.up.right.square")
                    Label("每个引擎独立超时，单个源失败不影响其他结果", systemImage: "clock.arrow.circlepath")
                } header: {
                    Text("说明")
                }
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
        }
    }

    @ViewBuilder
    private var testStatus: some View {
        switch testState {
        case .idle:
            EmptyView()
        case .running:
            Text("连接中…")
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
        case .ok(let detail):
            Label(detail, systemImage: "checkmark.circle")
                .font(.system(size: 12))
                .foregroundStyle(Theme.accentDeep)
        case .failed(let detail):
            Label(detail, systemImage: "exclamationmark.triangle")
                .font(.system(size: 12))
                .foregroundStyle(Color(hex: 0xFFB86B))
        }
    }

    private func runTest() async {
        guard let url = settings.baseURL else {
            testState = .failed("地址无效，需要形如 http://192.168.3.2:7860")
            return
        }
        testState = .running
        do {
            let health = try await APIClient(baseURL: url).health()
            testState = .ok("已连接 · \(health.engines) 个引擎")
        } catch {
            let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            testState = .failed(message)
        }
    }
}
