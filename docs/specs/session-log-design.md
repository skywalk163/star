# 群星会话日志（Star Session Log）设计文档

## 概述

借鉴 DeepSeek Harness 的 Append-only Session Log 设计理念，为群星系统构建一个统一的、可追溯的会话日志系统。每条任务交互记录为不可变事件流，支持回放、分叉、恢复和审计。

## 设计背景

### 当前问题

当前群星系统中，任务数据分散在多个位置：

| 数据来源 | 路径 | 格式 | 问题 |
|---|---|---|---|
| Agent 输出文件 | `~/.comate-engine/store/agents/*.output` | 纯文本 | 无结构化元数据 |
| 内核日志 | `~/.comate-engine/log/kernel-*.log` | 系统日志 | 混杂噪音，难以解析 |
| 计划文件 | `~/.comate/plans/*.plan.md` | Markdown | 与任务关联弱 |
| 会话状态缓存 | `dumate_bridge.session_status` | 内存 dict | 服务重启后丢失 |

总结：**数据分散、格式不统一、无版本管理、不可追溯**。

### DeepSeek Harness 的启发

Harness 的会话日志核心原则<sup>[1]</sup>：

> **"Model-visible means logged"** — 模型可见的，必须可被日志重建。

关键设计：
1. **Append-only**：只追加不删除，上下文压缩只替换表象，不删原始历史
2. **事件溯源**：所有交互记录为事件流，回放、分叉、恢复、搜索都基于同一事件流
3. **Trajectory 视图**：按来源追溯每条记录

## 设计目标

1. **统一存储**：所有 AI 的任务日志统一格式，统一存储
2. **不可变**：日志只追加，不删除、不修改历史记录
3. **可追溯**：任意时间点可重建任务状态
4. **可回放**：按时间顺序回放任务执行过程
5. **可恢复**：断连后可恢复任务状态
6. **可审计**：支持安全审计和合规检查

## 日志格式

### 事件记录结构

每条日志记录是一个 JSON 对象：

```json
{
  "version": 1,
  "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": 1723600000.123,
  "event_type": "task:created",
  "session_id": "session-uuid-xxxx",
  "ai_id": "dumate",
  "source": "dumate_bridge",
  "payload": { ... },
  "metadata": {
    "trace_id": "trace-uuid",
    "parent_event_id": null,
    "duration_ms": null
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `version` | int | 日志格式版本号 |
| `event_id` | UUID | 事件唯一标识 |
| `timestamp` | float | UNIX 时间戳 |
| `event_type` | str | 事件类型 |
| `session_id` | str | 所属会话/任务 ID |
| `ai_id` | str | AI 适配器标识 |
| `source` | str | 事件来源模块 |
| `payload` | dict | 事件载荷，随类型变化 |
| `metadata` | dict | 追踪元数据 |

### 事件类型清单

```
# 任务生命周期
task:created         # 任务创建
task:prompt_sent     # 提示词已发送
task:response_start  # AI 开始响应
task:response_chunk  # AI 响应片段
task:response_end    # AI 响应结束
task:completed       # 任务完成
task:failed          # 任务失败
task:cancelled       # 任务取消

# 状态变更
status:ai_changed    # AI 状态变化
status:session_changed  # 会话状态变化

# 系统事件
system:startup       # 系统启动
system:shutdown      # 系统关闭
system:error         # 系统错误
```

## 存储设计

### 文件结构

```
~/.star/session-logs/
├── index.json              # 会话索引（快速查找）
├── sessions/
│   ├── 2026/
│   │   ├── 08/
│   │   │   ├── session-{session_id}.log     # 事件流文件
│   │   │   └── session-{session_id}.index   # 事件位置索引
│   │   └── ...
│   └── ...
└── archive/
    ├── 2026-08-01.log       # 7天前归档
    └── ...
```

### 事件流文件格式

使用 **append-only** 格式，每行一个 JSON 事件：

```jsonl
{"version":1,"event_id":"...","event_type":"task:created","session_id":"...","payload":{...}}
{"version":1,"event_id":"...","event_type":"task:prompt_sent","session_id":"...","payload":{...}}
{"version":1,"event_id":"...","event_type":"task:response_chunk","session_id":"...","payload":{...}}
```

### 索引文件

内存中的索引用于快速定位：

```json
{
  "session_id": "session-uuid-xxxx",
  "ai_id": "dumate",
  "created_at": 1723600000.0,
  "updated_at": 1723600100.0,
  "event_count": 42,
  "status": "completed",
  "summary": "修复登录页面的 CSS 样式问题",
  "tags": ["dumate", "code", "frontend"]
}
```

## 接口设计

```python
import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional, List, Any, Iterator
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
import logging

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
        self._replay_buffer: list[SessionEvent] = []
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
                parts.append(f"\n[AI 响应完成]")
            elif event.event_type == "task:completed":
                parts.append(f"\n[任务完成] 耗时 {event.payload.get('duration_seconds', 0):.1f}s")
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
import threading
_init_lock = threading.Lock()

def get_session_log_manager() -> SessionLogManager:
    """获取全局会话日志管理器"""
    global _manager
    if _manager is None:
        with _init_lock:
            if _manager is None:
                _manager = SessionLogManager()
    return _manager
```

## 使用示例

### 在 DuMateBridge 中接入

```python
from star_core.session_log import get_session_log_manager

class DuMateBridge:
    
    def __init__(self, ...):
        self._log_manager = get_session_log_manager()
        self._session_logs = {}  # conversation_id -> SessionLog
    
    def create_task(self, prompt, ...):
        conv_id = self.create_conversation(...)
        log = self._log_manager.create_session(conv_id, ai_id="dumate")
        self._session_logs[conv_id] = log
        
        log.append("task:created", {
            "prompt": prompt,
            "workspace_id": workspace_id,
            "task_type": task_type,
        }, source="dumate_bridge")
        
        log.append("task:prompt_sent", {
            "prompt": prompt,
            "token_count": len(prompt),
        }, source="dumate_bridge")
        
        return conv_id
    
    def _process_incoming(self, text):
        for line in text.split("\n"):
            event = {"raw": line, ...}
            
            # 记录到会话日志
            conv_id = self._get_current_conversation()
            if conv_id in self._session_logs:
                log = self._session_logs[conv_id]
                log.append("dumate:engine_event", {
                    "event_type": event.get("type"),
                    "raw": line,
                }, source="pipe_reader")
            
            # 原有处理逻辑...
```

### 在前端 SSE 中回放

```javascript
// 通过 API 获取会话日志
const response = await fetch(`/api/session-logs/${sessionId}/replay`);
const events = await response.json();
events.forEach(event => {
  if (event.event_type === 'task:prompt_sent') {
    renderUserMessage(event.payload.prompt);
  } else if (event.event_type === 'task:response_chunk') {
    appendToAiResponse(event.payload.content);
  }
});
```

## 与现有系统的集成

### 数据迁移路径

1. **Phase 1**：新任务写入新格式，旧任务仍从旧位置读取
2. **Phase 2**：在 `dumate_bridge.py` 中嵌入日志记录，新事件自动写入
3. **Phase 3**：旧数据通过 Migration 工具导入统一格式
4. **Phase 4**：完全切换到会话日志，废弃旧数据源

### 路由端点

```python
# 新增 API 路由

@router.get("/session-logs/{session_id}/replay")
async def replay_session(session_id: str):
    """回放指定会话的事件流"""
    log = log_manager.get_or_create(session_id, ai_id="dumate")
    return [event for event in log.replay()]


@router.get("/session-logs/{session_id}/text")
async def get_session_text(session_id: str):
    """获取会话的人类可读文本"""
    log = log_manager.get_or_create(session_id, ai_id="dumate")
    return {"session_id": session_id, "text": log.get_full_text()}


@router.get("/session-logs")
async def list_sessions(ai_id: str = None, limit: int = 50):
    """列出所有会话日志"""
    manager = get_session_log_manager()
    return manager.list_sessions(ai_id=ai_id, limit=limit)
```

## 参考资料

1. DeepSeek Harness. Everything is a plugin. https://deepseek.com/harness/en/
2. Harness Architecture: Append-only Session Log. https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md
3. Event Sourcing pattern. Martin Fowler. https://martinfowler.com/eaaDev/EventSourcing.html