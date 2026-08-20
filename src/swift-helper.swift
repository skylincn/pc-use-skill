#!/usr/bin/env swift
import AppKit
import CoreGraphics
import Foundation

func respond(id: String, success: Bool, data: Any? = nil, error: String? = nil) {
    var resp: [String: Any] = ["id": id, "success": success]
    if let data = data { resp["data"] = data }
    if let error = error { resp["error"] = error }
    if let json = try? JSONSerialization.data(withJSONObject: resp) {
        if let str = String(data: json, encoding: .utf8) {
            print(str)
        }
    }
}

func handleScreenshot(_ params: [String: Any], id: String) {
    let crop = params["crop"] as? [String: Any]
    var cmd = ["screencapture", "-x"]
    if let c = crop {
        cmd += ["-R", "\(c["x"] as? Int ?? 0),\(c["y"] as? Int ?? 0),\(c["w"] as? Int ?? 800),\(c["h"] as? Int ?? 600)"]
    }
    let path = NSTemporaryDirectory() + "pc-use-" + Date().formatted(date: .numeric, time: .omitted).replacingOccurrences(of: "/", with: "-") + ".png"
    cmd.append(path)
    
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
    task.arguments = Array(cmd.dropFirst())
    try? task.run()
    task.waitUntilExit()
    
    if task.terminationStatus == 0 {
        respond(id: id, success: true, data: ["path": path])
    } else {
        respond(id: id, success: false, error: "Screenshot failed")
    }
}

func handleClick(_ params: [String: Any], id: String) {
    let source = CGEventSource(stateID: .hidSystemState)
    let down = CGEvent(mouseEventSource: source, mouseType: .leftMouseDown, mouseCursorPosition: NSEvent.mouseLocation, mouseButton: .left)
    let up = CGEvent(mouseEventSource: source, mouseType: .leftMouseUp, mouseCursorPosition: NSEvent.mouseLocation, mouseButton: .left)
    down?.post(tap: .cghidEventTap)
    up?.post(tap: .cghidEventTap)
    respond(id: id, success: true)
}

func handleDoubleClick(_ params: [String: Any], id: String) {
    let source = CGEventSource(stateID: .hidSystemState)
    for _ in 0..<2 {
        let down = CGEvent(mouseEventSource: source, mouseType: .leftMouseDown, mouseCursorPosition: NSEvent.mouseLocation, mouseButton: .left)
        let up = CGEvent(mouseEventSource: source, mouseType: .leftMouseUp, mouseCursorPosition: NSEvent.mouseLocation, mouseButton: .left)
        down?.post(tap: .cghidEventTap)
        up?.post(tap: .cghidEventTap)
    }
    respond(id: id, success: true)
}

func handleTypeText(_ params: [String: Any], id: String) {
    guard let text = params["text"] as? String else {
        respond(id: id, success: false, error: "No text")
        return
    }
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(text, forType: .string)
    let source = CGEventSource(stateID: .hidSystemState)
    let cmdV = CGEvent(keyboardEventSource: source, virtualKey: 0x09, keyDown: true)
    let cmdVup = CGEvent(keyboardEventSource: source, virtualKey: 0x09, keyDown: false)
    cmdV?.post(tap: .cghidEventTap)
    cmdVup?.post(tap: .cghidEventTap)
    respond(id: id, success: true)
}

func handleScroll(_ params: [String: Any], id: String) {
    let amount = params["amount"] as? Int ?? -100
    let event = CGEvent(scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 1, wheel1: Int32(amount), wheel2: 0, wheel3: 0)
    event?.post(tap: .cghidEventTap)
    respond(id: id, success: true)
}

func handleGetFrontmostApp(_ params: [String: Any], id: String) {
    let app = NSWorkspace.shared.frontmostApplication?.localizedName ?? "unknown"
    respond(id: id, success: true, data: ["app": app])
}

func handleGetWindows(_ params: [String: Any], id: String) {
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/sbin/system_profiler")
    task.arguments = ["SPDisplaysDataType", "-json"]
    let output = Pipe()
    task.standardOutput = output
    try? task.run()
    task.waitUntilExit()
    
    let data = output.fileHandleForReading.readData(ofLength: 4096 * 1024)
    let outputStr = String(data: data, encoding: .utf8) ?? ""
    
    respond(id: id, success: true, data: ["windows": [], "info": outputStr.prefix(500)])
}

func handleGetAccessibilityTree(_ params: [String: Any], id: String) {
    let appName = params["app"] as? String
    var tree: [String: Any] = [:]
    if let app = appName {
        if let appRef = NSRunningApplication.runningApplications(withBundleIdentifier: app).first {
            let axApp = AXUIElementCreateApplication(appRef.processIdentifier)
            var windows: CFArray?
            AXUIElementCopyAttributeValues(axApp, kAXWindowsAttribute as CFString, 0, 100, &windows)
            var windowList: [[String: Any]] = []
            if let wins = windows as? [AXUIElement] {
                for w in wins {
                    var title: CFTypeRef?
                    AXUIElementCopyAttributeValue(w, kAXTitleAttribute as CFString, &title)
                    var role: CFTypeRef?
                    AXUIElementCopyAttributeValue(w, kAXRoleAttribute as CFString, &role)
                    windowList.append(["title": title as? String ?? "", "role": role as? String ?? ""])
                }
            }
            tree = ["windows": windowList]
        }
    }
    respond(id: id, success: true, data: ["tree": tree])
}

func handleKeyDown(_ params: [String: Any], id: String) {
    let keys = params["keys"] as? [String] ?? []
    let source = CGEventSource(stateID: .hidSystemState)
    for key in keys {
        var keyCode: UInt16?
        switch key.lowercased() {
        case "return", "enter": keyCode = 0x24
        case "escape", "esc": keyCode = 0x35
        case "tab": keyCode = 0x30
        case "space": keyCode = 0x31
        case "delete": keyCode = 0x33
        case "home": keyCode = 0x73
        case "end": keyCode = 0x77
        case "left": keyCode = 0x7B
        case "right": keyCode = 0x7C
        case "up": keyCode = 0x7E
        case "down": keyCode = 0x7D
        default: break
        }
        if let kc = keyCode {
            let down = CGEvent(keyboardEventSource: source, virtualKey: kc, keyDown: true)
            let up = CGEvent(keyboardEventSource: source, virtualKey: kc, keyDown: false)
            down?.post(tap: .cghidEventTap)
            up?.post(tap: .cghidEventTap)
        }
    }
    respond(id: id, success: true)
}

// MARK: - Main
while let line = readLine() {
    guard let json = try? JSONSerialization.jsonObject(with: line.data(using: .utf8)!) as? [String: Any] else { continue }
    let id = json["id"] as? String ?? ""
    let action = json["action"] as? String ?? ""
    let params = json["params"] as? [String: Any] ?? [:]
    
    switch action {
    case "screenshot": handleScreenshot(params, id: id)
    case "click": handleClick(params, id: id)
    case "double_click": handleDoubleClick(params, id: id)
    case "type_text": handleTypeText(params, id: id)
    case "scroll": handleScroll(params, id: id)
    case "get_frontmost_app": handleGetFrontmostApp(params, id: id)
    case "get_windows": handleGetWindows(params, id: id)
    case "get_accessibility_tree": handleGetAccessibilityTree(params, id: id)
    case "key_combo": handleKeyDown(params, id: id)
    default: respond(id: id, success: false, error: "Unknown: \(action)")
    }
}
