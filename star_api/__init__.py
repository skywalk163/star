"""
星光接口（Star API）- FastAPI 后端
"""

# 必须先于 star_api.main 绑定：让 `from star_api import state` 拿到
# _StateCompat 实例而不是同名子模块。否则 websocket_connections /
# config / project_root 等预初始化属性全部丢失（子模块上并不存在）。
from star_api.state import state

from star_api.main import app

__all__ = ["app", "state"]
