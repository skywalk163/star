"""
tests/test_locators.py - 定位器基础包测试

覆盖:
- LocatorChain 降级顺序(uia miss -> visual miss -> ratio 命中)
- confidence 过滤
- 异常隔离(某 locator 抛异常, 后续仍执行)
- RatioLocator 坐标换算单测
- UIA/Visual 在无真实窗口时返回 None 不抛异常
- create_locator / default_registry 工厂函数
"""

import pytest

from star_core.locators.base import (
    ElementBox,
    Locator,
    LocatorChain,
    LocatorTarget,
    RatioQuery,
    UIAQuery,
    VisualQuery,
    WindowContext,
)
from star_core.locators import create_locator, default_registry
from star_core.locators.ratio import RatioLocator


# ---------------------------------------------------------------------------
# 辅助: 假定位器
# ---------------------------------------------------------------------------

class FakeLocator(Locator):
    """可编程的假定位器, 用于测试链式降级"""

    def __init__(self, name: str, result: ElementBox | None = None,
                 raises: Exception | None = None):
        self.name = name
        self._result = result
        self._raises = raises
        self.call_count = 0

    def find(self, target: LocatorTarget, ctx: WindowContext) -> ElementBox | None:
        self.call_count += 1
        if self._raises:
            raise self._raises
        return self._result


def _make_box(source: str, confidence: float, x: int = 100, y: int = 200) -> ElementBox:
    return ElementBox(
        x=x, y=y, width=50, height=30,
        confidence=confidence, source=source, meta={},
    )


def _make_targets() -> dict[str, LocatorTarget]:
    """构造一组测试用 LocatorTarget"""
    return {
        "input": LocatorTarget(
            kind="input",
            uia=UIAQuery(control_type="Edit", name_regex="输入"),
            visual=VisualQuery(hint_text="输入"),
            ratio=RatioQuery(x_ratio=0.5, y_ratio=0.93),
        ),
    }


# ---------------------------------------------------------------------------
# LocatorChain 降级顺序
# ---------------------------------------------------------------------------

class TestLocatorChainDegradation:

    def test_uia_miss_visual_miss_ratio_hit(self):
        """uia miss -> visual miss -> ratio 命中"""
        targets = _make_targets()
        registry = {
            "uia": FakeLocator("uia", result=None),
            "visual": FakeLocator("visual", result=None),
            "ratio": FakeLocator("ratio", result=_make_box("ratio", 0.3)),
        }
        chain = LocatorChain(targets, ["uia", "visual", "ratio"], registry)
        ctx = WindowContext(min_confidence=0.3)

        box = chain.locate("input", ctx)

        assert box is not None
        assert box.source == "ratio"
        assert registry["uia"].call_count == 1
        assert registry["visual"].call_count == 1
        assert registry["ratio"].call_count == 1

    def test_uia_hit_short_circuits(self):
        """uia 命中时不再调用后续定位器"""
        targets = _make_targets()
        registry = {
            "uia": FakeLocator("uia", result=_make_box("uia", 0.9)),
            "visual": FakeLocator("visual", result=_make_box("visual", 0.75)),
            "ratio": FakeLocator("ratio", result=_make_box("ratio", 0.3)),
        }
        chain = LocatorChain(targets, ["uia", "visual", "ratio"], registry)
        ctx = WindowContext(min_confidence=0.3)

        box = chain.locate("input", ctx)

        assert box is not None
        assert box.source == "uia"
        assert registry["uia"].call_count == 1
        assert registry["visual"].call_count == 0
        assert registry["ratio"].call_count == 0

    def test_all_miss_returns_none(self):
        """所有定位器都未命中时返回 None"""
        targets = _make_targets()
        registry = {
            "uia": FakeLocator("uia", result=None),
            "visual": FakeLocator("visual", result=None),
            "ratio": FakeLocator("ratio", result=None),
        }
        chain = LocatorChain(targets, ["uia", "visual", "ratio"], registry)
        ctx = WindowContext(min_confidence=0.3)

        box = chain.locate("input", ctx)
        assert box is None

    def test_unknown_kind_returns_none(self):
        """未注册的 kind 返回 None"""
        targets = _make_targets()
        registry = {"uia": FakeLocator("uia", result=_make_box("uia", 0.9))}
        chain = LocatorChain(targets, ["uia"], registry)
        ctx = WindowContext()

        assert chain.locate("nonexistent", ctx) is None


# ---------------------------------------------------------------------------
# confidence 过滤
# ---------------------------------------------------------------------------

class TestConfidenceFiltering:

    def test_low_confidence_skipped(self):
        """confidence < min_confidence 的结果被跳过"""
        targets = _make_targets()
        registry = {
            "uia": FakeLocator("uia", result=_make_box("uia", 0.2)),
            "ratio": FakeLocator("ratio", result=_make_box("ratio", 0.3)),
        }
        chain = LocatorChain(targets, ["uia", "ratio"], registry)
        ctx = WindowContext(min_confidence=0.3)

        box = chain.locate("input", ctx)

        # uia 返回 0.2 < 0.3, 被跳过; ratio 返回 0.3 >= 0.3, 命中
        assert box is not None
        assert box.source == "ratio"

    def test_high_min_confidence_filters_all(self):
        """min_confidence 过高导致全部被过滤"""
        targets = _make_targets()
        registry = {
            "ratio": FakeLocator("ratio", result=_make_box("ratio", 0.3)),
        }
        chain = LocatorChain(targets, ["ratio"], registry)
        ctx = WindowContext(min_confidence=0.8)

        assert chain.locate("input", ctx) is None


# ---------------------------------------------------------------------------
# 异常隔离
# ---------------------------------------------------------------------------

class TestExceptionIsolation:

    def test_exception_does_not_break_chain(self):
        """某 locator 抛异常, 后续仍执行"""
        targets = _make_targets()
        registry = {
            "uia": FakeLocator("uia", raises=RuntimeError("uia crashed")),
            "visual": FakeLocator("visual", raises=ValueError("visual crashed")),
            "ratio": FakeLocator("ratio", result=_make_box("ratio", 0.3)),
        }
        chain = LocatorChain(targets, ["uia", "visual", "ratio"], registry)
        ctx = WindowContext(min_confidence=0.3)

        box = chain.locate("input", ctx)

        assert box is not None
        assert box.source == "ratio"
        assert registry["uia"].call_count == 1
        assert registry["visual"].call_count == 1
        assert registry["ratio"].call_count == 1

    def test_all_raise_returns_none(self):
        """所有 locator 都抛异常时返回 None"""
        targets = _make_targets()
        registry = {
            "uia": FakeLocator("uia", raises=RuntimeError("boom")),
            "ratio": FakeLocator("ratio", raises=ValueError("bang")),
        }
        chain = LocatorChain(targets, ["uia", "ratio"], registry)
        ctx = WindowContext()

        assert chain.locate("input", ctx) is None


# ---------------------------------------------------------------------------
# RatioLocator 坐标换算
# ---------------------------------------------------------------------------

class TestRatioLocator:

    def test_coordinate_calculation(self, monkeypatch):
        """验证 RatioLocator 坐标换算正确"""
        # 构造假 win32gui.GetWindowRect(win32gui 是 lazy import, 直接 patch 模块属性)
        fake_rect = (100, 200, 1100, 1200)  # left=100, top=200, w=1000, h=1000
        monkeypatch.setattr("win32gui.GetWindowRect", lambda hwnd: fake_rect)

        target = LocatorTarget(
            kind="input",
            ratio=RatioQuery(x_ratio=0.5, y_ratio=0.93),
        )
        ctx = WindowContext(hwnd=12345, min_confidence=0.3)
        locator = RatioLocator()

        box = locator.find(target, ctx)

        assert box is not None
        assert box.source == "ratio"
        assert box.confidence == 0.3
        # x = 100 + 1000 * 0.5 = 600
        assert box.x == 600
        # y = 200 + 1000 * 0.93 = 1130
        assert box.y == 1130

    def test_uses_star_hwnd_when_ctx_hwnd_none(self, monkeypatch):
        """ctx.hwnd 为 None 时回退到 ctx.star.hwnd"""
        fake_rect = (0, 0, 800, 600)
        captured_hwnds = []

        def fake_get_rect(hwnd):
            captured_hwnds.append(hwnd)
            return fake_rect

        monkeypatch.setattr("win32gui.GetWindowRect", fake_get_rect)

        fake_star = type("FakeStar", (), {"hwnd": 9999})()
        target = LocatorTarget(kind="input", ratio=RatioQuery(x_ratio=0.5, y_ratio=0.92))
        ctx = WindowContext(hwnd=None, star=fake_star, min_confidence=0.3)

        box = RatioLocator().find(target, ctx)

        assert box is not None
        assert captured_hwnds == [9999]
        # x = 0 + 800 * 0.5 = 400
        assert box.x == 400
        # y = 0 + 600 * 0.92 = 552
        assert box.y == 552

    def test_no_hwnd_returns_none(self):
        """无 hwnd 且无 star 时返回 None"""
        target = LocatorTarget(kind="input", ratio=RatioQuery())
        ctx = WindowContext(hwnd=None, star=None)

        assert RatioLocator().find(target, ctx) is None

    def test_no_ratio_query_returns_none(self):
        """target.ratio 为 None 时返回 None"""
        target = LocatorTarget(kind="input")
        ctx = WindowContext(hwnd=123)

        assert RatioLocator().find(target, ctx) is None

    def test_zero_size_window_returns_none(self, monkeypatch):
        """窗口宽高为 0 时返回 None"""
        monkeypatch.setattr("win32gui.GetWindowRect", lambda hwnd: (100, 200, 100, 200))
        target = LocatorTarget(kind="input", ratio=RatioQuery())
        ctx = WindowContext(hwnd=123)

        assert RatioLocator().find(target, ctx) is None

    def test_win32_exception_returns_none(self, monkeypatch):
        """win32gui.GetWindowRect 抛异常时返回 None"""
        def boom(hwnd):
            raise OSError("access denied")

        monkeypatch.setattr("win32gui.GetWindowRect", boom)
        target = LocatorTarget(kind="input", ratio=RatioQuery())
        ctx = WindowContext(hwnd=123)

        assert RatioLocator().find(target, ctx) is None


# ---------------------------------------------------------------------------
# UIA / Visual 无真实窗口时不抛异常
# ---------------------------------------------------------------------------

class TestUIALocatorNoWindow:

    def test_no_hwnd_returns_none(self):
        """无 hwnd 时 UIA 定位器返回 None"""
        from star_core.locators.uia import UIALocator

        target = LocatorTarget(kind="input", uia=UIAQuery(control_type="Edit"))
        ctx = WindowContext(hwnd=None, star=None)

        assert UIALocator().find(target, ctx) is None

    def test_no_uia_query_returns_none(self):
        """target.uia 为 None 时返回 None"""
        from star_core.locators.uia import UIALocator

        target = LocatorTarget(kind="input")
        ctx = WindowContext(hwnd=123)

        assert UIALocator().find(target, ctx) is None

    def test_invalid_hwnd_returns_none(self):
        """无效 hwnd 时 UIA 定位器返回 None 不抛异常"""
        from star_core.locators.uia import UIALocator

        target = LocatorTarget(
            kind="input",
            uia=UIAQuery(control_type="Edit", name_regex="test"),
        )
        # hwnd=0 或很小的值, ControlFromHandle 会返回 None
        ctx = WindowContext(hwnd=1, star=None)

        result = UIALocator().find(target, ctx)
        # 不抛异常, 返回 None 或 ElementBox(取决于环境)
        assert result is None or isinstance(result, ElementBox)


class TestVisualLocatorNoWindow:

    def test_no_hwnd_returns_none(self):
        """无 hwnd 时 Visual 定位器返回 None"""
        from star_core.locators.visual import VisualLocator

        target = LocatorTarget(kind="input", visual=VisualQuery(hint_text="输入"))
        ctx = WindowContext(hwnd=None, star=None)

        assert VisualLocator().find(target, ctx) is None

    def test_no_visual_query_returns_none(self):
        """target.visual 为 None 时返回 None"""
        from star_core.locators.visual import VisualLocator

        target = LocatorTarget(kind="input")
        ctx = WindowContext(hwnd=123)

        assert VisualLocator().find(target, ctx) is None

    def test_invalid_hwnd_returns_none(self):
        """无效 hwnd 时 Visual 定位器返回 None 不抛异常"""
        from star_core.locators.visual import VisualLocator

        target = LocatorTarget(
            kind="input",
            visual=VisualQuery(hint_text="输入"),
        )
        ctx = WindowContext(hwnd=1, star=None)

        result = VisualLocator().find(target, ctx)
        assert result is None or isinstance(result, ElementBox)

    def test_template_only_returns_none(self):
        """仅有 template(无 hint_text)时返回 None"""
        from star_core.locators.visual import VisualLocator

        target = LocatorTarget(
            kind="input",
            visual=VisualQuery(template="assets/send.png"),
        )
        ctx = WindowContext(hwnd=123)

        assert VisualLocator().find(target, ctx) is None


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

class TestFactory:

    def test_create_locator_uia(self):
        locator = create_locator("uia")
        assert locator is not None
        assert locator.name == "uia"

    def test_create_locator_visual(self):
        locator = create_locator("visual")
        assert locator is not None
        assert locator.name == "visual"

    def test_create_locator_ratio(self):
        locator = create_locator("ratio")
        assert locator is not None
        assert locator.name == "ratio"

    def test_create_locator_unknown(self):
        assert create_locator("nonexistent") is None

    def test_create_locator_cdp_not_registered(self):
        """cdp 不在本 Task 范围内"""
        assert create_locator("cdp") is None

    def test_default_registry(self):
        registry = default_registry()
        assert "uia" in registry
        assert "visual" in registry
        assert "ratio" in registry
        assert "cdp" not in registry
        assert len(registry) == 3

    def test_default_registry_instances(self):
        registry = default_registry()
        assert registry["uia"].name == "uia"
        assert registry["visual"].name == "visual"
        assert registry["ratio"].name == "ratio"


# ---------------------------------------------------------------------------
# LocatorChain.available()
# ---------------------------------------------------------------------------

class TestLocatorChainAvailable:

    def test_available_returns_keys(self):
        registry = {
            "uia": FakeLocator("uia"),
            "ratio": FakeLocator("ratio"),
        }
        chain = LocatorChain({}, ["uia", "ratio"], registry)
        available = chain.available()
        assert "uia" in available
        assert "ratio" in available

    def test_available_empty(self):
        chain = LocatorChain({}, [], {})
        assert chain.available() == []
