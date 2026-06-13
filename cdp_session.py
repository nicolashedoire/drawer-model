#!/usr/bin/env python3
"""Atlas Bridge — CDP transport (virtual browser session).

A reliable, fluid, *cheap* alternative to driving the real macOS screen + cursor:
we launch an isolated Chrome, talk to it over the Chrome DevTools Protocol, and

  * STREAM the page in real time via ``Page.startScreencast`` (frames are *pushed*
    over the CDP WebSocket, not polled),
  * drive a VIRTUAL mouse/keyboard via ``Input.dispatchMouseEvent`` /
    ``dispatchKeyEvent`` — synthetic events injected into the page, which never
    move the real OS cursor and never steal window focus,
  * target elements at the pixel via the DOM (``getBoundingClientRect``) — no
    Retina/coordinate guesswork,
  * keep the human-gesture model (Bézier + Fitts + min-jerk) by dispatching the
    planned trajectory as a sequence of ``mouseMoved`` events.

Same ACP verbs as the screen transport, so the viewer / dataset recorder /
agent-factory integration can sit on top unchanged — only the transport differs.

This module is dependency-light: just ``websockets`` (already required) + stdlib.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

import websockets

from human_path import plan_human_path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEFAULT_PORT = 9333
DEFAULT_PROFILE = "/tmp/atlas-cdp-profile"


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class CDPSession:
    port: int = DEFAULT_PORT
    profile: str = DEFAULT_PROFILE
    headless: bool = False
    width: int = 1280
    height: int = 800
    _proc: Optional[subprocess.Popen] = None
    _ws: Any = None
    _id: int = 0
    _pending: dict = field(default_factory=dict)
    _screencast_session: Optional[int] = None
    latest_jpeg: Optional[bytes] = None
    last_frame_id: int = 0
    _reader: Any = None
    _cursor: tuple[float, float] = (10.0, 10.0)
    on_frame: Any = None  # optional callback(jpeg_bytes)

    # -- lifecycle -----------------------------------------------------------

    def launch_chrome(self) -> None:
        args = [
            CHROME,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile}",
            "--no-first-run",
            "--no-default-browser-check",
            f"--window-size={self.width},{self.height}",
            "--remote-allow-origins=*",
            "about:blank",
        ]
        if self.headless:
            args.insert(1, "--headless=new")
        self._proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _page_ws_url(self, timeout: float = 12.0) -> str:
        deadline = time.time() + timeout
        last_err = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json", timeout=2) as r:
                    targets = json.loads(r.read())
                for t in targets:
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        return t["webSocketDebuggerUrl"]
            except Exception as exc:  # Chrome still booting
                last_err = exc
            time.sleep(0.25)
        raise RuntimeError(f"no CDP page target on :{self.port} ({last_err})")

    async def connect(self) -> None:
        url = self._page_ws_url()
        self._ws = await websockets.connect(url, max_size=None)
        self._reader = asyncio.create_task(self._read_loop())
        await self.send("Page.enable")
        await self.send("DOM.enable")
        await self.send("Runtime.enable")

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                if "id" in msg and msg["id"] in self._pending:
                    self._pending.pop(msg["id"]).set_result(msg)
                elif msg.get("method") == "Page.screencastFrame":
                    p = msg["params"]
                    self.latest_jpeg = base64.b64decode(p["data"])
                    self.last_frame_id += 1
                    if self.on_frame:
                        try:
                            self.on_frame(self.latest_jpeg)
                        except Exception:
                            pass
                    # Must ack or the stream stalls.
                    await self.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]}, wait=False)
        except websockets.ConnectionClosed:
            pass

    async def send(self, method: str, params: Optional[dict] = None, *, wait: bool = True, timeout: float = 20.0) -> dict:
        self._id += 1
        mid = self._id
        await self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        if not wait:
            return {}
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        msg = await asyncio.wait_for(fut, timeout=timeout)
        if "error" in msg:
            raise RuntimeError(f"{method} -> {msg['error']}")
        return msg.get("result", {})

    async def start_screencast(self, quality: int = 60) -> None:
        await self.send(
            "Page.startScreencast",
            {"format": "jpeg", "quality": quality, "maxWidth": self.width, "maxHeight": self.height, "everyNthFrame": 1},
        )

    async def close(self) -> None:
        try:
            if self._ws:
                await self._ws.close()
        except Exception:
            pass
        if self._proc:
            self._proc.terminate()

    # -- navigation / eval ---------------------------------------------------

    async def navigate(self, url: str) -> None:
        await self.send("Page.navigate", {"url": url})

    async def eval(self, expression: str) -> Any:
        res = await self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        r = res.get("result", {})
        if r.get("subtype") == "error":
            raise RuntimeError(f"JS error: {r.get('description')}")
        return r.get("value")

    async def wait_for(self, expression: str, *, timeout: float = 12.0, every: float = 0.25) -> Any:
        """Poll a JS expression until it returns truthy (or timeout)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            val = await self.eval(expression)
            if val:
                return val
            await asyncio.sleep(every)
        return None

    async def rect_of(self, selector: str) -> Optional[dict]:
        """Center + box of the first element matching CSS selector, in viewport px.

        Scrolls it into view first. Returns None if absent or not visible.
        """
        js = (
            "(()=>{const e=document.querySelector(" + json.dumps(selector) + ");"
            "if(!e)return null;e.scrollIntoView({block:'center',inline:'center'});"
            "const r=e.getBoundingClientRect();"
            "if(r.width<1||r.height<1)return null;"
            "return {x:r.x+r.width/2,y:r.y+r.height/2,w:r.width,h:r.height,left:r.x,top:r.y};})()"
        )
        return await self.eval(js)

    async def rect_of_text(self, text: str, tag: str = "*") -> Optional[dict]:
        """Center of the first visible element whose trimmed text == text."""
        js = (
            "(()=>{const t=" + json.dumps(text) + ";"
            "const els=[...document.querySelectorAll(" + json.dumps(tag) + ")];"
            "for(const e of els){if(e.children.length===0&&e.textContent.trim()===t){"
            "e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();"
            "if(r.width>0&&r.height>0)return {x:r.x+r.width/2,y:r.y+r.height/2,w:r.width,h:r.height};}}"
            "return null;})()"
        )
        return await self.eval(js)

    # -- virtual mouse (human gesture) --------------------------------------

    async def _dispatch_mouse(self, mtype: str, x: float, y: float, *, button: str = "none", buttons: int = 0, clicks: int = 0) -> None:
        await self.send(
            "Input.dispatchMouseEvent",
            {"type": mtype, "x": float(x), "y": float(y), "button": button, "buttons": buttons, "clickCount": clicks},
            wait=False,
        )

    async def human_move(self, x: float, y: float, target_w: float = 40, target_h: float = 40) -> list[dict]:
        """Move the virtual cursor to (x,y) along a human Bézier/min-jerk path.

        Returns the executed trajectory [{x,y,t_ms}] (for the dataset recorder).
        """
        x0, y0 = self._cursor
        path = plan_human_path(x0, y0, x, y, target_w=target_w, target_h=target_h)
        t0 = now_ms()
        executed: list[dict] = []
        for p in path:
            await self._dispatch_mouse("mouseMoved", p["x"], p["y"])
            executed.append({"x": int(p["x"]), "y": int(p["y"]), "t_ms": now_ms() - t0})
            await asyncio.sleep(max(0.0, p["delay_ms"]) / 1000.0)
        self._cursor = (x, y)
        return executed

    async def click_xy(self, x: float, y: float, *, dwell: float = 0.09) -> None:
        await self._dispatch_mouse("mouseMoved", x, y)
        await asyncio.sleep(dwell)  # human aiming pause
        await self._dispatch_mouse("mousePressed", x, y, button="left", buttons=1, clicks=1)
        await asyncio.sleep(0.06)
        await self._dispatch_mouse("mouseReleased", x, y, button="left", buttons=1, clicks=1)

    async def human_click(self, x: float, y: float, target_w: float = 40, target_h: float = 40) -> list[dict]:
        traj = await self.human_move(x, y, target_w, target_h)
        await self.click_xy(x, y)
        return traj

    async def click_selector(self, selector: str, *, timeout: float = 8.0) -> Optional[dict]:
        rect = None
        deadline = time.time() + timeout
        while time.time() < deadline:
            rect = await self.rect_of(selector)
            if rect:
                break
            await asyncio.sleep(0.25)
        if not rect:
            return None
        await self.human_click(rect["x"], rect["y"], rect["w"], rect["h"])
        return rect

    # -- virtual keyboard ----------------------------------------------------

    async def type_text(self, text: str, *, per_char: float = 0.04) -> None:
        for ch in text:
            await self.send("Input.dispatchKeyEvent", {"type": "keyDown", "text": ch}, wait=False)
            await self.send("Input.dispatchKeyEvent", {"type": "keyUp", "text": ch}, wait=False)
            await asyncio.sleep(per_char)

    async def press_key(self, key: str, code: str, keycode: int) -> None:
        for t in ("keyDown", "keyUp"):
            await self.send(
                "Input.dispatchKeyEvent",
                {"type": t, "key": key, "code": code, "windowsVirtualKeyCode": keycode, "nativeVirtualKeyCode": keycode},
                wait=False,
            )
