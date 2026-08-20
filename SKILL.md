---
name: "pc-use"
description: "Cross-platform PC (macOS/Windows) observation and automation. Detects OS and uses native tools. Supports screenshot, accessibility tree, and UI interaction. Read-only actions require no confirmation; write actions require explicit user approval."
description_zh: "跨平台 PC（macOS/Windows）观测与自动化。自动检测系统并使用原生工具。支持截图、Accessibility Tree 和 UI 交互。只读操作无需确认，写操作需要明确用户审批。"
version: 1.3.0
display_name: "PC Use"
display_name_en: "PC Use"
display_name_zh: "PC Use"
visibility: "public"
---

# PC Use Skill

跨平台 PC 观测与自动化 Skill。自动检测操作系统并使用相应技术栈。

## ⚡ 执行策略：单截图 + 清理模式

**核心原则：**
1. **零截图执行** - 中间过程不截图，直接用命令完成操作
2. **单次验证截图** - 任务完成前只截一张图验证结果
3. **自动清理恢复** - 任务结束前关闭所有打开的窗口，恢复前台应用
4. **截图自动清理** - 任务完成后立即清理截图文件

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
```

### 7. 鼠标操作

```bash
# 点击坐标 (100, 200)
/usr/bin/swift -e 'import CoreGraphics; let p = CGPoint(x: 100, y: 200); let m = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: p, mouseButton: .left); m?.post(tap: .cghidEventTap)'
```

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

### 3. 读取 Accessibility Tree

```python
import uiautomation as auto

window = auto.GetForegroundControl()
print(f"Window: {window.Name}")

def print_control(control, depth=0):
    indent = "  " * depth
    print(f"{indent}{control.ControlTypeName}: {control.Name}")
    for child in control.GetChildren():
        print_control(child, depth + 1)

print_control(window)
```

### 4. 激活应用

```powershell
Start-Process "chrome"
```

### 5. 输入文本

```python
import pyautogui
pyautogui.write("Hello World", interval=0.1)
```

### 6. 发送按键

```python
import pyautogui
pyautogui.press('enter')
pyautogui.hotkey('ctrl', 'a')
```

### 7. 鼠标操作

```python
import pyautogui
pyautogui.click(100, 200)
pyautogui.scroll(100)
```

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

## 权限配置

### macOS
1. **辅助功能**: 系统设置 → 隐私与安全性 → 辅助功能
2. **屏幕录制**: 系统设置 → 隐私与安全性 → 屏幕录制
3. **输入监控**: 系统设置 → 隐私与安全性 → 输入监控

### Windows
1. **辅助功能**: 确保目标应用有 UI Automation 访问权限
2. **屏幕录制**: Windows 10+ 自动授予截图权限
3. **输入模拟**: pyautogui 需要管理员权限

## 错误处理

### macOS 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `-10004` | 未授予辅助功能权限 | 引导用户授予权限 |
| 截图失败 | 未授予屏幕录制权限 | 引导用户授予权限 |

### Windows 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `pyautogui` 导入失败 | 未安装 | `pip install pyautogui pywin32` |
| 权限不足 | 需要管理员权限 | 以管理员身份运行 |

## 故障排除

```bash
# macOS - 检查前台应用
swift -e 'import AppKit; print(NSWorkspace.shared.frontmostApplication?.localizedName ?? "unknown")'

# macOS - 测试 Accessibility 访问
osascript -e 'tell application "System Events" to get name of first process whose frontmost is true'
```

```powershell
# Windows - 检查前台窗口
Add-Type -AssemblyName System.Windows.Forms
Write-Output [System.Windows.Forms.Form]::FocusedForm?.Text
```
