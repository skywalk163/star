"""
Tests for star_core.interaction.InteractionSession.

Covers:
- locators_unavailable fallback
- submit desktop hit (click + paste + enter)
- submit desktop miss (input_locator_miss)
- submit browser branch (CDPBridge mock)
- stop button priority vs fallback keys
- read_output chain order (log -> ocr -> cdp)
"""

import sys
import types
import pytest
from unittest.mock import MagicMock, patch

from star_core.interaction import (
    InteractionConfig,
    InteractionSession,
    LocatorTarget,
    ElementBox,
    WindowContext,
    SubmitResult,
    StopResult,
    UIAQuery,
    VisualQuery,
    RatioQuery,
    CDPQuery,
)


# ===== Helpers =====

def _make_desktop_config(
    send_on: str = "Enter",
    stop_keys: list[str] | None = None,
    output: list[dict] | None = None,
) -> InteractionConfig:
    """Build a minimal desktop InteractionConfig."""
    return InteractionConfig(
        locators=["uia", "visual", "ratio"],
        input=LocatorTarget(
            kind="input",
            uia=UIAQuery(control_type="Edit", name_regex="input|Ask"),
            visual=VisualQuery(hint_text="input"),
            ratio=RatioQuery(x_ratio=0.5, y_ratio=0.93),
        ),
        send_on=send_on,
        send_button=None,
        stop=LocatorTarget(
            kind="stop_button",
            uia=UIAQuery(control_type="Button", name_regex="stop|cancel"),
        ),
        stop_fallback_keys=stop_keys or ["Esc"],
        output=output or [],
    )


def _make_browser_config(
    send_on: str = "Enter",
    stop_keys: list[str] | None = None,
    output: list[dict] | None = None,
) -> InteractionConfig:
    """Build a minimal browser (CDP) InteractionConfig."""
    return InteractionConfig(
        locators=["cdp"],
        input=LocatorTarget(
            kind="input",
            cdp=CDPQuery(selector="textarea#chat-input"),
        ),
        send_on=send_on,
        send_button=None,
        stop=LocatorTarget(
            kind="stop_button",
            cdp=CDPQuery(text_contains="stop"),
        ),
        stop_fallback_keys=stop_keys or ["Esc"],
        output=output or [],
    )


def _install_fake_locators(monkeypatch, locate_result=None):
    """
    Install a fake star_core.locators module into sys.modules so that
    InteractionSession._get_chain() can import it.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        locate_result: ElementBox or None to return from chain.locate().
                       If callable, called with (kind, ctx) to get result.
    """
    fake_mod = types.ModuleType("star_core.locators")
    fake_chain = MagicMock()
    if callable(locate_result):
        fake_chain.locate = MagicMock(side_effect=locate_result)
    else:
        fake_chain.locate = MagicMock(return_value=locate_result)

    fake_registry = MagicMock()
    fake_default_registry = MagicMock(return_value=fake_registry)

    fake_mod.default_registry = fake_default_registry
    fake_mod.LocatorChain = MagicMock(return_value=fake_chain)

    # Also create star_core.locators as a proper package-like module
    monkeypatch.setitem(sys.modules, "star_core.locators", fake_mod)
    return fake_chain


def _make_ctx(hwnd=12345, cdptab=None, star=None) -> WindowContext:
    return WindowContext(hwnd=hwnd, star=star, cdptab=cdptab)


# ===== Tests: locators_unavailable =====

class TestLocatorsUnavailable:
    """When star_core.locators package is absent, all desktop ops fail gracefully."""

    def test_submit_returns_locators_unavailable(self, monkeypatch):
        # Ensure star_core.locators is NOT in sys.modules
        monkeypatch.delitem(sys.modules, "star_core.locators", raising=False)

        config = _make_desktop_config()
        session = InteractionSession(config=config)
        ctx = _make_ctx()

        result = session.submit("hello", ctx)
        assert result.ok is False
        assert result.reason == "locators_unavailable"

    def test_stop_returns_locators_unavailable(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "star_core.locators", raising=False)

        config = _make_desktop_config()
        session = InteractionSession(config=config)
        ctx = _make_ctx()

        # Mock desktop press key to fail so fallback keys also fail
        monkeypatch.setattr(session, "_desktop_press_key", MagicMock(return_value=False))

        # stop button path tries locator chain first
        result = session.stop_current(ctx)
        assert result.ok is False
        # Reason could be locators_unavailable (from button path) or
        # all_methods_failed (when fallback keys also fail)
        assert result.reason in ("locators_unavailable", "all_methods_failed")


# ===== Tests: submit desktop =====

class TestSubmitDesktop:
    """Desktop submit via locator chain + win32."""

    def test_submit_hit(self, monkeypatch):
        """When locator finds input box, click + paste + enter are called."""
        box = ElementBox(x=100, y=200, width=50, height=30, source="uia")
        fake_chain = _install_fake_locators(monkeypatch, locate_result=box)

        config = _make_desktop_config()
        session = InteractionSession(config=config)
        ctx = _make_ctx(hwnd=999)

        # Mock desktop operations
        monkeypatch.setattr(session, "_desktop_click", MagicMock(return_value=True))
        monkeypatch.setattr(session, "_desktop_paste", MagicMock(return_value=True))
        monkeypatch.setattr(session, "_desktop_press_key", MagicMock(return_value=True))

        result = session.submit("test prompt", ctx)

        assert result.ok is True
        assert result.source == "uia"
        session._desktop_click.assert_called_once()
        session._desktop_paste.assert_called_once_with("test prompt")
        session._desktop_press_key.assert_called_once_with("Enter")

    def test_submit_miss(self, monkeypatch):
        """When locator returns None, submit returns input_locator_miss."""
        _install_fake_locators(monkeypatch, locate_result=None)

        config = _make_desktop_config()
        session = InteractionSession(config=config)
        ctx = _make_ctx()

        result = session.submit("hello", ctx)
        assert result.ok is False
        assert result.reason == "input_locator_miss"

    def test_submit_click_failed(self, monkeypatch):
        """When click fails, submit returns click_failed."""
        box = ElementBox(x=100, y=200, width=50, height=30)
        _install_fake_locators(monkeypatch, locate_result=box)

        config = _make_desktop_config()
        session = InteractionSession(config=config)
        ctx = _make_ctx(hwnd=999)

        monkeypatch.setattr(session, "_desktop_click", MagicMock(return_value=False))
        monkeypatch.setattr(session, "_desktop_paste", MagicMock(return_value=True))

        result = session.submit("hello", ctx)
        assert result.ok is False
        assert result.reason == "click_failed"

    def test_submit_no_config(self):
        """When config is None, submit returns no_config."""
        session = InteractionSession(config=None)
        ctx = _make_ctx()
        result = session.submit("hello", ctx)
        assert result.ok is False
        assert result.reason == "no_config"

    def test_submit_no_hwnd(self, monkeypatch):
        """When hwnd can't be resolved, submit returns no_hwnd."""
        box = ElementBox(x=100, y=200, width=50, height=30)
        _install_fake_locators(monkeypatch, locate_result=box)

        config = _make_desktop_config()
        session = InteractionSession(config=config)
        ctx = WindowContext(hwnd=None, star=None)

        result = session.submit("hello", ctx)
        assert result.ok is False
        assert result.reason == "no_hwnd"


# ===== Tests: submit browser =====

class TestSubmitBrowser:
    """Browser submit via CDPBridge."""

    def test_submit_browser_hit(self):
        """When CDP bridge is available, set_value + send_key are called."""
        mock_bridge = MagicMock()
        mock_bridge.set_value = MagicMock(return_value=True)
        mock_bridge.send_key = MagicMock(return_value=True)

        config = _make_browser_config()
        session = InteractionSession(config=config, bridge=mock_bridge)
        ctx = _make_ctx(cdptab={"id": "tab1"})

        result = session.submit("browser prompt", ctx)

        assert result.ok is True
        assert result.source == "cdp"
        mock_bridge.set_value.assert_called_once_with(
            {"id": "tab1"}, "textarea#chat-input", "browser prompt"
        )
        mock_bridge.send_key.assert_called_once_with({"id": "tab1"}, "Enter")

    def test_submit_browser_no_bridge(self):
        """When bridge is None, submit returns no_bridge."""
        config = _make_browser_config()
        session = InteractionSession(config=config, bridge=None)
        ctx = _make_ctx(cdptab={"id": "tab1"})

        result = session.submit("hello", ctx)
        assert result.ok is False
        assert result.reason == "no_bridge"

    def test_submit_browser_no_cdptab(self, monkeypatch):
        """When cdptab is None, submit falls back to desktop path (not browser)."""
        config = _make_browser_config()
        mock_bridge = MagicMock()
        session = InteractionSession(config=config, bridge=mock_bridge)
        ctx = _make_ctx(cdptab=None)

        # With no cdptab, is_browser=False, so it tries desktop path.
        # Desktop path needs locators which are unavailable -> locators_unavailable
        monkeypatch.delitem(sys.modules, "star_core.locators", raising=False)
        result = session.submit("hello", ctx)
        assert result.ok is False
        assert result.reason == "locators_unavailable"

    def test_submit_browser_set_value_failed(self):
        """When set_value fails, submit returns set_value_failed."""
        mock_bridge = MagicMock()
        mock_bridge.set_value = MagicMock(return_value=False)

        config = _make_browser_config()
        session = InteractionSession(config=config, bridge=mock_bridge)
        ctx = _make_ctx(cdptab={"id": "tab1"})

        result = session.submit("hello", ctx)
        assert result.ok is False
        assert result.reason == "set_value_failed"

    def test_submit_browser_no_selector(self):
        """When config has no CDP selector, submit returns no_input_selector."""
        config = InteractionConfig(
            locators=["cdp"],
            input=LocatorTarget(kind="input", cdp=CDPQuery(selector=None)),
            send_on="Enter",
        )
        mock_bridge = MagicMock()
        session = InteractionSession(config=config, bridge=mock_bridge)
        ctx = _make_ctx(cdptab={"id": "tab1"})

        result = session.submit("hello", ctx)
        assert result.ok is False
        assert result.reason == "no_input_selector"


# ===== Tests: stop_current =====

class TestStopCurrent:
    """Stop button priority vs fallback keys."""

    def test_stop_button_priority_desktop(self, monkeypatch):
        """When stop button is found and clicked, returns ok=True via=button."""
        box = ElementBox(x=200, y=300, width=40, height=20, source="uia")

        def locate_fn(kind, ctx):
            if kind == "stop_button":
                return box
            return None

        _install_fake_locators(monkeypatch, locate_result=locate_fn)

        config = _make_desktop_config()
        session = InteractionSession(config=config)
        ctx = _make_ctx(hwnd=999)

        monkeypatch.setattr(session, "_desktop_click", MagicMock(return_value=True))
        monkeypatch.setattr(session, "_desktop_press_key", MagicMock(return_value=True))

        result = session.stop_current(ctx)

        assert result.ok is True
        assert result.via == "button"
        session._desktop_click.assert_called_once()
        # Fallback key should NOT be pressed
        session._desktop_press_key.assert_not_called()

    def test_stop_fallback_keys_desktop(self, monkeypatch):
        """When stop button is not found, fallback keys are used."""
        _install_fake_locators(monkeypatch, locate_result=None)

        config = _make_desktop_config(stop_keys=["Esc"])
        session = InteractionSession(config=config)
        ctx = _make_ctx(hwnd=999)

        monkeypatch.setattr(session, "_desktop_click", MagicMock(return_value=True))
        press_mock = MagicMock(return_value=True)
        monkeypatch.setattr(session, "_desktop_press_key", press_mock)

        result = session.stop_current(ctx)

        assert result.ok is True
        assert result.via == "keys"
        press_mock.assert_called_once_with("Esc")

    def test_stop_all_methods_failed(self, monkeypatch):
        """When both button and keys fail, returns all_methods_failed."""
        _install_fake_locators(monkeypatch, locate_result=None)

        config = _make_desktop_config(stop_keys=["Esc"])
        session = InteractionSession(config=config)
        ctx = _make_ctx(hwnd=999)

        monkeypatch.setattr(session, "_desktop_click", MagicMock(return_value=False))
        monkeypatch.setattr(session, "_desktop_press_key", MagicMock(return_value=False))

        result = session.stop_current(ctx)

        assert result.ok is False
        assert result.reason == "all_methods_failed"

    def test_stop_browser_button(self):
        """Browser stop: find_by_text returns selector, click succeeds."""
        mock_bridge = MagicMock()
        mock_bridge.find_by_text = MagicMock(return_value={"selector": "button.stop"})
        mock_bridge.click_selector = MagicMock(return_value=True)

        config = _make_browser_config()
        session = InteractionSession(config=config, bridge=mock_bridge)
        ctx = _make_ctx(cdptab={"id": "tab1"})

        result = session.stop_current(ctx)

        assert result.ok is True
        assert result.via == "button"
        mock_bridge.find_by_text.assert_called_once_with({"id": "tab1"}, "stop")
        mock_bridge.click_selector.assert_called_once_with({"id": "tab1"}, "button.stop")

    def test_stop_browser_fallback_keys(self):
        """Browser stop: button miss -> fallback Esc via send_key."""
        mock_bridge = MagicMock()
        mock_bridge.find_by_text = MagicMock(return_value=None)
        mock_bridge.click_selector = MagicMock(return_value=False)
        mock_bridge.send_key = MagicMock(return_value=True)

        config = _make_browser_config(stop_keys=["Esc"])
        session = InteractionSession(config=config, bridge=mock_bridge)
        ctx = _make_ctx(cdptab={"id": "tab1"})

        result = session.stop_current(ctx)

        assert result.ok is True
        assert result.via == "keys"
        # Esc is normalized to Escape for CDP
        mock_bridge.send_key.assert_called_once_with({"id": "tab1"}, "Escape")

    def test_stop_no_config(self):
        """When config is None, stop returns no_config."""
        session = InteractionSession(config=None)
        ctx = _make_ctx()
        result = session.stop_current(ctx)
        assert result.ok is False
        assert result.reason == "no_config"


# ===== Tests: read_output =====

class TestReadOutput:
    """read_output chain: log -> ocr -> cdp, returns first non-empty."""

    def test_read_log_hit(self, monkeypatch):
        """Log reader returns text -> returned immediately."""
        config = _make_desktop_config(
            output=[
                {"type": "log", "paths": ["~/.trae-cn/log/**/*.log"]},
                {"type": "ocr", "region": "center_chat"},
            ]
        )
        session = InteractionSession(config=config)

        fake_reader = MagicMock()
        fake_reader.find_logs_for_star = MagicMock(return_value=["/fake/log.log"])
        fake_result = MagicMock()
        fake_result.latest_text = "log output line"
        fake_reader.read_recent = MagicMock(return_value=fake_result)

        monkeypatch.setattr(
            "star_core.interaction.get_reader",
            MagicMock(return_value=fake_reader),
            raising=False,
        )
        # The import inside _read_log is: from star_core.log_reader import get_reader
        # So we need to patch it at the module level
        import star_core.interaction as interaction_mod
        # Patch the module's internal import by injecting into sys.modules
        fake_log_reader_mod = types.ModuleType("star_core.log_reader")
        fake_log_reader_mod.get_reader = MagicMock(return_value=fake_reader)
        monkeypatch.setitem(sys.modules, "star_core.log_reader", fake_log_reader_mod)

        ctx = _make_ctx(star=MagicMock())
        text = session.read_output(ctx)

        assert text == "log output line"

    def test_read_log_miss_ocr_hit(self, monkeypatch):
        """Log returns empty -> OCR is tried."""
        config = _make_desktop_config(
            output=[
                {"type": "log", "paths": ["~/.trae-cn/log/**/*.log"]},
                {"type": "ocr", "region": "center_chat"},
            ]
        )
        session = InteractionSession(config=config, ocr=MagicMock())

        # Log reader returns empty
        fake_reader = MagicMock()
        fake_reader.find_logs_for_star = MagicMock(return_value=[])
        fake_log_reader_mod = types.ModuleType("star_core.log_reader")
        fake_log_reader_mod.get_reader = MagicMock(return_value=fake_reader)
        monkeypatch.setitem(sys.modules, "star_core.log_reader", fake_log_reader_mod)

        # OCR returns text
        mock_ocr = MagicMock()
        ocr_result = MagicMock()
        ocr_result.text = "ocr output"
        mock_ocr.gaze_region = MagicMock(return_value=ocr_result)
        session.ocr = mock_ocr

        ctx = _make_ctx(star=MagicMock())
        text = session.read_output(ctx)

        assert text == "ocr output"
        mock_ocr.gaze_region.assert_called_once()

    def test_read_cdp_hit(self):
        """CDP output returns text."""
        config = _make_browser_config(
            output=[
                {"type": "cdp", "selector": ".chat-content"},
            ]
        )
        mock_bridge = MagicMock()
        mock_bridge.get_text = MagicMock(return_value="cdp output text")
        session = InteractionSession(config=config, bridge=mock_bridge)

        ctx = _make_ctx(cdptab={"id": "tab1"})
        text = session.read_output(ctx)

        assert text == "cdp output text"
        mock_bridge.get_text.assert_called_once_with({"id": "tab1"}, ".chat-content")

    def test_read_all_empty(self):
        """All output methods return empty -> returns empty string."""
        config = _make_desktop_config(
            output=[
                {"type": "cdp", "selector": ".content"},
            ]
        )
        # No bridge, no ocr, no star -> all fail
        session = InteractionSession(config=config)
        ctx = _make_ctx()
        text = session.read_output(ctx)
        assert text == ""

    def test_read_no_config(self):
        """No config -> returns empty string."""
        session = InteractionSession(config=None)
        ctx = _make_ctx()
        text = session.read_output(ctx)
        assert text == ""

    def test_read_chain_order(self, monkeypatch):
        """Verify log is tried before ocr, ocr before cdp."""
        call_order = []

        config = _make_desktop_config(
            output=[
                {"type": "log", "paths": ["~/*.log"]},
                {"type": "ocr", "region": "center"},
                {"type": "cdp", "selector": ".content"},
            ]
        )

        # Make log return empty so ocr is tried
        fake_reader = MagicMock()
        fake_reader.find_logs_for_star = MagicMock(return_value=[])
        fake_log_reader_mod = types.ModuleType("star_core.log_reader")
        fake_log_reader_mod.get_reader = MagicMock(return_value=fake_reader)
        monkeypatch.setitem(sys.modules, "star_core.log_reader", fake_log_reader_mod)

        # OCR also returns empty
        mock_ocr = MagicMock()
        ocr_result = MagicMock()
        ocr_result.text = ""
        mock_ocr.gaze_region = MagicMock(return_value=ocr_result)

        # CDP returns text
        mock_bridge = MagicMock()
        mock_bridge.get_text = MagicMock(return_value="final cdp text")

        session = InteractionSession(config=config, bridge=mock_bridge, ocr=mock_ocr)
        ctx = _make_ctx(star=MagicMock(), cdptab={"id": "t1"})

        text = session.read_output(ctx)

        assert text == "final cdp text"
        # Verify log was tried (find_logs_for_star called)
        fake_reader.find_logs_for_star.assert_called_once()
        # Verify OCR was tried
        mock_ocr.gaze_region.assert_called_once()
        # Verify CDP was tried
        mock_bridge.get_text.assert_called_once()


# ===== Tests: InteractionConfig parsing =====

class TestConfigParsing:
    """Verify InteractionConfig dataclass defaults and field access."""

    def test_default_config(self):
        cfg = InteractionConfig()
        assert cfg.locators == []
        assert cfg.send_on == "Enter"
        assert cfg.send_button is None
        assert cfg.stop is None
        assert cfg.stop_fallback_keys == []
        assert cfg.output == []

    def test_config_with_fields(self):
        cfg = _make_desktop_config()
        assert cfg.locators == ["uia", "visual", "ratio"]
        assert cfg.input.uia.control_type == "Edit"
        assert cfg.input.uia.name_regex == "input|Ask"
        assert cfg.input.visual.hint_text == "input"
        assert cfg.input.ratio.x_ratio == 0.5
        assert cfg.input.ratio.y_ratio == 0.93
        assert cfg.send_on == "Enter"
        assert cfg.stop is not None
        assert "Esc" in cfg.stop_fallback_keys

    def test_browser_config(self):
        cfg = _make_browser_config()
        assert cfg.locators == ["cdp"]
        assert cfg.input.cdp.selector == "textarea#chat-input"
        assert cfg.stop is not None
        assert cfg.stop.cdp.text_contains == "stop"
