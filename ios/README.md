# OmniHunt · iOS 客户端（SwiftUI）

原生 iOS 前端，连同一台电脑上的 `omnihunt serve`，复用它的聚合内核（Bing / 百度 / 360 / Ahmia / OnionSearchEngine / 成人目录 / 磁力目录）。

## 目录

```
ios/
├─ project.yml                 # XcodeGen 工程描述
└─ OmniHunt/
   ├─ OmniHuntApp.swift        # @main
   ├─ ContentView.swift        # 搜索栏 / 类型筛选 / 结果列表 / 空态
   ├─ ResultRow.swift          # 结果卡片：复制 / 打开 / 磁力 / 分享
   ├─ SettingsView.swift       # 服务器地址、连通性测试、默认值
   ├─ SearchStore.swift        # @MainActor 状态机（取消、超时、错误归属）
   ├─ APIClient.swift          # async/await URLSession + Codable
   ├─ Models.swift             # SearchResponse / SearchResult / JSONValue
   ├─ AppSettings.swift        # UserDefaults 持久化
   ├─ Theme.swift              # 配色 + 品牌图标
   ├─ Info.plist               # ATS 例外 + 局域网权限
   └─ Assets.xcassets          # AppIcon 1024 / AccentColor
```

## 构建（需要 macOS + Xcode 15+）

```bash
brew install xcodegen
cd ios
xcodegen generate
open OmniHunt.xcodeproj
```

1. **Signing & Capabilities**：选自己的 Team，把 `PRODUCT_BUNDLE_IDENTIFIER` 改成自己的域名。
2. 选模拟器或真机运行。
3. 首次请求局域网会弹「本地网络」权限，允许即可。
4. 点右上角齿轮，把服务器地址填成 `http://<电脑IP>:7860`，点「测试连接」应显示 `已连接 · 8 个引擎`。

模拟器直接用 `http://127.0.0.1:7860` 也能连（模拟器和 Mac 共享 loopback）。

命令行打包（签名配好后）：

```bash
xcodebuild -project OmniHunt.xcodeproj -scheme OmniHunt \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath build/OmniHunt.xcarchive archive
```

导出 IPA 需要 `ExportOptions.plist`（含 Team ID 与分发方式），Xcode 的 Organizer 里点一次 Export 就会生成模板。

## 电脑端要先这么起

```powershell
cd E:\deepseeek\omnihunt
python -m omnihunt serve --host 0.0.0.0 --port 7860
```

- `--host 0.0.0.0` 才会监听局域网；默认只监听 `127.0.0.1`，手机连不上。
- 查本机 IP：`ipconfig | findstr IPv4`，例如 `192.168.3.2`。
- Windows 防火墙需放行 7860（首次运行 Python 时点「允许访问」即可；或用管理员 PowerShell）：

```powershell
New-NetFirewallRule -DisplayName "OmniHunt 7860" -Direction Inbound -Protocol TCP -LocalPort 7860 -Action Allow
```

- 手机和电脑必须在同一 Wi-Fi / 同一网段，访客网络或 AP 隔离会挡。

## 设计要点

- **后端不变**：App 只打 `/api/search`、`/health`、`/api/engines`，聚合、去重、排序、缓存、Tor 出口都在 Python 侧；换引擎不用重发 App。
- **取消与超时**：每次搜索取消上一个 Task；请求 35s，整轮由后端 25s 收口，单个引擎失败只进「N 个引擎失败」面板。
- **类型筛选**：全部 / 网页 / 暗网 / 成人 / 磁力 / 模式，切换即重查（`kinds=` 参数）。
- **磁力**：结果 `extra.magnet` 存在时按钮变「磁力」，一点复制 `magnet:?xt=urn:btih:...`。
- **打开方式**：`.onion` 默认交系统浏览器；要真正打开请装 Tor Browser，或复制链接到 Tor 里。
- **ATS**：`NSAllowsArbitraryLoads + NSAllowsLocalNetworking` 允许明文局域网地址；这是本地工具，别拿去连公网 HTTP。

## 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 连不上，提示 transport error | 后端没开 `--host 0.0.0.0`，或防火墙挡了，或不在同一网段 |
| 首次请求转圈很久 | iOS 本地网络权限弹窗在后台，回桌面再进一次 |
| 暗网筛选 0 条 | 中文关键词在 onion 索引里基本 0 命中；换英文，或看目录入口 |
| 部分引擎失败 | 正常现象，点开错误面板看具体站点；不影响其他结果 |
| 想改 UI 颜色 | `Theme.swift` 一处改完，全局生效 |

## 不想装 Xcode？

用同一套 Web UI 的 PWA：iPhone Safari 打开 `http://<电脑IP>:7860` → 分享 → **添加到主屏幕**，得到全屏无地址栏的 App 图标，功能与网页一致。
