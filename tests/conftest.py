import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 初始化 API 全局状态（避免 503 错误）
from star_api import state
from unittest.mock import MagicMock

# 创建 mock orbit_engine
mock_engine = MagicMock()
mock_engine.star_seeker = MagicMock()
mock_engine.star_seeker.scan_skies.return_value = []
mock_engine.star_seeker.list_star_types.return_value = []
mock_engine.star_seeker.get_star.return_value = None
mock_engine.star_seeker.refresh_star.return_value = None
mock_engine.star_seeker.get_idle_stars.return_value = []
mock_engine._active_novas = {}
mock_engine.get_novas_by_status.return_value = []
mock_engine.get_novas_by_star.return_value = []
mock_engine.get_nova.return_value = None
mock_engine.birth_nova = MagicMock(return_value='test-nova-id')
mock_engine.launch_nova = MagicMock(return_value=True)
mock_engine.adjust_orbit = MagicMock(return_value=True)
mock_engine.add_echo = MagicMock(return_value=True)
mock_engine.fade_nova = MagicMock(return_value=True)
mock_engine.darken_nova = MagicMock(return_value=True)

state.orbit_engine = mock_engine
state.config = {'auth': {'enabled': False}}
state.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
