"""`/api/work/ai/*` 三个端点的回归测试。

历史缺陷（本文件即为其回归网）：
- `list_ais()` 依赖从未被赋值的 `state.emissaries`，恒返回空表；
- `ask_ai()` 对同步的 `StarEmissary.ask` 用了 `await` 且多传 `adapter_name`，任何调用必抛 TypeError。

现在这三个端点统一以 `AIAdapterRegistry` 为底座，与 `/api/dumate/adapters` 同源。
"""

import pytest
from fastapi.testclient import TestClient

from star_api.main import app
from star_api import state
from star_api.routes import work as work_routes
from star_core.ai_adapter import AIAdapterInfo, AIAdapterRegistry


client = TestClient(app)


class FakeAdapter:
    """够用就好的假适配器：只实现注册表与 work 路由真正会碰的那几个成员。"""

    AI_ID = "fake_ai"
    AI_NAME = "假适配器"
    AI_VERSION = "1.0"
    DESCRIPTION = "测试用"

    def __init__(self, connected=True, status="idle", create_ok=True):
        self.connected = connected
        self._status = status
        self._create_ok = create_ok
        self.created_prompts = []

    def get_info(self):
        return AIAdapterInfo(
            ai_id=self.AI_ID,
            ai_name=self.AI_NAME,
            ai_version=self.AI_VERSION,
            description=self.DESCRIPTION,
            connected=self.connected,
            capabilities=[],
            error_message=None,
        )

    def get_status(self):
        return self._status

    def is_alive(self):
        return self.connected

    def create_task(self, prompt, workspace_id="", task_type="work", **kwargs):
        self.created_prompts.append(prompt)
        if not self._create_ok:
            return {"success": False, "conversation_id": "", "message": "模拟失败"}
        return {"success": True, "conversation_id": "conv-1", "message": "已创建"}

    def disconnect(self):
        self.connected = False


@pytest.fixture(autouse=True)
def _auth_off():
    """本文件只测业务逻辑，显式关掉鉴权，避免受其他测试文件改 state.config 的影响。"""
    state.config = {'auth': {'enabled': False}}
    yield


@pytest.fixture
def isolated_registry(monkeypatch):
    """给 work 路由换一个干净的注册表，不污染全局单例。"""
    registry = AIAdapterRegistry()
    monkeypatch.setattr(work_routes, "get_adapter_registry", lambda: registry)
    return registry


class TestListAIs:
    def test_returns_registered_adapter(self, isolated_registry):
        isolated_registry.register(FakeAdapter())

        res = client.get('/api/work/ai')
        assert res.status_code == 200
        data = res.json()

        # 核心断言：不再恒空
        assert data['total'] == 1
        item = data['ais'][0]
        assert item['ai_id'] == 'fake_ai'
        assert item['name'] == '假适配器'
        assert item['status'] == 'idle'

    def test_empty_registry_returns_empty_list(self, isolated_registry):
        res = client.get('/api/work/ai')
        assert res.status_code == 200
        assert res.json() == {'ais': [], 'total': 0}

    def test_disconnected_adapter_marked_offline(self, isolated_registry):
        isolated_registry.register(FakeAdapter(connected=False))

        res = client.get('/api/work/ai')
        assert res.json()['ais'][0]['status'] == 'offline'

    def test_connected_but_runtime_offline_is_offline(self, isolated_registry):
        """注册表说 connected、单体 status 却是 offline —— 按 offline 记，别让调用方对着死适配器发任务。"""
        isolated_registry.register(FakeAdapter(connected=True, status='offline'))

        res = client.get('/api/work/ai')
        assert res.json()['ais'][0]['status'] == 'offline'

    def test_generating_maps_to_busy(self, isolated_registry):
        isolated_registry.register(FakeAdapter(connected=True, status='generating'))

        res = client.get('/api/work/ai')
        assert res.json()['ais'][0]['status'] == 'busy'

    def test_status_probe_failure_does_not_break_list(self, isolated_registry):
        adapter = FakeAdapter()
        adapter.get_status = lambda: (_ for _ in ()).throw(RuntimeError('探测炸了'))
        isolated_registry.register(adapter)

        res = client.get('/api/work/ai')
        assert res.status_code == 200
        assert res.json()['ais'][0]['status'] == 'offline'


class TestGetAIStatus:
    def test_known_adapter(self, isolated_registry):
        isolated_registry.register(FakeAdapter())

        res = client.get('/api/work/ai/fake_ai/status')
        assert res.status_code == 200
        assert res.json()['ai_id'] == 'fake_ai'

    def test_unknown_adapter_404(self, isolated_registry):
        res = client.get('/api/work/ai/nope/status')
        assert res.status_code == 404


class TestAskAI:
    def test_ask_succeeds_without_typeerror(self, isolated_registry):
        """本次修复的核心断言：旧实现在这里必抛 TypeError。"""
        adapter = FakeAdapter()
        isolated_registry.register(adapter)

        res = client.post('/api/work/ai/fake_ai/ask', json={'prompt': '你好'})
        assert res.status_code == 200
        data = res.json()
        assert data['success'] is True
        assert data['conversation_id'] == 'conv-1'
        assert adapter.created_prompts == ['你好']

    def test_adapter_name_is_ignored_not_forwarded(self, isolated_registry):
        """旧实现把 adapter_name 透传给 ask() 导致 TypeError；现在该字段只是被忽略。"""
        adapter = FakeAdapter()
        isolated_registry.register(adapter)

        res = client.post(
            '/api/work/ai/fake_ai/ask',
            json={'prompt': '带上多余字段', 'adapter_name': 'trae', 'timeout': 5},
        )
        assert res.status_code == 200
        assert adapter.created_prompts == ['带上多余字段']

    def test_unknown_adapter_404(self, isolated_registry):
        res = client.post('/api/work/ai/nope/ask', json={'prompt': 'x'})
        assert res.status_code == 404

    def test_disconnected_adapter_503(self, isolated_registry):
        isolated_registry.register(FakeAdapter(connected=False))

        res = client.post('/api/work/ai/fake_ai/ask', json={'prompt': 'x'})
        assert res.status_code == 503

    def test_create_task_failure_500(self, isolated_registry):
        isolated_registry.register(FakeAdapter(create_ok=False))

        res = client.post('/api/work/ai/fake_ai/ask', json={'prompt': 'x'})
        assert res.status_code == 500
        assert '模拟失败' in res.json()['detail']
