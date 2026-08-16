"""
群星会话日志（Star Session Log）

借鉴 DeepSeek Harness 的 Append-only Session Log 设计理念，
为群星系统构建一个统一的、可追溯的会话日志系统。

设计文档: docs/specs/session-log-design.md
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional, List, Any, Iterator
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
import logging
import threading

logger = logging.getLogger(__name__)

# 默认存储目录
_LOG_DIR = os.path.expanduser("~/.star/session-logs")
_SESSION_DIR = os.path.join(_LOG_DIR, "sessions")


@dataclass
class SessionEvent:
    """会话事件"""
    version: int = 1
    event_id: str = ""
    timestamp: float = 0.0
    event_type: str = ""
    session_id: str = ""
    ai_id: str = ""
    source: str = ""
    payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "SessionEvent":
        data = json.loads(text)
        return cls(**data)


class SessionLog:
    """
    会话日志

    提供 append-only 的事件记录和回放功能。
    """

    def __init__(self, session_id: str, ai_id: str = "unknown"):
        self.session_id = session_id
        self.ai_id = ai_id
        self._log_path = self._get_log_path(session_id)
        self._event_count = 0
        self._logger = logging.getLogger(f"{__name__}.{session_id[:8]}")

        # 确保目录存在
        os.makedirs(os.path.dirname(self._log_path), exist_ok=True)

    def _get_log_path(self, session_id: str) -> str:
        """获取日志文件路径（按日期分目录）"""
        now = datetime.now(timezone.utc)
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        dir_path = os.path.join(_SESSION_DIR, year, month, day)
        return os.path.join(dir_path, f"session-{session_id}.log")

    def append(self, event_type: str, payload: dict,
               source: str = "", metadata: dict = None) -> SessionEvent:
        """
        追加一条事件记录

        Args:
            event_type: 事件类型
            payload: 事件载荷
            source: 事件来源模块名
            metadata: 追踪元数据

        Returns:
            创建的事件对象
        """
        event = SessionEvent(
            version=1,
            event_id=str(uuid.uuid4()),
            timestamp=time.time(),
            event_type=event_type,
            session_id=self.session_id,
            ai_id=self.ai_id,
            source=source,
            payload=payload,
            metadata=metadata or {},
        )

        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")
            self._event_count += 1
        except Exception as e:
            self._logger.error("写入日志失败: %s", e)

        return event

    def replay(self) -> Iterator[SessionEvent]:
        """
        回放所有事件

        Yields:
            按时间顺序的事件对象
        """
        if not os.path.exists(self._log_path):
            return

        with open(self._log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield SessionEvent.from_json(line)
                    except json.JSONDecodeError:
                        self._logger.warning("解析事件失败: %s", line[:80])

    def get_events_by_type(self, event_type: str) -> List[SessionEvent]:
        """按类型过滤事件"""
        return [e for e in self.replay() if e.event_type == event_type]

    def get_event_count(self) -> int:
        """获取事件总数"""
        if self._event_count == 0 and os.path.exists(self._log_path):
            try:
                with open(self._log_path, "r", encoding="utf-8") as f:
                    self._event_count = sum(1 for _ in f)
            except Exception:
                pass
        return self._event_count

    def get_duration(self) -> Optional[float]:
        """获取会话持续时间（秒）"""
        events = list(self.replay())
        if not events:
            return None
        return events[-1].timestamp - events[0].timestamp

    def get_full_text(self) -> str:
        """获取完整会话文本（用于展示）"""
        parts = []
        for event in self.replay():
            if event.event_type == "task:prompt_sent":
                parts.append(f"[用户] {event.payload.get('prompt', '')}")
            elif event.event_type == "task:response_chunk":
                parts.append(event.payload.get('content', ''))
            elif event.event_type == "task:response_end":
                parts.append("\n[AI 响应完成]")
            elif event.event_type == "task:completed":
                parts.append(
                    "\n[任务完成] 耗时 {}s".format(
                        event.payload.get('duration_seconds', 0)
                    )
                )
        return "\n".join(parts)


class SessionLogManager:
    """
    会话日志管理器

    负责管理所有会话日志的整体生命周期：
    - 创建新会话日志
    - 查找历史会话
    - 归档旧日志
    - 维护索引
    """

    def __init__(self, log_dir: str = None):
        self._log_dir = log_dir or _LOG_DIR
        self._sessions: dict[str, SessionLog] = {}
        self._logger = logging.getLogger(__name__)
        os.makedirs(self._log_dir, exist_ok=True)

    def create_session(self, session_id: str, ai_id: str = "unknown") -> SessionLog:
        """创建新会话日志"""
        log = SessionLog(session_id, ai_id=ai_id)
        self._sessions[session_id] = log

        # 记录系统事件
        log.append("system:session_created", {
            "ai_id": ai_id,
        }, source="session_log")

        return log

    def get_session(self, session_id: str) -> Optional[SessionLog]:
        """获取会话日志（如果已创建）"""
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str, ai_id: str = "unknown") -> SessionLog:
        """获取或创建会话日志"""
        if session_id not in self._sessions:
            # 检查是否已有已存在的日志文件
            log = SessionLog(session_id, ai_id=ai_id)
            if log.get_event_count() > 0:
                self._sessions[session_id] = log
            else:
                log.append("system:session_created", {"ai_id": ai_id}, source="session_log")
                self._sessions[session_id] = log
        return self._sessions[session_id]

    def list_sessions(self, ai_id: str = None, limit: int = 50) -> List[dict]:
        """列出最近的会话摘要"""
        sessions = []
        session_dir = Path(_SESSION_DIR)
        if not session_dir.is_dir():
            return sessions

        # 遍历所有 .log 文件
        for log_file in sorted(session_dir.rglob("session-*.log"),
                                key=os.path.getmtime, reverse=True):
            if len(sessions) >= limit:
                break

            session_id = log_file.stem.replace("session-", "", 1)
            if ai_id:
                # 检查第一行中的 ai_id
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        first_line = f.readline().strip()
                        if first_line:
                            first_event = SessionEvent.from_json(first_line)
                            if first_event.ai_id != ai_id:
                                continue
                except Exception:
                    continue

            sessions.append({
                "session_id": session_id,
                "log_file": str(log_file),
                "size": log_file.stat().st_size,
                "modified_at": log_file.stat().st_mtime,
            })

        return sessions


# 全局管理器
_manager: Optional[SessionLogManager] = None
_init_lock = threading.Lock()


def get_session_log_manager() -> SessionLogManager:
    """获取全局会话日志管理器"""
    global _manager
    if _manager is None:
        with _init_lock:
            if _manager is None:
                _manager = SessionLogManager()
    return _manager