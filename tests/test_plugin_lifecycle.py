"""
插件系统生命周期测试

测试 star_core.plugin_system 中新增的生命周期管理功能：
- enable_plugin / disable_plugin
- configure_plugin / get_plugin_config
- load_enabled_plugins_from_db
- _activate_plugin / _deactivate_plugin
- _register_plugin_hooks / _unregister_plugin_hooks
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from star_core.plugin_system import (
    PluginManager,
    PluginInfo,
    PluginType,
    PluginStatus,
    StarPlugin,
    HookPlugin,
    InjectorPlugin,
    GazerPlugin,
)
from star_core.plugin_hooks import HookPoint, get_hook_dispatcher


# ========== 测试用插件类 ==========

class SampleHookPlugin(HookPlugin):
    """测试用钩子插件"""
    PLUGIN_NAME = "sample_hook"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_AUTHOR = "tester"
    PLUGIN_DESCRIPTION = "sample hook plugin"

    def __init__(self):
        self.call_log = []
        self._config = None

    def on_nova_create(self, nova) -> None:
        self.call_log.append(("on_nova_create", nova))

    def on_nova_launch(self, nova, star_body) -> bool:
        self.call_log.append(("on_nova_launch", nova, star_body))
        return True

    def on_nova_complete(self, nova) -> None:
        self.call_log.append(("on_nova_complete", nova))

    def on_system_startup(self) -> None:
        self.call_log.append(("on_system_startup",))

    def configure(self, config: dict):
        self._config = config


class ConfigurableHookPlugin(HookPlugin):
    """带 configure 方法的钩子插件"""
    PLUGIN_NAME = "configurable_hook"
    PLUGIN_VERSION = "1.0.0"

    def __init__(self):
        self.config = {}

    def configure(self, config: dict):
        self.config = config

    def on_nova_create(self, nova) -> None:
        pass


class SampleStarPlugin(StarPlugin):
    """测试用星体插件（非钩子）"""
    PLUGIN_NAME = "sample_star"
    STAR_TYPE = "sample_star_type"

    def get_star_signature(self) -> dict:
        return {
            "process_names": ["sample.exe"],
            "window_class": ["SampleClass"],
            "window_title_patterns": ["Sample"],
        }


class SampleInjectorPlugin(InjectorPlugin):
    """测试用注入插件"""
    PLUGIN_NAME = "sample_injector"
    STRATEGY_NAME = "sample"
    STRATEGY_PRIORITY = 5

    def inject(self, hwnd: int, text: str) -> bool:
        return True


# ========== Fixtures ==========

@pytest.fixture(autouse=True)
def clean_global_dispatcher():
    """每个测试前后清空全局钩子分发器，避免测试间相互干扰"""
    dispatcher = get_hook_dispatcher()
    dispatcher.clear()
    yield
    dispatcher.clear()


@pytest.fixture
def mock_db():
    """Mock 数据库服务，避免真实 DB 交互"""
    db_mock = MagicMock()
    db_mock.get_plugin_config.return_value = None
    db_mock.list_plugin_configs.return_value = []
    db_mock.save_plugin_config.return_value = None
    db_mock.health_check.return_value = True
    with patch('star_core.database.get_db_service', return_value=db_mock):
        yield db_mock


@pytest.fixture
def manager():
    """创建独立的 PluginManager 实例"""
    return PluginManager()


def make_plugin_info(name="sample_hook", plugin_type=PluginType.HOOK, status=PluginStatus.LOADED):
    """构造测试用 PluginInfo"""
    return PluginInfo(
        name=name,
        version="1.0.0",
        author="tester",
        description="test plugin",
        plugin_type=plugin_type,
        status=status,
        module_path=f"test_module_{name}",
    )


def load_plugin_into_manager(mgr, plugin, name=None, plugin_type=PluginType.HOOK, status=PluginStatus.LOADED):
    """将插件实例直接装入管理器（绕过磁盘发现）"""
    pname = name or getattr(plugin, 'PLUGIN_NAME', 'unknown')
    info = make_plugin_info(pname, plugin_type, status)
    mgr._plugins[pname] = plugin
    mgr._plugin_infos[pname] = info
    # 按类型分类注册（模拟 load_plugin 的行为）
    mgr._register_by_type(plugin, info)
    return pname, info


# ========== enable_plugin 测试 ==========

class TestEnablePlugin:
    """测试 enable_plugin"""

    def test_enable_loaded_plugin(self, manager, mock_db):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin)
        assert info.status == PluginStatus.LOADED

        result = manager.enable_plugin(pname)
        assert result is True
        assert info.status == PluginStatus.ACTIVE
        assert info.error_message is None

    def test_enable_registers_hooks_for_hook_plugin(self, manager, mock_db):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin)

        dispatcher = get_hook_dispatcher()
        # 激活前没有钩子
        assert not dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        manager.enable_plugin(pname)

        # 激活后钩子应已注册
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)
        assert dispatcher.has_hooks(HookPoint.NOVA_LAUNCH)
        assert dispatcher.has_hooks(HookPoint.SYSTEM_STARTUP)

    def test_enable_already_active_returns_true(self, manager, mock_db):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, status=PluginStatus.ACTIVE)

        result = manager.enable_plugin(pname)
        assert result is True
        assert info.status == PluginStatus.ACTIVE

    def test_enable_saves_config_to_db(self, manager, mock_db):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin)

        manager.enable_plugin(pname)

        # 应该调用 save_plugin_config 保存启用状态
        mock_db.save_plugin_config.assert_called_once()
        call_args = mock_db.save_plugin_config.call_args
        assert call_args[0][0] == pname  # plugin_name
        assert call_args[0][1] is True    # enabled = True

    def test_enable_reads_existing_config_from_db(self, manager, mock_db):
        mock_db.get_plugin_config.return_value = {'config': {'key': 'value'}}
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin)

        manager.enable_plugin(pname)

        # 应该读取现有配置并保存（enabled=True）
        mock_db.get_plugin_config.assert_called_with(pname)
        save_call = mock_db.save_plugin_config.call_args
        assert save_call[0][2] == {'key': 'value'}  # config 保留

    def test_enable_nonexistent_plugin_returns_false(self, manager, mock_db):
        # 插件不在 _plugin_infos 中，且 load_plugin 会发现不到
        result = manager.enable_plugin("nonexistent_plugin_xyz")
        assert result is False

    def test_enable_does_not_register_hooks_for_star_plugin(self, manager, mock_db):
        plugin = SampleStarPlugin()
        pname, info = load_plugin_into_manager(
            manager, plugin, name="sample_star", plugin_type=PluginType.STAR
        )

        dispatcher = get_hook_dispatcher()
        manager.enable_plugin(pname)

        assert info.status == PluginStatus.ACTIVE
        # 星体插件不是 HookPlugin，不应注册钩子
        assert not dispatcher.has_hooks(HookPoint.NOVA_CREATE)

    def test_enable_works_without_db(self, manager):
        # 不使用 mock_db fixture，DB 调用会失败但应被捕获
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin)

        result = manager.enable_plugin(pname)
        # 即使 DB 失败，启用仍应成功
        assert result is True
        assert info.status == PluginStatus.ACTIVE


# ========== disable_plugin 测试 ==========

class TestDisablePlugin:
    """测试 disable_plugin"""

    def test_disable_active_plugin(self, manager, mock_db):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, status=PluginStatus.ACTIVE)
        # 先注册钩子
        manager._register_plugin_hooks(pname, plugin)

        dispatcher = get_hook_dispatcher()
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        result = manager.disable_plugin(pname)
        assert result is True
        assert info.status == PluginStatus.LOADED

    def test_disable_unregisters_hooks(self, manager, mock_db):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, status=PluginStatus.ACTIVE)
        manager._register_plugin_hooks(pname, plugin)

        dispatcher = get_hook_dispatcher()
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        manager.disable_plugin(pname)

        # 禁用后钩子应被注销
        assert not dispatcher.has_hooks(HookPoint.NOVA_CREATE)
        assert not dispatcher.has_hooks(HookPoint.NOVA_LAUNCH)

    def test_disable_already_loaded_returns_true(self, manager, mock_db):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, status=PluginStatus.LOADED)

        result = manager.disable_plugin(pname)
        assert result is True
        assert info.status == PluginStatus.LOADED

    def test_disable_disabled_returns_true(self, manager, mock_db):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, status=PluginStatus.DISABLED)

        result = manager.disable_plugin(pname)
        assert result is True

    def test_disable_nonexistent_returns_false(self, manager, mock_db):
        result = manager.disable_plugin("nonexistent")
        assert result is False

    def test_disable_saves_config_to_db(self, manager, mock_db):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, status=PluginStatus.ACTIVE)
        manager._register_plugin_hooks(pname, plugin)

        manager.disable_plugin(pname)

        mock_db.save_plugin_config.assert_called_once()
        call_args = mock_db.save_plugin_config.call_args
        assert call_args[0][0] == pname
        assert call_args[0][1] is False  # enabled = False

    def test_disable_star_plugin_no_hook_unregister(self, manager, mock_db):
        plugin = SampleStarPlugin()
        pname, info = load_plugin_into_manager(
            manager, plugin, name="sample_star",
            plugin_type=PluginType.STAR, status=PluginStatus.ACTIVE
        )

        # 星体插件不涉及钩子注销，但应正常停用
        result = manager.disable_plugin(pname)
        assert result is True
        assert info.status == PluginStatus.LOADED

    def test_enable_then_disable_cycle(self, manager, mock_db):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin)

        dispatcher = get_hook_dispatcher()

        # 启用
        manager.enable_plugin(pname)
        assert info.status == PluginStatus.ACTIVE
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        # 禁用
        manager.disable_plugin(pname)
        assert info.status == PluginStatus.LOADED
        assert not dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        # 再次启用
        manager.enable_plugin(pname)
        assert info.status == PluginStatus.ACTIVE
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)


# ========== configure_plugin / get_plugin_config 测试 ==========

class TestConfigurePlugin:
    """测试 configure_plugin 和 get_plugin_config"""

    def test_configure_calls_plugin_configure_method(self, manager, mock_db):
        plugin = ConfigurableHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, name="configurable_hook")

        config = {"timeout": 30, "retries": 3}
        result = manager.configure_plugin(pname, config)
        assert result is True
        assert plugin.config == config

    def test_configure_plugin_without_configure_method(self, manager, mock_db):
        # SampleHookPlugin 没有 configure 方法
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin)

        result = manager.configure_plugin(pname, {"key": "value"})
        assert result is True

    def test_configure_saves_to_db(self, manager, mock_db):
        plugin = ConfigurableHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, name="configurable_hook")

        config = {"key": "value"}
        manager.configure_plugin(pname, config)

        mock_db.save_plugin_config.assert_called_once()
        call_args = mock_db.save_plugin_config.call_args
        assert call_args[0][0] == pname
        assert call_args[0][2] == config

    def test_configure_nonexistent_plugin(self, manager, mock_db):
        # 插件不在 _plugins 中，但仍应保存配置到 DB
        result = manager.configure_plugin("unknown_plugin", {"k": "v"})
        assert result is True
        mock_db.save_plugin_config.assert_called_once()

    def test_configure_plugin_active_status_preserved(self, manager, mock_db):
        plugin = ConfigurableHookPlugin()
        pname, info = load_plugin_into_manager(
            manager, plugin, name="configurable_hook", status=PluginStatus.ACTIVE
        )

        manager.configure_plugin(pname, {"key": "value"})

        # 保存时 enabled 应反映当前 ACTIVE 状态
        save_call = mock_db.save_plugin_config.call_args
        assert save_call[0][1] is True  # enabled=True

    def test_configure_plugin_loaded_status_preserved(self, manager, mock_db):
        plugin = ConfigurableHookPlugin()
        pname, info = load_plugin_into_manager(
            manager, plugin, name="configurable_hook", status=PluginStatus.LOADED
        )

        manager.configure_plugin(pname, {"key": "value"})

        save_call = mock_db.save_plugin_config.call_args
        assert save_call[0][1] is False  # enabled=False

    def test_get_plugin_config_from_db(self, manager, mock_db):
        mock_db.get_plugin_config.return_value = {
            'plugin_name': 'test_plugin',
            'enabled': 1,
            'config': {'timeout': 60},
        }

        config = manager.get_plugin_config('test_plugin')
        assert config == {'timeout': 60}
        mock_db.get_plugin_config.assert_called_with('test_plugin')

    def test_get_plugin_config_no_config_returns_empty(self, manager, mock_db):
        mock_db.get_plugin_config.return_value = None

        config = manager.get_plugin_config('nonexistent')
        assert config == {}

    def test_get_plugin_config_db_error_returns_empty(self, manager):
        # 不使用 mock_db，DB 调用会抛异常
        config = manager.get_plugin_config('test_plugin')
        assert config == {}

    def test_get_plugin_config_empty_config_field(self, manager, mock_db):
        mock_db.get_plugin_config.return_value = {
            'plugin_name': 'test',
            'enabled': 0,
            # 没有 config 字段
        }

        config = manager.get_plugin_config('test')
        assert config == {}


# ========== load_enabled_plugins_from_db 测试 ==========

class TestLoadEnabledPluginsFromDb:
    """测试 load_enabled_plugins_from_db"""

    def test_load_enabled_plugins_calls_enable_for_enabled(self, manager, mock_db):
        mock_db.list_plugin_configs.return_value = [
            {'plugin_name': 'plugin_a', 'enabled': 1, 'config': {}},
            {'plugin_name': 'plugin_b', 'enabled': 0, 'config': {}},
            {'plugin_name': 'plugin_c', 'enabled': 1, 'config': {}},
        ]

        # Mock enable_plugin 来跟踪调用
        enabled_plugins = []
        original_enable = manager.enable_plugin

        def mock_enable(name):
            enabled_plugins.append(name)
            return True

        manager.enable_plugin = mock_enable

        manager.load_enabled_plugins_from_db()

        # 只对 enabled=1 的插件调用 enable
        assert 'plugin_a' in enabled_plugins
        assert 'plugin_c' in enabled_plugins
        assert 'plugin_b' not in enabled_plugins

    def test_load_enabled_plugins_no_configs(self, manager, mock_db):
        mock_db.list_plugin_configs.return_value = []

        # 不应抛异常
        manager.load_enabled_plugins_from_db()
        mock_db.list_plugin_configs.assert_called_once()

    def test_load_enabled_plugins_continues_on_error(self, manager, mock_db):
        mock_db.list_plugin_configs.return_value = [
            {'plugin_name': 'bad_plugin', 'enabled': 1, 'config': {}},
            {'plugin_name': 'good_plugin', 'enabled': 1, 'config': {}},
        ]

        call_log = []

        def mock_enable(name):
            call_log.append(name)
            if name == 'bad_plugin':
                raise RuntimeError("boom")
            return True

        manager.enable_plugin = mock_enable

        # 即使 bad_plugin 失败，good_plugin 仍应被处理
        manager.load_enabled_plugins_from_db()
        assert 'bad_plugin' in call_log
        assert 'good_plugin' in call_log

    def test_load_enabled_plugins_db_error_handled(self, manager):
        # 不使用 mock_db，list_plugin_configs 会抛异常
        # 应被捕获，不传播
        manager.load_enabled_plugins_from_db()
        # 不报错即可

    def test_load_enabled_plugins_uses_truthy_check(self, manager, mock_db):
        mock_db.list_plugin_configs.return_value = [
            {'plugin_name': 'p1', 'enabled': True, 'config': {}},
            {'plugin_name': 'p2', 'enabled': False, 'config': {}},
            {'plugin_name': 'p3', 'enabled': 1, 'config': {}},
            {'plugin_name': 'p4', 'enabled': 0, 'config': {}},
        ]

        enabled = []
        manager.enable_plugin = lambda name: enabled.append(name) or True

        manager.load_enabled_plugins_from_db()
        assert 'p1' in enabled
        assert 'p3' in enabled
        assert 'p2' not in enabled
        assert 'p4' not in enabled


# ========== _activate_plugin / _deactivate_plugin 测试 ==========

class TestActivateDeactivate:
    """测试 _activate_plugin 和 _deactivate_plugin"""

    def test_activate_sets_status_active(self, manager):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, status=PluginStatus.LOADED)

        manager._activate_plugin(pname)
        assert info.status == PluginStatus.ACTIVE
        assert info.error_message is None

    def test_activate_clears_error_message(self, manager):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, status=PluginStatus.ERROR)
        info.error_message = "previous error"

        manager._activate_plugin(pname)
        assert info.status == PluginStatus.ACTIVE
        assert info.error_message is None

    def test_activate_registers_hooks_for_hook_plugin(self, manager):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, status=PluginStatus.LOADED)

        dispatcher = get_hook_dispatcher()
        assert not dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        manager._activate_plugin(pname)

        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)
        assert dispatcher.has_hooks(HookPoint.NOVA_LAUNCH)
        assert dispatcher.has_hooks(HookPoint.NOVA_COMPLETE)

    def test_activate_does_not_register_hooks_for_star_plugin(self, manager):
        plugin = SampleStarPlugin()
        pname, info = load_plugin_into_manager(
            manager, plugin, name="sample_star",
            plugin_type=PluginType.STAR, status=PluginStatus.LOADED
        )

        dispatcher = get_hook_dispatcher()
        manager._activate_plugin(pname)

        assert info.status == PluginStatus.ACTIVE
        assert not dispatcher.has_hooks(HookPoint.NOVA_CREATE)

    def test_activate_nonexistent_plugin_no_error(self, manager):
        # 不存在的插件应静默返回
        manager._activate_plugin("nonexistent")
        # 不报错即可

    def test_deactivate_sets_status_loaded(self, manager):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, status=PluginStatus.ACTIVE)
        manager._register_plugin_hooks(pname, plugin)

        manager._deactivate_plugin(pname)
        assert info.status == PluginStatus.LOADED

    def test_deactivate_unregisters_hooks(self, manager):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, status=PluginStatus.ACTIVE)
        manager._register_plugin_hooks(pname, plugin)

        dispatcher = get_hook_dispatcher()
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        manager._deactivate_plugin(pname)

        assert not dispatcher.has_hooks(HookPoint.NOVA_CREATE)
        assert not dispatcher.has_hooks(HookPoint.NOVA_LAUNCH)

    def test_deactivate_star_plugin_no_hook_ops(self, manager):
        plugin = SampleStarPlugin()
        pname, info = load_plugin_into_manager(
            manager, plugin, name="sample_star",
            plugin_type=PluginType.STAR, status=PluginStatus.ACTIVE
        )

        manager._deactivate_plugin(pname)
        assert info.status == PluginStatus.LOADED

    def test_deactivate_nonexistent_plugin_no_error(self, manager):
        manager._deactivate_plugin("nonexistent")
        # 不报错即可

    def test_activate_deactivate_cycle(self, manager):
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, status=PluginStatus.LOADED)

        dispatcher = get_hook_dispatcher()

        # 激活
        manager._activate_plugin(pname)
        assert info.status == PluginStatus.ACTIVE
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        # 停用
        manager._deactivate_plugin(pname)
        assert info.status == PluginStatus.LOADED
        assert not dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        # 再激活
        manager._activate_plugin(pname)
        assert info.status == PluginStatus.ACTIVE
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)


# ========== _register_plugin_hooks / _unregister_plugin_hooks 测试 ==========

class TestRegisterUnregisterHooks:
    """测试 _register_plugin_hooks 和 _unregister_plugin_hooks"""

    def test_register_registers_all_hook_methods(self, manager):
        plugin = SampleHookPlugin()
        pname = "sample_hook"

        manager._register_plugin_hooks(pname, plugin)

        dispatcher = get_hook_dispatcher()
        # SampleHookPlugin 实现了部分 on_* 方法，其余继承自 HookPlugin
        # _register_plugin_hooks 注册所有 hasattr 的方法
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)
        assert dispatcher.has_hooks(HookPoint.NOVA_LAUNCH)
        assert dispatcher.has_hooks(HookPoint.NOVA_SHINE)
        assert dispatcher.has_hooks(HookPoint.NOVA_COMPLETE)
        assert dispatcher.has_hooks(HookPoint.NOVA_FADE)
        assert dispatcher.has_hooks(HookPoint.STARLIGHT_RECEIVED)
        assert dispatcher.has_hooks(HookPoint.STAR_DISCOVERED)
        assert dispatcher.has_hooks(HookPoint.STAR_LOST)
        assert dispatcher.has_hooks(HookPoint.CONSTELLATION_CREATE)
        assert dispatcher.has_hooks(HookPoint.CONSTELLATION_COMPLETE)
        assert dispatcher.has_hooks(HookPoint.SYSTEM_STARTUP)
        assert dispatcher.has_hooks(HookPoint.SYSTEM_SHUTDOWN)

    def test_register_hooks_callable_via_dispatcher(self, manager):
        plugin = SampleHookPlugin()
        pname = "sample_hook"

        manager._register_plugin_hooks(pname, plugin)

        # 通过分发器调用钩子，应触发插件方法
        dispatcher = get_hook_dispatcher()
        dispatcher.dispatch(HookPoint.NOVA_CREATE, "nova_1")

        assert ("on_nova_create", "nova_1") in plugin.call_log

    def test_register_hooks_for_nova_launch(self, manager):
        plugin = SampleHookPlugin()
        pname = "sample_hook"

        manager._register_plugin_hooks(pname, plugin)

        dispatcher = get_hook_dispatcher()
        results = dispatcher.dispatch_until_false(HookPoint.NOVA_LAUNCH, "nova_1", "star_1")

        assert results is True  # on_nova_launch 返回 True
        assert ("on_nova_launch", "nova_1", "star_1") in plugin.call_log

    def test_unregister_removes_all_hooks(self, manager):
        plugin = SampleHookPlugin()
        pname = "sample_hook"

        manager._register_plugin_hooks(pname, plugin)
        dispatcher = get_hook_dispatcher()
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        manager._unregister_plugin_hooks(pname, plugin)

        assert not dispatcher.has_hooks(HookPoint.NOVA_CREATE)
        assert not dispatcher.has_hooks(HookPoint.NOVA_LAUNCH)
        assert not dispatcher.has_hooks(HookPoint.SYSTEM_STARTUP)
        assert not dispatcher.has_hooks(HookPoint.SYSTEM_SHUTDOWN)

    def test_unregister_makes_hooks_not_callable(self, manager):
        plugin = SampleHookPlugin()
        pname = "sample_hook"

        manager._register_plugin_hooks(pname, plugin)
        dispatcher = get_hook_dispatcher()

        manager._unregister_plugin_hooks(pname, plugin)

        # 注销后调用不应触发插件方法
        plugin.call_log.clear()
        dispatcher.dispatch(HookPoint.NOVA_CREATE, "nova_1")
        assert len(plugin.call_log) == 0

    def test_register_multiple_plugins(self, manager):
        plugin1 = SampleHookPlugin()
        plugin2 = SampleHookPlugin()
        plugin2.PLUGIN_NAME = "second_hook"

        manager._register_plugin_hooks("first", plugin1)
        manager._register_plugin_hooks("second", plugin2)

        dispatcher = get_hook_dispatcher()
        # 两个插件的钩子都应注册
        results = dispatcher.dispatch(HookPoint.NOVA_CREATE, "nova")
        assert len(results) == 2

    def test_unregister_one_of_multiple(self, manager):
        plugin1 = SampleHookPlugin()
        plugin2 = SampleHookPlugin()

        manager._register_plugin_hooks("first", plugin1)
        manager._register_plugin_hooks("second", plugin2)

        dispatcher = get_hook_dispatcher()
        assert len(dispatcher.dispatch(HookPoint.NOVA_CREATE, "nova")) == 2

        # 只注销第一个
        manager._unregister_plugin_hooks("first", plugin1)

        results = dispatcher.dispatch(HookPoint.NOVA_CREATE, "nova")
        assert len(results) == 1

    def test_register_unregister_register(self, manager):
        plugin = SampleHookPlugin()
        pname = "sample_hook"

        # 注册 -> 注销 -> 再注册
        manager._register_plugin_hooks(pname, plugin)
        dispatcher = get_hook_dispatcher()
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        manager._unregister_plugin_hooks(pname, plugin)
        assert not dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        manager._register_plugin_hooks(pname, plugin)
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)

    def test_register_hooks_for_injector_plugin(self, manager):
        # InjectorPlugin 不是 HookPlugin，但其方法不会被 _register_plugin_hooks 处理
        # 因为 _activate_plugin 只对 HookPlugin 调用 _register_plugin_hooks
        # 这里直接调用 _register_plugin_hooks 仍会注册（因为它检查 hasattr）
        # InjectorPlugin 没有 on_* 方法，所以不会注册任何钩子
        plugin = SampleInjectorPlugin()
        manager._register_plugin_hooks("injector", plugin)

        dispatcher = get_hook_dispatcher()
        # InjectorPlugin 没有 on_nova_create 等方法
        assert not dispatcher.has_hooks(HookPoint.NOVA_CREATE)

    def test_hook_mappings_complete(self, manager):
        """测试 _get_hook_mappings 覆盖所有钩子点"""
        mappings = manager._get_hook_mappings()
        assert len(mappings) == 12
        # 验证映射覆盖所有 HookPoint
        mapped_points = set(mappings.values())
        assert HookPoint.NOVA_CREATE in mapped_points
        assert HookPoint.NOVA_LAUNCH in mapped_points
        assert HookPoint.NOVA_SHINE in mapped_points
        assert HookPoint.NOVA_COMPLETE in mapped_points
        assert HookPoint.NOVA_FADE in mapped_points
        assert HookPoint.STARLIGHT_RECEIVED in mapped_points
        assert HookPoint.STAR_DISCOVERED in mapped_points
        assert HookPoint.STAR_LOST in mapped_points
        assert HookPoint.CONSTELLATION_CREATE in mapped_points
        assert HookPoint.CONSTELLATION_COMPLETE in mapped_points
        assert HookPoint.SYSTEM_STARTUP in mapped_points
        assert HookPoint.SYSTEM_SHUTDOWN in mapped_points


# ========== 综合场景测试 ==========

class TestIntegrationScenarios:
    """综合场景测试"""

    def test_full_lifecycle_with_db(self, manager, mock_db):
        """完整生命周期：加载 -> 启用 -> 配置 -> 禁用"""
        plugin = ConfigurableHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin, name="configurable_hook")

        dispatcher = get_hook_dispatcher()

        # 1. 启用
        assert manager.enable_plugin(pname) is True
        assert info.status == PluginStatus.ACTIVE
        assert dispatcher.has_hooks(HookPoint.NOVA_CREATE)

        # 2. 配置
        config = {"timeout": 30}
        assert manager.configure_plugin(pname, config) is True
        assert plugin.config == config

        # 3. 禁用
        assert manager.disable_plugin(pname) is True
        assert info.status == PluginStatus.LOADED
        assert not dispatcher.has_hooks(HookPoint.NOVA_CREATE)

    def test_multiple_plugins_independent_lifecycle(self, manager, mock_db):
        """多个插件独立生命周期"""
        plugin1 = SampleHookPlugin()
        plugin2 = ConfigurableHookPlugin()
        load_plugin_into_manager(manager, plugin1, name="hook1")
        load_plugin_into_manager(manager, plugin2, name="hook2")

        dispatcher = get_hook_dispatcher()

        # 只启用 plugin1
        manager.enable_plugin("hook1")
        assert manager.get_plugin_info("hook1").status == PluginStatus.ACTIVE
        assert manager.get_plugin_info("hook2").status == PluginStatus.LOADED

        # 两个插件都注册了 NOVA_CREATE 钩子，启用 plugin1 后应有 1 个
        results = dispatcher.dispatch(HookPoint.NOVA_CREATE, "nova")
        assert len(results) == 1

        # 启用 plugin2，应有 2 个
        manager.enable_plugin("hook2")
        results = dispatcher.dispatch(HookPoint.NOVA_CREATE, "nova")
        assert len(results) == 2

        # 禁用 plugin1，应剩 1 个
        manager.disable_plugin("hook1")
        results = dispatcher.dispatch(HookPoint.NOVA_CREATE, "nova")
        assert len(results) == 1

    def test_hook_dispatch_after_enable(self, manager, mock_db):
        """启用后通过分发器调用钩子，验证插件方法被触发"""
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin)

        manager.enable_plugin(pname)

        dispatcher = get_hook_dispatcher()
        # 触发 system_startup 钩子
        dispatcher.dispatch(HookPoint.SYSTEM_STARTUP)

        assert ("on_system_startup",) in plugin.call_log

    def test_hook_dispatch_until_false_after_enable(self, manager, mock_db):
        """启用后通过 dispatch_until_false 调用，验证返回值正确"""
        plugin = SampleHookPlugin()
        pname, info = load_plugin_into_manager(manager, plugin)

        manager.enable_plugin(pname)

        dispatcher = get_hook_dispatcher()
        # on_nova_launch 返回 True，应通过
        result = dispatcher.dispatch_until_false(HookPoint.NOVA_LAUNCH, "nova", "star")
        assert result is True
        assert ("on_nova_launch", "nova", "star") in plugin.call_log
