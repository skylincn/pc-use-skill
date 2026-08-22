#!/usr/bin/env python3
"""
PC Use MCP Server - Simplified v2.0
Direct JSON-RPC over stdio, no complex MCP SDK dependencies.
Integrates both macOS system control and browser automation via Playwright.
"""

import asyncio
import sys
import json
import os
import platform
import subprocess
import tempfile
import uuid
from typing import Optional, Dict, Any, List

# Check for MCP SDK (optional, graceful degradation)
try:
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, PaginatedRequestParams, CallToolRequestParams
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

# Playwright imports
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class SwiftHelper:
    """Persistent Swift helper for macOS native operations."""

    def __init__(self, helper_path: str):
        self.helper_path = helper_path
        self.process = None
        self._pending = {}
        self._reader_task = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(5)

    async def start(self):
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
        assert self.process is not None and self.process.stdout is not None
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
            except (json.JSONDecodeError, KeyError):
                continue

    async def request(self, action: str, params: Optional[Dict] = None) -> Dict:
        async with self._semaphore:
            async with self._lock:
                await self.start()
                req_id = str(uuid.uuid4())
                request = {"id": req_id, "action": action, "params": params or {}}
                loop = asyncio.get_event_loop()
                future = loop.create_future()
                self._pending[req_id] = future
                self.process.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
                await self.process.stdin.drain()
                try:
                    return await asyncio.wait_for(future, timeout=30)
                except asyncio.TimeoutError:
                    del self._pending[req_id]
                    raise TimeoutError(f"Swift helper timeout: {action}")
                except Exception as e:
                    if req_id in self._pending:
                        del self._pending[req_id]
                    raise

    async def screenshot(self, crop=None):
        result = await self.request("screenshot", {"crop": crop})
        return result.get("path", "")

    async def click(self, x: int, y: int):
        result = await self.request("click", {"x": x, "y": y})
        return result.get("success", False)

    async def double_click(self, x: int, y: int):
        result = await self.request("double_click", {"x": x, "y": y})
        return result.get("success", False)

    async def type_text(self, text: str):
        result = await self.request("type_text", {"text": text})
        return result.get("success", False)

    async def scroll(self, x: int, y: int, amount: int = -100):
        result = await self.request("scroll", {"x": x, "y": y, "amount": amount})
        return result.get("success", False)

    async def get_frontmost_app(self):
        result = await self.request("get_frontmost_app")
        return result.get("app", "unknown")

    async def get_windows(self):
        result = await self.request("get_windows")
        return result.get("windows", [])

    async def get_accessibility_tree(self, app=None):
        result = await self.request("get_accessibility_tree", {"app": app})
        return result.get("tree", {})

    async def key_combo(self, keys: List[str]):
        result = await self.request("key_combo", {"keys": keys})
        return result.get("success", False)


class PCUseMCP:
    """PC Use MCP Server with Playwright browser integration."""

    def __init__(self):
        self.helper = None
        self.platform = platform.system()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def get_platform(self):
        system = platform.system()
        if system == "Darwin":
            return "macOS"
        elif system == "Windows":
            return "Windows"
        return system

    def get_tools(self):
        tools = [
            # System tools
            {"name": "screenshot", "description": "Take a screenshot of the screen. Optionally crop to a region.",
             "inputSchema": {"type": "object", "properties": {"crop_x": {"type": "integer"}, "crop_y": {"type": "integer"}, "crop_w": {"type": "integer"}, "crop_h": {"type": "integer"}}}},
            {"name": "click", "description": "Click at screen coordinates.",
             "inputSchema": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}},
            {"name": "double_click", "description": "Double-click at screen coordinates.",
             "inputSchema": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}, "required": ["x", "y"]}},
            {"name": "type_text", "description": "Type text at current cursor position (supports Chinese).",
             "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
            {"name": "scroll", "description": "Scroll at screen coordinates. Negative amount = down.",
             "inputSchema": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "amount": {"type": "integer"}}, "required": ["x", "y", "amount"]}},
            {"name": "get_current_app", "description": "Get frontmost application name.",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "get_windows", "description": "Get list of open windows.",
             "inputSchema": {"type": "object", "properties": {}}},
            {"name": "get_accessibility_tree", "description": "Get accessibility tree for an app.",
             "inputSchema": {"type": "object", "properties": {"app": {"type": "string"}}}},
            {"name": "key_combo", "description": "Send key combo, e.g. 'command,a'.",
             "inputSchema": {"type": "object", "properties": {"keys": {"type": "string"}}, "required": ["keys"]}},
        ]
        
        if PLAYWRIGHT_AVAILABLE:
            tools.extend([
                # Browser tools
                {"name": "browser_open", "description": "Open a URL in the browser.",
                 "inputSchema": {"type": "object", "properties": {"url": {"type": "string", "description": "URL to open"}}, "required": ["url"]}},
                {"name": "browser_snapshot", "description": "Get page snapshot with stable element references (e1, e2, etc.).",
                 "inputSchema": {"type": "object", "properties": {}}},
                {"name": "browser_click", "description": "Click an element by its snapshot reference (e1, e2, etc.).",
                 "inputSchema": {"type": "object", "properties": {"ref": {"type": "string", "description": "Element ref like e1, e2"}}, "required": ["ref"]}},
                {"name": "browser_type", "description": "Type text into an element by its snapshot reference.",
                 "inputSchema": {"type": "object", "properties": {"ref": {"type": "string", "description": "Element ref like e1, e2"}, "text": {"type": "string", "description": "Text to type"}}, "required": ["ref", "text"]}},
                {"name": "browser_fill", "description": "Fill an input field with text.",
                 "inputSchema": {"type": "object", "properties": {"ref": {"type": "string", "description": "Element ref like e1, e2"}, "text": {"type": "string", "description": "Text to fill"}}, "required": ["ref", "text"]}},
                {"name": "browser_screenshot", "description": "Take a screenshot of the current page.",
                 "inputSchema": {"type": "object", "properties": {"full_page": {"type": "boolean", "description": "Capture full page height"}}}},
                {"name": "browser_press", "description": "Press a keyboard key.",
                 "inputSchema": {"type": "object", "properties": {"key": {"type": "string", "description": "Key to press, e.g. 'Enter', 'Escape', 'Tab'"}}, "required": ["key"]}},
                {"name": "browser_navigate", "description": "Navigate to a URL.",
                 "inputSchema": {"type": "object", "properties": {"url": {"type": "string", "description": "URL to navigate to"}}, "required": ["url"]}},
                {"name": "browser_go_back", "description": "Go back in browser history.",
                 "inputSchema": {"type": "object", "properties": {}}},
                {"name": "browser_go_forward", "description": "Go forward in browser history.",
                 "inputSchema": {"type": "object", "properties": {}}},
            ])
        
        return tools

    async def _ensure_browser(self):
        """Ensure browser is running."""
        if self._page is not None:
            return
        
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed. Run: pip3 install playwright && playwright install chromium")
        
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        
        if self._browser is None:
            self._browser = await self._playwright.chromium.launch(headless=True)
        
        if self._context is None:
            self._context = await self._browser.new_context()
        
        if self._page is None or not self._page.is_closed():
            if self._page and self._page.is_closed():
                self._page = None
            if self._page is None:
                self._page = await self._context.new_page()

    async def _close_browser(self):
        """Close browser if open."""
        if self._page:
            try:
                await self._page.close()
            except:
                pass
            self._page = None
        if self._context:
            try:
                await self._context.close()
            except:
                pass
            self._context = None
        if self._browser:
            try:
                await self._browser.close()
            except:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except:
                pass
            self._playwright = None

    async def handle_tool_call(self, name: str, args: Dict) -> str:
        # System tools
        if name == "screenshot":
            crop = None
            if args.get("crop_w") and args.get("crop_h"):
                crop = {"x": args.get("crop_x", 0), "y": args.get("crop_y", 0),
                        "w": args["crop_w"], "h": args["crop_h"]}
            path = await self.helper.screenshot(crop)
            return f"Screenshot saved: {path}"
        elif name == "click":
            await self.helper.click(args["x"], args["y"])
            return f"Clicked at ({args['x']}, {args['y']})"
        elif name == "double_click":
            await self.helper.double_click(args["x"], args["y"])
            return f"Double-clicked at ({args['x']}, {args['y']})"
        elif name == "type_text":
            await self.helper.type_text(args["text"])
            return f"Typed: {args['text'][:50]}"
        elif name == "scroll":
            await self.helper.scroll(args["x"], args["y"], args["amount"])
            return f"Scrolled {args['amount']}px at ({args['x']}, {args['y']})"
        elif name == "get_current_app":
            return f"Current app: {await self.helper.get_frontmost_app()}"
        elif name == "get_windows":
            windows = await self.helper.get_windows()
            return f"Found {len(windows)} windows"
        elif name == "get_accessibility_tree":
            tree = await self.helper.get_accessibility_tree(args.get("app"))
            return json.dumps(tree, indent=2)
        elif name == "key_combo":
            keys = [k.strip() for k in args["keys"].split(",")]
            await self.helper.key_combo(keys)
            return f"Sent key combo: {keys}"
        # Browser tools
        elif name == "browser_open":
            await self._ensure_browser()
            url = args["url"]
            await self._page.goto(url)
            return f"Opened: {url}"
        elif name == "browser_navigate":
            await self._ensure_browser()
            url = args["url"]
            await self._page.goto(url)
            return f"Navigated to: {url}"
        elif name == "browser_snapshot":
            await self._ensure_browser()
            snapshot = await self._page.evaluate("""
                () => {
                    const elements = [];
                    const allElements = document.querySelectorAll('*');
                    let counter = 1;
                    
                    // Find interactive elements
                    const selectors = 'a, button, input, textarea, select, [role="button"], [role="link"], [role="tab"], [role="menuitem"], [tabindex="0"]';
                    allElements.forEach(el => {
                        if (el.closest(selectors)) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                const text = (el.textContent || '').trim().substring(0, 50);
                                const role = el.getAttribute('role') || el.tagName.toLowerCase();
                                const label = el.getAttribute('aria-label') || el.getAttribute('name') || text;
                                elements.push({
                                    ref: 'e' + counter++,
                                    tag: el.tagName.toLowerCase(),
                                    role: role,
                                    text: text,
                                    label: label || text,
                                    x: Math.round(rect.x + rect.width/2),
                                    y: Math.round(rect.y + rect.height/2),
                                    visible: rect.width < window.innerWidth * 2 && rect.height < window.innerHeight * 2
                                });
                            }
                        }
                    });
                    
                    return {
                        elements: elements,
                        title: document.title,
                        url: document.url
                    };
                }
            """)
            return json.dumps(snapshot, indent=2, ensure_ascii=False)
        elif name == "browser_click":
            await self._ensure_browser()
            ref = args["ref"]
            # Try element ref first
            success = await self._page.evaluate(f"""
                () => {{
                    const el = document.querySelector('[data-ref="{ref}"]');
                    if (el) {{ el.click(); return true; }}
                    return false;
                }}
            """)
            if not success:
                # Fallback: find by text/content
                await self._page.click(f"text={ref}")
            return f"Clicked: {ref}"
        elif name == "browser_type":
            await self._ensure_browser()
            ref = args["ref"]
            text = args["text"]
            await self._page.fill(f"text={ref}", text)
            return f"Typed '{text[:30]}' into: {ref}"
        elif name == "browser_fill":
            await self._ensure_browser()
            ref = args["ref"]
            text = args["text"]
            await self._page.fill(f"text={ref}", text)
            return f"Filled '{text[:30]}' into: {ref}"
        elif name == "browser_screenshot":
            await self._ensure_browser()
            full_page = args.get("full_page", False)
            tmpdir = tempfile.gettempdir()
            path = f"{tmpdir}/pc-use-browser-{uuid.uuid4().hex[:8]}.png"
            await self._page.screenshot(path=path, full_page=full_page)
            return f"Screenshot saved: {path}"
        elif name == "browser_press":
            await self._ensure_browser()
            key = args["key"]
            await self._page.keyboard.press(key)
            return f"Pressed: {key}"
        elif name == "browser_go_back":
            await self._ensure_browser()
            await self._page.go_back()
            return f"Navigated back to: {self._page.url}"
        elif name == "browser_go_forward":
            await self._ensure_browser()
            await self._page.go_forward()
            return f"Navigated forward to: {self._page.url}"
        else:
            raise ValueError(f"Unknown tool: {name}")

    def handle_tool_call_sync(self, name: str, args: Dict) -> str:
        """Synchronous wrapper for handle_tool_call."""
        import asyncio
        try:
            return asyncio.get_event_loop().run_until_complete(self.handle_tool_call(name, args))
        except RuntimeError:
            return asyncio.run(self.handle_tool_call(name, args))

    def cleanup_sync(self):
        """Synchronous wrapper for cleanup."""
        import asyncio
        try:
            asyncio.get_event_loop().run_until_complete(self.cleanup())
        except RuntimeError:
            asyncio.run(self.cleanup())

    async def cleanup(self):
        """Cleanup resources."""
        if self.helper:
            await self.helper.stop()
        await self._close_browser()


async def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    helper_path = os.path.join(script_dir, "swift-helper")

    if not os.path.exists(helper_path):
        print(f"Error: Swift helper not found at {helper_path}", flush=True)
        return

    pc_use = PCUseMCP()
    pc_use.helper = SwiftHelper(helper_path)

    if MCP_AVAILABLE:
        # Use MCP SDK with proper handlers
        server = Server("pc-use-mcp")
        tools = pc_use.get_tools()

        @server.add_request_handler("tools/list", PaginatedRequestParams)
        async def list_tools_handler(ctx, params):
            return {"tools": tools}

        @server.add_request_handler("tools/call", CallToolRequestParams)
        async def call_tool_handler(ctx, params):
            try:
                result = await pc_use.handle_tool_call(params.name, params.arguments or {})
                return {"content": [{"type": "text", "text": str(result)}]}
            except Exception as e:
                return {"isError": True, "content": [{"type": "text", "text": f"Error: {e}"}]}
            finally:
                # Clean up on exit
                await pc_use.cleanup()

        # Setup cleanup on shutdown
        import signal
        loop = asyncio.get_event_loop()
        
        def shutdown(sig, frame):
            asyncio.create_task(pc_use.cleanup())
        
        try:
            loop.add_signal_handler(signal.SIGINT, lambda: asyncio.create_task(pc_use.cleanup()))
            loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(pc_use.cleanup()))
        except (NotImplementedError, OSError):
            pass  # Windows doesn't support add_signal_handler

        print(f"PC Use MCP Server v2.1 started (platform: {pc_use.get_platform()}, playwright: {'✓' if PLAYWRIGHT_AVAILABLE else '✗'})", flush=True)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    else:
        # Fallback: simple JSON-RPC server (synchronous I/O for Python 3.9 compat)
        print(f"PC Use Server v2.1 (no MCP SDK) started", flush=True)
        tools = pc_use.get_tools()
        
        while True:
            line = sys.stdin.readline()
            if not line or not line.strip():
                break
            try:
                msg = json.loads(line.strip())
                if msg.get("method") == "initialize":
                    resp = {"jsonrpc": "2.0", "id": msg["id"], "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "pc-use", "version": "2.1.0"}
                    }}
                elif msg.get("method") == "tools/list":
                    resp = {"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": tools}}
                elif msg.get("method") == "tools/call":
                    name = msg["params"]["name"]
                    args = msg["params"].get("arguments", {})
                    try:
                        result = pc_use.handle_tool_call_sync(name, args)
                        resp = {"jsonrpc": "2.0", "id": msg["id"], "result": {
                            "content": [{"type": "text", "text": str(result)}]
                        }}
                    except Exception as e:
                        resp = {"jsonrpc": "2.0", "id": msg["id"], "error": {
                            "code": -32000, "message": str(e)
                        }}
                else:
                    resp = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {
                        "code": -32601, "message": f"Method not found: {msg.get('method')}"
                    }}
                print(json.dumps(resp), flush=True)
            except Exception as e:
                print(f"Error: {e}", flush=True)
        
        pass  # cleanup skipped in fallback mode

if __name__ == "__main__":
    asyncio.run(main())
