# PC Use Skill

跨平台 PC 观测与自动化 Skill，支持 macOS 和 Windows。

## 功能特性

- **平台检测**: 自动识别 macOS / Windows
- **前台应用检测**: 获取当前活跃应用
- **截图验证**: 单次截图验证任务结果
- **Accessibility Tree**: 读取 UI 元素树
- **UI 交互**: 点击、输入、按键、滚动
- **自动清理**: 任务完成后清理临时文件

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 1.3.0 | 2026-08-20 | 添加单截图 + 清理模式 |
| 1.2.0 | 2026-08-20 | 优化执行流程，零中间截图 |
| 1.1.0 | 2026-08-20 | 初始版本 |

## 安装

将 `SKILL.md` 文件复制到:
- macOS: `~/.codex/skills/` 或 `/Users/skymini/Documents/skills/`
- Windows: `%USERPROFILE%\.codex\skills\`

## 使用示例

### 设置深色模式 (macOS)
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

## 权限配置

### macOS
需要在系统设置中授予：
- 辅助功能
- 屏幕录制
- 输入监控

### Windows
- 管理员权限（pyautogui）
- UI Automation 访问权限

## License

MIT
