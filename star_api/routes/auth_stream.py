"""流式连接票据签发。

浏览器原生 EventSource / WebSocket 无法设置 X-API-Key 请求头，所以这里提供
「用 header 鉴权换一张短时一次性票据」的入口，票据再随 query 参数带进连接 URL。

见 star_api/auth.py 的「流式连接票据」一节，那里写了为什么不直接把 API Key
塞进 query 参数。
"""

from fastapi import APIRouter, Depends

from star_api.auth import (
    STREAM_TICKET_TTL,
    get_current_user,
    is_auth_enabled,
    issue_stream_ticket,
)

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/stream-ticket")
async def create_stream_ticket(current_user: dict = Depends(get_current_user)):
    """签发一张流式连接票据（WebSocket / SSE 用）

    票据继承调用者的角色，权限不会被放大；一次性、TTL 见 STREAM_TICKET_TTL。
    鉴权未启用时返回空票据 —— 此时流式端点本来就放行，前端不必特殊处理。
    """
    if not is_auth_enabled():
        return {"ticket": "", "expires_in": 0, "auth_enabled": False}

    ticket = issue_stream_ticket(
        role=current_user.get("role", "viewer"),
        name=current_user.get("name", "unknown"),
    )
    return {
        "ticket": ticket,
        "expires_in": STREAM_TICKET_TTL,
        "auth_enabled": True,
    }
