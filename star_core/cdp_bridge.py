"""CDP 桥：管控浏览器的 Chrome DevTools Protocol 连接与 DOM 操作。

通过 HTTP /json 枚举浏览器标签页，通过 WebSocket 执行 CDP 命令
（Runtime.evaluate / Input.dispatchKeyEvent），为浏览器网页 AI
（文心一言等）提供任务提交、输出读取与按键能力。

连接模型：每次命令新建一次 WebSocket 连接（无持久会话，天然抗断线），
失败时按指数退避（1s/2s/4s）重试，仍失败则返回 None 而非向上抛异常。
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from websockets.asyncio.client import connect

logger = logging.getLogger(__name__)

#: 连接失败后的指数退避间隔（秒）；_send 共尝试 len(_RECONNECT_DELAYS) + 1 次
_RECONNECT_DELAYS: tuple[float, ...] = (1.0, 2.0, 4.0)

#: list_tabs 需要保留的 /json target 字段
_TAB_FIELDS: tuple[str, ...] = ("id", "title", "url", "webSocketDebuggerUrl")

#: 支持的按键 -> (windowsVirtualKeyCode, code)
_KEY_CODES: dict[str, tuple[int, str]] = {
    "Enter": (13, "Enter"),
    "Escape": (27, "Escape"),
    "Backspace": (8, "Backspace"),
}


class CDPBridge:
    """管控浏览器 CDP 桥（标签页枚举 + DOM 读写 + 按键）。"""

    def __init__(self, port: int = 9222):
        self.port = port
        self._base_url = f"http://127.0.0.1:{port}"
        self._seq = itertools.count(1)

    @property
    def base_url(self) -> str:
        """CDP HTTP 端点根地址。"""
        return self._base_url

    def is_alive(self) -> bool:
        """探测 CDP HTTP 端点是否可达。"""
        try:
            with urllib.request.urlopen(f"{self._base_url}/json", timeout=2.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_tabs(self) -> list[dict]:
        """枚举全部标签页 target，失败返回空列表。"""
        try:
            with urllib.request.urlopen(f"{self._base_url}/json", timeout=2.0) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            targets = json.loads(raw)
        except Exception:
            logger.warning("CDP /json 枚举失败", exc_info=True)
            return []
        tabs = []
        for target in targets:
            if not isinstance(target, dict):
                continue
            tabs.append({field: target.get(field) for field in _TAB_FIELDS})
        return tabs

    def version(self) -> dict | None:
        """读取 CDP /json/version，返回浏览器/协议版本信息；失败返回 None。

        用于能力自检：确认端口上是真实的 CDP（而非死监听），并取回
        ``Browser`` / ``Protocol-Version`` / ``webSocketDebuggerUrl``。
        """
        try:
            with urllib.request.urlopen(f"{self._base_url}/json/version", timeout=2.0) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            return None

    def find_tab(self, url_pattern: str) -> dict | None:
        """按 url 匹配标签页：优先正则，正则非法时退化为子串匹配。

        url_pattern 为空时返回 None（未配置则不匹配任何标签页）。
        """
        if not url_pattern:
            return None
        for tab in self.list_tabs():
            url = tab.get("url") or ""
            try:
                if re.search(url_pattern, url, re.IGNORECASE):
                    return tab
            except re.error:
                if url_pattern in url:
                    return tab
        return None

    def evaluate(self, tab: dict, expr: str) -> Any:
        """Runtime.evaluate 执行表达式并返回 result.value。

        CDP 不可达、表达式抛异常或执行结果不含 value 时返回 None，不向上抛。
        """
        resp = self._send(
            tab,
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True},
        )
        if resp is None or "error" in resp:
            return None
        result = resp.get("result") or {}
        if "exceptionDetails" in result:
            return None
        inner = result.get("result")
        if not isinstance(inner, dict):
            return None
        if inner.get("type") == "undefined":
            return None
        return inner.get("value")

    def set_value(self, tab: dict, sel: str, text: str) -> bool:
        """给选择器命中的输入框设值并派发 input/change 事件。

        元素不存在时 JS 抛异常，evaluate 返回 None，本方法返回 False。
        """
        expr = (
            "(el=>{"
            "el.value=" + json.dumps(text) + ";"
            "el.dispatchEvent(new Event('input',{bubbles:true}));"
            "el.dispatchEvent(new Event('change',{bubbles:true}));"
            "return true;"
            "})(document.querySelector(" + json.dumps(sel) + "))"
        )
        return self.evaluate(tab, expr) is True

    def click_selector(self, tab: dict, sel: str) -> bool:
        """点击选择器命中的元素（DOM click 事件），未命中返回 False。"""
        expr = (
            "(el=>{"
            "if(!el)return false;"
            "el.click();"
            "return true;"
            "})(document.querySelector(" + json.dumps(sel) + "))"
        )
        return self.evaluate(tab, expr) is True

    def get_text(self, tab: dict, sel: str) -> str:
        """读取选择器命中元素的可见文本（innerText 优先，其次 value）。"""
        expr = (
            "(()=>{"
            "const el=document.querySelector(" + json.dumps(sel) + ");"
            "return el?(el.innerText||el.value||''):'';"
            "})()"
        )
        value = self.evaluate(tab, expr)
        return str(value) if value is not None else ""

    def get_element_rect(self, tab: dict, sel: str) -> dict | None:
        """返回选择器命中元素的视口坐标 {x, y, width, height}，未命中返回 None。"""
        expr = (
            "(()=>{"
            "const el=document.querySelector(" + json.dumps(sel) + ");"
            "if(!el)return null;"
            "const r=el.getBoundingClientRect();"
            "return {x:r.x,y:r.y,width:r.width,height:r.height};"
            "})()"
        )
        value = self.evaluate(tab, expr)
        if not isinstance(value, dict):
            return None
        return {k: value.get(k) for k in ("x", "y", "width", "height")}

    def insert_text(self, tab: dict, text: str) -> bool:
        """通过 ``Input.insertText`` 向当前焦点元素插入文本。

        与 :meth:`set_value` 的区别：``set_value`` 直接改 ``el.value``，只适用于
        原生 input/textarea；富文本编辑器（Lexical / ProseMirror / Slate）把内容
        存在自己的 model 里，直接改 DOM 不会被感知。``Input.insertText`` 走浏览器
        真实输入管线，编辑器能正常收到 ``beforeinput``/``input``。

        调用前需先让目标元素获得焦点（例如 ``evaluate(tab, "el.focus()")``）。
        """
        resp = self._send(tab, "Input.insertText", {"text": text})
        return resp is not None and "error" not in resp

    def send_key(self, tab: dict, key: str) -> bool:
        """通过 Input.dispatchKeyEvent 发送按键（Enter / Escape）。

        keyDown + keyUp 两次事件；不支持的按键或连接失败返回 False。
        """
        code = _KEY_CODES.get(key)
        if code is None:
            return False
        vk, code_name = code
        ok = True
        for event_type in ("keyDown", "keyUp"):
            resp = self._send(
                tab,
                "Input.dispatchKeyEvent",
                {
                    "type": event_type,
                    "key": key,
                    "code": code_name,
                    "windowsVirtualKeyCode": vk,
                    "nativeVirtualKeyCode": vk,
                },
            )
            if resp is None or "error" in resp:
                ok = False
        return ok

    def find_by_text(self, tab: dict, text: str) -> dict | None:
        """在按钮/可点击元素中查找可见文本包含 text 的元素。

        命中时给元素打上临时属性并返回 {"selector": "[data-star-findbytext=...]"}，
        未命中返回 None。返回的选择器可直接传给 get_element_rect / click_selector。
        """
        css = 'button,[role="button"],[class*="btn"],a,input[type="button"]'
        expr = (
            "(()=>{"
            "const text=" + json.dumps(text) + ";"
            "const css=" + json.dumps(css) + ";"
            "const cands=document.querySelectorAll(css);"
            "for(const el of cands){"
            "const t=(el.innerText||el.value||'').trim();"
            "if(t&&t.includes(text)){"
            "const mark='star-hit-'+Date.now()+'-'+Math.random().toString(36).slice(2,8);"
            "el.setAttribute('data-star-findbytext',mark);"
            "return {selector:'[data-star-findbytext=\"'+mark+'\"]'};"
            "}"
            "}"
            "return null;"
            "})()"
        )
        value = self.evaluate(tab, expr)
        if isinstance(value, dict) and value.get("selector"):
            return value
        return None

    def _send(
        self,
        tab: dict,
        method: str,
        params: dict | None = None,
    ) -> dict | None:
        """向 tab 的 WebSocket 发送 CDP 命令并返回完整响应 dict；失败返回 None。"""
        if not isinstance(tab, dict):
            return None
        ws_url = tab.get("webSocketDebuggerUrl")
        if not isinstance(ws_url, str) or not ws_url:
            return None
        payload = params or {}
        last_exc: Exception | None = None
        for attempt in range(len(_RECONNECT_DELAYS) + 1):
            try:
                return self._run_coro(self._send_async(ws_url, method, payload))
            except Exception as exc:
                last_exc = exc
                if attempt < len(_RECONNECT_DELAYS):
                    time.sleep(_RECONNECT_DELAYS[attempt])
        logger.warning("CDP 命令失败: %s (%s)", method, last_exc)
        return None

    @staticmethod
    def _run_coro(coro):
        """运行一个协程并返回结果。

        在 FastAPI 的异步端点里，当前线程已有运行中的事件循环，此时
        asyncio.run() 会抛 "cannot be called from a running event loop"，
        导致 CDP 调用整体失败（HTTP 500）。故检测到运行中的循环时，改在
        独立线程里用全新循环执行，避免阻塞并绕开该限制。
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # 无运行中的事件循环：直接 asyncio.run
            return asyncio.run(coro)

        # 已在事件循环线程上：换独立线程 + 新循环执行
        result: dict = {}

        def _worker() -> None:
            try:
                result["value"] = asyncio.run(coro)
            except Exception as exc:  # noqa: BLE001
                result["error"] = exc

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join()
        if "error" in result:
            raise result["error"]
        return result.get("value")

    async def _send_async(
        self,
        ws_url: str,
        method: str,
        params: dict,
    ) -> dict | None:
        """单次 WebSocket 命令往返：发送命令并等待本 id 的响应。"""
        async with connect(ws_url, open_timeout=5.0, close_timeout=2.0) as ws:
            msg_id = next(self._seq)
            await ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
            for _ in range(50):
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                data = json.loads(raw)
                if data.get("id") == msg_id:
                    return data
        return None