"""
群星事件总线（Star Event Bus）

借鉴 DeepSeek Harness 的 Cordis 事件系统设计理念，
提供统一的事件总线支持四种派发模式：

1. emit (观察) - 所有处理器同步执行，异常隔离不影响其他
2. waterfall (中间件) - 顺序执行，前一个输出传给下一个，支持短路
3. parallel (并行) - 所有处理器并发执行，等待全部完成
4. serial (串行) - 顺序执行，收集所有非空结果

设计文档: docs/specs/event-bus-design.md
"""

import asyncio
import logging
import threading
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


class EventDispatchMode:
    """派发模式常量"""
    EMIT = "emit"
    WATERFALL = "waterfall"
    PARALLEL = "parallel"
    SERIAL = "serial"


class EventBus:
    """事件总线

    提供统一的事件订阅/发布机制，支持多种派发模式。
    """

    def __init__(self):
        self._handlers: dict[str, List[Callable]] = {}
        self._lock = threading.RLock()
        self._logger = logging.getLogger(__name__)

    def on(self, event_name: str, handler: Callable) -> None:
        """注册事件处理器

        Args:
            event_name: 事件名称
            handler: 处理器函数
        """
        with self._lock:
            if event_name not in self._handlers:
                self._handlers[event_name] = []
            self._handlers[event_name].append(handler)

    def off(self, event_name: str, handler: Callable) -> None:
        """注销事件处理器

        Args:
            event_name: 事件名称
            handler: 要注销的处理器
        """
        with self._lock:
            if event_name in self._handlers:
                try:
                    self._handlers[event_name].remove(handler)
                except ValueError:
                    pass

    def emit(self, event_name: str, payload: Any = None) -> None:
        """
        Emit 模式：触发事件，所有处理器同步执行

        异常被捕获并记录，不影响其他处理器。
        适用于观察者模式，比如通知 UI 更新、日志记录等。

        Args:
            event_name: 事件名称
            payload: 事件载荷
        """
        handlers = self._get_handlers(event_name)
        if not handlers:
            return

        for handler in handlers:
            try:
                handler(payload)
            except Exception:
                self._logger.exception(f"Event handler error for {event_name} (emit)")

    async def waterfall(self, event_name: str, initial: Any) -> Any:
        """
        Waterfall 模式：顺序执行，前一个输出传给下一个

        返回 False 时短路停止后续执行。
        适用于中间件链、验证链等场景。

        Args:
            event_name: 事件名称
            initial: 初始输入值

        Returns:
            最终结果，False 表示被短路
        """
        handlers = self._get_handlers(event_name)
        current = initial

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(current)
                else:
                    result = handler(current)

                if result is False:
                    # 短路
                    return False
                if result is not None:
                    current = result
            except Exception:
                self._logger.exception(f"Event handler error for {event_name} (waterfall)")
                return False

        return current

    async def parallel(self, event_name: str, payload: Any) -> List[Any]:
        """
        Parallel 模式：并发执行所有处理器

        等待全部完成，收集结果，异常被忽略。
        适用于多个独立处理器处理同一事件，比如任务完成后同时更新多个组件。

        Args:
            event_name: 事件名称
            payload: 事件载荷

        Returns:
            所有非异常结果的列表
        """
        handlers = self._get_handlers(event_name)
        if not handlers:
            return []

        tasks = []
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                tasks.append(asyncio.create_task(handler(payload)))
            else:
                # 包装同步函数为异步任务
                tasks.append(asyncio.create_task(asyncio.to_thread(handler, payload)))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 过滤异常，只返回正常结果
        return [r for r in results if not isinstance(r, Exception)]

    async def serial(self, event_name: str, payload: Any) -> List[Any]:
        """
        Serial 模式：顺序执行，收集所有非空结果

        适用于初始化流程、批量处理等场景。

        Args:
            event_name: 事件名称
            payload: 事件载荷

        Returns:
            所有非空结果列表
        """
        handlers = self._get_handlers(event_name)
        results = []

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(payload)
                else:
                    result = handler(payload)
                if result is not None:
                    results.append(result)
            except Exception:
                self._logger.exception(f"Event handler error for {event_name} (serial)")

        return results

    def has_listeners(self, event_name: str) -> bool:
        """检查事件是否有监听器

        Args:
            event_name: 事件名称

        Returns:
            True 表示有至少一个监听器
        """
        with self._lock:
            return event_name in self._handlers and len(self._handlers[event_name]) > 0

    def clear(self) -> None:
        """清空所有处理器（测试用）"""
        with self._lock:
            self._handlers.clear()

    def _get_handlers(self, event_name: str) -> List[Callable]:
        """获取处理器列表（快照，线程安全）"""
        with self._lock:
            if event_name not in self._handlers:
                return []
            return list(self._handlers[event_name])


# 预定义的事件名称（约定）
class EventNames:
    """系统事件名称常量"""

    # 系统事件
    SYSTEM_STARTUP = "system:startup"
    SYSTEM_SHUTDOWN = "system:shutdown"
    CONFIG_CHANGED = "system:config_changed"

    # AI 连接事件
    AI_CONNECTED = "ai:connected"
    AI_DISCONNECTED = "ai:disconnected"
    AI_ERROR = "ai:error"

    # 任务生命周期事件
    TASK_CREATED = "task:created"
    TASK_STARTED = "task:started"
    TASK_PROGRESS = "task:progress"
    TASK_OUTPUT_UPDATED = "task:output_updated"
    TASK_STOPPING = "task:stopping"
    TASK_STOPPED = "task:stopped"
    TASK_COMPLETED = "task:completed"
    TASK_FAILED = "task:failed"

    # 会话事件
    SESSION_STATUS_CHANGED = "session:status_changed"
    SESSION_FOREGROUND_CHANGED = "session:foreground_changed"

    # DuMate 特定
    DUMATE_ENGINE_EVENT = "dumate:engine_event"
    DUMATE_KERNEL_LOG = "dumate:kernel_log"


# 全局单例
_event_bus: Optional[EventBus] = None
_init_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """获取全局事件总线实例"""
    global _event_bus
    if _event_bus is None:
        with _init_lock:
            if _event_bus is None:
                _event_bus = EventBus()
    return _event_bus