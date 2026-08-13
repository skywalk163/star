"""
坐标比例定位器 - 最后兜底

将原有 input_click_x_ratio/y_ratio 逻辑迁移为定位器,
通过窗口 rect 与比例坐标计算绝对点击位置.
confidence 恒 0.3, 保证在同链中只做兜底.
"""

from __future__ import annotations

from star_core.locators.base import (
    ElementBox,
    Locator,
    LocatorTarget,
    WindowContext,
)


class RatioLocator(Locator):
    """坐标比例定位器, confidence 恒 0.3"""
    name = "ratio"

    def find(self, target: LocatorTarget, ctx: WindowContext) -> ElementBox | None:
        if target.ratio is None:
            return None

        # 优先用 ctx.hwnd, 回退到 ctx.star.hwnd
        hwnd = ctx.hwnd
        if hwnd is None and ctx.star is not None:
            hwnd = ctx.star.hwnd
        if hwnd is None:
            return None

        try:
            import win32gui
            rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            return None

        if not rect:
            return None

        left, top, right, bottom = rect
        w = right - left
        h = bottom - top
        if w <= 0 or h <= 0:
            return None

        abs_x = int(left + w * target.ratio.x_ratio)
        abs_y = int(top + h * target.ratio.y_ratio)

        return ElementBox(
            x=abs_x,
            y=abs_y,
            width=1,
            height=1,
            confidence=0.3,
            source="ratio",
            meta={
                "x_ratio": target.ratio.x_ratio,
                "y_ratio": target.ratio.y_ratio,
                "window_rect": list(rect),
            },
        )
