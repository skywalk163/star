"""
星图插件系统（Star Plugin System）

提供可扩展的插件架构，支持：
- 自定义星体类型
- 自定义注入策略
- 自定义观星策略
- 任务钩子
"""

import importlib
import inspect
import logging
import pkgutil
from typing import Optional, Type, Any
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import sys

logger = logging.getLogger(__name__)


class PluginType(Enum):
    """插件类型"""
    STAR = "star"              # 星体插件（自定义星体类型）
    INJECTOR = "injector"      # 注入策略插件
    GAZER = "gazer"            # 观星策略插件
    HOOK = "hook"              # 任务钩子插件
    EXTENSION = "extension"    # 通用扩展插件


class PluginStatus(Enum):
    """插件状态"""
    DISABLED = "disabled"       # 已禁用
    LOADED = "loaded"           # 已加载
    ACTIVE = "active"           # 已激活
    ERROR = "error"             # 加载错误


@dataclass
class PluginInfo:
    """插件信息"""
    name: str
    version: str
    author: str
    description: str
    plugin_type: PluginType
    status: PluginStatus = PluginStatus.DISABLED
    error_message: Optional[str] = None
    module_path: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "type": self.plugin_type.value,
            "status": self.status.value,
            "error": self.error_message
        }


class StarPlugin(ABC):
    """
    星体插件基类
    
    实现自定义星体类型，继承此类并实现必要方法。
    """
    
    # 插件元信息（子类必须重写）
    PLUGIN_NAME = "custom_star"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "anonymous"
    PLUGIN_DESCRIPTION = "自定义星体插件"
    
    # 星体签名（子类必须重写）
    STAR_TYPE = ""
    PROCESS_NAMES: list[str] = []
    WINDOW_CLASS: list[str] = []
    WINDOW_TITLE_PATTERNS: list[str] = []
    DESCRIPTION = ""
    
    # 亲缘性关键词
    AFFINITY_KEYWORDS: list[str] = []
    AFFINITY_WEIGHT: float = 1.0
    
    def __init__(self):
        self._enabled = True
    
    @abstractmethod
    def get_star_signature(self) -> dict:
        """
        获取星体签名（用于 StarSeeker 识别）
        
        Returns:
            签名字典，包含 process_names, window_class, window_title_patterns
        """
        pass
    
    def get_affinity(self) -> dict:
        """
        获取亲缘性配置（用于智能路由）
        
        Returns:
            亲缘性字典，包含 keywords 和 weight
        """
        return {
            "keywords": self.AFFINITY_KEYWORDS,
            "weight": self.AFFINITY_WEIGHT
        }
    
    def on_inject(self, star_body, text: str) -> bool:
        """
        自定义注入逻辑（可选）
        
        返回 True 表示已处理，False 表示使用默认策略
        """
        return False
    
    def on_gaze(self, star_body) -> Optional[str]:
        """
        自定义观星逻辑（可选）
        
        返回 None 表示使用默认策略
        """
        return None
    
    def on_launch(self, star_body, nova) -> bool:
        """
        发射前钩子（可选）
        
        返回 False 可以阻止发射
        """
        return True
    
    def on_complete(self, star_body, nova) -> None:
        """
        完成后钩子（可选）
        """
        pass


class InjectorPlugin(ABC):
    """
    注入策略插件基类
    
    实现自定义文本注入策略
    """
    
    PLUGIN_NAME = "custom_injector"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "anonymous"
    PLUGIN_DESCRIPTION = "自定义注入策略插件"
    
    STRATEGY_NAME = "custom"
    STRATEGY_PRIORITY = 10  # 数值越大优先级越高
    
    @abstractmethod
    def inject(self, hwnd: int, text: str) -> bool:
        """
        执行注入
        
        Args:
            hwnd: 目标窗口句柄
            text: 要注入的文本
            
        Returns:
            是否成功
        """
        pass
    
    def cleanup(self) -> None:
        """清理资源（可选）"""
        pass


class GazerPlugin(ABC):
    """
    观星策略插件基类
    
    实现自定义输出捕获策略
    """
    
    PLUGIN_NAME = "custom_gazer"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "anonymous"
    PLUGIN_DESCRIPTION = "自定义观星策略插件"
    
    @abstractmethod
    def capture(self, hwnd: int) -> Optional[str]:
        """
        捕获输出
        
        Args:
            hwnd: 目标窗口句柄
            
        Returns:
            捕获的文本，None 表示未捕获到
        """
        pass


class HookPlugin(ABC):
    """
    任务钩子插件基类
    
    在任务生命周期的各个节点插入自定义逻辑
    """
    
    PLUGIN_NAME = "custom_hook"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "anonymous"
    PLUGIN_DESCRIPTION = "自定义任务钩子插件"
    
    def on_nova_create(self, nova) -> None:
        """新星创建时"""
        pass
    
    def on_nova_launch(self, nova, star_body) -> bool:
        """
        新星发射前
        
        返回 False 可阻止发射
        """
        return True
    
    def on_nova_shine(self, nova, star_body) -> None:
        """新星开始闪耀时"""
        pass
    
    def on_starlight_received(self, nova, content: str) -> None:
        """收到星辉时"""
        pass
    
    def on_nova_complete(self, nova) -> None:
        """新星完成时"""
        pass
    
    def on_nova_fade(self, nova, reason: str) -> None:
        """新星失败时"""
        pass
    
    def on_star_discovered(self, star_body) -> None:
        """星体发现时"""
        pass
    
    def on_star_lost(self, star_body) -> None:
        """星体丢失时"""
        pass
    
    def on_constellation_create(self, constellation) -> None:
        """星座创建时"""
        pass
    
    def on_constellation_complete(self, constellation) -> None:
        """星座完成时"""
        pass
    
    def on_system_startup(self) -> None:
        """系统启动时"""
        pass
    
    def on_system_shutdown(self) -> None:
        """系统关闭时"""
        pass


class PluginManager:
    """
    插件管理器
    
    负责插件的发现、加载、注册和管理
    """
    
    def __init__(self, plugin_dir: Optional[str] = None):
        self._plugins: dict[str, Any] = {}
        self._plugin_infos: dict[str, PluginInfo] = {}
        self._star_plugins: dict[str, StarPlugin] = {}
        self._injector_plugins: list[InjectorPlugin] = []
        self._gazer_plugins: list[GazerPlugin] = []
        self._hook_plugins: list[HookPlugin] = []
        
        self._plugin_dir = plugin_dir or "star_plugins"
        self._loaded = False
    
    def discover_plugins(self) -> list[PluginInfo]:
        """
        发现所有可用插件
        
        Returns:
            发现的插件信息列表
        """
        discovered = []
        
        # 从插件目录发现
        plugin_path = Path(self._plugin_dir)
        if plugin_path.exists():
            discovered.extend(self._discover_from_directory(plugin_path))
        
        # 从已安装的包发现（star_* 命名约定）
        discovered.extend(self._discover_from_entry_points())
        
        return discovered
    
    def _discover_from_directory(self, directory: Path) -> list[PluginInfo]:
        """从目录发现插件"""
        infos = []
        
        if not directory.exists():
            return infos
        
        # 添加到 sys.path
        dir_str = str(directory.resolve())
        if dir_str not in sys.path:
            sys.path.insert(0, dir_str)
        
        for item in directory.iterdir():
            if item.is_dir() and not item.name.startswith('_'):
                # 尝试作为包导入
                try:
                    module = importlib.import_module(item.name)
                    plugin_class = self._find_plugin_class(module)
                    if plugin_class:
                        info = self._create_plugin_info(plugin_class, item.name)
                        infos.append(info)
                except Exception as e:
                    pass
            elif item.suffix == '.py' and not item.name.startswith('_'):
                # 尝试作为模块导入
                try:
                    module_name = item.stem
                    module = importlib.import_module(module_name)
                    plugin_class = self._find_plugin_class(module)
                    if plugin_class:
                        info = self._create_plugin_info(plugin_class, item.stem)
                        infos.append(info)
                except Exception as e:
                    pass
        
        return infos
    
    def _discover_from_entry_points(self) -> list[PluginInfo]:
        """从入口点发现插件"""
        infos = []
        
        try:
            from importlib.metadata import entry_points
            
            try:
                eps = entry_points(group='star_plugins')
            except TypeError:
                # 旧版本 Python 兼容
                eps = entry_points().get('star_plugins', [])
            
            for ep in eps:
                try:
                    plugin_class = ep.load()
                    info = self._create_plugin_info(plugin_class, ep.name)
                    infos.append(info)
                except Exception:
                    pass
        except Exception:
            pass
        
        return infos
    
    def _find_plugin_class(self, module) -> Optional[Type]:
        """在模块中查找插件类"""
        plugin_bases = (StarPlugin, InjectorPlugin, GazerPlugin, HookPlugin)
        
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (issubclass(obj, plugin_bases) and 
                obj not in plugin_bases and
                not inspect.isabstract(obj)):
                return obj
        
        return None
    
    def _create_plugin_info(self, plugin_class: Type, module_name: str) -> PluginInfo:
        """创建插件信息"""
        plugin_type = self._detect_plugin_type(plugin_class)
        
        return PluginInfo(
            name=getattr(plugin_class, 'PLUGIN_NAME', module_name),
            version=getattr(plugin_class, 'PLUGIN_VERSION', '0.0.0'),
            author=getattr(plugin_class, 'PLUGIN_AUTHOR', 'anonymous'),
            description=getattr(plugin_class, 'PLUGIN_DESCRIPTION', ''),
            plugin_type=plugin_type,
            status=PluginStatus.DISABLED,
            module_path=module_name
        )
    
    def _detect_plugin_type(self, plugin_class: Type) -> PluginType:
        """检测插件类型"""
        if issubclass(plugin_class, StarPlugin):
            return PluginType.STAR
        elif issubclass(plugin_class, InjectorPlugin):
            return PluginType.INJECTOR
        elif issubclass(plugin_class, GazerPlugin):
            return PluginType.GAZER
        elif issubclass(plugin_class, HookPlugin):
            return PluginType.HOOK
        else:
            return PluginType.EXTENSION
    
    def load_plugin(self, plugin_name: str) -> bool:
        """
        加载指定插件
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            是否成功加载
        """
        if plugin_name in self._plugins:
            return True
        
        # 先发现
        infos = self.discover_plugins()
        target_info = next(
            (i for i in infos if i.name == plugin_name),
            None
        )
        
        if not target_info:
            return False
        
        try:
            # 导入模块
            module = importlib.import_module(target_info.module_path)
            plugin_class = self._find_plugin_class(module)
            
            if not plugin_class:
                return False
            
            # 实例化
            plugin_instance = plugin_class()
            
            # 注册
            self._plugins[plugin_name] = plugin_instance
            self._plugin_infos[plugin_name] = target_info
            target_info.status = PluginStatus.LOADED
            
            # 按类型分类注册
            self._register_by_type(plugin_instance, target_info)
            
            return True
            
        except Exception as e:
            target_info.status = PluginStatus.ERROR
            target_info.error_message = str(e)
            return False
    
    def _register_by_type(self, plugin, info: PluginInfo):
        """按类型注册插件"""
        if isinstance(plugin, StarPlugin):
            star_type = getattr(plugin, 'STAR_TYPE', info.name)
            self._star_plugins[star_type] = plugin
        
        if isinstance(plugin, InjectorPlugin):
            self._injector_plugins.append(plugin)
            # 按优先级排序
            self._injector_plugins.sort(
                key=lambda p: getattr(p, 'STRATEGY_PRIORITY', 0),
                reverse=True
            )
        
        if isinstance(plugin, GazerPlugin):
            self._gazer_plugins.append(plugin)
        
        if isinstance(plugin, HookPlugin):
            self._hook_plugins.append(plugin)
    
    def _get_hook_mappings(self) -> dict:
        """获取钩子方法名到 HookPoint 的映射"""
        from star_core.plugin_hooks import HookPoint
        
        return {
            'on_nova_create': HookPoint.NOVA_CREATE,
            'on_nova_launch': HookPoint.NOVA_LAUNCH,
            'on_nova_shine': HookPoint.NOVA_SHINE,
            'on_starlight_received': HookPoint.STARLIGHT_RECEIVED,
            'on_nova_complete': HookPoint.NOVA_COMPLETE,
            'on_nova_fade': HookPoint.NOVA_FADE,
            'on_star_discovered': HookPoint.STAR_DISCOVERED,
            'on_star_lost': HookPoint.STAR_LOST,
            'on_constellation_create': HookPoint.CONSTELLATION_CREATE,
            'on_constellation_complete': HookPoint.CONSTELLATION_COMPLETE,
            'on_system_startup': HookPoint.SYSTEM_STARTUP,
            'on_system_shutdown': HookPoint.SYSTEM_SHUTDOWN,
        }
    
    def _register_plugin_hooks(self, plugin_name: str, plugin):
        """注册插件钩子到全局分发器"""
        from star_core.plugin_hooks import get_hook_dispatcher
        
        dispatcher = get_hook_dispatcher()
        hook_mappings = self._get_hook_mappings()
        
        for method_name, hook_point in hook_mappings.items():
            if hasattr(plugin, method_name):
                handler = getattr(plugin, method_name)
                dispatcher.register(hook_point, handler)
                logger.debug(f"Registered hook {hook_point.value} from plugin {plugin_name}")
    
    def _unregister_plugin_hooks(self, plugin_name: str, plugin):
        """从全局分发器注销插件钩子"""
        from star_core.plugin_hooks import get_hook_dispatcher
        
        dispatcher = get_hook_dispatcher()
        hook_mappings = self._get_hook_mappings()
        
        for method_name, hook_point in hook_mappings.items():
            if hasattr(plugin, method_name):
                handler = getattr(plugin, method_name)
                dispatcher.unregister(hook_point, handler)
                logger.debug(f"Unregistered hook {hook_point.value} from plugin {plugin_name}")
    
    def _activate_plugin(self, plugin_name: str):
        """激活插件"""
        info = self._plugin_infos.get(plugin_name)
        if not info:
            return
        info.status = PluginStatus.ACTIVE
        info.error_message = None
        
        plugin = self._plugins.get(plugin_name)
        if plugin and isinstance(plugin, HookPlugin):
            self._register_plugin_hooks(plugin_name, plugin)

    def _deactivate_plugin(self, plugin_name: str):
        """停用插件"""
        info = self._plugin_infos.get(plugin_name)
        if not info:
            return
        
        plugin = self._plugins.get(plugin_name)
        if plugin and isinstance(plugin, HookPlugin):
            self._unregister_plugin_hooks(plugin_name, plugin)
        
        info.status = PluginStatus.LOADED

    def enable_plugin(self, plugin_name: str) -> bool:
        """启用插件"""
        if plugin_name not in self._plugin_infos:
            if not self.load_plugin(plugin_name):
                return False
        
        info = self._plugin_infos[plugin_name]
        if info.status == PluginStatus.ACTIVE:
            return True
        
        try:
            self._activate_plugin(plugin_name)
            
            try:
                from star_core.database import get_db_service
                db = get_db_service()
                existing_cfg = db.get_plugin_config(plugin_name)
                config = existing_cfg.get('config', {}) if existing_cfg else {}
                db.save_plugin_config(plugin_name, True, config)
            except Exception as e:
                logger.warning(f"Failed to save plugin config for {plugin_name}: {e}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to enable plugin {plugin_name}: {e}")
            info.status = PluginStatus.ERROR
            info.error_message = str(e)
            return False
    
    def disable_plugin(self, plugin_name: str) -> bool:
        """禁用插件"""
        if plugin_name not in self._plugin_infos:
            return False
        
        info = self._plugin_infos[plugin_name]
        if info.status != PluginStatus.ACTIVE:
            return True
        
        try:
            self._deactivate_plugin(plugin_name)
            
            try:
                from star_core.database import get_db_service
                db = get_db_service()
                existing_cfg = db.get_plugin_config(plugin_name)
                config = existing_cfg.get('config', {}) if existing_cfg else {}
                db.save_plugin_config(plugin_name, False, config)
            except Exception as e:
                logger.warning(f"Failed to save plugin config for {plugin_name}: {e}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to disable plugin {plugin_name}: {e}")
            return False

    def configure_plugin(self, plugin_name: str, config: dict) -> bool:
        """配置插件"""
        try:
            if plugin_name in self._plugins:
                plugin = self._plugins[plugin_name]
                if hasattr(plugin, 'configure'):
                    plugin.configure(config)
            
            try:
                from star_core.database import get_db_service
                db = get_db_service()
                info = self._plugin_infos.get(plugin_name)
                enabled = info.status == PluginStatus.ACTIVE if info else False
                db.save_plugin_config(plugin_name, enabled, config)
            except Exception as e:
                logger.warning(f"Failed to save plugin config for {plugin_name}: {e}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to configure plugin {plugin_name}: {e}")
            return False

    def get_plugin_config(self, plugin_name: str) -> dict:
        """获取插件配置"""
        try:
            from star_core.database import get_db_service
            db = get_db_service()
            cfg = db.get_plugin_config(plugin_name)
            return cfg.get('config', {}) if cfg else {}
        except Exception as e:
            logger.warning(f"Failed to get plugin config for {plugin_name}: {e}")
            return {}

    def load_enabled_plugins_from_db(self):
        """从数据库加载已启用的插件"""
        try:
            from star_core.database import get_db_service
            db = get_db_service()
            configs = db.list_plugin_configs()
            for cfg in configs:
                if cfg.get('enabled'):
                    try:
                        self.enable_plugin(cfg['plugin_name'])
                    except Exception as e:
                        logger.warning(f"Failed to enable plugin {cfg['plugin_name']} from DB: {e}")
        except Exception as e:
            logger.warning(f"Failed to load enabled plugins from DB: {e}")
    
    def get_plugin(self, plugin_name: str) -> Optional[Any]:
        """获取插件实例"""
        return self._plugins.get(plugin_name)
    
    def get_plugin_info(self, plugin_name: str) -> Optional[PluginInfo]:
        """获取插件信息"""
        return self._plugin_infos.get(plugin_name)
    
    def list_plugins(self, plugin_type: Optional[PluginType] = None) -> list[PluginInfo]:
        """列出所有插件"""
        infos = list(self._plugin_infos.values())
        
        # 加上已发现但未加载的
        discovered = self.discover_plugins()
        loaded_names = set(self._plugin_infos.keys())
        for info in discovered:
            if info.name not in loaded_names:
                infos.append(info)
        
        if plugin_type:
            infos = [i for i in infos if i.plugin_type == plugin_type]
        
        return infos
    
    def get_star_plugins(self) -> dict[str, StarPlugin]:
        """获取所有已激活的星体插件"""
        return {
            name: plugin
            for name, plugin in self._star_plugins.items()
            if self._plugin_infos.get(name, PluginInfo(
                name="", version="", author="", description="",
                plugin_type=PluginType.STAR
            )).status == PluginStatus.ACTIVE
        }
    
    def get_injector_plugins(self) -> list[InjectorPlugin]:
        """获取所有已激活的注入策略插件"""
        return [
            p for p in self._injector_plugins
            if self._plugin_infos.get(
                getattr(p, 'PLUGIN_NAME', ''), 
                PluginInfo(name="", version="", author="", description="", plugin_type=PluginType.INJECTOR)
            ).status == PluginStatus.ACTIVE
        ]
    
    def get_gazer_plugins(self) -> list[GazerPlugin]:
        """获取所有已激活的观星策略插件"""
        return [
            p for p in self._gazer_plugins
            if self._plugin_infos.get(
                getattr(p, 'PLUGIN_NAME', ''),
                PluginInfo(name="", version="", author="", description="", plugin_type=PluginType.GAZER)
            ).status == PluginStatus.ACTIVE
        ]
    
    def get_hook_plugins(self) -> list[HookPlugin]:
        """获取所有已激活的钩子插件"""
        return [
            p for p in self._hook_plugins
            if self._plugin_infos.get(
                getattr(p, 'PLUGIN_NAME', ''),
                PluginInfo(name="", version="", author="", description="", plugin_type=PluginType.HOOK)
            ).status == PluginStatus.ACTIVE
        ]
    
    def trigger_hook(self, hook_name: str, *args, **kwargs) -> list:
        """
        触发钩子
        
        Args:
            hook_name: 钩子方法名
            *args, **kwargs: 参数
            
        Returns:
            所有钩子的返回值列表
        """
        results = []
        for hook in self.get_hook_plugins():
            method = getattr(hook, hook_name, None)
            if method and callable(method):
                try:
                    result = method(*args, **kwargs)
                    results.append(result)
                except Exception:
                    pass
        return results
