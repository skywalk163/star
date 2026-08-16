"""UIA / COM 串行执行器。

`uiautomation` 底层是 COM。若在多个线程上并发访问，或在 asyncio 事件循环
线程上被高频驱动，会触发进程级原生崩溃——没有 Python traceback，进程直接
以非零码退出。

本模块把所有 UIA 调用收敛到**一个**常驻工作线程，并在该线程启动时完成 COM
初始化。这样既保证同一时刻只有一个 UIA 调用在执行，也让异步端点不再在事件
循环线程上做阻塞的原生调用。
"""

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")

#: UIA 调用默认超时（秒）。控件树遍历偶发卡死时避免拖垮整个请求。
DEFAULT_TIMEOUT = 20.0

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def _init_com() -> None:
    """在工作线程上初始化 COM（缺少 pywin32 时静默跳过）。"""
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        with _lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix="uia",
                    initializer=_init_com,
                )
    return _executor


def run_uia(
    fn: Callable[..., T],
    *args: Any,
    timeout: float = DEFAULT_TIMEOUT,
    default: Any = None,
    **kwargs: Any,
) -> T | Any:
    """在专用 UIA 线程上同步执行 fn。超时或抛错时返回 default。"""
    try:
        future = _get_executor().submit(fn, *args, **kwargs)
        return future.result(timeout=timeout)
    except Exception:
        return default


async def run_uia_async(
    fn: Callable[..., T],
    *args: Any,
    timeout: float = DEFAULT_TIMEOUT,
    default: Any = None,
    **kwargs: Any,
) -> T | Any:
    """在专用 UIA 线程上执行 fn，不阻塞事件循环。超时或抛错返回 default。"""
    try:
        future = _get_executor().submit(fn, *args, **kwargs)
        return await asyncio.wait_for(asyncio.wrap_future(future), timeout=timeout)
    except Exception:
        return default
