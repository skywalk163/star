"""
配置服务测试

测试 star_core.config_service 中的 ConfigService
"""

import pytest
import os
import tempfile
import yaml
from star_core.config_service import ConfigService


@pytest.fixture
def temp_config_dir():
    """创建临时配置目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_config_file(temp_config_dir):
    """创建示例配置文件"""
    config_data = {
        'agents': [
            {
                'id': 'test_agent',
                'name': '测试 Agent',
                'vendor': 'test_vendor',
                'category': 'ide',
                'description': '测试用 Agent',
                'process_names': ['test.exe'],
                'window_class': ['TestWindow'],
                'title_patterns': ['Test'],
                'adapter_config': {
                    'input_click_ratio': [0.5, 0.8],
                    'timeout': 60,
                }
            },
            {
                'id': 'another_agent',
                'name': '另一个 Agent',
                'category': 'browser',
                'description': '另一个测试 Agent',
                'process_names': ['another.exe'],
                'title_patterns': ['Another'],
            }
        ],
        'default_adapter_config': {
            'input_click_ratio': [0.3, 0.7],
            'timeout': 30,
            'completion_keywords': ['完成', '好的'],
        }
    }
    yaml_path = os.path.join(temp_config_dir, 'ai-agents.yaml')
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f, allow_unicode=True)
    return temp_config_dir


class TestConfigService:
    """测试 ConfigService"""

    def test_create_with_default_dir(self):
        svc = ConfigService()
        assert svc is not None

    def test_create_with_custom_dir(self, temp_config_dir):
        svc = ConfigService(config_dir=temp_config_dir)
        assert svc.config_dir == temp_config_dir

    def test_load_config(self, sample_config_file):
        svc = ConfigService(config_dir=sample_config_file)
        agents = svc.get_all_agents()
        assert len(agents) == 2
        assert 'test_agent' in agents
        assert 'another_agent' in agents

    def test_get_agent(self, sample_config_file):
        svc = ConfigService(config_dir=sample_config_file)
        agent = svc.get_agent('test_agent')
        assert agent is not None
        assert agent['name'] == '测试 Agent'
        assert agent['category'] == 'ide'

    def test_get_agent_not_found(self, sample_config_file):
        svc = ConfigService(config_dir=sample_config_file)
        agent = svc.get_agent('nonexistent')
        assert agent is None

    def test_get_star_signatures(self, sample_config_file):
        svc = ConfigService(config_dir=sample_config_file)
        sigs = svc.get_star_signatures()
        assert 'test_agent' in sigs
        assert 'process_names' in sigs['test_agent']
        assert sigs['test_agent']['process_names'] == ['test.exe']
        assert 'window_title_patterns' in sigs['test_agent']

    def test_adapter_config_with_defaults(self, sample_config_file):
        svc = ConfigService(config_dir=sample_config_file)
        # test_agent 有自己的 adapter_config，应该合并默认值
        adapter = svc.get_adapter_config('test_agent')
        assert adapter is not None
        assert 'timeout' in adapter
        assert 'completion_keywords' in adapter  # 来自默认配置

    def test_adapter_config_agent_specific_overrides(self, sample_config_file):
        svc = ConfigService(config_dir=sample_config_file)
        adapter = svc.get_adapter_config('test_agent')
        # test_agent 的 timeout 是 60，应该覆盖默认的 30
        assert adapter['timeout'] == 60

    def test_adapter_config_inherits_defaults(self, sample_config_file):
        svc = ConfigService(config_dir=sample_config_file)
        # another_agent 没有 adapter_config，应该使用默认值
        adapter = svc.get_adapter_config('another_agent')
        assert adapter is not None
        assert adapter['timeout'] == 30
        assert 'completion_keywords' in adapter

    def test_get_all_adapter_configs(self, sample_config_file):
        svc = ConfigService(config_dir=sample_config_file)
        configs = svc.get_all_adapter_configs()
        assert len(configs) == 2
        assert 'test_agent' in configs
        assert 'another_agent' in configs

    def test_get_default_adapter_config(self, sample_config_file):
        svc = ConfigService(config_dir=sample_config_file)
        default = svc.get_default_adapter_config()
        assert 'timeout' in default
        assert default['timeout'] == 30

    def test_validate_agent_config_valid(self, sample_config_file):
        svc = ConfigService(config_dir=sample_config_file)
        valid, errors = svc.validate_agent_config('test_agent')
        assert valid == True
        assert len(errors) == 0

    def test_validate_agent_config_not_found(self, sample_config_file):
        svc = ConfigService(config_dir=sample_config_file)
        valid, errors = svc.validate_agent_config('nonexistent')
        assert valid == False
        assert len(errors) > 0

    def test_reload_if_changed(self, sample_config_file):
        svc = ConfigService(config_dir=sample_config_file)
        initial_agents = svc.get_all_agents()
        # 文件未修改，应该返回 False
        result = svc.reload_if_changed()
        assert result == False

    def test_config_file_not_found(self, temp_config_dir):
        # 没有配置文件的情况
        svc = ConfigService(config_dir=temp_config_dir)
        agents = svc.get_all_agents()
        assert len(agents) == 0
