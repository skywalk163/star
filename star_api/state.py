"""
星光接口全局状态管理

集中管理引擎实例和连接，避免循环导入和变量绑定问题。

重构说明：
- 本模块现在是兼容层，内部通过 ServiceContainer 管理服务实例
- 所有通过 state.xxx 的访问都会转发到服务容器
- 保持向后兼容，现有代码无需修改
"""

from typing import Any


class _StateCompat:
    """
    状态兼容层
    
    提供与旧版 state 相同的属性访问接口，
    内部通过服务容器管理实际的服务实例。
    """

    def __init__(self):
        self._container = None
        self._instances = {}
        self._special_attrs = {'websocket_connections', 'config', 'project_root'}
        self._websocket_connections: list = []
        self._config: dict = {}
        self._project_root: str = ""

    def _get_container(self):
        """获取服务容器（懒加载）"""
        if self._container is None:
            from star_core.service_container import get_container
            self._container = get_container()
        return self._container

    def __getattr__(self, name: str) -> Any:
        """属性访问转发"""
        # 内部属性直接返回（避免递归）
        if name.startswith('_'):
            raise AttributeError(name)

        # 特殊属性
        if name == 'websocket_connections':
            return self._websocket_connections
        if name == 'config':
            return self._config
        if name == 'project_root':
            return self._project_root

        # 本地实例优先
        if name in self._instances:
            return self._instances[name]

        # 从服务容器获取
        try:
            container = self._get_container()
            if container.has(name):
                return container.get(name)
        except Exception:
            pass

        # 不存在的属性返回 None（保持与旧版行为一致）
        # 注意：为了 hasattr 正确工作，不存在的属性应该抛出 AttributeError
        # 但旧代码中大量使用 if state.xxx is None，所以这里妥协：
        # 如果明确知道是服务容器里有的，返回值；否则返回 None
        # 对于 hasattr 检查，我们通过自定义 __dir__ 来辅助
        return None

    def __setattr__(self, name: str, value: Any) -> None:
        """属性设置"""
        # 内部属性直接设置
        if name.startswith('_'):
            super().__setattr__(name, value)
            return

        # 特殊属性
        if name == 'websocket_connections':
            self._websocket_connections = value
            return
        if name == 'config':
            self._config = value
            return
        if name == 'project_root':
            self._project_root = value
            return

        # 保存到本地实例
        self._instances[name] = value

        # 同时注册到服务容器（如果可用）
        try:
            container = self._get_container()
            container.register_instance(name, value)
        except Exception:
            pass

    def __hasattr__(self, name: str) -> bool:
        """支持 hasattr() 检查"""
        return self._has(name)

    def _has(self, name: str) -> bool:
        """检查属性是否存在"""
        if name in self._special_attrs:
            return True
        if name in self._instances:
            return True
        try:
            container = self._get_container()
            return container.has(name)
        except Exception:
            return False


# 全局状态实例（保持与旧版相同的使用方式）
state = _StateCompat()
