"""
service_container.py - 服务容器

统一管理所有服务实例，避免循环导入和全局变量散落。
采用懒加载模式，按需初始化服务。
"""

import threading
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field


class ServiceContainer:
    """
    服务容器 - 统一管理应用服务实例
    
    特性：
    - 懒加载：按需初始化
    - 单例：每个服务只有一个实例
    - 线程安全：并发访问安全
    - 可替换：测试时可替换为 mock
    """
    
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._lock = threading.RLock()
    
    def register_factory(self, name: str, factory: Callable):
        """注册服务工厂函数"""
        with self._lock:
            self._factories[name] = factory
    
    def register_instance(self, name: str, instance: Any):
        """直接注册服务实例"""
        with self._lock:
            self._services[name] = instance
    
    def get(self, name: str) -> Any:
        """获取服务实例（懒加载）"""
        with self._lock:
            if name in self._services:
                return self._services[name]
            
            if name not in self._factories:
                raise KeyError(f"Service '{name}' not registered")
            
            factory = self._factories[name]
            instance = factory()
            self._services[name] = instance
            return instance
    
    def has(self, name: str) -> bool:
        """检查服务是否已注册（工厂或实例）"""
        with self._lock:
            return name in self._services or name in self._factories
    
    def clear(self):
        """清空所有服务（测试用）"""
        with self._lock:
            self._services.clear()
            self._factories.clear()
    
    def reset(self, name: str = None):
        """重置指定服务（下次获取时重新创建）"""
        with self._lock:
            if name:
                self._services.pop(name, None)
            else:
                self._services.clear()
    
    # ========== 便捷属性访问 ==========
    
    @property
    def config_service(self):
        """配置服务"""
        return self.get('config_service')
    
    @property
    def db_service(self):
        """数据库服务"""
        return self.get('db_service')
    
    @property
    def audit_logger(self):
        """审计日志"""
        return self.get('audit_logger')
    
    @property
    def star_seeker(self):
        """寻星者"""
        return self.get('star_seeker')
    
    @property
    def orbit_engine(self):
        """轨道引擎"""
        return self.get('orbit_engine')
    
    @property
    def plugin_manager(self):
        """插件管理器"""
        return self.get('plugin_manager')
    
    @property
    def hook_dispatcher(self):
        """钩子分发器"""
        return self.get('hook_dispatcher')


# 全局容器实例
_container: Optional[ServiceContainer] = None
_init_lock = threading.Lock()


def get_container() -> ServiceContainer:
    """获取全局服务容器"""
    global _container
    if _container is None:
        with _init_lock:
            if _container is None:
                _container = ServiceContainer()
                _register_default_services(_container)
    return _container


def _register_default_services(container: ServiceContainer):
    """注册默认服务工厂"""
    
    def config_factory():
        from star_core.config_service import get_config_service
        return get_config_service()
    
    def db_factory():
        from star_core.database import get_db_service
        return get_db_service()
    
    def audit_factory():
        from star_core.star_auditor import get_audit_logger
        return get_audit_logger()
    
    def observatory_factory():
        from star_core.observatory import Observatory
        return Observatory()
    
    def seeker_factory():
        from star_core.star_seeker import StarSeeker
        obs = container.get('observatory')
        plugin_mgr = None
        if container.has('plugin_manager'):
            try:
                plugin_mgr = container.get('plugin_manager')
            except Exception:
                pass
        return StarSeeker(observatory=obs, plugin_manager=plugin_mgr)
    
    def hook_dispatcher_factory():
        from star_core.plugin_hooks import get_hook_dispatcher
        return get_hook_dispatcher()
    
    container.register_factory('config_service', config_factory)
    container.register_factory('db_service', db_factory)
    container.register_factory('audit_logger', audit_factory)
    container.register_factory('observatory', observatory_factory)
    container.register_factory('star_seeker', seeker_factory)
    container.register_factory('hook_dispatcher', hook_dispatcher_factory)
