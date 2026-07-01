"""
数据模型测试

测试 star_core.models 中的数据类
"""

import pytest
import time
from star_core.models import (
    StarWindowContext,
    StarWindow,
    StarBody,
    AuditLogEntry,
)


class TestStarWindowContext:
    """测试 StarWindowContext"""

    def test_default_values(self):
        ctx = StarWindowContext()
        assert ctx.project_name == ""
        assert ctx.file_name == ""
        assert ctx.window_type == "unknown"
        assert ctx.is_work_mode == False

    def test_to_dict(self):
        ctx = StarWindowContext(
            project_name="test_proj",
            file_name="test.py",
            window_type="editor",
            is_work_mode=True,
        )
        d = ctx.to_dict()
        assert d['project_name'] == "test_proj"
        assert d['file_name'] == "test.py"
        assert d['window_type'] == "editor"
        assert d['is_work_mode'] == True


class TestStarWindow:
    """测试 StarWindow"""

    def test_creation(self):
        win = StarWindow(hwnd=12345, title="Test Window")
        assert win.hwnd == 12345
        assert win.title == "Test Window"
        assert win.class_name == ""
        assert win.rect == ()
        assert win.is_visible == True

    def test_parse_context_trae_editor(self):
        win = StarWindow(
            hwnd=123,
            title="main.py - myproject - Trae CN"
        )
        ctx = win.parse_context("trae")
        assert ctx.project_name == "myproject"
        assert ctx.file_name == "main.py"
        assert ctx.window_type == "editor"

    def test_parse_context_trae_work_mode(self):
        win = StarWindow(
            hwnd=123,
            title="TRAE Work CN - 任务模式"
        )
        ctx = win.parse_context("trae")
        assert ctx.is_work_mode == True
        assert ctx.window_type == "work_mode"

    def test_parse_context_trae_preview(self):
        win = StarWindow(
            hwnd=123,
            title="readme.md (Preview) - myproject - Trae CN"
        )
        ctx = win.parse_context("trae")
        assert ctx.window_type == "preview"

    def test_parse_context_empty_title(self):
        win = StarWindow(hwnd=123, title="")
        ctx = win.parse_context("trae")
        assert ctx.project_name == ""
        assert ctx.window_type == "unknown"

    def test_get_context_alias(self):
        win = StarWindow(hwnd=123, title="test.py - proj - Trae CN")
        ctx1 = win.parse_context("trae")
        ctx2 = win.get_context("trae")
        assert ctx1.project_name == ctx2.project_name

    def test_to_dict(self):
        win = StarWindow(
            hwnd=12345,
            title="test.py - myproj - Trae CN",
            class_name="Chrome_WidgetWin_1",
            rect=(0, 0, 800, 600),
            is_visible=True,
        )
        d = win.to_dict()
        assert d['hwnd'] == 12345
        assert d['title'] == "test.py - myproj - Trae CN"
        assert d['class_name'] == "Chrome_WidgetWin_1"
        assert d['is_visible'] == True
        assert 'context' in d


class TestStarBody:
    """测试 StarBody"""

    def test_creation(self):
        star = StarBody(
            star_type="trae",
            pid=1234,
            hwnd=5678,
            title="Test Star",
        )
        assert star.star_type == "trae"
        assert star.pid == 1234
        assert star.hwnd == 5678
        assert star.title == "Test Star"
        assert star.windows == []
        assert star.is_shining == False

    def test_refresh_activity(self):
        star = StarBody(star_type="trae", pid=1, hwnd=2, title="test")
        before = star.last_activity
        time.sleep(0.01)
        star.refresh_activity()
        assert star.last_activity > before

    def test_mark_shining(self):
        star = StarBody(star_type="trae", pid=1, hwnd=2, title="test")
        assert star.is_shining == False
        star.mark_shining(True)
        assert star.is_shining == True
        star.mark_shining(False)
        assert star.is_shining == False

    def test_get_window_count(self):
        star = StarBody(star_type="trae", pid=1, hwnd=2, title="test")
        assert star.get_window_count() == 0
        star.windows = [StarWindow(hwnd=1), StarWindow(hwnd=2)]
        assert star.get_window_count() == 2

    def test_to_dict(self):
        star = StarBody(
            star_type="trae",
            pid=1234,
            hwnd=5678,
            title="Test",
            is_shining=True,
        )
        d = star.to_dict()
        assert d['star_id'] == 'star_1234'
        assert d['star_type'] == 'trae'
        assert d['pid'] == 1234
        assert d['is_shining'] == True

    def test_hash(self):
        star1 = StarBody(star_type="trae", pid=123, hwnd=456, title="test")
        star2 = StarBody(star_type="trae", pid=123, hwnd=789, title="test2")
        assert hash(star1) == hash(star2)


class TestAuditLogEntry:
    """测试 AuditLogEntry"""

    def test_creation(self):
        entry = AuditLogEntry(operation="test_op")
        assert entry.operation == "test_op"
        assert entry.hwnd is None
        assert entry.params == {}
        assert entry.user == "default"
        assert entry.role == "admin"
        assert entry.result == "success"
        assert entry.detail == ""

    def test_to_dict(self):
        entry = AuditLogEntry(
            operation="click",
            hwnd=12345,
            params={"x": 100, "y": 200},
            user="admin",
            role="admin",
            result="success",
            detail="test detail",
        )
        d = entry.to_dict()
        assert d['operation'] == "click"
        assert d['hwnd'] == 12345
        assert d['params'] == {"x": 100, "y": 200}
        assert d['user'] == "admin"
        assert d['role'] == "admin"
        assert d['result'] == "success"
        assert d['detail'] == "test detail"
        assert 'timestamp' in d
        assert 'time_str' in d

    def test_time_str_property(self):
        entry = AuditLogEntry(operation="test")
        time_str = entry.time_str
        assert isinstance(time_str, str)
        assert len(time_str) > 0

    def test_repr(self):
        entry = AuditLogEntry(operation="test_op", result="success")
        repr_str = repr(entry)
        assert "test_op" in repr_str
        assert "default" in repr_str
        assert "admin" in repr_str

    def test_repr_failure(self):
        entry = AuditLogEntry(operation="test_op", result="failed")
        repr_str = repr(entry)
        assert "✗" in repr_str
