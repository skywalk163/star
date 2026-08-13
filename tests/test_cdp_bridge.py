"""CDP 桥单元测试。

全部使用 mock：urllib.request.urlopen 模拟 /json 响应，
websockets connect 替换为记录发送内容的假连接，不连接真实浏览器。
"""

from __future__ import annotations

import json
import urllib.error

import pytest

import star_core.cdp_bridge as cdp_module
from star_core.cdp_bridge import CDPBridge

TAB = {
    "id": "t1",
    "title": "文心一言",
    "url": "https://yiyan.baidu.com/chat",
    "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/t1",
}


@pytest.fixture(autouse=True)
def fast_reconnect(monkeypatch):
    """测试中把指数退避降为 0 秒，失败即返回，避免测试挂起。"""
    monkeypatch.setattr(cdp_module, "_RECONNECT_DELAYS", (0.0, 0.0))


class FakeHttpResponse:
    """模拟 urllib.request.urlopen 的响应对象。"""

    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *exc) -> bool:
        return False


class FakeWebSocket:
    """记录发送内容、按命令 id 回显预设结果的假 WebSocket 连接。"""

    def __init__(self, value=None, exception_details=False, connect_error=None):
        self.sent = []
        self._value = value
        self._exception_details = exception_details
        self._connect_error = connect_error
        self._last_id: int | None = None

    async def __aenter__(self) -> "FakeWebSocket":
        if self._connect_error is not None:
            raise self._connect_error
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def send(self, payload: str) -> None:
        data = json.loads(payload)
        self._last_id = data["id"]
        self.sent.append(data)

    async def recv(self) -> str:
        assert self._last_id is not None
        if self._exception_details:
            return json.dumps(
                {"id": self._last_id, "result": {"exceptionDetails": {"text": "TypeError"}}}
            )
        if self._value is not None:
            return json.dumps({"id": self._last_id, "result": {"result": self._value}})
        return json.dumps(
            {"id": self._last_id, "result": {"result": {"type": "undefined"}}}
        )


def patch_http(monkeypatch, payload=None, status=200, error=None):
    """把 urllib.request.urlopen 替换为假实现。"""

    def fake_urlopen(url, timeout=2.0):
        if error is not None:
            raise error
        return FakeHttpResponse(payload, status=status)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return fake_urlopen


def patch_ws(monkeypatch, value=None, exception_details=False, connect_error=None):
    """把 websockets connect 替换为假连接，返回 (FakeWebSocket, 断言结果)。"""
    ws = FakeWebSocket(
        value=value,
        exception_details=exception_details,
        connect_error=connect_error,
    )

    def fake_connect(*args, **kwargs):
        return ws

    monkeypatch.setattr(cdp_module, "connect", fake_connect)
    return ws


# ---------- is_alive ----------


def test_is_alive_true(monkeypatch):
    patch_http(monkeypatch, payload=[])
    assert CDPBridge().is_alive() is True


def test_is_alive_false_on_connection_error(monkeypatch):
    patch_http(monkeypatch, error=urllib.error.URLError("connection refused"))
    assert CDPBridge().is_alive() is False


# ---------- list_tabs / find_tab ----------


def test_list_tabs_parses_fields(monkeypatch):
    targets = [
        {"id": "t1", "title": "A", "url": "http://a", "type": "page",
         "webSocketDebuggerUrl": "ws://a"},
        {"id": "t2", "title": "B", "url": "http://b", "type": "page",
         "webSocketDebuggerUrl": "ws://b"},
    ]
    patch_http(monkeypatch, payload=targets)
    tabs = CDPBridge().list_tabs()
    assert len(tabs) == 2
    assert tabs[0] == {"id": "t1", "title": "A", "url": "http://a",
                       "webSocketDebuggerUrl": "ws://a"}
    assert tabs[1]["id"] == "t2"
    assert tabs[1]["webSocketDebuggerUrl"] == "ws://b"


def test_list_tabs_returns_empty_on_error(monkeypatch):
    patch_http(monkeypatch, error=urllib.error.URLError("refused"))
    assert CDPBridge().list_tabs() == []


def test_find_tab_matches_substring(monkeypatch):
    patch_http(
        monkeypatch,
        payload=[
            {"id": "t1", "title": "other", "url": "https://example.com",
             "webSocketDebuggerUrl": "ws://1"},
            {"id": "t2", "title": "yiyan", "url": "https://yiyan.baidu.com/chat",
             "webSocketDebuggerUrl": "ws://2"},
        ],
    )
    tab = CDPBridge().find_tab("yiyan.baidu.com")
    assert tab is not None
    assert tab["id"] == "t2"


def test_find_tab_matches_regex(monkeypatch):
    targets = [
        {"id": "t1", "title": "a", "url": "https://yiyan.baidu.com/x",
         "webSocketDebuggerUrl": "ws://1"},
    ]
    patch_http(monkeypatch, payload=targets)
    # 转义点号精确匹配 + IGNORECASE：.COM 命中 .com
    tab = CDPBridge().find_tab(r"yiyan\.baidu\.COM")
    assert tab is not None
    assert tab["id"] == "t1"


def test_find_tab_empty_pattern_returns_none(monkeypatch):
    patch_http(monkeypatch, payload=[TAB])
    assert CDPBridge().find_tab("") is None


def test_find_tab_invalid_regex_falls_back_to_substring(monkeypatch):
    targets = [
        {"id": "t1", "title": "a", "url": "https://a.example.com/x",
         "webSocketDebuggerUrl": "ws://1"},
    ]
    patch_http(monkeypatch, payload=targets)
    # "(" 不是合法正则，触发 re.error 退化分支；url 不含 "(" 所以不命中
    assert CDPBridge().find_tab("(") is None


# ---------- evaluate ----------


def test_evaluate_returns_value(monkeypatch):
    ws = patch_ws(monkeypatch, value={"type": "string", "value": "hello"})
    result = CDPBridge().evaluate(TAB, "document.title")
    assert result == "hello"
    cmd = ws.sent[0]
    assert cmd["method"] == "Runtime.evaluate"
    assert cmd["params"]["expression"] == "document.title"
    assert cmd["params"]["returnByValue"] is True


def test_evaluate_returns_none_on_connection_error(monkeypatch):
    patch_ws(monkeypatch, connect_error=ConnectionError("no browser on 9222"))
    assert CDPBridge().evaluate(TAB, "1+1") is None


def test_evaluate_returns_none_on_js_exception(monkeypatch):
    patch_ws(monkeypatch, exception_details=True)
    assert CDPBridge().evaluate(TAB, "null.value") is None


def test_evaluate_returns_none_without_ws_url():
    assert CDPBridge().evaluate({"id": "x", "url": "http://a"}, "1") is None


# ---------- set_value ----------


def test_set_value_builds_correct_js(monkeypatch):
    ws = patch_ws(monkeypatch, value={"type": "boolean", "value": True})
    ok = CDPBridge().set_value(TAB, "#msg-input", "你好 world")
    assert ok is True
    expr = ws.sent[0]["params"]["expression"]
    assert json.dumps("#msg-input") in expr
    assert json.dumps("你好 world") in expr
    assert "el.value=" in expr
    assert "dispatchEvent(new Event('input',{bubbles:true}))" in expr
    assert "dispatchEvent(new Event('change',{bubbles:true}))" in expr
    assert "document.querySelector(" in expr
    assert "return true" in expr


def test_set_value_returns_false_when_element_missing(monkeypatch):
    patch_ws(monkeypatch, exception_details=True)
    assert CDPBridge().set_value(TAB, "#absent", "x") is False


# ---------- click_selector ----------


def test_click_selector_builds_correct_js(monkeypatch):
    ws = patch_ws(monkeypatch, value={"type": "boolean", "value": True})
    assert CDPBridge().click_selector(TAB, "#send-btn") is True
    expr = ws.sent[0]["params"]["expression"]
    assert json.dumps("#send-btn") in expr
    assert "el.click()" in expr
    assert "if(!el)return false" in expr


def test_click_selector_returns_false_when_missing(monkeypatch):
    patch_ws(monkeypatch, exception_details=True)
    assert CDPBridge().click_selector(TAB, "#absent") is False


# ---------- get_text ----------


def test_get_text_returns_text(monkeypatch):
    patch_ws(monkeypatch, value={"type": "string", "value": "结果内容"})
    assert CDPBridge().get_text(TAB, ".markdown-body") == "结果内容"


def test_get_text_returns_empty_string_on_failure(monkeypatch):
    patch_ws(monkeypatch, connect_error=OSError("offline"))
    assert CDPBridge().get_text(TAB, ".x") == ""


# ---------- get_element_rect ----------


def test_get_element_rect_returns_viewport_coords(monkeypatch):
    value = {"type": "object",
             "value": {"x": 10, "y": 20, "width": 100, "height": 50}}
    patch_ws(monkeypatch, value=value)
    rect = CDPBridge().get_element_rect(TAB, "#box")
    assert rect == {"x": 10, "y": 20, "width": 100, "height": 50}


def test_get_element_rect_returns_none_when_missing(monkeypatch):
    patch_ws(monkeypatch, value={"type": "object", "value": None})
    assert CDPBridge().get_element_rect(TAB, "#absent") is None


# ---------- send_key ----------


def test_send_key_enter_two_events(monkeypatch):
    ws = patch_ws(monkeypatch, value={"type": "object", "value": {}})
    assert CDPBridge().send_key(TAB, "Enter") is True
    assert [cmd["method"] for cmd in ws.sent] == [
        "Input.dispatchKeyEvent",
        "Input.dispatchKeyEvent",
    ]
    down = ws.sent[0]["params"]
    up = ws.sent[1]["params"]
    assert down["type"] == "keyDown" and down["key"] == "Enter"
    assert down["code"] == "Enter" and down["windowsVirtualKeyCode"] == 13
    assert up["type"] == "keyUp" and up["key"] == "Enter"


def test_send_key_escape(monkeypatch):
    ws = patch_ws(monkeypatch, value={"type": "object", "value": {}})
    assert CDPBridge().send_key(TAB, "Escape") is True
    assert ws.sent[0]["params"]["windowsVirtualKeyCode"] == 27


def test_send_key_unknown_key_returns_false():
    assert CDPBridge().send_key(TAB, "Tab") is False


def test_send_key_returns_false_on_connection_error(monkeypatch):
    patch_ws(monkeypatch, connect_error=OSError("offline"))
    assert CDPBridge().send_key(TAB, "Enter") is False


# ---------- find_by_text ----------


def test_find_by_text_returns_selector(monkeypatch):
    value = {"type": "object",
             "value": {"selector": "[data-star-findbytext=\"star-hit-abc123\"]"}}
    ws = patch_ws(monkeypatch, value=value)
    hit = CDPBridge().find_by_text(TAB, "停止生成")
    assert hit is not None
    assert hit["selector"].startswith("[data-star-findbytext=")
    expr = ws.sent[0]["params"]["expression"]
    assert json.dumps("停止生成") in expr
    assert "includes(text)" in expr
    assert "querySelectorAll(css)" in expr


def test_find_by_text_returns_none_when_empty(monkeypatch):
    patch_ws(monkeypatch, value={"type": "object", "value": None})
    assert CDPBridge().find_by_text(TAB, "不存在的东西") is None