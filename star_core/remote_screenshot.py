"""
星影者（RemoteScreenshotManager）- 远程截图调度器

自适应间隔截图：无变化时间隔翻倍，降低带宽占用
"""

import os
import time
import tempfile
from typing import Optional, Dict
from dataclasses import dataclass, field

from star_core.observatory import Observatory


@dataclass
class WindowScreenshotState:
    hwnd: int
    last_screenshot_path: str = ""
    last_screenshot_time: float = 0.0
    last_hash: int = 0
    current_interval: int = 60
    min_interval: int = 60
    max_interval: int = 1800
    no_change_count: int = 0


class RemoteScreenshotManager:
    def __init__(self, observatory: Optional[Observatory] = None):
        self.observatory = observatory or Observatory()
        self._states: Dict[int, WindowScreenshotState] = {}
        self._temp_dir = os.path.join(tempfile.gettempdir(), "star_remote")
        os.makedirs(self._temp_dir, exist_ok=True)

    def get_state(self, hwnd: int) -> WindowScreenshotState:
        if hwnd not in self._states:
            self._states[hwnd] = WindowScreenshotState(hwnd=hwnd)
        return self._states[hwnd]

    def _compute_hash(self, img_path: str) -> int:
        try:
            from PIL import Image
            img = Image.open(img_path).convert("L").resize((32, 32))
            pixels = list(img.getdata())
            avg = sum(pixels) / len(pixels)
            h = 0
            for p in pixels:
                h = (h << 1) | (1 if p > avg else 0)
            return h
        except Exception:
            return 0

    def should_refresh(self, hwnd: int) -> bool:
        state = self.get_state(hwnd)
        if not state.last_screenshot_path:
            return True
        elapsed = time.time() - state.last_screenshot_time
        return elapsed >= state.current_interval

    def capture(self, hwnd: int, force: bool = False) -> Optional[str]:
        state = self.get_state(hwnd)

        if not force and not self.should_refresh(hwnd):
            return state.last_screenshot_path or None

        try:
            from star_core.ocr_gazer import OCRGazer
            gazer = OCRGazer()
            save_path = os.path.join(
                self._temp_dir,
                "remote_%d_%d.jpg" % (hwnd, int(time.time()))
            )
            img_path = gazer.capture_window(hwnd, save_path=save_path)
            if not img_path:
                return state.last_screenshot_path or None
        except Exception:
            return state.last_screenshot_path or None

        new_hash = self._compute_hash(img_path)
        if state.last_screenshot_path and new_hash == state.last_hash:
            state.no_change_count += 1
            state.current_interval = min(
                state.current_interval * 2,
                state.max_interval
            )
        else:
            state.no_change_count = 0
            state.current_interval = state.min_interval
            if state.last_screenshot_path and os.path.exists(state.last_screenshot_path):
                try:
                    os.remove(state.last_screenshot_path)
                except Exception:
                    pass

        state.last_hash = new_hash
        state.last_screenshot_path = img_path
        state.last_screenshot_time = time.time()

        return img_path

    def get_status(self, hwnd: int) -> dict:
        state = self.get_state(hwnd)
        return {
            'hwnd': hwnd,
            'last_screenshot_time': state.last_screenshot_time,
            'current_interval': state.current_interval,
            'no_change_count': state.no_change_count,
            'last_screenshot_path': state.last_screenshot_path,
        }
