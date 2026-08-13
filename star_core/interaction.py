"""
交互动作原语 (InteractionSession) - 高层交互能力封装

将"定位 -> 点击 -> 注入 -> 发送"和"停止当前生成"封装为统一动作原语，
供 StarEmissary 调用。支持桌面应用 (win32) 和浏览器应用 (CDP) 两种模式。

设计要点:
- locators 包的 import 延迟到方法内部, 与 Task A 并行开发解耦
- 桌面操作 (点击/剪贴板/按键) 独立实现, 不 import star_emissary 以免循环依赖
- 全部方法 try/except 包裹, 失败返回空串/False 带 reason, 不抛出
"""

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from loguru import logger

if TYPE_CHECKING:
    from star_core.locators.base import (
        ElementBox as _RealElementBox,
        LocatorChain as _RealLocatorChain,
        LocatorTarget as _RealLocatorTarget,
        WindowContext as _RealWindowContext,
    )
    from star_core.cdp_bridge import CDPBridge as _CDPBridge
    from star_core.ocr_gazer import OCRGazer as _OCRGazer


# ===== Fallback data type definitions =====
# Used at runtime; structurally compatible with star_core.locators.base.
# When locators package is available, LocatorChain works with these via duck typing.

@dataclass
class UIAQuery:
    """UI Automation query parameters."""
    control_type: Optional[str] = None
    automation_id: Optional[str] = None
    name_regex: Optional[str] = None
    depth_limit: int = 8


@dataclass
class VisualQuery:
    """Visual/OCR query parameters."""
    hint_text: Optional[str] = None
    template: Optional[str] = None
    region: str = "full_window"
    ocr_min_confidence: float = 0.5


@dataclass
class RatioQuery:
    """Coordinate ratio query parameters."""
    x_ratio: float = 0.5
    y_ratio: float = 0.92


@dataclass
class CDPQuery:
    """CDP DOM query parameters."""
    selector: Optional[str] = None
    text_contains: Optional[str] = None
    role: Optional[str] = None


@dataclass
class LocatorTarget:
    """A single locator request: what to find."""
    kind: str = ""
    uia: Optional[UIAQuery] = None
    visual: Optional[VisualQuery] = None
    ratio: Optional[RatioQuery] = None
    cdp: Optional[CDPQuery] = None


@dataclass
class ElementBox:
    """Locator result: screen geometry of a hit element."""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    confidence: float = 0.0
    source: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class WindowContext:
    """Window/page context for locator execution."""
    hwnd: Optional[int] = None
    star: Any = None
    cdptab: Optional[dict] = None
    min_confidence: float = 0.3


# ===== Result types =====

@dataclass
class SubmitResult:
    """Result of a submit action."""
    ok: bool
    source: str = ""
    reason: str = ""


@dataclass
class StopResult:
    """Result of a stop action."""
    ok: bool
    via: str = ""
    reason: str = ""


# ===== Config =====

@dataclass
class InteractionConfig:
    """Parsed from yaml interaction section."""
    locators: list[str] = field(default_factory=list)
    input: LocatorTarget = field(default_factory=LocatorTarget)
    send_on: str = "Enter"
    send_button: Optional[LocatorTarget] = None
    stop: Optional[LocatorTarget] = None
    stop_fallback_keys: list[str] = field(default_factory=list)
    output: list[dict] = field(default_factory=list)


def _normalize_cdp_key(key: str) -> str:
    """Normalize desktop key name to CDP key name."""
    mapping = {
        "Enter": "Enter",
        "Esc": "Escape",
        "Ctrl_C": "Escape",
    }
    return mapping.get(key, key)


class InteractionSession:
    """One agent's interaction capabilities, held by StarEmissary."""

    def __init__(
        self,
        config: Optional[InteractionConfig] = None,
        bridge: Any = None,
        ocr: Any = None,
    ):
        """
        Initialize interaction session.

        Args:
            config: Interaction config parsed from yaml. None = no interaction.
            bridge: CDPBridge instance for browser agents. None for desktop.
            ocr: OCRGazer instance for visual output reading. None to skip OCR.
        """
        self.config = config
        self.bridge = bridge
        self.ocr = ocr
        self._chain: Any = None
        self._chain_built: bool = False
        self._chain_error: Optional[str] = None

    # ----- Chain management -----

    def _get_chain(self) -> Any:
        """Lazily build LocatorChain from config. Returns chain or None."""
        if self._chain_built:
            return self._chain
        self._chain_built = True
        if self.config is None:
            self._chain_error = "no_config"
            return None
        try:
            from star_core.locators import default_registry, LocatorChain
            registry = default_registry()
            targets: dict[str, LocatorTarget] = {"input": self.config.input}
            if self.config.send_button:
                targets["send_button"] = self.config.send_button
            if self.config.stop:
                targets["stop_button"] = self.config.stop
            self._chain = LocatorChain(
                targets=targets,
                order=self.config.locators,
                registry=registry,
            )
            return self._chain
        except ImportError:
            self._chain_error = "locators_unavailable"
            logger.debug("[Interaction] locators package unavailable")
            return None
        except Exception as e:
            self._chain_error = str(e)
            logger.debug(f"[Interaction] chain build failed: {e}")
            return None

    def locate(self, kind: str, ctx: WindowContext) -> Optional[ElementBox]:
        """Locate an element by kind. Returns ElementBox or None."""
        chain = self._get_chain()
        if chain is None:
            return None
        try:
            return chain.locate(kind, ctx)
        except Exception as e:
            logger.debug(f"[Interaction] locate({kind}) failed: {e}")
            return None

    def _build_ctx(
        self,
        star: Any = None,
        hwnd: Optional[int] = None,
        cdptab: Optional[dict] = None,
    ) -> WindowContext:
        """Build WindowContext from available info."""
        return WindowContext(
            hwnd=hwnd,
            star=star,
            cdptab=cdptab,
            min_confidence=0.3,
        )

    # ----- Desktop operations (independent, not importing star_emissary) -----

    def _desktop_click(self, box: ElementBox, hwnd: int) -> bool:
        """Click at ElementBox center using win32 API."""
        try:
            import win32api
            import win32con
            import win32gui

            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            time.sleep(0.15)

            cx = box.x + box.width // 2
            cy = box.y + box.height // 2

            win32api.SetCursorPos((cx, cy))
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, cx, cy, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, cx, cy, 0, 0)
            time.sleep(0.1)
            return True
        except Exception as e:
            logger.debug(f"[Interaction] desktop_click failed: {e}")
            return False

    def _desktop_paste(self, text: str) -> bool:
        """Paste text via clipboard + Ctrl+V."""
        try:
            import win32api
            import win32con
            import pyperclip

            backup = pyperclip.paste()
            try:
                pyperclip.copy(text)
                time.sleep(0.05)
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(ord("V"), 0, 0, 0)
                time.sleep(0.05)
                win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.02)
                win32api.keybd_event(
                    win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0
                )
                time.sleep(0.1)
                return True
            finally:
                pyperclip.copy(backup)
        except Exception as e:
            logger.debug(f"[Interaction] desktop_paste failed: {e}")
            return False

    def _desktop_press_key(self, key: str) -> bool:
        """Press a key. Supports Enter, Esc, Ctrl_C."""
        try:
            import win32api
            import win32con

            key_map = {
                "Enter": win32con.VK_RETURN,
                "Esc": win32con.VK_ESCAPE,
            }

            if key in key_map:
                vk = key_map[key]
                win32api.keybd_event(vk, 0, 0, 0)
                time.sleep(0.05)
                win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.1)
                return True
            elif key == "Ctrl_C":
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(ord("C"), 0, 0, 0)
                time.sleep(0.05)
                win32api.keybd_event(ord("C"), 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.02)
                win32api.keybd_event(
                    win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0
                )
                time.sleep(0.1)
                return True
            return False
        except Exception as e:
            logger.debug(f"[Interaction] desktop_press_key({key}) failed: {e}")
            return False

    # ----- Browser operations -----

    def _browser_set_value(self, tab: dict, selector: str, text: str) -> bool:
        """Set input value via CDP bridge."""
        try:
            if self.bridge is None:
                return False
            return self.bridge.set_value(tab, selector, text)
        except Exception:
            return False

    def _browser_click_selector(self, tab: dict, selector: str) -> bool:
        """Click element via CDP bridge."""
        try:
            if self.bridge is None:
                return False
            return self.bridge.click_selector(tab, selector)
        except Exception:
            return False

    def _browser_send_key(self, tab: dict, key: str) -> bool:
        """Send key via CDP bridge."""
        try:
            if self.bridge is None:
                return False
            return self.bridge.send_key(tab, key)
        except Exception:
            return False

    def _browser_get_text(self, tab: dict, selector: str) -> str:
        """Get text via CDP bridge."""
        try:
            if self.bridge is None:
                return ""
            return self.bridge.get_text(tab, selector) or ""
        except Exception:
            return ""

    def _browser_find_by_text(self, tab: dict, text: str) -> Optional[str]:
        """Find element by text, return selector or None."""
        try:
            if self.bridge is None:
                return None
            result = self.bridge.find_by_text(tab, text)
            if result:
                if isinstance(result, dict):
                    return result.get("selector")
                return str(result)
            return None
        except Exception:
            return None

    # ----- Helper: resolve hwnd from ctx -----

    @staticmethod
    def _resolve_hwnd(ctx: WindowContext) -> Optional[int]:
        """Get hwnd from context, falling back to star.hwnd."""
        if ctx.hwnd is not None:
            return ctx.hwnd
        if ctx.star is not None:
            return getattr(ctx.star, "hwnd", None)
        return None

    # ----- Public API: submit -----

    def submit(self, prompt: str, ctx: WindowContext) -> SubmitResult:
        """
        Submit prompt: locate input -> focus/click -> inject text -> trigger send.

        Args:
            prompt: Text to submit.
            ctx: Window context for locator execution.

        Returns:
            SubmitResult with ok, source, and reason.
        """
        if self.config is None:
            return SubmitResult(ok=False, reason="no_config")

        is_browser = ctx.cdptab is not None

        if is_browser:
            return self._submit_browser(prompt, ctx)
        return self._submit_desktop(prompt, ctx)

    def _submit_desktop(self, prompt: str, ctx: WindowContext) -> SubmitResult:
        """Desktop submit via locator chain + win32."""
        chain = self._get_chain()
        if chain is None:
            return SubmitResult(
                ok=False,
                reason=self._chain_error or "locators_unavailable",
            )

        try:
            box = chain.locate("input", ctx)
        except Exception as e:
            return SubmitResult(ok=False, reason="locator_exception")

        if box is None:
            return SubmitResult(ok=False, reason="input_locator_miss")

        hwnd = self._resolve_hwnd(ctx)
        if hwnd is None:
            return SubmitResult(ok=False, reason="no_hwnd")

        if not self._desktop_click(box, hwnd):
            return SubmitResult(ok=False, reason="click_failed")

        if not self._desktop_paste(prompt):
            return SubmitResult(ok=False, reason="paste_failed")

        if self.config.send_on == "Enter":
            self._desktop_press_key("Enter")
        elif self.config.send_on == "click":
            try:
                send_box = chain.locate("send_button", ctx)
                if send_box:
                    self._desktop_click(send_box, hwnd)
            except Exception:
                pass

        return SubmitResult(ok=True, source=box.source)

    def _submit_browser(self, prompt: str, ctx: WindowContext) -> SubmitResult:
        """Browser submit via CDP."""
        tab = ctx.cdptab
        if tab is None:
            return SubmitResult(ok=False, reason="no_cdptab")

        if self.bridge is None:
            return SubmitResult(ok=False, reason="no_bridge")

        input_target = self.config.input
        selector = None
        if input_target and input_target.cdp:
            selector = input_target.cdp.selector

        if not selector:
            return SubmitResult(ok=False, reason="no_input_selector")

        if not self._browser_set_value(tab, selector, prompt):
            return SubmitResult(ok=False, reason="set_value_failed")

        if self.config.send_on == "Enter":
            self._browser_send_key(tab, "Enter")
        elif self.config.send_on == "click":
            if self.config.send_button and self.config.send_button.cdp:
                btn_sel = self.config.send_button.cdp.selector
                if btn_sel:
                    self._browser_click_selector(tab, btn_sel)

        return SubmitResult(ok=True, source="cdp")

    # ----- Public API: stop_current -----

    def stop_current(self, ctx: WindowContext) -> StopResult:
        """
        Stop current generation: button priority, key fallback.

        Args:
            ctx: Window context for locator execution.

        Returns:
            StopResult with ok, via, and reason.
        """
        if self.config is None:
            return StopResult(ok=False, reason="no_config")

        is_browser = ctx.cdptab is not None

        # Try stop button first
        if self.config.stop is not None:
            if is_browser:
                stop_result = self._stop_browser(ctx)
                if stop_result.ok:
                    return stop_result
            else:
                stop_result = self._stop_desktop(ctx)
                if stop_result.ok:
                    return stop_result

        # Fallback: keys
        for key in self.config.stop_fallback_keys:
            if is_browser:
                if self._browser_send_key(ctx.cdptab, _normalize_cdp_key(key)):
                    return StopResult(ok=True, via="keys")
            else:
                hwnd = self._resolve_hwnd(ctx)
                if hwnd is not None and self._desktop_press_key(key):
                    return StopResult(ok=True, via="keys")

        return StopResult(ok=False, reason="all_methods_failed")

    def _stop_desktop(self, ctx: WindowContext) -> StopResult:
        """Desktop stop: locate stop button and click."""
        chain = self._get_chain()
        if chain is None:
            return StopResult(
                ok=False,
                reason=self._chain_error or "locators_unavailable",
            )

        try:
            box = chain.locate("stop_button", ctx)
        except Exception:
            return StopResult(ok=False, reason="locator_exception")

        if box is None:
            return StopResult(ok=False, reason="stop_button_miss")

        hwnd = self._resolve_hwnd(ctx)
        if hwnd is None:
            return StopResult(ok=False, reason="no_hwnd")

        if self._desktop_click(box, hwnd):
            return StopResult(ok=True, via="button")
        return StopResult(ok=False, reason="click_failed")

    def _stop_browser(self, ctx: WindowContext) -> StopResult:
        """Browser stop: find and click stop button via CDP."""
        tab = ctx.cdptab
        if tab is None or self.bridge is None:
            return StopResult(ok=False, reason="no_bridge")

        stop_target = self.config.stop
        if stop_target and stop_target.cdp:
            if stop_target.cdp.text_contains:
                selector = self._browser_find_by_text(
                    tab, stop_target.cdp.text_contains
                )
                if selector:
                    if self._browser_click_selector(tab, selector):
                        return StopResult(ok=True, via="button")
            if stop_target.cdp.selector:
                if self._browser_click_selector(tab, stop_target.cdp.selector):
                    return StopResult(ok=True, via="button")

        return StopResult(ok=False, reason="stop_button_miss")

    # ----- Public API: read_output -----

    def read_output(self, ctx: WindowContext) -> str:
        """
        Read output: iterate output chain (log/ocr/cdp).

        Args:
            ctx: Window context.

        Returns:
            Output text, or empty string if all methods fail.
        """
        if self.config is None or not self.config.output:
            return ""

        for item in self.config.output:
            otype = item.get("type", "")
            try:
                if otype == "log":
                    text = self._read_log(item, ctx)
                    if text:
                        return text
                elif otype == "ocr":
                    text = self._read_ocr(item, ctx)
                    if text:
                        return text
                elif otype == "cdp":
                    text = self._read_cdp(item, ctx)
                    if text:
                        return text
            except Exception as e:
                logger.debug(f"[Interaction] read_output({otype}) failed: {e}")
                continue

        return ""

    def _read_log(self, item: dict, ctx: WindowContext) -> str:
        """Read output from log files."""
        try:
            from star_core.log_reader import get_reader

            reader = get_reader()
            star = ctx.star
            if star is None:
                return ""
            log_files = reader.find_logs_for_star(star)
            if log_files:
                result = reader.read_recent(log_files, max_lines=50)
                if result.latest_text:
                    return result.latest_text
        except Exception as e:
            logger.debug(f"[Interaction] log read failed: {e}")
        return ""

    def _read_ocr(self, item: dict, ctx: WindowContext) -> str:
        """Read output via OCR."""
        try:
            if self.ocr is None:
                return ""
            star = ctx.star
            if star is None:
                return ""
            region = item.get("region", "center_chat")
            result = self.ocr.gaze_region(star, region)
            if result and hasattr(result, "text"):
                return result.text
        except Exception as e:
            logger.debug(f"[Interaction] ocr read failed: {e}")
        return ""

    def _read_cdp(self, item: dict, ctx: WindowContext) -> str:
        """Read output via CDP."""
        try:
            tab = ctx.cdptab
            if tab is None or self.bridge is None:
                return ""
            selector = item.get("selector", "")
            if selector:
                return self._browser_get_text(tab, selector)
        except Exception as e:
            logger.debug(f"[Interaction] cdp read failed: {e}")
        return ""
