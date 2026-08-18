"""DuMate 桌面端 CDP 桥 —— 版本韧性相关单元测试。

不连真实浏览器：注入一个假 CDPBridge，按模块里预置的 JS 常量路由到预设返回值，
从而验证「候选选择器按优先级 try」「probe 体检」「发送/读取回复流程」等逻辑在
不依赖具体 DOM 的前提下成立。DuMate 每次发版会换 CSS 哈希、偶尔调 DOM，这些测试
锁住的是我们这侧的判定逻辑，不锁 DuMate 的实现细节。
"""

from __future__ import annotations

import star_core.dumate_app_cdp_bridge as m
from star_core.dumate_app_cdp_bridge import DuMateAppCDPBridge


TARGET = {"webSocketDebuggerUrl": "ws://127.0.0.1:9225/devtools/page/t1"}


class FakeCDP:
    """按注入的 {js_constant: value} 表回应 evaluate；其余动作记录后成功。"""

    def __init__(self, responses: dict, alive: bool = True, tab: dict | None = TARGET):
        self._responses = responses
        self._alive = alive
        self._tab = tab
        self.inserted: list[str] = []
        self.keys: list[str] = []

    def is_alive(self) -> bool:
        return self._alive

    def find_tab(self, pattern):
        return self._tab

    def evaluate(self, target, expr):
        for js, value in self._responses.items():
            if expr == js:
                return value
        return None

    def insert_text(self, target, text) -> bool:
        self.inserted.append(text)
        return True

    def send_key(self, target, key) -> bool:
        self.keys.append(key)
        return True


def _bridge(responses, **kw):
    b = DuMateAppCDPBridge()
    b._cdp = FakeCDP(responses, **kw)
    return b


# ---------------------------------------------------------------------------
# 选择器候选：语义属性优先、类名子串兜底
# ---------------------------------------------------------------------------

def test_selector_candidates_semantic_first():
    assert m._MSG_SELS[0] == "[data-markdown-body]"
    assert m._MSG_SELS[-1].startswith("[class*=")
    assert m._SEND_SELS[0] == 'button[title="发送"]'
    assert m._INPUT_SELS[0] == '[data-lexical-editor="true"]'
    # 类名兜底候选一律用子串匹配，不写死哈希
    for sel in (m._MSG_SELS[-1], m._SEND_SELS[-1], m._STOP_SELS[-1]):
        assert "*=" in sel


def test_legacy_single_selector_names_preserved():
    # 旧变量名保留，指向各组首选，避免外部引用断裂
    assert m._INPUT_SEL == m._INPUT_SELS[0]
    assert m._SEND_SEL == m._SEND_SELS[0]
    assert m._MSG_SEL == m._MSG_SELS[0]
    assert m._NEW_TASK_SEL == m._NEW_TASK_SELS[0]


def test_js_snippets_are_balanced_iife():
    for name in (
        "_GET_INPUT_JS", "_CLICK_SEND_JS", "_READ_LATEST_JS",
        "_DETECT_STATUS_JS", "_PROBE_SELECTORS_JS", "_CLICK_NEW_TASK_JS",
        "_SELECT_ALL_JS", "_SEND_ENABLED_JS", "_CLICK_STOP_JS",
    ):
        js = getattr(m, name)
        assert js.startswith("(() => {") and js.endswith("})()"), name
        assert js.count("{") == js.count("}"), name
        assert js.count("(") == js.count(")"), name
        assert js.count("[") == js.count("]"), name


def test_probe_selectors_all_matched():
    roles = {
        "input": {"matched": m._INPUT_SELS[0], "count": 1, "candidates": []},
        "send": {"matched": m._SEND_SELS[0], "count": 1, "candidates": []},
        "stop": {"matched": None, "count": 0, "candidates": []},
        "message": {"matched": m._MSG_SELS[0], "count": 3, "candidates": []},
        "assistant": {"matched": m._ASSISTANT_MSG_SELS[0], "count": 2, "candidates": []},
        "new_task": {"matched": m._NEW_TASK_SELS[0], "count": 1, "candidates": []},
    }
    b = _bridge({m._PROBE_SELECTORS_JS: roles})
    out = b.probe_selectors()
    # stop 缺失是常态（空闲时没有停止按钮），但其余角色都应命中
    assert out["roles"]["input"]["matched"] == m._INPUT_SELS[0]
    assert "stop" in out["missing"]
    assert out["ok"] is False  # 因为 stop 未命中


def test_probe_selectors_no_target():
    b = _bridge({}, tab=None)
    out = b.probe_selectors()
    assert out == {"ok": False, "reason": "no-target"}


# ---------------------------------------------------------------------------
# 读取回复：助手容器优先，count 基线区分新旧
# ---------------------------------------------------------------------------

def test_read_latest_reports_text_and_count():
    b = _bridge({m._READ_LATEST_JS: {"text": "你好", "count": 2}})
    snap = b.read_latest()
    assert snap == {"text": "你好", "count": 2}


def test_read_latest_unreachable_count_minus_one():
    b = _bridge({}, tab=None)
    assert b.read_latest() == {"text": "", "count": -1}


def test_get_new_response_requires_count_over_baseline():
    b = _bridge({m._READ_LATEST_JS: {"text": "旧回答", "count": 1}})
    # 未发过消息，无基线 -> 退化为最新回复
    assert b.get_new_response() == "旧回答"
    # 设定基线为 1：条数未超过基线 -> None（旧回答残留，不误判）
    b._response_baseline = 1
    assert b.get_new_response() is None
    # 条数超过基线 -> 返回新回答
    b._cdp = FakeCDP({m._READ_LATEST_JS: {"text": "新回答", "count": 2}})
    b._response_baseline = 1
    assert b.get_new_response() == "新回答"


# ---------------------------------------------------------------------------
# 状态检测
# ---------------------------------------------------------------------------

def test_status_generating_when_stop_present():
    b = _bridge({m._DETECT_STATUS_JS: {"status": "generating", "via": "stop-button"}})
    assert b.get_status() == "generating"


def test_status_unknown_when_no_target():
    b = _bridge({}, tab=None)
    assert b.get_status() == "unknown"
