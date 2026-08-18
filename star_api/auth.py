"""
星鉴者（StarAuth）- 认证与权限控制

API Key 认证 + 角色权限（admin/viewer）
"""

from typing import Optional, List
from secrets import compare_digest, token_urlsafe
import threading
import time
from fastapi import HTTPException, Header, Depends, Query, Request
from star_api import state


# 角色权限定义
ROLE_PERMISSIONS = {
    'admin': ['read', 'write', 'control', 'admin'],
    'viewer': ['read'],
}

# 不产生副作用的方法，只需 read 权限
_SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})


def _get_auth_config() -> dict:
    """获取认证配置"""
    if not hasattr(state, 'config') or not state.config:
        return {}
    return state.config.get('auth', {})


def is_auth_enabled() -> bool:
    """检查认证是否启用"""
    cfg = _get_auth_config()
    return cfg.get('enabled', False)


def _get_api_keys() -> List[dict]:
    """获取所有 API Key 配置"""
    cfg = _get_auth_config()
    keys = cfg.get('api_keys', [])
    if not keys:
        return []
    # 兼容字典和列表两种格式
    if isinstance(keys, dict):
        return [{'key': k, 'role': v.get('role', 'viewer'), 'name': v.get('name', k)}
                for k, v in keys.items()]
    return keys


def _find_key_info(api_key: str) -> Optional[dict]:
    """根据 key 查找配置信息

    用 compare_digest 做定长时间比较，避免按前缀逐字节泄漏 Key 内容。
    仍然要遍历全部候选，不能命中即返回，否则匹配位置会体现在耗时上。
    """
    matched = None
    for key_info in _get_api_keys():
        candidate = key_info.get('key') or ''
        if compare_digest(str(candidate), api_key) and matched is None:
            matched = key_info
    return matched


def has_permission(role: str, permission: str) -> bool:
    """检查角色是否拥有指定权限"""
    perms = ROLE_PERMISSIONS.get(role, [])
    return permission in perms


async def get_current_user(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> dict:
    """
    获取当前用户（认证依赖）

    如果认证未启用，返回默认 admin 角色
    如果认证启用，验证 API Key 并返回用户信息
    """
    if not is_auth_enabled():
        return {'role': 'admin', 'name': 'default', 'authenticated': False}

    if not x_api_key:
        raise HTTPException(status_code=401, detail="缺少 API Key")

    key_info = _find_key_info(x_api_key)
    if not key_info:
        raise HTTPException(status_code=401, detail="无效的 API Key")

    return {
        'role': key_info.get('role', 'viewer'),
        'name': key_info.get('name', 'unknown'),
        'authenticated': True,
    }


def require_permission(permission: str):
    """
    创建权限检查依赖

    用法: @router.get(..., dependencies=[Depends(require_permission('write'))])
    """
    async def checker(current_user: dict = Depends(get_current_user)):
        if not is_auth_enabled():
            return
        if not has_permission(current_user['role'], permission):
            raise HTTPException(
                status_code=403,
                detail=f"权限不足：需要 {permission} 权限"
            )
    return checker


# 预定义的权限依赖（直接作为 callable 传入 dependencies=[]）
require_read = require_permission('read')
require_write = require_permission('write')
require_control = require_permission('control')
require_admin = require_permission('admin')


def require_by_method(write_permission: str = 'write'):
    """按 HTTP 方法分级的权限依赖，用于整个 router。

    GET/HEAD/OPTIONS 视为只读，要 read 权限；其余方法会产生副作用，
    要 write_permission（write / control / admin）。

    这么设计是为了让「默认安全」成为结构性保证：只要在 include_router 时挂一次，
    该 router 之后新增的路由自动继承鉴权，不会再出现漏挂依赖导致接口裸奔。
    单条路由若需更严格的权限，仍可另外叠加 require_admin 等，依赖是叠加执行的。

    认证途径有两条，**header 优先**：
    1. `X-API-Key` 请求头 —— 常规途径，后端到后端调用继续用这条；
    2. `ticket` query 参数 —— 仅在没带 header 时才尝试，且**只对安全方法生效**。
       它是给浏览器原生 EventSource / WebSocket 用的（那两者设不了请求头），
       票据会出现在 URL 里，所以最坏后果必须被限制在「一次只读请求」之内。

    用法: app.include_router(r, dependencies=[Depends(require_by_method('control'))])
    """
    async def checker(
        request: Request,
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        ticket: Optional[str] = Query(None, description="流式连接票据（仅安全方法可用）"),
    ):
        if not is_auth_enabled():
            return
        needed = 'read' if request.method in _SAFE_METHODS else write_permission

        if x_api_key:
            key_info = _find_key_info(x_api_key)
            if not key_info:
                raise HTTPException(status_code=401, detail="无效的 API Key")
            role = key_info.get('role', 'viewer')
        else:
            # 写方法一律不接受票据：票据进过 URL，不能用来改状态。
            if request.method not in _SAFE_METHODS:
                raise HTTPException(status_code=401, detail="缺少 API Key")
            info = consume_stream_ticket(ticket)
            if info is None:
                raise HTTPException(status_code=401, detail="缺少 API Key 或票据无效")
            # 票据继承签发者的角色，下面照常过权限检查，权限不会被放大
            role = info['role']

        if not has_permission(role, needed):
            raise HTTPException(
                status_code=403,
                detail=f"权限不足：需要 {needed} 权限"
            )
    return checker


# ==================== 流式连接票据（WebSocket / SSE） ====================
#
# 浏览器原生的 EventSource 与 WebSocket 都不能设置自定义请求头，
# 所以 X-API-Key 那套对它们天然失效。
#
# 这里不走「把 API Key 塞进 query 参数」——那会把长期有效的 Key 写进
# 浏览器历史、access log 和任何反向代理日志里，为补一个鉴权缺口开一个泄露口。
# 改为：先用 header 鉴权换一张短时、一次性的票据，票据才进 URL。
# 票据即使被记进日志也无法复用，泄露面被限制在 TTL 之内。

#: 票据有效期（秒）。够浏览器拿到后立刻发起连接，又短到来不及被人捡走复用。
STREAM_TICKET_TTL = 60

#: 票据表容量上限。防止有人反复调用签发接口把内存撑爆。
_MAX_STREAM_TICKETS = 512

#: ticket -> {'role': str, 'name': str, 'expires_at': float}
_stream_tickets: dict = {}
_stream_ticket_lock = threading.Lock()


def _purge_expired_tickets(now: float) -> None:
    """惰性清理过期票据。

    调用方必须已持有 _stream_ticket_lock。
    用惰性清理而不是后台任务：票据量小、TTL 短，没必要为此多一个线程。
    """
    expired = [t for t, info in _stream_tickets.items() if info['expires_at'] <= now]
    for t in expired:
        del _stream_tickets[t]


def issue_stream_ticket(role: str, name: str = 'unknown') -> str:
    """签发一张一次性流式连接票据。

    Args:
        role: 票据继承的角色，权限不会超过签发者
        name: 签发者名称，仅用于排查

    Returns:
        票据字符串
    """
    now = time.monotonic()
    ticket = token_urlsafe(32)
    with _stream_ticket_lock:
        _purge_expired_tickets(now)
        if len(_stream_tickets) >= _MAX_STREAM_TICKETS:
            # 清理后仍然满，说明有人在刷。丢掉最早过期的那张腾位置。
            oldest = min(_stream_tickets, key=lambda t: _stream_tickets[t]['expires_at'])
            del _stream_tickets[oldest]
        _stream_tickets[ticket] = {
            'role': role,
            'name': name,
            'expires_at': now + STREAM_TICKET_TTL,
        }
    return ticket


def consume_stream_ticket(ticket: Optional[str]) -> Optional[dict]:
    """校验并消费一张票据（用后即焚）。

    Args:
        ticket: 票据字符串

    Returns:
        {'role', 'name'}；票据不存在/已过期/已用过时返回 None
    """
    if not ticket:
        return None
    now = time.monotonic()
    with _stream_ticket_lock:
        _purge_expired_tickets(now)
        # 用 compare_digest 逐个比，避免按前缀逐字节泄漏票据内容；
        # 仍然遍历全部候选，不能命中即 break。
        matched_key = None
        for candidate in _stream_tickets:
            if compare_digest(candidate, ticket) and matched_key is None:
                matched_key = candidate
        if matched_key is None:
            return None
        info = _stream_tickets.pop(matched_key)
    return {'role': info['role'], 'name': info['name']}


def clear_stream_tickets() -> None:
    """清空票据表（测试用）"""
    with _stream_ticket_lock:
        _stream_tickets.clear()


def authorize_stream(ticket: Optional[str], permission: str = 'read') -> bool:
    """流式连接的统一鉴权入口（WebSocket 与 SSE 共用）。

    鉴权未启用时直接放行，保证自用场景行为不变。

    Args:
        ticket: 从 query 参数取到的票据
        permission: 需要的权限，默认 read

    Returns:
        True 表示允许连接
    """
    if not is_auth_enabled():
        return True
    info = consume_stream_ticket(ticket)
    if info is None:
        return False
    return has_permission(info['role'], permission)


