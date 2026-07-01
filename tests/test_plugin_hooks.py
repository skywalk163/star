"""
插件钩子系统测试

测试 star_core.plugin_hooks 中的 HookPoint / HookDispatcher / get_hook_dispatcher
"""

import threading
import pytest

from star_core.plugin_hooks import (
    HookPoint,
    HookDispatcher,
    get_hook_dispatcher,
)


# ========== HookPoint 枚举测试 ==========

class TestHookPoint:
    """测试 HookPoint 枚举完整性"""

    def test_enum_members_count(self):
        # 应包含新星/星体/星辉/星座/系统事件等钩子点
        assert len(HookPoint) >= 12

    def test_nova_lifecycle_hooks(self):
        assert HookPoint.NOVA_CREATE.value == "nova_create"
        assert HookPoint.NOVA_LAUNCH.value == "nova_launch"
        assert HookPoint.NOVA_SHINE.value == "nova_shine"
        assert HookPoint.NOVA_COMPLETE.value == "nova_complete"
        assert HookPoint.NOVA_FADE.value == "nova_fade"

    def test_star_hooks(self):
        assert HookPoint.STAR_DISCOVERED.value == "star_discovered"
        assert HookPoint.STAR_LOST.value == "star_lost"

    def test_starlight_hook(self):
        assert HookPoint.STARLIGHT_RECEIVED.value == "starlight_received"

    def test_constellation_hooks(self):
        assert HookPoint.CONSTELLATION_CREATE.value == "constellation_create"
        assert HookPoint.CONSTELLATION_COMPLETE.value == "constellation_complete"

    def test_system_hooks(self):
        assert HookPoint.SYSTEM_STARTUP.value == "system_startup"
        assert HookPoint.SYSTEM_SHUTDOWN.value == "system_shutdown"

    def test_is_string_enum(self):
        # HookPoint 继承 str，可直接当字符串使用
        assert HookPoint.NOVA_CREATE == "nova_create"
        assert isinstance(HookPoint.NOVA_CREATE, str)


# ========== HookDispatcher 基础测试 ==========

class TestHookDispatcherBasic:
    """测试 HookDispatcher 基础功能"""

    def test_create_dispatcher(self):
        d = HookDispatcher()
        assert d is not None

    def test_register_and_has_hooks(self):
        d = HookDispatcher()
        handler = lambda: None
        assert d.has_hooks(HookPoint.NOVA_CREATE) is False

        d.register(HookPoint.NOVA_CREATE, handler)
        assert d.has_hooks(HookPoint.NOVA_CREATE) is True

    def test_register_with_string_key(self):
        d = HookDispatcher()
        handler = lambda: None
        d.register("nova_create", handler)
        assert d.has_hooks("nova_create") is True
        # HookPoint 与字符串应能互通
        assert d.has_hooks(HookPoint.NOVA_CREATE) is True

    def test_has_hooks_empty(self):
        d = HookDispatcher()
        assert d.has_hooks(HookPoint.NOVA_LAUNCH) is False
        assert d.has_hooks("nonexistent") is False

    def test_register_multiple_handlers(self):
        d = HookDispatcher()
        h1 = lambda: 1
        h2 = lambda: 2
        h3 = lambda: 3
        d.register(HookPoint.NOVA_CREATE, h1)
        d.register(HookPoint.NOVA_CREATE, h2)
        d.register(HookPoint.NOVA_CREATE, h3)
        # 应该全部注册成功
        results = d.dispatch(HookPoint.NOVA_CREATE)
        assert results == [1, 2, 3]

    def test_register_different_hook_points_independent(self):
        d = HookDispatcher()
        h_create = lambda: "create"
        h_launch = lambda: "launch"
        d.register(HookPoint.NOVA_CREATE, h_create)
        d.register(HookPoint.NOVA_LAUNCH, h_launch)

        assert d.dispatch(HookPoint.NOVA_CREATE) == ["create"]
        assert d.dispatch(HookPoint.NOVA_LAUNCH) == ["launch"]
        assert d.dispatch(HookPoint.NOVA_COMPLETE) == []


# ========== register / unregister 测试 ==========

class TestRegisterUnregister:
    """测试注册与注销"""

    def test_unregister_single(self):
        d = HookDispatcher()
        h1 = lambda: 1
        h2 = lambda: 2
        d.register(HookPoint.NOVA_CREATE, h1)
        d.register(HookPoint.NOVA_CREATE, h2)

        d.unregister(HookPoint.NOVA_CREATE, h1)
        assert d.dispatch(HookPoint.NOVA_CREATE) == [2]
        assert d.has_hooks(HookPoint.NOVA_CREATE) is True

    def test_unregister_all(self):
        d = HookDispatcher()
        h1 = lambda: 1
        h2 = lambda: 2
        d.register(HookPoint.NOVA_CREATE, h1)
        d.register(HookPoint.NOVA_CREATE, h2)

        d.unregister(HookPoint.NOVA_CREATE, h1)
        d.unregister(HookPoint.NOVA_CREATE, h2)
        assert d.has_hooks(HookPoint.NOVA_CREATE) is False
        assert d.dispatch(HookPoint.NOVA_CREATE) == []

    def test_unregister_nonexistent_handler(self):
        # 注销一个未注册的处理器不应抛异常
        d = HookDispatcher()
        h1 = lambda: 1
        h2 = lambda: 2
        d.register(HookPoint.NOVA_CREATE, h1)

        # h2 未注册，应静默处理
        d.unregister(HookPoint.NOVA_CREATE, h2)
        assert d.dispatch(HookPoint.NOVA_CREATE) == [1]

    def test_unregister_from_nonexistent_hook_point(self):
        d = HookDispatcher()
        h = lambda: 1
        # 钩子点不存在，应静默处理
        d.unregister(HookPoint.NOVA_CREATE, h)
        # 不报错即可
        assert d.has_hooks(HookPoint.NOVA_CREATE) is False

    def test_unregister_with_string_key(self):
        d = HookDispatcher()
        h = lambda: 1
        d.register(HookPoint.NOVA_CREATE, h)
        d.unregister("nova_create", h)
        assert d.has_hooks(HookPoint.NOVA_CREATE) is False

    def test_register_same_handler_twice(self):
        d = HookDispatcher()
        h = lambda: 1
        d.register(HookPoint.NOVA_CREATE, h)
        d.register(HookPoint.NOVA_CREATE, h)
        # 同一个 handler 注册两次，会被调用两次
        results = d.dispatch(HookPoint.NOVA_CREATE)
        assert results == [1, 1]

        # 注销一次只会移除一个
        d.unregister(HookPoint.NOVA_CREATE, h)
        assert d.dispatch(HookPoint.NOVA_CREATE) == [1]


# ========== dispatch 测试 ==========

class TestDispatch:
    """测试 dispatch 分发"""

    def test_dispatch_returns_results_list(self):
        d = HookDispatcher()
        d.register(HookPoint.NOVA_CREATE, lambda: 1)
        d.register(HookPoint.NOVA_CREATE, lambda: 2)
        results = d.dispatch(HookPoint.NOVA_CREATE)
        assert isinstance(results, list)
        assert results == [1, 2]

    def test_dispatch_empty_returns_empty_list(self):
        d = HookDispatcher()
        results = d.dispatch(HookPoint.NOVA_CREATE)
        assert results == []

    def test_dispatch_passes_args(self):
        d = HookDispatcher()
        captured = []

        def handler(*args, **kwargs):
            captured.append((args, kwargs))
            return None

        d.register(HookPoint.NOVA_SHINE, handler)
        d.dispatch(HookPoint.NOVA_SHINE, "nova1", "star1", level=5)

        assert len(captured) == 1
        assert captured[0][0] == ("nova1", "star1")
        assert captured[0][1] == {"level": 5}

    def test_dispatch_with_string_key(self):
        d = HookDispatcher()
        d.register(HookPoint.NOVA_CREATE, lambda: "ok")
        assert d.dispatch("nova_create") == ["ok"]

    def test_dispatch_returns_none_values(self):
        d = HookDispatcher()
        d.register(HookPoint.NOVA_CREATE, lambda: None)
        results = d.dispatch(HookPoint.NOVA_CREATE)
        assert results == [None]


# ========== dispatch_until_false 测试 ==========

class TestDispatchUntilFalse:
    """测试 dispatch_until_false"""

    def test_all_true_returns_true(self):
        d = HookDispatcher()
        d.register(HookPoint.NOVA_LAUNCH, lambda: True)
        d.register(HookPoint.NOVA_LAUNCH, lambda: True)
        assert d.dispatch_until_false(HookPoint.NOVA_LAUNCH) is True

    def test_returns_false_when_handler_returns_false(self):
        d = HookDispatcher()
        d.register(HookPoint.NOVA_LAUNCH, lambda: True)
        d.register(HookPoint.NOVA_LAUNCH, lambda: False)
        d.register(HookPoint.NOVA_LAUNCH, lambda: True)
        # 第二个返回 False 应该停止后续调用
        result = d.dispatch_until_false(HookPoint.NOVA_LAUNCH)
        assert result is False

    def test_no_handlers_returns_true(self):
        d = HookDispatcher()
        assert d.dispatch_until_false(HookPoint.NOVA_LAUNCH) is True

    def test_stops_at_first_false(self):
        d = HookDispatcher()
        call_count = 0

        def counter():
            nonlocal call_count
            call_count += 1
            return True

        def blocker():
            nonlocal call_count
            call_count += 1
            return False

        d.register(HookPoint.NOVA_LAUNCH, counter)
        d.register(HookPoint.NOVA_LAUNCH, blocker)
        d.register(HookPoint.NOVA_LAUNCH, counter)

        result = d.dispatch_until_false(HookPoint.NOVA_LAUNCH)
        assert result is False
        # blocker 之后的 counter 不应被调用
        assert call_count == 2

    def test_falsey_values_not_treated_as_false(self):
        # 仅严格等于 False 才阻止，None/0/""不阻止
        d = HookDispatcher()
        d.register(HookPoint.NOVA_LAUNCH, lambda: None)
        d.register(HookPoint.NOVA_LAUNCH, lambda: 0)
        d.register(HookPoint.NOVA_LAUNCH, lambda: "")
        assert d.dispatch_until_false(HookPoint.NOVA_LAUNCH) is True

    def test_passes_args(self):
        d = HookDispatcher()
        captured = []

        def handler(nova, star):
            captured.append((nova, star))
            return True

        d.register(HookPoint.NOVA_LAUNCH, handler)
        d.dispatch_until_false(HookPoint.NOVA_LAUNCH, "nova1", "star1")
        assert captured == [("nova1", "star1")]


# ========== 异常隔离测试 ==========

class TestExceptionIsolation:
    """测试异常隔离：处理器异常不影响其他处理器"""

    def test_dispatch_isolates_exception(self):
        d = HookDispatcher()
        d.register(HookPoint.NOVA_CREATE, lambda: 1)

        def raise_handler():
            raise ValueError("boom")

        d.register(HookPoint.NOVA_CREATE, raise_handler)
        d.register(HookPoint.NOVA_CREATE, lambda: 3)

        results = d.dispatch(HookPoint.NOVA_CREATE)
        # 异常处理器返回 None，其他正常执行
        assert results == [1, None, 3]

    def test_dispatch_exception_does_not_propagate(self):
        d = HookDispatcher()

        def raise_handler():
            raise RuntimeError("fatal")

        d.register(HookPoint.NOVA_CREATE, raise_handler)
        # 不应抛出异常
        results = d.dispatch(HookPoint.NOVA_CREATE)
        assert results == [None]

    def test_dispatch_until_false_isolates_exception(self):
        d = HookDispatcher()
        d.register(HookPoint.NOVA_LAUNCH, lambda: True)

        def raise_handler():
            raise ValueError("boom")

        d.register(HookPoint.NOVA_LAUNCH, raise_handler)
        d.register(HookPoint.NOVA_LAUNCH, lambda: True)

        # 异常被隔离，整体应返回 True（没有处理器显式返回 False）
        assert d.dispatch_until_false(HookPoint.NOVA_LAUNCH) is True

    def test_multiple_exceptions_isolated(self):
        d = HookDispatcher()

        def raise1():
            raise ValueError("e1")

        def raise2():
            raise RuntimeError("e2")

        d.register(HookPoint.NOVA_CREATE, raise1)
        d.register(HookPoint.NOVA_CREATE, raise2)
        d.register(HookPoint.NOVA_CREATE, lambda: "ok")

        results = d.dispatch(HookPoint.NOVA_CREATE)
        assert results == [None, None, "ok"]


# ========== clear 测试 ==========

class TestClear:
    """测试 clear 清空所有钩子"""

    def test_clear_removes_all_hooks(self):
        d = HookDispatcher()
        d.register(HookPoint.NOVA_CREATE, lambda: 1)
        d.register(HookPoint.NOVA_LAUNCH, lambda: 2)
        d.register(HookPoint.SYSTEM_STARTUP, lambda: 3)

        d.clear()

        assert d.has_hooks(HookPoint.NOVA_CREATE) is False
        assert d.has_hooks(HookPoint.NOVA_LAUNCH) is False
        assert d.has_hooks(HookPoint.SYSTEM_STARTUP) is False
        assert d.dispatch(HookPoint.NOVA_CREATE) == []

    def test_clear_empty_dispatcher(self):
        d = HookDispatcher()
        d.clear()
        # 不报错即可
        assert d.dispatch(HookPoint.NOVA_CREATE) == []

    def test_clear_then_register_again(self):
        d = HookDispatcher()
        d.register(HookPoint.NOVA_CREATE, lambda: 1)
        d.clear()
        d.register(HookPoint.NOVA_CREATE, lambda: 2)
        assert d.dispatch(HookPoint.NOVA_CREATE) == [2]


# ========== 全局单例测试 ==========

class TestGlobalDispatcher:
    """测试 get_hook_dispatcher 全局单例"""

    def test_get_dispatcher_returns_instance(self):
        d = get_hook_dispatcher()
        assert d is not None
        assert isinstance(d, HookDispatcher)

    def test_singleton_identity(self):
        d1 = get_hook_dispatcher()
        d2 = get_hook_dispatcher()
        assert d1 is d2


# ========== 线程安全测试 ==========

class TestThreadSafety:
    """测试线程安全"""

    def test_concurrent_register(self):
        d = HookDispatcher()
        N = 20
        threads = []

        def register_handler(i):
            d.register(HookPoint.NOVA_CREATE, lambda i=i: i)

        for i in range(N):
            t = threading.Thread(target=register_handler, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(d.dispatch(HookPoint.NOVA_CREATE)) == N

    def test_concurrent_dispatch(self):
        d = HookDispatcher()
        d.register(HookPoint.NOVA_CREATE, lambda: 1)
        results = []
        lock = threading.Lock()

        def dispatch():
            r = d.dispatch(HookPoint.NOVA_CREATE)
            with lock:
                results.append(r)

        threads = [threading.Thread(target=dispatch) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 20
        for r in results:
            assert r == [1]

    def test_concurrent_register_and_unregister(self):
        d = HookDispatcher()

        def register_loop():
            for i in range(50):
                d.register(HookPoint.NOVA_CREATE, lambda i=i: i)

        def unregister_loop():
            # 尝试注销（即使不存在也不报错）
            for i in range(50):
                d.unregister(HookPoint.NOVA_CREATE, lambda i=i: i)

        t1 = threading.Thread(target=register_loop)
        t2 = threading.Thread(target=unregister_loop)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        # 不报错、不死锁即可

    def test_concurrent_dispatch_until_false(self):
        d = HookDispatcher()
        d.register(HookPoint.NOVA_LAUNCH, lambda: True)
        results = []
        lock = threading.Lock()

        def dispatch():
            r = d.dispatch_until_false(HookPoint.NOVA_LAUNCH)
            with lock:
                results.append(r)

        threads = [threading.Thread(target=dispatch) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 20
        for r in results:
            assert r is True

    def test_concurrent_clear_and_dispatch(self):
        d = HookDispatcher()
        d.register(HookPoint.NOVA_CREATE, lambda: 1)

        def clear_loop():
            for _ in range(10):
                d.clear()
                d.register(HookPoint.NOVA_CREATE, lambda: 1)

        def dispatch_loop():
            for _ in range(10):
                d.dispatch(HookPoint.NOVA_CREATE)

        t1 = threading.Thread(target=clear_loop)
        t2 = threading.Thread(target=dispatch_loop)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        # 不报错、不死锁即可
