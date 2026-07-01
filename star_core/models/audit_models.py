"""
audit_models.py - 审计相关数据模型

核心数据类：
- AuditLogEntry: 单条审计日志
"""

import time
from typing import Optional
from datetime import datetime


class AuditLogEntry:
    """单条审计日志"""

    def __init__(
        self,
        operation: str,
        hwnd: Optional[int] = None,
        params: Optional[dict] = None,
        user: str = "default",
        role: str = "admin",
        result: str = "success",
        detail: str = "",
    ):
        self.timestamp = time.time()
        self.operation = operation
        self.hwnd = hwnd
        self.params = params or {}
        self.user = user
        self.role = role
        self.result = result
        self.detail = detail

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp,
            'time_str': datetime.fromtimestamp(self.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
            'operation': self.operation,
            'hwnd': self.hwnd,
            'params': self.params,
            'user': self.user,
            'role': self.role,
            'result': self.result,
            'detail': self.detail,
        }

    @property
    def time_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp).strftime('%Y-%m-%d %H:%M:%S')

    def __repr__(self):
        return f"[{self.time_str}] {self.user}({self.role}) {self.operation} {'✓' if self.result == 'success' else '✗'}"
