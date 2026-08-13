"""
混合定位器基础抽象

定义定位器链的核心数据结构与降级执行逻辑:
- ElementBox:       定位结果(命中元素的屏幕几何信息)
- UIAQuery / VisualQuery / RatioQuery / CDPQuery: 各定位器查询参数
- LocatorTarget:    一次定位请求(找什么)
- WindowContext:    窗口/页面上下文
- Locator:          定位器抽象基类
- LocatorChain:     链式降级执行器
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from star_core.star_seeker import StarBody


@dataclass
class ElementBox:
    """定位结果: 命中元素的屏幕几何信息"""
    x: int
    y: int                       # 元素左上角(或点击锚点) 屏幕绝对坐标
    width: int
    height: int
    confidence: float            # 0~1, 用于同链多命中排序
    source: str                  # "uia" / "visual" / "ratio" / "cdp"
    meta: dict = field(default_factory=dict)


@dataclass
class UIAQuery:
    """UIA 查询参数"""
    control_type: str | None = None       # "Edit" / "Button" / "Document" / None=任意
    automation_id: str | None = None      # 精确匹配
    name_regex: str | None = None         # Name 正则(如 "输入|Ask|Message")
    depth_limit: int = 8


@dataclass
class VisualQuery:
    """视觉查询参数"""
    hint_text: str | None = None          # OCR 占位文本(如 "输入" / "请输入")
    template: str | None = None           # 模板图片路径(相对 star 项目根)
    region: str = "full_window"
    ocr_min_confidence: float = 0.5


@dataclass
class RatioQuery:
    """坐标比例查询参数"""
    x_ratio: float = 0.5
    y_ratio: float = 0.92


@dataclass
class CDPQuery:
    """CDP 查询参数"""
    selector: str | None = None           # DOM 选择器
    text_contains: str | None = None      # 按可见文本找按钮
    role: str | None = None               # 可访问性 role


@dataclass
class LocatorTarget:
    """一次定位请求: 找什么"""
    kind: str                             # "input" / "send_button" / "stop_button"
    uia: UIAQuery | None = None
    visual: VisualQuery | None = None
    ratio: RatioQuery | None = None
    cdp: CDPQuery | None = None


@dataclass
class WindowContext:
    """窗口/页面上下文"""
    hwnd: int | None = None
    star: StarBody | None = None
    cdptab: dict | None = None            # {"ws": ..., "page_url": str, "viewport": {...}}
    min_confidence: float = 0.3


class Locator(ABC):
    """定位器抽象基类"""
    name: str                             # "uia" / "visual" / "ratio" / "cdp"

    @abstractmethod
    def find(self, target: LocatorTarget, ctx: WindowContext) -> ElementBox | None:
        """在窗口/页面上下文中定位目标元素"""
        ...


class LocatorChain:
    """按配置顺序执行定位器, 返回第一个置信度达标的命中"""

    def __init__(
        self,
        targets: dict[str, LocatorTarget],
        order: list[str],
        registry: dict[str, Locator],
    ):
        self.targets = targets
        self.order = order
        self.registry = registry

    def locate(self, kind: str, ctx: WindowContext) -> ElementBox | None:
        """
        按 self.order 顺序执行 registry 中对应的定位器,
        返回第一个 confidence >= ctx.min_confidence 的命中.
        任一 locator 抛异常记 log 后继续下一个, 不中断.
        """
        target = self.targets.get(kind)
        if target is None:
            logger.warning(f"[LocatorChain] kind={kind} not in targets")
            return None

        for name in self.order:
            locator = self.registry.get(name)
            if locator is None:
                continue
            try:
                box = locator.find(target, ctx)
            except Exception as e:
                logger.warning(f"[LocatorChain] locator '{name}' raised: {e}")
                continue
            if box is not None and box.confidence >= ctx.min_confidence:
                return box
        return None

    def available(self) -> list[str]:
        """返回 registry 中已注册的定位器名称列表"""
        return list(self.registry.keys())
