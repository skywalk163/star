"""
UIA 定位器 - 优先级最高

基于 uiautomation 库, 从窗口根控件深度优先遍历查找目标元素.
lazy import uiautomation, import 失败或控件树异常时返回 None 不抛出.
"""

from __future__ import annotations

import re

from star_core.locators.base import (
    ElementBox,
    Locator,
    LocatorTarget,
    WindowContext,
)

# control_type -> uiautomation 控件类名映射
_CONTROL_TYPE_MAP: dict[str, str] = {
    "Edit": "EditControl",
    "Button": "ButtonControl",
    "Document": "DocumentControl",
    "Text": "TextControl",
    "ComboBox": "ComboBoxControl",
    "ListItem": "ListItemControl",
    "List": "ListControl",
    "CheckBox": "CheckBoxControl",
    "RadioButton": "RadioButtonControl",
    "Tab": "TabControl",
    "TabItem": "TabItemControl",
    "Tree": "TreeControl",
    "TreeItem": "TreeItemControl",
    "ToolBar": "ToolBarControl",
    "MenuBar": "MenuBarControl",
    "MenuItem": "MenuItemControl",
    "Custom": "CustomControl",
    "Pane": "PaneControl",
    "Window": "WindowControl",
    "Image": "ImageControl",
    "Hyperlink": "HyperlinkControl",
    "ProgressBar": "ProgressBarControl",
    "Slider": "SliderControl",
    "Spinner": "SpinnerControl",
    "StatusBar": "StatusBarControl",
    "ToolTip": "ToolTipControl",
    "GroupBox": "GroupBoxControl",
    "DataGrid": "DataGridControl",
    "DataItem": "DataItemControl",
    "Header": "HeaderControl",
    "HeaderItem": "HeaderItemControl",
    "Menu": "MenuControl",
    "Scroll": "ScrollControl",
    "Thumb": "ThumbControl",
    "Separator": "SeparatorControl",
    "AppBar": "AppBarControl",
}


class UIALocator(Locator):
    """UIA 控件树定位器, confidence 0.9"""
    name = "uia"

    def find(self, target: LocatorTarget, ctx: WindowContext) -> ElementBox | None:
        if target.uia is None:
            return None

        hwnd = ctx.hwnd
        if hwnd is None and ctx.star is not None:
            hwnd = ctx.star.hwnd
        if hwnd is None:
            return None

        try:
            import uiautomation as ua
        except ImportError:
            return None

        try:
            root = ua.ControlFromHandle(hwnd)
            if root is None:
                return None

            query = target.uia
            name_pattern = None
            if query.name_regex:
                name_pattern = re.compile(query.name_regex)

            matched = self._search(
                root, query, name_pattern, query.depth_limit, 0,
            )
            if matched is None:
                return None

            rect = matched.BoundingRectangle
            left = rect.left
            top = rect.top
            width = rect.right - rect.left
            height = rect.bottom - rect.top

            if width <= 0 or height <= 0:
                return None

            return ElementBox(
                x=left,
                y=top,
                width=width,
                height=height,
                confidence=0.9,
                source="uia",
                meta={
                    "control_type": query.control_type or "",
                    "name": getattr(matched, "Name", "") or "",
                    "automation_id": getattr(matched, "AutomationId", "") or "",
                },
            )
        except Exception:
            return None

    def _search(self, control, query, name_pattern, depth_limit, depth):
        """深度优先遍历查找匹配控件"""
        if depth > depth_limit:
            return None

        if self._match(control, query, name_pattern):
            return control

        try:
            children = control.GetChildren()
        except Exception:
            children = []

        for child in children:
            result = self._search(
                child, query, name_pattern, depth_limit, depth + 1,
            )
            if result is not None:
                return result

        return None

    @staticmethod
    def _match(control, query, name_pattern) -> bool:
        """
        检查控件是否匹配查询条件(AND 逻辑).
        至少需要一个非 None 条件才会匹配.
        """
        has_condition = False

        # control_type 匹配
        if query.control_type:
            has_condition = True
            ct = getattr(control, "ControlTypeName", "") or ""
            if ct != query.control_type and ct != query.control_type + "Control":
                return False

        # automation_id 精确匹配
        if query.automation_id:
            has_condition = True
            aid = getattr(control, "AutomationId", "") or ""
            if aid != query.automation_id:
                return False

        # name_regex 匹配(跳过空 Name)
        if name_pattern:
            has_condition = True
            name = getattr(control, "Name", "") or ""
            if not name:
                return False
            if not name_pattern.search(name):
                return False

        return has_condition
