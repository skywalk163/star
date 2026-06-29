import pytest
from star_core.star_emissary import (
    StarAdapterConfig,
    StarAdapter,
    PRESET_ADAPTERS,
    CompletionStrategy,
)


class TestStarAdapterConfig:
    def test_default_values(self):
        cfg = StarAdapterConfig(name='test')
        assert cfg.name == 'test'
        assert cfg.input_click_x_ratio == 0.5
        assert cfg.input_click_y_ratio == 0.92
        assert cfg.output_region == 'center_chat'
        assert cfg.stable_count == 3
        assert cfg.check_interval == 2.0
        assert cfg.timeout == 300.0
        assert cfg.ocr_lang == 'ch'

    def test_custom_values(self):
        cfg = StarAdapterConfig(
            name='custom',
            input_click_x_ratio=0.3,
            input_click_y_ratio=0.8,
            stable_count=5,
            timeout=120.0,
        )
        assert cfg.input_click_x_ratio == 0.3
        assert cfg.input_click_y_ratio == 0.8
        assert cfg.stable_count == 5
        assert cfg.timeout == 120.0


class TestStarAdapter:
    def test_from_name_exists(self):
        adapter = StarAdapter.from_name('trae')
        assert adapter is not None
        assert adapter.config.name == 'trae'

    def test_from_name_not_exists(self):
        adapter = StarAdapter.from_name('nonexistent')
        # from_name 对未知名称直接返回传入的名字
        assert adapter.config.name == 'nonexistent'

    def test_from_star_type_trae(self):
        adapter = StarAdapter.from_star_type('trae')
        assert adapter.config.name == 'trae'

    def test_from_star_type_chatgpt(self):
        adapter = StarAdapter.from_star_type('chatgpt')
        assert adapter.config.name == 'chatgpt'

    def test_from_star_type_unknown(self):
        adapter = StarAdapter.from_star_type('unknown_xyz')
        assert adapter.config.name == 'generic'

    def test_all_preset_adapters_loadable(self):
        for name in PRESET_ADAPTERS:
            adapter = StarAdapter.from_name(name)
            assert adapter is not None
            assert adapter.config.name == name

    def test_preset_count(self):
        assert len(PRESET_ADAPTERS) >= 14

    def test_domestic_adapters_exist(self):
        domestic = ['ernie', 'spark', 'glm', 'step', 'wanzhi',
                    'shangliang', 'hailuo', 'baichuan', 'qwen']
        for name in domestic:
            assert name in PRESET_ADAPTERS, f'{name} adapter missing'
            adapter = StarAdapter.from_name(name)
            assert adapter.config.ocr_lang == 'ch'

    def test_adapter_has_completion_keywords(self):
        for name, cfg in PRESET_ADAPTERS.items():
            assert len(cfg.completion_keywords) > 0, f'{name} missing completion_keywords'
            # running_keywords 对某些适配器可能为空（如 chatgpt）
            assert isinstance(cfg.running_keywords, list), f'{name} running_keywords not a list'

    def test_adapter_click_ratios_in_range(self):
        for name, cfg in PRESET_ADAPTERS.items():
            assert 0 <= cfg.input_click_x_ratio <= 1, f'{name} x_ratio out of range'
            assert 0 <= cfg.input_click_y_ratio <= 1, f'{name} y_ratio out of range'

    def test_adapter_timeout_positive(self):
        for name, cfg in PRESET_ADAPTERS.items():
            assert cfg.timeout > 0, f'{name} timeout must be positive'

    def test_star_type_aliases(self):
        alias_tests = {
            'yiyan': 'ernie',
            '文心': 'ernie',
            '星火': 'spark',
            '智谱': 'glm',
            '跃问': 'step',
            '万知': 'wanzhi',
            '商量': 'shangliang',
            '海螺': 'hailuo',
            '百川': 'baichuan',
            '通义': 'qwen',
        }
        for alias, expected in alias_tests.items():
            adapter = StarAdapter.from_star_type(alias)
            assert adapter.config.name == expected, f'alias {alias} -> {expected} failed'
