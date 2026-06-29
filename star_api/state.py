"""
星光接口全局状态管理

集中管理引擎实例和连接，避免循环导入和变量绑定问题
"""

from typing import Optional


orbit_engine: Optional[object] = None
plugin_manager: Optional[object] = None
history_store: Optional[object] = None
analytics: Optional[object] = None
websocket_connections: list = []
config: dict = {}
project_root: str = ""
