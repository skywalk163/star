"""CDP 定位器：通过管控浏览器 DOM 定位页面元素（浏览器 agent 专用）。

依赖 locators/base.py 的抽象（Task A 提供）；"cdp" 在 locators 注册表的
登记由整合阶段统一完成，本模块不修改 `star_core/locators/__init__.py`。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import ElementBox, Locator, LocatorTarget, WindowContext

if TYPE_CHECKING:
    from ..cdp_bridge import CDPBridge

logger = logging.getLogger(__name__)


class CDPLocator(Locator):
    """基于 CDP DOM 的浏览器定位器：命中返回视口坐标，confidence 恒 0.95。"""

    name = "cdp"

    def __init__(self, bridge: CDPBridge | None = None):
        self.bridge = bridge

    def find(self, target: LocatorTarget, ctx: WindowContext) -> ElementBox | None:
        """在 ctx.cdptab 指定的标签页中定位目标元素。

        ctx.cdptab 为 None、bridge 不可用或页面未命中时返回 None；
        异常一律降级为 None，不中断调用方。
        """
        if self.bridge is None or ctx is None or ctx.cdptab is None:
            return None
        tab = self._extract_tab(ctx)
        if tab is None:
            return None
        query = target.cdp if target is not None else None
        if query is None:
            return None
        try:
            selector = query.selector
            if not selector and query.role:
                selector = '[role="' + query.role + '"]'
            if selector:
                box = self._locate_selector(tab, selector, query)
                if box is not None:
                    return box
            if query.text_contains:
                box = self._locate_text(tab, query.text_contains)
                if box is not None:
                    return box
        except Exception:
            logger.exception("CDPLocator.find 失败")
        return None

    def _locate_selector(
        self,
        tab: dict,
        selector: str,
        query: LocatorTarget,
    ) -> ElementBox | None:
        """按 DOM 选择器定位，返回元素视口坐标。"""
        rect = self.bridge.get_element_rect(tab, selector)
        if not rect:
            return None
        meta: dict[str, Any] = {"selector": selector}
        if query is not None and query.cdp is not None and query.cdp.text_contains:
            meta["text"] = query.cdp.text_contains
        return self._to_box(rect, meta)

    def _locate_text(self, tab: dict, text: str) -> ElementBox | None:
        """按可见文本定位按钮类元素。"""
        hit = self.bridge.find_by_text(tab, text)
        if not hit or not hit.get("selector"):
            return None
        rect = self.bridge.get_element_rect(tab, hit["selector"])
        if not rect:
            return None
        return self._to_box(rect, {"selector": hit["selector"], "text": text})

    def _extract_tab(self, ctx: WindowContext) -> dict | None:
        """从 ctx.cdptab 提取 tab dict（需含 webSocketDebuggerUrl）。"""
        cdptab = ctx.cdptab
        if not isinstance(cdptab, dict):
            return None
        if isinstance(cdptab.get("tab"), dict):
            return cdptab["tab"]
        if cdptab.get("webSocketDebuggerUrl"):
            return cdptab
        return None

    def _to_box(self, rect: dict[str, Any], meta: dict[str, Any]) -> ElementBox:
        return ElementBox(
            x=int(rect.get("x", 0) or 0),
            y=int(rect.get("y", 0) or 0),
            width=int(rect.get("width", 0) or 0),
            height=int(rect.get("height", 0) or 0),
            confidence=0.95,
            source="cdp",
            meta=meta,
        )