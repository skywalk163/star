"""
plugin_hooks.py - 插件钩子分发器

统一管理插件钩子的注册和调用，
避免各模块直接依赖 PluginManager。
"""

from typing import Any, Optional, List, Callable
from enum import Enum
import logging
import threading

logger = logging.getLogger(__name__)


class HookPoint(str, Enum):
    """钩子点枚举"""
    # 新星生命周期
    NOVA_CREATE = "nova_create"
    NOVA_LAUNCH = "nova_launch"
    NOVA_SHINE = "nova_shine"
    NOVA_COMPLETE = "nova_complete"
    NOVA_FADE = "nova_fade"
    
    # 星体生命周期
    STAR_DISCOVERED = "star_discovered"
    STAR_LOST = "star_lost"
    
    # 星辉接收
    STARLIGHT_RECEIVED = "starlight_received"
    
    # 星座生命周期
    CONSTELLATION_CREATE = "constellation_create"
    CONSTELLATION_COMPLETE = "constellation_complete"
    
    # 系统事件
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"


class HookDispatcher:
    """
    钩子分发器
    
    负责：
    - 注册钩子处理器
    - 分发钩子事件
    - 处理钩子异常
    """
    
    def __init__(self):
        self._handlers: dict[str, List[Callable]] = {}
        self._lock = threading.RLock()
    
    def register(self, hook_point: str | HookPoint, handler: Callable):
        """注册钩子处理器"""
        key = hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        with self._lock:
            if key not in self._handlers:
                self._handlers[key] = []
            self._handlers[key].append(handler)
    
    def unregister(self, hook_point: str | HookPoint, handler: Callable):
        """注销钩子处理器"""
        key = hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        with self._lock:
            if key in self._handlers:
                try:
                    self._handlers[key].remove(handler)
                except ValueError:
                    pass
    
    def dispatch(self, hook_point: str | HookPoint, *args, **kwargs) -> list:
        """
        分发钩子事件
        
        Returns:
            所有处理器的返回值列表
        """
        key = hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        results = []
        
        with self._lock:
            handlers = list(self._handlers.get(key, []))
        
        for handler in handlers:
            try:
                result = handler(*args, **kwargs)
                results.append(result)
            except Exception:
                logger.exception(f"Hook handler error for {key}")
                results.append(None)
        
        return results
    
    def dispatch_until_false(self, hook_point: str | HookPoint, *args, **kwargs) -> bool:
        """
        分发钩子事件，直到返回 False
        
        Returns:
            False 表示有处理器阻止了事件，True 表示全部通过
        """
        key = hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        
        with self._lock:
            handlers = list(self._handlers.get(key, []))
        
        for handler in handlers:
            try:
                result = handler(*args, **kwargs)
                if result is False:
                    return False
            except Exception:
                logger.exception(f"Hook handler error for {key}")
        
        return True
    
    def clear(self):
        """清空所有钩子"""
        with self._lock:
            self._handlers.clear()
    
    def has_hooks(self, hook_point: str | HookPoint) -> bool:
        """检查某个钩子点是否有处理器"""
        key = hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        with self._lock:
            return key in self._handlers and len(self._handlers[key]) > 0


# 全局钩子分发器实例
_global_dispatcher: Optional[HookDispatcher] = None
_init_lock = threading.Lock()


def get_hook_dispatcher() -> HookDispatcher:
    """获取全局钩子分发器"""
    global _global_dispatcher
    if _global_dispatcher is None:
        with _init_lock:
            if _global_dispatcher is None:
                _global_dispatcher = HookDispatcher()
    return _global_dispatcher
