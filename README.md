# 托管 Agent 操控电脑应用

跨平台 托管 Agent 操控电脑应用 Skill，支持 macOS 和 Windows。

媲美 Codex Computer Use 功能。

## 🎯 核心特性

- **双平台支持**: macOS 和 Windows
- **零截图执行**: 中间过程不截图，提升速度
- **单截图验证**: 仅任务完成时截图一次
- **自动清理**: 任务完成后自动清理临时文件
- **权限检测**: 自动检测并提示所需权限
- **Agent 兼容**: 支持 Codex、WorkBuddy、DSH、OpenCode 等

## 📦 安装

### 方法 1：手动安装

将 `SKILL.md` 文件复制到对应位置：

```bash
# macOS Codex/Desktop
cp SKILL.md ~/.codex/skills/pc-use/

# macOS WorkBuddy
ln -s ~/.skills ~/.workbuddy/skills

# Windows
copy SKILL.md %USERPROFILE%\.codex\skills\pc-use\
```

### 方法 2：通过 git clone

```bash
git clone https://github.com/skylincn/pc-use-skill.git
cd pc-use-skill
cp SKILL.md ~/.codex/skills/pc-use/
```

## 🚀 快速开始

### 设置深色模式
```bash
defaults write -g AppleInterfaceStyle Dark
```

### 设置浅色模式
```bash
defaults write -g AppleInterfaceStyle ""
```

### 设置自适应模式
```bash
defaults write -g AppleInterfaceStyleSwitchesAutomatically -bool true
defaults write -g NSAutomaticAppearanceVariationEnabled -bool true
```

## 📊 能力对比

| 功能 | pc-use skill | Codex Computer Use |
|------|--------------|-------------------|
| 平台检测 | ✅ | ✅ |
| 前台应用检测 | ✅ 无截图 | ✅ 需截图 |
| Accessibility Tree | ✅ | ✅ |
| 截图验证 | ✅ 单张 | ✅ 多张 |
| UI 交互 | ✅ | ✅ |
| 自动清理 | ✅ | ❌ |
| 命令执行 | ✅ 直接 | ⚠️ 浏览器依赖 |

## 🛠️ 支持的 Agent 软件

| 软件 | 状态 | 备注 |
|------|------|------|
| Codex Desktop | ✅ | 原生支持 |
| WorkBuddy | ✅ | macOS/Windows |
| DSH | ✅ | 跨平台 |
| OpenCode | ✅ | 开源版本 |
| Claude Desktop | ✅ | 通过 Skills |
| Cursor | ⚠️ | 需配置 |
| VS Code | ⚠️ | 需插件 |

## 📝 使用示例

### 示例 1：操作系统设置
```bash
# 打开系统设置
open -a "System Settings"

# 导航到特定面板
open "x-apple.systempreferences:com.apple.Appearance-Settings.extension"
```

### 示例 2：文件操作
```bash
# 创建目录
mkdir -p /tmp/project

# 列出文件
ls -la /tmp/project
```

### 示例 3：浏览器操作
```bash
# 打开 Chrome
open -a "Google Chrome" "https://example.com"
```

## 🔒 权限配置

### macOS
需要在系统设置中授予：
- 辅助功能
- 屏幕录制
- 输入监控

### Windows
- 管理员权限（pyautogui）
- UI Automation 访问权限


## 📊 详细对比分析

完整对比文档请查看 [COMPARISON.md](COMPARISON.md)

### 核心架构对比

| 维度 | PC Use v2.0 | oil-oil/cua | wimi321/mcu | Codex CUA |
|------|:----------:|:----------:|:----------:|:--------:|
| **架构** | Python MCP + 持久 Swift Helper | Shell + cliclick | MCP Server (TypeScript) | 闭源 SDK |
| **通信协议** | JSON-lines (stdin/stdout) | 进程 spawn | MCP stdio | SDK 直连 |
| **进程模型** | 单次启动，持久运行 | 每次操作 spawn | 每次请求 spawn | 常驻后台 |
| **依赖项** | Python 3.11 + MCP SDK | cliclick (brew) | Node.js + TypeScript | 无 |
| **跨平台** | macOS + Windows | macOS only | macOS only | macOS/Windows |

### 性能对比（实测 Apple M4）

| 操作 | PC Use v2.0 | oil-oil/cua | wimi321/mcu | Codex CUA |
|------|:---------:|:---------:|:---------:|:--------:|
| 鼠标点击 | 36ms | 80ms | 120ms | 10ms |
| 滚动 | 32ms | 90ms | 150ms | 15ms |
| 输入文字 | 41ms | 100ms | 130ms | 20ms |
| 获取前台应用 | 6ms | 80ms | 50ms | 10ms |
| **平均延迟** | **60ms** | **83ms** | **111ms** | **15ms** |

### Token 消耗对比

| 操作 | PC Use v2.0 | oil-oil/cua | wimi321/mcu |
|------|:----------:|:----------:|:----------:|
| 获取前台应用 | **0 token** | 500+ tokens | 200+ tokens |
| 点击/滚动 | **0 token** | 0 token | 0 token |
| **关键优势** | **零截图执行** | 需截图 | 需截图 |

### 功能覆盖对比

| 功能 | PC Use v2.0 | oil-oil/cua | wimi321/mcu | Codex CUA |
|------|:----------:|:----------:|:----------:|:--------:|
| 平台检测 | ✅ | ✅ | ✅ | ✅ |
| 权限自动检测 | ✅ | ❌ | ✅ | ✅ |
| Retina 缩放支持 | ✅ | ✅ | ✅ | ✅ |
| 中文输入优化 | ✅ | ✅ | ✅ | ✅ |
| 单截图验证 | ✅ | ❌ | ❌ | ❌ |
| 自动清理 | ✅ | ❌ | ✅ | ❌ |
| MCP Server | ✅ | ❌ | ✅ | ❌ |
| 并发控制 | ✅ (Semaphore) | ❌ | ⚠️ | ❌ |
| Accessibility Tree | ✅ | ❌ | ✅ | ✅ |

### 独有功能

**PC Use v2.0 独有**：
- ✓ 持久 Swift 进程 - 消除启动开销
- ✓ 零截图执行 - 节省 90% Token
- ✓ 内置并发控制 - Semaphore(5)
- ✓ 跨平台统一 API - macOS + Windows

---
## 📄 License

MIT
