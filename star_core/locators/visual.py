"""
视觉定位器 - 通用兜底

通过截图 + OCR 识别占位文本(hint_text)定位输入框锚点.
lazy import OCRGazer, OCR 不可用时返回 None.
"""

from __future__ import annotations

from star_core.locators.base import (
    ElementBox,
    Locator,
    LocatorTarget,
    WindowContext,
)


class VisualLocator(Locator):
    """视觉 OCR 定位器, confidence 0.75"""
    name = "visual"

    # hint_text 命中后, 输入区 y 方向偏移量(像素)
    _INPUT_Y_OFFSET = 20

    def find(self, target: LocatorTarget, ctx: WindowContext) -> ElementBox | None:
        if target.visual is None:
            return None

        vq = target.visual

        # hint_text 模式
        if vq.hint_text:
            return self._find_by_hint_text(vq, ctx)

        # template 模式(留接口, 暂不实现)
        if vq.template:
            return None

        return None

    def _find_by_hint_text(self, vq, ctx: WindowContext) -> ElementBox | None:
        """通过 OCR 占位文本定位输入框锚点"""
        hwnd = ctx.hwnd
        if hwnd is None and ctx.star is not None:
            hwnd = ctx.star.hwnd
        if hwnd is None:
            return None

        # 取窗口 rect 用于坐标换算
        try:
            import win32gui
            rect = win32gui.GetWindowRect(hwnd)
        except Exception:
            return None

        if not rect:
            return None

        win_left, win_top = rect[0], rect[1]

        # 截图
        screenshot_path = self._capture(hwnd)
        if screenshot_path is None:
            return None

        # OCR 识别
        lines = self._ocr_lines(screenshot_path, vq)
        if not lines:
            return None

        # 查找含 hint_text 的行
        for line in lines:
            text = getattr(line, "text", "") or ""
            if vq.hint_text in text:
                x_center = getattr(line, "x_center", 0.0)
                y_center = getattr(line, "y_center", 0.0)
                width = getattr(line, "width", 0.0)
                height = getattr(line, "height", 0.0)

                # OCR 坐标是相对截图图像的, 需加窗口左上角偏移转为屏幕坐标
                screen_x = int(win_left + x_center)
                # y 方向偏移: 文本框中心下方若干像素为输入区
                screen_y = int(win_top + y_center + self._INPUT_Y_OFFSET)

                return ElementBox(
                    x=screen_x,
                    y=screen_y,
                    width=int(width) if width > 0 else 1,
                    height=int(height) if height > 0 else 1,
                    confidence=0.75,
                    source="visual",
                    meta={
                        "hint_text": vq.hint_text,
                        "matched_text": text,
                        "ocr_confidence": getattr(line, "confidence", 0.0),
                    },
                )

        return None

    def _capture(self, hwnd: int) -> str | None:
        """截取窗口图像, 返回文件路径; 失败返回 None"""
        # 优先用 OCRGazer.capture_window
        try:
            from star_core.ocr_gazer import OCRGazer
            ocr = OCRGazer()
            path = ocr.capture_window(hwnd)
            if path:
                return path
        except Exception:
            pass

        # 兜底: PIL ImageGrab
        try:
            import win32gui
            from PIL import ImageGrab
            rect = win32gui.GetWindowRect(hwnd)
            img = ImageGrab.grab(bbox=rect, all_screens=True)
            import os
            import tempfile
            import time
            tmp_dir = os.path.join(tempfile.gettempdir(), "star_locators")
            os.makedirs(tmp_dir, exist_ok=True)
            path = os.path.join(tmp_dir, f"visual_{hwnd}_{int(time.time())}.png")
            img.save(path)
            return path
        except Exception:
            return None

    def _ocr_lines(self, image_path: str, vq):
        """对截图执行 OCR, 返回行列表; 失败返回空列表"""
        try:
            from star_core.ocr_gazer import OCRGazer
            ocr = OCRGazer(min_confidence=vq.ocr_min_confidence)
            region = vq.region if vq.region != "full_window" else None
            result = ocr.recognize_text(image_path, region=region)
            return result.lines
        except Exception:
            return []
