"""流式连接票据（SSE / WebSocket 鉴权）的回归测试。

背景：浏览器原生 EventSource / WebSocket 设不了 X-API-Key 请求头。
在票据机制之前，这四个流式端点在「鉴权开启」时必然 401、在「鉴权关闭」时完全裸奔，
等于没有可用的中间态。本文件锁住票据链路的关键性质：

- 一次性：同一张票据用过即失效；
- 短时效：过期即拒；
- 权限不放大：票据继承签发者角色，仍要过 has_permission；
- 只对安全方法生效：票据会进 URL，不能用来改状态；
- 鉴权关闭时行为不变：自用场景不受影响。
"""
import pytest
from fastapi.testclient import TestClient

from star_api import state
from star_api import auth
from star_api.auth import (
    authorize_stream,
    clear_stream_tickets,
    consume_stream_ticket,
    issue_stream_ticket,
)
from star_api.main import app

client = TestClient(app)

ADMIN_KEY = 'test-admin-key-0001'
VIEWER_KEY = 'test-viewer-key-0001'


@pytest.fixture(autouse=True)
def _clean_tickets():
    """每个用例前后都清空票据表，避免相互串味。"""
    clear_stream_tickets()
    yield
    clear_stream_tickets()


@pytest.fixture
def auth_on():
    """开启鉴权，并配好 admin / viewer 两把 Key。

    其他测试文件会改 state.config 且不复位，所以这里每次都显式重写，
    让本文件的结果与执行顺序无关。
    """
    state.config = {
        'auth': {
            'enabled': True,
            'api_keys': [
                {'key': ADMIN_KEY, 'role': 'admin', 'name': 'tester'},
                {'key': VIEWER_KEY, 'role': 'viewer', 'name': 'watcher'},
            ],
        }
    }
    yield
    state.config = {'auth': {'enabled': False}}


@pytest.fixture
def auth_off():
    state.config = {'auth': {'enabled': False}}
    yield


class TestTicketLifecycle:
    def test_issue_then_consume_returns_role(self):
        ticket = issue_stream_ticket('admin', 'tester')
        info = consume_stream_ticket(ticket)
        assert info == {'role': 'admin', 'name': 'tester'}

    def test_ticket_is_single_use(self):
        ticket = issue_stream_ticket('admin')
        assert consume_stream_ticket(ticket) is not None
        # 第二次就该失效——这是票据即使进了日志也不怕被复用的根据
        assert consume_stream_ticket(ticket) is None

    def test_expired_ticket_rejected(self, monkeypatch):
        # TTL 设成负数，签发即过期，不必真的等 60 秒
        monkeypatch.setattr(auth, 'STREAM_TICKET_TTL', -1)
        ticket = issue_stream_ticket('admin')
        assert consume_stream_ticket(ticket) is None

    def test_unknown_ticket_rejected(self):
        assert consume_stream_ticket('never-issued') is None

    def test_empty_ticket_rejected(self):
        assert consume_stream_ticket('') is None
        assert consume_stream_ticket(None) is None

    def test_table_capacity_is_bounded(self, monkeypatch):
        monkeypatch.setattr(auth, '_MAX_STREAM_TICKETS', 4)
        for _ in range(10):
            issue_stream_ticket('admin')
        assert len(auth._stream_tickets) <= 4


class TestAuthorizeStream:
    def test_auth_disabled_allows_without_ticket(self, auth_off):
        # 自用场景（不开鉴权）行为必须与引入票据之前完全一致
        assert authorize_stream(None) is True

    def test_missing_ticket_denied_when_auth_on(self, auth_on):
        assert authorize_stream(None) is False

    def test_valid_ticket_allowed(self, auth_on):
        assert authorize_stream(issue_stream_ticket('admin')) is True

    def test_viewer_ticket_passes_read(self, auth_on):
        assert authorize_stream(issue_stream_ticket('viewer'), 'read') is True

    def test_viewer_ticket_denied_for_control(self, auth_on):
        # 票据继承签发者角色，权限不会被放大
        assert authorize_stream(issue_stream_ticket('viewer'), 'control') is False

    def test_ticket_consumed_even_on_permission_failure(self, auth_on):
        ticket = issue_stream_ticket('viewer')
        assert authorize_stream(ticket, 'control') is False
        # 权限不足也算用掉了，不给重试的机会
        assert authorize_stream(ticket, 'read') is False


class TestStreamTicketEndpoint:
    def test_requires_api_key_when_auth_on(self, auth_on):
        res = client.post('/api/auth/stream-ticket')
        assert res.status_code == 401

    def test_issues_ticket_with_valid_key(self, auth_on):
        res = client.post('/api/auth/stream-ticket', headers={'X-API-Key': ADMIN_KEY})
        assert res.status_code == 200
        body = res.json()
        assert body['auth_enabled'] is True
        assert body['ticket']
        assert body['expires_in'] == auth.STREAM_TICKET_TTL
        # 票据确实可用，且继承了签发者角色
        assert consume_stream_ticket(body['ticket'])['role'] == 'admin'

    def test_viewer_can_get_ticket(self, auth_on):
        # 签发本身是只读操作，viewer 必须能取，否则它连事件流都看不了
        res = client.post('/api/auth/stream-ticket', headers={'X-API-Key': VIEWER_KEY})
        assert res.status_code == 200
        assert consume_stream_ticket(res.json()['ticket'])['role'] == 'viewer'

    def test_returns_empty_ticket_when_auth_off(self, auth_off):
        res = client.post('/api/auth/stream-ticket')
        assert res.status_code == 200
        body = res.json()
        assert body['auth_enabled'] is False
        assert body['ticket'] == ''


class TestSseTicketFallback:
    """SSE 端点走 router 级 require_by_method，票据在那里被识别。"""

    def test_sse_without_key_or_ticket_is_401(self, auth_on):
        res = client.get('/api/dumate/stream')
        assert res.status_code == 401

    def test_sse_with_valid_ticket_passes_auth(self, auth_on):
        ticket = issue_stream_ticket('viewer')
        res = client.get('/api/dumate/stream', params={'ticket': ticket})
        # 内核没跑，所以拿到 503；关键是**不再是 401**，说明鉴权已通过
        assert res.status_code != 401
        assert res.status_code == 503

    def test_sse_with_bad_ticket_is_401(self, auth_on):
        res = client.get('/api/dumate/stream', params={'ticket': 'forged'})
        assert res.status_code == 401

    def test_sse_ticket_cannot_be_reused(self, auth_on):
        ticket = issue_stream_ticket('viewer')
        assert client.get('/api/dumate/stream', params={'ticket': ticket}).status_code == 503
        assert client.get('/api/dumate/stream', params={'ticket': ticket}).status_code == 401

    def test_header_still_works(self, auth_on):
        res = client.get('/api/dumate/stream', headers={'X-API-Key': ADMIN_KEY})
        assert res.status_code == 503

    def test_ticket_rejected_for_write_method(self, auth_on):
        # 票据进过 URL，绝不能用来改状态
        ticket = issue_stream_ticket('admin')
        res = client.post('/api/dumate/adapters/dumate/connect', params={'ticket': ticket})
        assert res.status_code == 401
