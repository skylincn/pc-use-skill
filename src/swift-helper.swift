#!/usr/bin/env swift
// PC Use Swift Helper — Persistent macOS native operations
//
// Communicates via JSON-lines protocol over stdin/stdout.
// Spawns once, handles many requests — eliminates per-call `swift -e`
// spawn overhead (~60-120ms saved per operation).
//
// Optimization vs v1.x:
//   - Persistent process: no subprocess spawn per call
//   - Direct CGEvent for click/scroll: no cliclick dependency
//   - Pixel-precise scroll via CGEvent scrollWheelEvent2
//   - Accessibility tree via AXUIElement
//   - Window listing via NSWorkspace

import AppKit
import CoreGraphics
import Foundation

// MARK: - AnyCodable (flexible JSON value)

struct AnyCodable: Codable {
    let value: Any?

    init(_ value: Any?) { self.value = value }

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { value = nil }
        else if let v = try? c.decode(Bool.self) { value = v }
        else if let v = try? c.decode(Int.self) { value = v }
        else if let v = try? c.decode(Double.self) { value = v }
        else if let v = try? c.decode(String.self) { value = v }
        else if let v = try? c.decode([AnyCodable].self) { value = v }
        else if let v = try? c.decode([String: AnyCodable].self) { value = v }
        else { value = nil }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        guard let v = value else { try c.encodeNil(); return }
        switch v {
        case let b as Bool: try c.encode(b)
        case let i as Int: try c.encode(i)
        case let d as Double: try c.encode(d)
        case let s as String: try c.encode(s)
        case let a as [Any]: try c.encode(a.map(AnyCodable.init))
        case let d as [String: Any]: try c.encode(d.mapValues(AnyCodable.init))
        default: try c.encodeNil()
        }
    }
}

// MARK: - Request / Response

struct HelperRequest: Codable {
    let id: String
    let action: String
    let params: [String: AnyCodable]?
}

struct HelperResponse: Codable {
    let id: String
    let success: Bool
    let data: AnyCodable?
    let error: String?
}

// MARK: - Helper

class PCUseHelper {

    // ── Screenshot ──────────────────────────────────────────────────

    func takeScreenshot(crop: [String: Any]?) -> String? {
        let ts = Int64(Date().timeIntervalSince1970 * 1000)
        let path = NSTemporaryDirectory() + "pc-use-\(ts).png"

        let screen = NSScreen.main
        let screenRect = screen?.frame ?? NSRect(x: 0, y: 0, width: 1920, height: 1080)
        let image = CGWindowListCreateImage(screenRect, .optionOnScreenOnly, kCGNullWindowID, .imageResolution)
        guard let cgImage = image else { return nil }

        let finalRect: NSRect
        if let crop,
           let x = crop["x"] as? Int,
           let y = crop["y"] as? Int,
           let w = crop["w"] as? Int,
           let h = crop["h"] as? Int {
            finalRect = NSRect(x: CGFloat(x), y: CGFloat(y), width: CGFloat(w), height: CGFloat(h))
        } else {
            finalRect = NSRect(x: 0, y: 0, width: Int(cgImage.width), height: Int(cgImage.height))
        }

        let cropped = cgImage.cropping(to: finalRect)
        guard let cropped = cropped else { return nil }

        let nsImage = NSImage(cgImage: cropped, size: finalRect.size)
        guard let tiff = nsImage.tiffRepresentation else { return nil }
        let bitmap = NSBitmapImageRep(data: tiff)
        guard let bitmap = bitmap else { return nil }

        let url = URL(fileURLWithPath: path)
        bitmap.write(to: url)
        return path
    }

    // ── Click ────────────────────────────────────────────────────────

    func click(x: Int, y: Int, double: Bool = false) -> Bool {
        let point = CGPoint(x: CGFloat(x), y: CGFloat(y))

        // Move
        let move = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left)
        move?.post(tap: .cghidEventTap)

        // Down
        let down = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left)
        down?.post(tap: .cghidEventTap)

        // Double-click: second down+up
        if double {
            let down2 = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left)
            down2?.post(tap: .cghidEventTap)
            let up2 = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left)
            up2?.post(tap: .cghidEventTap)
        }

        // Up
        let up = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left)
        up?.post(tap: .cghidEventTap)

        return true
    }

    // ── Scroll (pixel-precise CGEvent) ───────────────────────────────

    func scroll(x: Int, y: Int, amount: Int) -> Bool {
        let event = CGEvent(scrollWheelEvent2Source: nil,
                           units: .pixel,
                           wheelCount: 1,
                           wheel1: Int32(amount),
                           wheel2: 0,
                           wheel3: 0)
        event?.setIntegerValue(Int32(x), field: .mouseEventPositionX)
        event?.setIntegerValue(Int32(y), field: .mouseEventPositionY)
        event?.post(tap: .cghidEventTap)
        return true
    }

    // ── Type text (clipboard + Cmd+V for Unicode) ────────────────────

    func typeText(_ text: String) -> Bool {
        let pb = NSPasteboard.general
        let old = pb.string(forType: .string)
        pb.clearContents()
        pb.setString(text, forType: .string)

        let script = "tell application \"System Events\"\n    keystroke \"v\" using command down\nend tell"
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        task.arguments = ["-e", script]
        try? task.run()
        task.waitUntilExit()

        // Restore clipboard
        if let old = old {
            pb.clearContents()
            pb.setString(old, forType: .string)
        }
        return true
    }

    // ── Key combo ────────────────────────────────────────────────────

    func keyCombo(keys: [String]) -> Bool {
        let mods = keys.dropFirst()
        let key = keys.first ?? ""
        let modStr = mods.joined(separator: " using ")
        let script = "tell application \"System Events\"\n    keystroke \"\(key)\" using \(modStr)\nend tell"

        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        task.arguments = ["-e", script]
        try? task.run()
        task.waitUntilExit()
        return true
    }

    // ── Frontmost app ────────────────────────────────────────────────

    func getFrontmostApp() -> String {
        return NSWorkspace.shared.frontmostApplication?.localizedName ?? "unknown"
    }

    // ── Window list ──────────────────────────────────────────────────

    func getWindowList() -> [[String: Any]] {
        var windows: [[String: Any]] = []
        for app in NSWorkspace.shared.runningApplications {
            if let name = app.localizedName {
                windows.append(["name": name, "pid": app.processIdentifier, "active": app.isActive])
            }
        }
        return windows
    }

    // ── Accessibility tree ───────────────────────────────────────────

    func getAccessibilityTree(appName: String?) -> [String: Any] {
        let targetApp: NSRunningApplication?
        if let appName = appName {
            targetApp = NSWorkspace.shared.runningApplications.first { $0.localizedName == appName }
        } else {
            targetApp = NSWorkspace.shared.frontmostApplication
        }

        guard let app = targetApp else {
            return ["error": "No application found"]
        }

        let pid = app.processIdentifier
        let axApp = AXUIElementCreateApplication(pid)
        var windowsRef: CFRetained = 0
        AXUIElementCopyAttributeValue(axApp, kAXWindowsAttribute as CFString, &windowsRef)

        guard let windows = windowsRef.value as? [AXUIElement] else {
            return ["app": app.localizedName ?? "unknown", "windows": []]
        }

        var result: [[String: Any]] = []
        for window in windows {
            var titleRef: CFRetained = ""
            AXUIElementCopyAttributeValue(window, kAXTitleAttribute as CFString, &titleRef)
            var posRef: CFRetained = ""
            AXUIElementCopyAttributeValue(window, kAXPositionAttribute as CFString, &posRef)
            var sizeRef: CFRetained = ""
            AXUIElementCopyAttributeValue(window, kAXSizeAttribute as CFString, &sizeRef)

            result.append([
                "title": (titleRef.value as? String) ?? "",
                "position": "\(posRef.value)",
                "size": "\(sizeRef.value)"
            ])
        }

        return ["app": app.localizedName ?? "unknown", "windows": result]
    }
}

// MARK: - Main loop

let helper = PCUseHelper()
let inputPipe = FileHandle.standardInput
let outputPipe = FileHandle.standardOutput

var buffer = Data()

func sendResponse(_ resp: HelperResponse) {
    guard let data = try? JSONEncoder().encode(resp) else { return }
    outputPipe.write(data)
    outputPipe.write(Array("\n".utf8))
    outputPipe.synchronizeFile()
}

func processRequest(_ data: Data) {
    guard let req = try? JSONDecoder().decode(HelperRequest.self, from: data) else {
        sendResponse(HelperResponse(id: "unknown", success: false, data: nil, error: "Invalid JSON"))
        return
    }

    var resp: HelperResponse

    switch req.action {
    case "screenshot":
        let crop = req.params?["crop"]?.value as? [String: Any]
        let path = helper.takeScreenshot(crop: crop)
        resp = HelperResponse(id: req.id, success: path != nil, data: AnyCodable(path), error: path == nil ? "Screenshot failed" : nil)

    case "click":
        let x = req.params?["x"]?.value as? Int ?? 0
        let y = req.params?["y"]?.value as? Int ?? 0
        let dbl = req.params?["double"]?.value as? Bool ?? false
        let ok = helper.click(x: x, y: y, double: dbl)
        resp = HelperResponse(id: req.id, success: ok, data: AnyCodable(["x": x, "y": y, "double": dbl]), error: nil)

    case "scroll":
        let x = req.params?["x"]?.value as? Int ?? 0
        let y = req.params?["y"]?.value as? Int ?? 0
        let amount = req.params?["amount"]?.value as? Int ?? -100
        let ok = helper.scroll(x: x, y: y, amount: amount)
        resp = HelperResponse(id: req.id, success: ok, data: AnyCodable(["x": x, "y": y, "amount": amount]), error: nil)

    case "type_text":
        let text = req.params?["text"]?.value as? String ?? ""
        let ok = helper.typeText(text)
        resp = HelperResponse(id: req.id, success: ok, data: AnyCodable(["text": text]), error: nil)

    case "key_combo":
        let keys = req.params?["keys"]?.value as? [String] ?? []
        let ok = helper.keyCombo(keys: keys)
        resp = HelperResponse(id: req.id, success: ok, data: AnyCodable(["keys": keys]), error: nil)

    case "get_current_app":
        let app = helper.getFrontmostApp()
        resp = HelperResponse(id: req.id, success: true, data: AnyCodable(app), error: nil)

    case "get_windows":
        let windows = helper.getWindowList()
        resp = HelperResponse(id: req.id, success: true, data: AnyCodable(windows), error: nil)

    case "get_accessibility_tree":
        let appName = req.params?["app"]?.value as? String
        let tree = helper.getAccessibilityTree(appName: appName)
        resp = HelperResponse(id: req.id, success: true, data: AnyCodable(tree), error: nil)

    default:
        resp = HelperResponse(id: req.id, success: false, data: nil, error: "Unknown action: \(req.action)")
    }

    sendResponse(resp)
}

// Read loop: read stdin, split on newlines, process each line
while true {
    let chunk = inputPipe.readData(ofLength: 4096)
    if chunk.isEmpty { break }
    buffer.append(chunk)

    while let nlRange = buffer.range(of: Array("\n".utf8)) {
        let line = buffer.subrange(in: ..<nlRange.location)
        buffer.removeSubrange(in: ..<nlRange.location)
        if !line.isEmpty {
            processRequest(Data(line))
        }
    }
}