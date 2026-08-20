---
name: "pc-use"
description: "Cross-platform PC (macOS/Windows) observation and automation. Detects OS and uses native tools. Supports screenshot, accessibility tree, and UI interaction. Read-only actions require no confirmation; write actions require explicit user approval."
description_zh: "跨平台 PC（macOS/Windows）观测与自动化。自动检测系统并使用原生工具。支持截图、Accessibility Tree 和 UI 交互。只读操作无需确认，写操作需要明确用户审批。"
version: 1.4.0
display_name: "PC Use"
display_name_en: "PC Use"
display_name_zh: "PC Use"
visibility: "public"
---

# PC Use Skill

跨平台 PC 观测与自动化 Skill。自动检测操作系统并使用相应技术栈。

**兼容性**: Codex Desktop / DSh / WorkBuddy / OpenCode / 任何其他支持 Skills 的 Agent 软件

**对标能力**: 媲美 Codex Desktop 的 Computer Use，支持 macOS 和 Windows 双平台

---

## ⚡ 执行策略：单截图 + 清理模式

**核心原则：**
1. **零截图执行** - 中间过程不截图，直接用命令完成操作
2. **单次验证截图** - 任务完成前只截一张图验证结果
3. **自动清理恢复** - 任务结束前关闭所有打开的窗口，恢复前台应用
4. **截图自动清理** - 任务完成后立即清理截图文件

---

## 前置检查

执行任何操作前，检查操作系统：

```bash
UNAME=$(uname -s)
if [[ "$UNAME" == "Darwin" ]]; then
    PLATFORM="macOS"
elif [[ "$UNAME" == MINGW* ]] || [[ "$UNAME" == MSYS* ]] || [[ "$UNAME" == CYGWIN* ]] || [[ "$UNAME" == NT ]]; then
    PLATFORM="Windows"
else
    PLATFORM="unknown"
fi
echo "Platform: $PLATFORM"
```

**记录当前前台应用**（用于后续恢复）：
```bash
FRONT_APP=$(/usr/bin/swift -e 'import AppKit; print(NSWorkspace.shared.frontmostApplication?.localizedName ?? "unknown")' 2>/dev/null)
echo "Front app: $FRONT_APP"
```

---

## 核心能力对比

| 能力 | pc-use skill | Codex Computer Use |
|------|--------------|-------------------|
| 平台检测 | ✅ macOS/Windows | ✅ macOS/Windows |
| 前台应用检测 | ✅ 无需截图 | ✅ 需要截图 |
| Accessibility Tree | ✅ System Events | ✅ 内置支持 |
| 截图验证 | ✅ 单张截图 | ✅ 多张截图 |
| UI 交互 | ✅ 点击/输入/按键 | ✅ 点击/输入/按键 |
| 自动清理 | ✅ 任务后清理 | ❌ 需手动清理 |
| 命令执行 | ✅ 直接命令行 | ⚠️ 依赖浏览器 |
| 权限配置 | ✅ 自动检测 | ✅ 自动检测 |

---

## macOS 命令

### 1. 观察前台应用（不截图）

```bash
/usr/bin/swift -e 'import AppKit; print(NSWorkspace.shared.frontmostApplication?.localizedName ?? "unknown")'
```

### 2. 截取屏幕（仅最终验证时使用）

```bash
# 只在全局任务完成时截图一次
TIMESTAMP=$(date +%s)
IMG_PATH="/tmp/pc-use-final-${TIMESTAMP}.png"
/usr/sbin/screencapture -x "$IMG_PATH"
echo "$IMG_PATH"
```

### 3. 读取 Accessibility Tree

```bash
/usr/bin/osascript 2>&1 << 'APPLESCRIPT'
tell application "System Events"
    set frontAppName to name of first process whose frontmost is true
    try
        tell process frontAppName
            set elemList to {}
            try
                set mainWin to window 1
                set elems to UI elements of mainWin
                repeat with ctrl in elems
                    try
                        set r to role of ctrl
                        set n to name of ctrl
                        if r is not missing value and n is not missing value then
                            set end of elemList to (r as text) & "|" & (n as text)
                        else if r is not missing value then
                            set end of elemList to (r as text) & "|"
                        end if
                    on error
                        skip
                    end try
                end repeat
            on error
                skip
            end try
            
            if (count of elemList) > 0 then
                set AppleScript's text item delimiters to linefeed
                return "App: " & frontAppName & linefeed & (elemList as text)
            else
                return "App: " & frontAppName & linefeed & "(no accessible elements)"
            end if
        end tell
    on error errMsg
        return "Error: " & errMsg
    end try
end tell
APPLESCRIPT
```

### 4. 激活应用

```bash
/usr/bin/osascript -e 'tell application "Google Chrome" to activate'
```

### 5. 输入文本

```bash
/usr/bin/osascript -e 'tell application "System Events" to keystroke "Hello World"'
```

### 6. 发送按键

```bash
# Enter
/usr/bin/osascript -e 'tell application "System Events" to key code 36'

# Cmd+A
/usr/bin/osascript -e 'tell application "System Events" to keystroke "a" using command down'

# 方向键
/usr/bin/osascript -e 'tell application "System Events" to key code 124'  # Right
/usr/bin/osascript -e 'tell application "System Events" to key code 126'  # Up
```

### 7. 鼠标操作

```bash
# 点击坐标 (100, 200)
/usr/bin/swift -e 'import CoreGraphics; let p = CGPoint(x: 100, y: 200); let m = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: p, mouseButton: .left); m?.post(tap: .cghidEventTap)'

# 滚动
/usr/bin/swift -e 'import CoreGraphics; let e = CGEvent(scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 1, wheel1: Int32(100), wheel2: 0, wheel3: 0)!; e.post(tap: .cghidEventTap)'
```

---

## Windows 命令

### 1. 观察前台窗口

```powershell
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class WinAPI {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);
}
"@
$hwnd = [WinAPI]::GetForegroundWindow()
$title = New-Object System.Text.StringBuilder(256)
[WinAPI]::GetWindowText($hwnd, $title, 256) | Out-Null
Write-Output $title.ToString()
```

或使用 Python：

```python
import pyautogui
import win32gui

hwnd = win32gui.GetForegroundWindow()
title = win32gui.GetWindowText(hwnd)
print(f"Foreground: {title} (HWND: {hwnd})")
```

### 2. 截取屏幕（仅最终验证时使用）

```powershell
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$path = "C:\temp\pc-use-final-${timestamp}.png"
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait("{PRTSC}")
Start-Sleep -Milliseconds 500
$img = [System.Windows.Forms.Clipboard]::GetImage()
$img.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Output $path
```

或使用 Python：

```python
import pyautogui
import datetime

timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
path = f"/tmp/pc-use-{timestamp}.png"
img = pyautogui.screenshot()
img.save(path)
print(path)
```

### 3. 读取 Accessibility Tree

```python
import uiautomation as auto

# 获取前台窗口
window = auto.GetForegroundControl()
print(f"Window: {window.Name}")

# 遍历 UI 元素
def print_control(control, depth=0):
    indent = "  " * depth
    print(f"{indent}{control.ControlTypeName}: {control.Name} ({control.AutomationId})")
    for child in control.GetChildren():
        print_control(child, depth + 1)

print_control(window)
```

### 4. 激活应用

```powershell
# 启动应用
Start-Process "chrome"

# 激活已有窗口
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class WinAPI {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr FindWindow(string className, string windowName);
}
"@
$hwnd = [WinAPI]::FindWindow($null, "Google Chrome")
[WinAPI]::SetForegroundWindow($hwnd)
```

### 5. 输入文本

```powershell
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait("Hello World")
```

或使用 Python：

```python
import pyautogui
pyautogui.write("Hello World", interval=0.1)
```

### 6. 发送按键

```powershell
Add-Type -AssemblyName System.Windows.Forms

# Enter
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")

# Ctrl+A
[System.Windows.Forms.SendKeys]::SendWait("^a")

# 方向键
[System.Windows.Forms.SendKeys]::SendWait("{RIGHT}")
```

或使用 Python：

```python
import pyautogui

pyautogui.press('enter')
pyautogui.hotkey('ctrl', 'a')
pyautogui.press('right')
```

### 7. 鼠标操作

```python
import pyautogui

# 点击
pyautogui.click(100, 200)

# 双击
pyautogui.click(100, 200, clicks=2)

# 右键
pyautogui.rightClick(100, 200)

# 滚动
pyautogui.scroll(100)  # 向上
pyautogui.scroll(-100)  # 向下

# 拖拽
pyautogui.dragTo(300, 400, duration=1)
```

---

## 标准执行流程

```
1. 记录当前前台应用
   FRONT_APP=$(前台应用检测命令)

2. 执行任务操作（不截图）
   - 使用命令行直接操作
   - 避免不必要的 UI 导航

3. 最终验证截图（仅一次）
   TIMESTAMP=$(date +%s)
   screencapture -x /tmp/pc-use-final-${TIMESTAMP}.png

4. 清理截图文件
   find /tmp -name "pc-use-final-*.png" -type f -delete

5. 清理恢复
   - 关闭打开的窗口
   - 恢复前台应用到 FRONT_APP
```

---

## 应用场景示例

### 示例 1：设置深色/浅色/自适应模式

```bash
# 平台检测
UNAME=$(uname -s)
if [[ "$UNAME" == "Darwin" ]]; then
    echo "macOS detected"
fi

# 设置深色模式
defaults write -g AppleInterfaceStyle Dark

# 设置浅色模式
defaults write -g AppleInterfaceStyle ""

# 设置自适应模式（根据日出日落自动切换）
defaults write -g AppleInterfaceStyleSwitchesAutomatically -bool true
defaults write -g NSAutomaticAppearanceVariationEnabled -bool true
```

### 示例 2：操作系统设置

```bash
# 打开系统设置并导航到特定面板
open "x-apple.systempreferences:com.apple.Appearance-Settings.extension"
open "x-apple.systempreferences:com.apple.preferences.wifi"
open "x-apple.systempreferences:com.apple.preferences.bluetooth"
```

### 示例 3：文件管理操作

```bash
# 创建目录
mkdir -p /tmp/project && echo "✓ 目录已创建"

# 列出文件
ls -la /tmp/project

# 复制文件
cp source.txt /tmp/project/ && echo "✓ 文件已复制"
```

### 示例 4：浏览器自动化

```bash
# 打开 Chrome
open -a "Google Chrome" "https://example.com"

# 使用 Selenium（需要安装）
python3 -c "
from selenium import webdriver
driver = webdriver.Chrome()
driver.get('https://example.com')
print(driver.title)
driver.quit()
"
```

---

## 截图自动清理

### macOS 清理

```bash
# 任务完成后立即清理截图
find /tmp -name "pc-use-final-*.png" -type f -mmin +0 -delete

# macOS /tmp 自动清理机制：
# - 系统重启时自动清理
# - 超过 24 小时未访问的文件会被清理
```

### Windows 清理

```powershell
# 任务完成后立即清理截图
Get-ChildItem "C:\temp\pc-use-final-*.png" | Where-Object { $_.LastAccessTime -lt (Get-Date).AddMinutes(-1) } | Remove-Item -Force
```

---

## 清理恢复命令

### macOS 清理

```bash
# 关闭指定的应用窗口
osascript -e "tell application \"System Settings\" to quit" 2>/dev/null

# 恢复前台应用
open -a "$FRONT_APP" 2>/dev/null
```

### Windows 清理

```powershell
# 关闭指定窗口
Stop-Process -Name "控制面板" -Force 2>$null

# 恢复前台应用
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class WinAPI {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@
# 找到并恢复原窗口
```

---

## 安全策略

### 确认模式

| 操作类型 | 确认要求 |
|----------|----------|
| 只读操作（observe、accessibility_tree） | 无需确认 |
| 写操作（设置、点击、输入） | 执行前说明，等待确认 |
| 高风险操作（删除、支付） | 必须明确确认 |

### 风险分类

**需额外确认：**
- 删除文件或数据
- 修改系统安全设置
- 登录或提交表单
- 输入敏感信息

**无需额外确认：**
- 读取应用状态
- 截图验证
- 用户明确要求的设置操作

---

## 权限配置

### macOS

用户需要在以下位置授予权限：

1. **辅助功能**: 系统设置 → 隐私与安全性 → 辅助功能 → 添加对应应用
2. **屏幕录制**: 系统设置 → 隐私与安全性 → 屏幕录制 → 添加对应应用
3. **输入监控**: 系统设置 → 隐私与安全性 → 输入监控 → 添加对应应用

### Windows

1. **辅助功能**: 确保目标应用有 UI Automation 访问权限
2. **屏幕录制**: Windows 10+ 自动授予截图权限
3. **输入模拟**: pyautogui 需要管理员权限才能正常工作

---

## 错误处理

### macOS 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `-10004` / `Accessibility unavailable` | 未授予辅助功能权限 | 引导用户授予权限 |
| 截图失败 | 未授予屏幕录制权限 | 引导用户授予权限 |
| `element_index` 无效 | UI 状态已变化 | 重新调用 observe 获取最新状态 |

### Windows 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `pyautogui` 导入失败 | 未安装 | `pip install pyautogui pywin32` |
| 权限不足 | 需要管理员权限 | 以管理员身份运行 |
| UI Automation 失败 | 应用不支持 UIA | 使用截图 + 坐标操作 |

---

## 故障排除

```bash
# macOS - 检查前台应用
swift -e 'import AppKit; print(NSWorkspace.shared.frontmostApplication?.localizedName ?? "unknown")'

# macOS - 测试 Accessibility 访问
osascript -e 'tell application "System Events" to get name of first process whose frontmost is true'

# macOS - 重置权限（谨慎使用）
tccutil reset All com.apple.Terminal
tccutil reset All com.openai.chat
```

```powershell
# Windows - 检查前台窗口
Add-Type -AssemblyName System.Windows.Forms
Write-Output [System.Windows.Forms.Form]::FocusedForm?.Text

# Windows - 安装依赖
pip install pyautogui pywin32 uiautomation
```

---

## 兼容的 Agent 软件

| 软件 | 支持状态 | 备注 |
|------|----------|------|
| Codex Desktop | ✅ 完全支持 | 对标 computer-use |
| WorkBuddy | ✅ 完全支持 | macOS/Windows |
| DSh | ✅ 完全支持 | 跨平台 |
| OpenCode | ✅ 完全支持 | 开源版本 |
| Claude Desktop | ✅ 完全支持 | 通过 Skills |
| Cursor | ⚠️ 部分支持 | 需要额外配置 |
| VS Code | ⚠️ 部分支持 | 通过插件 |

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 1.4.0 | 2026-08-20 | 添加 Agent 软件兼容性列表 |
| 1.3.0 | 2026-08-20 | 添加单截图 + 清理模式 |
| 1.2.0 | 2026-08-20 | 优化执行流程，零中间截图 |
| 1.1.0 | 2026-08-20 | 初始版本 |

---

## License

MIT
