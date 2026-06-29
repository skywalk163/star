import pytest
from star_core.star_seeker import (
    StarWindowContext,
    StarSeeker,
)


STAR_SIGNATURES = StarSeeker.STAR_SIGNATURES


class TestStarSignatures:
    def test_signatures_not_empty(self):
        assert len(STAR_SIGNATURES) > 0

    def test_trae_signature_exists(self):
        assert 'trae' in STAR_SIGNATURES
        sig = STAR_SIGNATURES['trae']
        assert 'process_names' in sig
        assert 'window_title_patterns' in sig
        assert 'trae' in [n.lower() for n in sig['process_names']]

    def test_domestic_signatures_exist(self):
        domestic = ['ernie', 'spark', 'glm', 'step', 'wanzhi',
                    'shangliang', 'hailuo', 'baichuan', 'qwen']
        for name in domestic:
            assert name in STAR_SIGNATURES, f'{name} signature missing'
            sig = STAR_SIGNATURES[name]
            assert 'window_title_patterns' in sig
            assert len(sig['window_title_patterns']) > 0

    def test_ai_coding_assistant_signatures_exist(self):
        coding_agents = ['trae', 'codearts_agent', 'dumate', 'cursor', 'windsurf']
        for name in coding_agents:
            assert name in STAR_SIGNATURES, f'{name} signature missing'
            sig = STAR_SIGNATURES[name]
            assert 'process_names' in sig
            assert len(sig['process_names']) > 0

    def test_codearts_agent_signature(self):
        assert 'codearts_agent' in STAR_SIGNATURES
        sig = STAR_SIGNATURES['codearts_agent']
        assert any('codearts-agent' in n.lower() or 'codearts agent' in n.lower()
                    for n in sig['process_names'])
        assert any('CodeArts Agent' in p for p in sig['window_title_patterns'])

    def test_dumate_signature(self):
        assert 'dumate' in STAR_SIGNATURES
        sig = STAR_SIGNATURES['dumate']
        assert any('dumate' in n.lower() for n in sig['process_names'])
        assert any('DuMate' in p or '搭子' in p for p in sig['window_title_patterns'])

    def test_signature_structure(self):
        for name, sig in STAR_SIGNATURES.items():
            assert 'process_names' in sig, f'{name}: missing process_names'
            assert 'window_class' in sig, f'{name}: missing window_class'
            assert 'window_title_patterns' in sig, f'{name}: missing window_title_patterns'
            assert 'description' in sig, f'{name}: missing description'
            assert isinstance(sig['process_names'], list)
            assert isinstance(sig['window_title_patterns'], list)


class TestStarWindowContext:
    def test_context_creation(self):
        ctx = StarWindowContext(
            project_name='test_project',
            file_name='test.py',
            window_type='code',
            is_work_mode=True,
        )
        assert ctx.project_name == 'test_project'
        assert ctx.file_name == 'test.py'
        assert ctx.window_type == 'code'
        assert ctx.is_work_mode is True

    def test_context_defaults(self):
        ctx = StarWindowContext()
        assert ctx.project_name == ''
        assert ctx.file_name == ''
        assert ctx.window_type == 'unknown'
        assert ctx.is_work_mode is False


class TestStarSeeker:
    def test_seeker_instance(self):
        seeker = StarSeeker()
        assert seeker is not None

    def test_seeker_has_methods(self):
        seeker = StarSeeker()
        assert hasattr(seeker, 'scan_skies')
        assert hasattr(seeker, 'get_star')
        assert hasattr(seeker, 'list_star_types')
