#!/usr/bin/env python3
"""
PC Use MCP Server - Optimized v2.0
==================================
Persistent Swift helper for macOS native operations.
Low-latency, concurrent, multi-task safe.

Architecture:
  Python MCP Server (asyncio) <-> Swift Helper (persistent subprocess)
  JSON-lines protocol over stdin/stdout for sub-millisecond round-trips.

Optimizations vs v1.x:
  - Persistent Swift process (no per-call `swift -e` spawn = ~50-100ms saved per op)
  - Direct CoreGraphics CGEvent scroll (pixel-precise, no cliclick dependency)
  - asyncio.Semaphore concurrency control (safe multi-task)
  - Accessibility tree via AXUIElement
  - Window listing, drag, key combos, clipboard-aware typing
"""

import asyncio
import json
import os
import platform
import subprocess
import tempfile
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

# ── MCP SDK (optional, graceful degradation) ──────────────────────────
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════
#  Swift Helper Client — persistent subprocess, JSON-lines protocol
# ═══════════════════════════════════════════════════════════════════════

class SwiftHelper:
    """Manages a persistent Swift helper subprocess for macOS native ops.

    Spawns once at startup, sends JSON-line requests, receives JSON-line
    responses.  Eliminates the ~60-120ms per-call `swift -e` spawn overhead.

    Uses asyncio subprocess for clean async I/O with the event loop.
    """

    def __init__(self, helper_path: str):
        self.helper_path = helper_path
        self.process: Optional[asyncio.subprocess.Process] = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self):
        """Spawn the Swift helper subprocess."""
        if self.process is not None:
            return
        self.process = await asyncio.create_subprocess_exec(
            self.helper_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

    async def stop(self):
        """Terminate the Swift helper."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self.process:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2)
            except asyncio.TimeoutError:
                self.process.kill()
            self.process = None

    async def _read_loop(self):
        """Background task: read JSON-line responses and resolve pending futures."""
        assert self.process is not None and self.process.stdout is not None
        loop = asyncio.get_running_loop()
        while True:
            try:
                line = await self.process.stdout.readline()
            except Exception:
                break
            if not line:
                break
            try:
                resp = json.loads(line.decode("utf-8").strip())
                req_id = resp.get("id")
                future = self._pending.get(req_id)
                if future and not future.done():
                    future.set_result(resp)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

    async def call(self, action: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
        """Send a request to the Swift helper and await the response."""
        if self.process is None:
            await self.start()
        assert self.process is not None and self.process.stdin is not None

        req_id = str(uuid.uuid4())
        request = {"id": req_id, "action": action, "params": params or {}}

        future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future

        data = json.dumps(request).encode("utf-8") + b"\n"
        self.process.stdin.write(data)
        await self.process.stdin.drain()

        try:
            resp = await asyncio.wait_for(future, timeout=timeout)
            return resp
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"SwiftHelper timeout for action '{action}'")
        finally:
            self._pending.pop(req_id, None)


# ═══════════════════════════════════════════════════════════════════════
#  PC Use Server
# ═══════════════════════════════════════════════════════════════════════

class PCUseServer:
    def __init__(self):
        self.screen_state = {"last_screenshot": None, "timestamp": None}
        self.temp_dir = tempfile.gettempdir()
        self.helper: Optional[SwiftHelper] = None
        self._sem = asyncio.Semaphore(5)  # max 5 concurrent operations

    def get_platform(self) -> str:
        system = platform.system()
        if system == "Darwin":
            return "macOS"
        elif system == "Windows":
            return "Windows"
        elif system == "Linux":
            return "Linux"
        return system

    async def _ensure_helper(self):
        """Lazy-init the Swift helper on first use (macOS only)."""
        if self.get_platform() != "macOS":
            return
        if self.helper is None:
            helper_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swift-helper.swift")
            if not os.path.exists(helper_path):
                raise FileNotFoundError(f"Swift helper not found: {helper_path}")
            self.helper = SwiftHelper(helper_path)
            await self.helper.start()

    async def _macos_op(self, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a macOS native operation via the Swift helper."""
        await self._ensure_helper()
        assert self.helper is not None
        async with self._sem:
            return await self.helper.call(action, params)

    # ── Screenshot ────────────────────────────────────────────────────

    async def take_screenshot(self, crop: Optional[Dict[str, int]] = None) -> str:
        """Take a screenshot, optionally cropped to a region."""
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(self.temp_dir, f"pc-use-{ts}.png")

        if self.get_platform() == "macOS":
            resp = await self._macos_op("screenshot", {"crop": crop} if crop else None)
            if resp.get("success") and resp.get("data"):
                return resp["data"]
            # Fallback to screencapture command
            cmd = ["screencapture", "-x"]
            if crop:
                cmd += ["-R", f"{crop['x']},{crop['y']},{crop['w']},{crop['h']}"]
            cmd.append(path)
            subprocess.run(cmd, capture_output=True, timeout=5)
        elif self.get_platform() == "Windows":
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
                if crop:
                    img = img.crop((crop["x"], crop["y"], crop["x"] + crop["w"], crop["y"] + crop["h"]))
                img.save(path, "PNG")
            except ImportError:
                raise RuntimeError("Pillow not installed: pip install pillow")

        self.screen_state["last_screenshot"] = path
        self.screen_state["timestamp"] = datetime.now()
        return path

    # ── Click ─────────────────────────────────────────────────────────

    async def click(self, x: int, y: int, double: bool = False) -> bool:
        """Click at coordinates. Supports double-click."""
        if self.get_platform() == "macOS":
            resp = await self._macos_op("click", {"x": x, "y": y, "double": double})
            return resp.get("success", False)
        elif self.get_platform() == "Windows":
            import pyautogui
            if double:
                pyautogui.doubleClick(x, y)
            else:
                pyautogui.click(x, y)
            return True
        return False

    async def drag(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        """Drag from (x1,y1) to (x2,y2)."""
        if self.get_platform() == "macOS":
            # Use CGEvent for drag: mouseDown, mouseDragged, mouseUp
            import subprocess
            code = f"""
            import CoreGraphics
            let start = CGPoint(x: {x1}, y: {y1})
            let end = CGPoint(x: {x2}, y: {y2})
            let down = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: start, mouseButton: .left)
            let drag = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDragged, mouseCursorPosition: end, mouseButton: .left)
            let up = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: end, mouseButton: .left)
            down?.post(tap: .cghidEventTap)
            drag?.post(tap: .cghidEventTap)
            up?.post(tap: .cghidEventTap)
            """
            subprocess.run(["/usr/bin/swift", "-e", code], capture_output=True, timeout=3)
            return True
        elif self.get_platform() == "Windows":
            import pyautogui
            pyautogui.moveTo(x1, y1)
            pyautogui.mouseDown()
            pyautogui.moveTo(x2, y2, duration=0.3)
            pyautogui.mouseUp()
            return True
        return False

    # ── Type text ─────────────────────────────────────────────────────

    async def type_text(self, text: str) -> bool:
        """Type text. Uses clipboard + Cmd+V for reliable Unicode/Chinese input."""
        if self.get_platform() == "macOS":
            resp = await self._macos_op("type_text", {"text": text})
            return resp.get("success", False)
        elif self.get_platform() == "Windows":
            import pyautogui
            pyautogui.write(text)
            return True
        return False

    # ── Scroll ────────────────────────────────────────────────────────

    async def scroll(self, x: int, y: int, amount: int = -100) -> bool:
        """Pixel-precise scroll via CGEvent. Negative = scroll down, positive = up."""
        if self.get_platform() == "macOS":
            resp = await self._macos_op("scroll", {"x": x, "y": y, "amount": amount})
            return resp.get("success", False)
        elif self.get_platform() == "Windows":
            import pyautogui
            pyautogui.scroll(amount, x, y)
            return True
        return False

    # ── Key combo ─────────────────────────────────────────────────────

    async def key_combo(self, keys: List[str]) -> bool:
        """Send a key combination, e.g. ['command', 'a'] for Cmd+A."""
        if self.get_platform() == "macOS":
            resp = await self._macos_op("key_combo", {"keys": keys})
            return resp.get("success", False)
        elif self.get_platform() == "Windows":
            import pyautogui
            pyautogui.hotkey(*keys)
            return True
        return False

    # ── Frontmost app ─────────────────────────────────────────────────

    async def get_frontmost_app(self) -> str:
        """Get the name of the frontmost application (no screenshot needed)."""
        if self.get_platform() == "macOS":
            resp = await self._macos_op("get_current_app")
            return resp.get("data", "unknown")
        elif self.get_platform() == "Windows":
            import pyautogui
            return pyautogui.active()
        return "unknown"

    # ── Window list ───────────────────────────────────────────────────

    async def get_window_list(self) -> List[Dict[str, Any]]:
        """List all running applications with their windows."""
        if self.get_platform() == "macOS":
            resp = await self._macos_op("get_windows")
            return resp.get("data", [])
        return []

    # ── Accessibility tree ────────────────────────────────────────────

    async def get_accessibility_tree(self, app: Optional[str] = None) -> Dict[str, Any]:
        """Read the accessibility tree of the frontmost (or named) application."""
        if self.get_platform() == "macOS":
            resp = await self._macos_op("get_accessibility_tree", {"app": app} if app else None)
            return resp.get("data", {})
        return {}


# ═══════════════════════════════════════════════════════════════════════
#  MCP Server entry point
# ═══════════════════════════════════════════════════════════════════════

async def main():
    if not MCP_AVAILABLE:
        print("MCP SDK not available. Install with: pip install mcp", flush=True)
        return

    server = Server("pc-use-mcp")
    pc = PCUseServer()

    @server.tool()
    async def screenshot(crop_x: int = 0, crop_y: int = 0, crop_w: int = 0, crop_h: int = 0) -> str:
        """Take a screenshot. Optionally crop to a region.

        Args:
            crop_x, crop_y: Top-left corner of crop region.
            crop_w, crop_h: Width and height of crop region (0 = full screen).
        """
        crop = {"x": crop_x, "y": crop_y, "w": crop_w, "h": crop_h} if crop_w > 0 and crop_h > 0 else None
        path = await pc.take_screenshot(crop)
        return path

    @server.tool()
    async def click_at(x: int, y: int, double: bool = False) -> str:
        """Click at screen coordinates. Supports double-click."""
        await pc.click(x, y, double)
        action = "double-clicked" if double else "clicked"
        return f"{action} ({x}, {y})"

    @server.tool()
    async def type_text_tool(text: str) -> str:
        """Type text at the current cursor position. Supports Unicode/Chinese."""
        await pc.type_text(text)
        return f"typed: {text[:50]}"

    @server.tool()
    async def scroll_at(x: int = 0, y: int = 0, amount: int = -100) -> str:
        """Scroll at coordinates. Negative = down, positive = up. Pixel-precise via CGEvent."""
        await pc.scroll(x, y, amount)
        direction = "down" if amount < 0 else "up"
        return f"scrolled {direction} {abs(amount)}px at ({x}, {y})"

    @server.tool()
    async def get_current_app() -> str:
        """Get the frontmost application name (no screenshot)."""
        app = await pc.get_frontmost_app()
        return f"current app: {app}"

    @server.tool()
    async def get_windows() -> str:
        """List all running applications."""
        windows = await pc.get_window_list()
        return json.dumps(windows, indent=2)

    @server.tool()
    async def get_accessibility_tree(app: str = "") -> str:
        """Read the accessibility tree of the frontmost or named application."""
        tree = await pc.get_accessibility_tree(app if app else None)
        return json.dumps(tree, indent=2)

    @server.tool()
    async def key_combo_tool(keys: str) -> str:
        """Send a key combination. Comma-separated, e.g. 'command,a' for Cmd+A."""
        key_list = [k.strip() for k in keys.split(",")]
        await pc.key_combo(key_list)
        return f"sent key combo: {key_list}"

    @server.tool()
    async def drag_at(x1: int, y1: int, x2: int, y2: int) -> str:
        """Drag from (x1,y1) to (x2,y2)."""
        await pc.drag(x1, y1, x2, y2)
        return f"dragged ({x1},{y1}) → ({x2},{y2})"

    print(f"PC Use MCP Server v2.0 started (platform: {pc.get_platform()})", flush=True)

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_state())


if __name__ == "__main__":
    asyncio.run(main())