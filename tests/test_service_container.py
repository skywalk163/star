"""
服务容器测试

测试 star_core.service_container 中的 ServiceContainer
"""

import pytest
import threading
from star_core.service_container import ServiceContainer, get_container


class TestServiceContainer:
    """测试 ServiceContainer"""

    def test_create_container(self):
        container = ServiceContainer()
        assert container is not None

    def test_register_factory_and_get(self):
        container = ServiceContainer()
        container.register_factory('test_service', lambda: {'value': 42})
        svc = container.get('test_service')
        assert svc['value'] == 42

    def test_singleton_behavior(self):
        container = ServiceContainer()
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return {'count': call_count}

        container.register_factory('counter', factory)
        svc1 = container.get('counter')
        svc2 = container.get('counter')
        assert svc1 is svc2
        assert call_count == 1

    def test_register_instance(self):
        container = ServiceContainer()
        instance = {'key': 'value'}
        container.register_instance('my_svc', instance)
        assert container.get('my_svc') is instance

    def test_has_service(self):
        container = ServiceContainer()
        assert container.has('nonexistent') == False
        container.register_factory('exists', lambda: {})
        assert container.has('exists') == True

    def test_get_not_registered(self):
        container = ServiceContainer()
        with pytest.raises(KeyError):
            container.get('not_registered')

    def test_clear(self):
        container = ServiceContainer()
        container.register_factory('svc1', lambda: {})
        container.register_instance('svc2', {})
        assert container.has('svc1') == True
        assert container.has('svc2') == True
        container.clear()
        assert container.has('svc1') == False
        assert container.has('svc2') == False

    def test_reset_single(self):
        container = ServiceContainer()
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return call_count

        container.register_factory('counter', factory)
        container.get('counter')
        assert call_count == 1
        container.reset('counter')
        container.get('counter')
        assert call_count == 2

    def test_reset_all(self):
        container = ServiceContainer()
        container.register_factory('a', lambda: 1)
        container.register_factory('b', lambda: 2)
        container.get('a')
        container.get('b')
        container.reset()
        # 重置后应该没有缓存的实例了
        assert 'a' not in container._services
        assert 'b' not in container._services

    def test_thread_safety(self):
        container = ServiceContainer()
        container.register_factory('thread_svc', lambda: {'val': 0})

        results = []

        def get_service():
            svc = container.get('thread_svc')
            results.append(svc)

        threads = [threading.Thread(target=get_service) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        # 所有线程获取的应该是同一个实例
        for r in results:
            assert r is results[0]


class TestGlobalContainer:
    """测试全局容器实例"""

    def test_get_container(self):
        container = get_container()
        assert container is not None
        assert isinstance(container, ServiceContainer)

    def test_singleton(self):
        c1 = get_container()
        c2 = get_container()
        assert c1 is c2

    def test_default_services_registered(self):
        container = get_container()
        # 配置服务应该已经注册
        assert container.has('config_service')
        assert container.has('db_service')
        assert container.has('audit_logger')

    def test_config_service_property(self):
        container = get_container()
        svc = container.config_service
        assert svc is not None

    def test_db_service_property(self):
        container = get_container()
        svc = container.db_service
        assert svc is not None

    def test_audit_logger_property(self):
        container = get_container()
        svc = container.audit_logger
        assert svc is not None
