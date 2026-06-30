"""
星语者（StarAuditor）- 远程控制审计日志

记录所有远程控制操作的时间、用户、操作类型、参数和结果
"""

import os
import json
import time
import logging
from typing import Optional, List, Dict
from collections import deque
from threading import Lock
from datetime import datetime

logger = logging.getLogger(__name__)


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


class AuditLogger:
    """审计日志管理器（内存环形缓冲区 + SQLite 持久化 + 可选文件持久化）"""

    def __init__(self, max_entries: int = 1000, log_dir: Optional[str] = None,
                 enable_db: bool = True):
        self._entries: deque = deque(maxlen=max_entries)
        self._lock = Lock()
        self._log_dir = log_dir
        self._enable_db = enable_db
        self._db = None
        
        if enable_db:
            try:
                from star_core.database import get_db_service
                self._db = get_db_service()
            except Exception as e:
                logger.warning(f"初始化审计日志数据库失败: {e}")

    def log(
        self,
        operation: str,
        hwnd: Optional[int] = None,
        params: Optional[dict] = None,
        user: str = "default",
        role: str = "admin",
        result: str = "success",
        detail: str = "",
    ) -> AuditLogEntry:
        """记录一条审计日志"""
        entry = AuditLogEntry(
            operation=operation,
            hwnd=hwnd,
            params=params,
            user=user,
            role=role,
            result=result,
            detail=detail,
        )

        with self._lock:
            self._entries.append(entry)

        if self._db:
            try:
                self._db.insert_audit_log(entry.to_dict())
            except Exception as e:
                logger.warning(f"写入审计日志数据库失败: {e}")

        if self._log_dir:
            self._write_to_file(entry)

        return entry

    def _write_to_file(self, entry: AuditLogEntry):
        """写入文件（按天分片）"""
        try:
            os.makedirs(self._log_dir, exist_ok=True)
            date_str = datetime.fromtimestamp(entry.timestamp).strftime('%Y%m%d')
            file_path = os.path.join(self._log_dir, f"audit_{date_str}.jsonl")

            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + '\n')
        except Exception as e:
            logger.warning(f"写入审计日志文件失败: {e}")

    def query(
        self,
        limit: int = 50,
        offset: int = 0,
        operation: Optional[str] = None,
        hwnd: Optional[int] = None,
        user: Optional[str] = None,
        result: Optional[str] = None,
        use_db: bool = False,
    ) -> List[dict]:
        """查询审计日志（支持筛选）"""
        if use_db and self._db:
            try:
                rows, _ = self._db.query_audit_logs(
                    limit=limit, offset=offset,
                    operation=operation, hwnd=hwnd, result=result
                )
                if user:
                    rows = [r for r in rows if r.get('user') == user]
                return rows
            except Exception as e:
                logger.warning(f"查询审计日志数据库失败: {e}")
        
        with self._lock:
            entries = list(self._entries)

        entries.reverse()

        if operation:
            entries = [e for e in entries if e.operation == operation]
        if hwnd is not None:
            entries = [e for e in entries if e.hwnd == hwnd]
        if user:
            entries = [e for e in entries if e.user == user]
        if result:
            entries = [e for e in entries if e.result == result]

        sliced = entries[offset:offset + limit]
        return [e.to_dict() for e in sliced]

    def stats(self) -> dict:
        """获取审计统计"""
        with self._lock:
            entries = list(self._entries)

        total = len(entries)
        op_counts: Dict[str, int] = {}
        result_counts: Dict[str, int] = {}
        user_counts: Dict[str, int] = {}

        for e in entries:
            op_counts[e.operation] = op_counts.get(e.operation, 0) + 1
            result_counts[e.result] = result_counts.get(e.result, 0) + 1
            user_counts[e.user] = user_counts.get(e.user, 0) + 1

        return {
            'total_entries': total,
            'max_capacity': self._entries.maxlen,
            'operations': op_counts,
            'results': result_counts,
            'users': user_counts,
            'first_timestamp': entries[0].timestamp if entries else None,
            'last_timestamp': entries[-1].timestamp if entries else None,
        }


# 全局审计日志实例
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """获取全局审计日志实例"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def audit(operation: str, **kwargs):
    """便捷函数：记录操作审计日志"""
    return get_audit_logger().log(operation=operation, **kwargs)