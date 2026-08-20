#!/usr/bin/env python3
"""
PC Use MCP Server - Optimized v2.0
==================================
Persistent Swift helper for macOS native operations.
Low-latency, concurrent, multi-task safe.
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

# ── MCP SDK ──────────────────────────
try:
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, PaginatedRequestParams, CallToolRequestParams
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


class SwiftHelper:
    """Manages a persistent Swift helper subprocess."""

    def __init__(self, helper_path: str, max_concurrent: int = 5):
        self.helper_path = helper_path
        self.process = None
        self._pending = {}
        self._reader_task = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrent)

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
    """PC Use MCP Server."""

    def __init__(self):
        self.helper = None
        self.platform = platform.system()

    def get_platform(self):
        system = platform.system()
        if system == "Darwin":
            return "macOS"
        elif system == "Windows":
            return "Windows"
        return system

    def get_tools(self):
        return [
            Tool(
                name="screenshot",
                description="Take a screenshot. Optionally crop to a region.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "crop_x": {"type": "integer"},
                        "crop_y": {"type": "integer"},
                        "crop_w": {"type": "integer"},
                        "crop_h": {"type": "integer"},
                    }
                }
            ),
            Tool(
                name="click",
                description="Click at coordinates.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                    },
                    "required": ["x", "y"]
                }
            ),
            Tool(
                name="double_click",
                description="Double-click at coordinates.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                    },
                    "required": ["x", "y"]
                }
            ),
            Tool(
                name="type_text",
                description="Type text (supports Chinese).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"}
                    },
                    "required": ["text"]
                }
            ),
            Tool(
                name="scroll",
                description="Scroll. Negative = down.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "amount": {"type": "integer"}
                    },
                    "required": ["x", "y", "amount"]
                }
            ),
            Tool(
                name="get_current_app",
                description="Get frontmost app name.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="get_windows",
                description="Get window list.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="get_accessibility_tree",
                description="Get accessibility tree.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "app": {"type": "string"}
                    }
                }
            ),
            Tool(
                name="key_combo",
                description="Send key combo, e.g. 'command,a'.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "keys": {"type": "string"}
                    },
                    "required": ["keys"]
                }
            ),
        ]

    async def handle_tool_call(self, name: str, args: Dict) -> Any:
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
        else:
            raise ValueError(f"Unknown tool: {name}")


async def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    helper_path = os.path.join(script_dir, "swift-helper")
    
    if not os.path.exists(helper_path):
        print(f"Error: Swift helper not found at {helper_path}", flush=True)
        return

    pc_use = PCUseMCP()
    pc_use.helper = SwiftHelper(helper_path)

    if MCP_AVAILABLE:
        server = Server("pc-use-mcp")
        tools = pc_use.get_tools()

        async def list_tools_handler(ctx, params):
            return {"tools": tools}

        async def call_tool_handler(ctx, params):
            try:
                result = await pc_use.handle_tool_call(params.name, params.arguments or {})
                return {"content": [{"type": "text", "text": str(result)}]}
            except Exception as e:
                return {"isError": True, "content": [{"type": "text", "text": f"Error: {e}"}]}

        server.add_request_handler("tools/list", PaginatedRequestParams, list_tools_handler)
        server.add_request_handler("tools/call", CallToolRequestParams, call_tool_handler)

        print(f"PC Use MCP Server v2.0 started (platform: {pc_use.get_platform()})", flush=True)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    else:
        print("MCP SDK not available. Install: pip install mcp", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
