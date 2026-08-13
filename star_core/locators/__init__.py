"""
定位器注册表与工厂

create_locator(name):  按名称 lazy import 并实例化定位器
default_registry():    返回默认定位器注册表(uia/visual/ratio, 不含 cdp)
"""

from __future__ import annotations

from star_core.locators.base import Locator


def create_locator(name: str) -> Locator | None:
    """按名称实例化定位器(lazy import), 未知名返回 None"""
    if name == "uia":
        from star_core.locators.uia import UIALocator
        return UIALocator()
    if name == "visual":
        from star_core.locators.visual import VisualLocator
        return VisualLocator()
    if name == "ratio":
        from star_core.locators.ratio import RatioLocator
        return RatioLocator()
    return None


def default_registry() -> dict[str, Locator]:
    """返回默认定位器注册表: {"uia": ..., "visual": ..., "ratio": ...}"""
    registry: dict[str, Locator] = {}
    for name in ("uia", "visual", "ratio"):
        locator = create_locator(name)
        if locator is not None:
            registry[name] = locator
    return registry
