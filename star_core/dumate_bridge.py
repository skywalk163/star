"""
搭子桥（DuMateBridge）- 通过命名管道连接 DuMate 内核

DuMate（百度文心快码 Comate）内核通过命名管道进行 IPC 通信。

== 协议（2026-08-14 逆向分析）==
发送命令:
  COMATE_AGENT_START_NEW_CHAT {"agentPayload":{...}}
  COMATE_AGENT_NEW_MESSAGE {"agentPayload":{...}}
  COMATE_AGENT_SET_FOREGROUND_CONVERSATION {"agentPayload":{...}}
  COMATE_AGENT_STOP

内核响应（通过同一管道返回）:
  <--------- ENGINE SEND: EVENT_NAME {...}
  KERNEL_SPEC_STATE_CHANGED: {"type":"SESSION_STATUS_UPDATED","payload":{...}}

== 会话生命周期 ==
1. START_NEW_CHAT → 创建会话（指定 workspaceId, conversationType）
2. NEW_MESSAGE (add-message) → 发送用户消息（含 query、agent、model）
3. 内核通过 ENGINE SEND 返回 AI 响应流
4. STOP → 停止生成
5. KERNEL_SPEC_STATE_CHANGED → 会话状态更新（running/completed）

== 任务类型 ==
通过 agent 配置的 strategy 区分:
  - "TODOS" → 通用工作模式（work）
  - "CODE"  → 代码模式（code）
  - 其他     → 设计模式（design）

== 插件化架构 =============================================================
本模块已重构为 AIAdapter 插件，遵循群星插件化架构。

  之前: DuMateBridge 单体类，硬编码所有逻辑
  现在: DuMateBridge(AIAdapter) 实现统一接口，自注册到 AIAdapterRegistry

  ┌─────────────────────────────────────────────────────┐
  │  AIAdapterRegistry (注册表)                          │
  │  ├── DuMateAdapter (via DuMateBridge)               │
  │  ├── TraeWorkAdapter (未来)                          │
  │  └── CursorAdapter (未来)                            │
  └─────────────────────────────────────────────────────┘
                     │ 统一接口
                     ▼
              调用方 (API 路由 / 前端)
==========================================================================
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import win32file
    import win32pipe
    import win32con
    import pywintypes
    import win32event
    HAS_PYWIN32 = True
except ImportError:
    HAS_PYWIN32 = False

from star_core.ai_adapter import (
    AIAdapter,
    AICapability,
    AIAdapterInfo,
    get_adapter_registry,
)

logger = logging.getLogger(__name__)

#: DuMate 目录
_DUMATE_ENGINE_DIR = os.path.expanduser("~/.comate-engine")
_DUMATE_CONFIG_DIR = os.path.expanduser("~/.comate")
_AGENT_OUTPUT_DIR = os.path.join(_DUMATE_ENGINE_DIR, "store", "agents")
_KERNEL_LOG_DIR = os.path.join(_DUMATE_ENGINE_DIR, "log")

#: 会话存储目录。内核把每个会话的完整内容写成单个 JSON 文件
#: ``store/chat_session_<sessionUuid>``，并在 ``store/comate_chat_sessions.jsonl``
#: 维护一行一条的会话索引。这是结果的**权威来源**；
#: ``store/agents/*.output`` 只存放 IDE 自身 subagent 的转录，不是会话结果。
_SESSION_STORE_DIR = os.path.join(_DUMATE_ENGINE_DIR, "store")
_SESSION_INDEX_FILE = os.path.join(_SESSION_STORE_DIR, "comate_chat_sessions.jsonl")

#: assistant 消息 elements 树里承载"用户可见回复"的节点类型。
#: REASON 是思考过程、TOOL 是工具调用，都不算回复正文。
_VISIBLE_ELEMENT_TYPES = ("TEXT",)


def read_session_index() -> list:
    """读取会话索引 ``comate_chat_sessions.jsonl``。

    索引按追加写入，同一 sessionUuid 会出现多行（每次更新追加一条），
    故按 sessionUuid 去重并保留 utime 最大的那条。

    Returns:
        会话字典列表，按 utime 降序。读不到时返回空列表。
    """
    if not os.path.isfile(_SESSION_INDEX_FILE):
        return []
    latest: dict = {}
    try:
        with open(_SESSION_INDEX_FILE, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                suuid = rec.get("sessionUuid")
                if not suuid:
                    continue
                prev = latest.get(suuid)
                if prev is None or rec.get("utime", 0) >= prev.get("utime", 0):
                    latest[suuid] = rec
    except Exception as e:
        logger.warning("read_session_index: 读取 %s 失败: %s", _SESSION_INDEX_FILE, e)
        return []
    return sorted(latest.values(), key=lambda r: r.get("utime", 0), reverse=True)


def read_session_file(session_uuid: str) -> Optional[dict]:
    """读取单个会话的完整 JSON（``store/chat_session_<uuid>``）。

    Returns:
        解析后的 dict；文件不存在或解析失败返回 None。
    """
    path = os.path.join(_SESSION_STORE_DIR, f"chat_session_{session_uuid}")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _collect_visible_text(node, out: list) -> None:
    """递归收集 elements 树中可见回复文本。

    节点形如 ``{"type": "TEXT", "content": "...", "children": [...]}``，
    也存在只有 children 的容器节点（type 缺失），故需无条件下钻。
    """
    if isinstance(node, dict):
        if node.get("type") in _VISIBLE_ELEMENT_TYPES:
            content = node.get("content")
            if isinstance(content, str) and content.strip():
                out.append(content)
        for value in node.values():
            _collect_visible_text(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_visible_text(item, out)


def extract_session_reply(session_uuid: str) -> Optional[dict]:
    """提取会话中最后一条 assistant 回复的正文与状态。

    Returns:
        ``{"text": str, "status": str, "completed": bool}``；
        会话不存在或还没有 assistant 消息时返回 None。
    """
    data = read_session_file(session_uuid)
    if not data:
        return None
    messages = data.get("messages")
    if not isinstance(messages, list):
        return None
    assistants = [
        m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"
    ]
    if not assistants:
        return None
    last = assistants[-1]
    chunks: list = []
    _collect_visible_text(last.get("elements"), chunks)
    status = str(last.get("status") or "")
    return {
        "text": "\n\n".join(chunks).strip(),
        "status": status,
        # inProgress 表示仍在生成；success/cancelled/failed 视为已收尾
        "completed": status not in ("inProgress", ""),
    }


#: 任务类型 → Agent 策略映射
TASK_TYPE_STRATEGIES = {
    "work": "TODOS",
    "code": "CODE",
    "design": "DESIGN",
}

#: 任务类型 → Agent 配置
TASK_TYPE_AGENTS = {
    "work": {
        "agentId": 1,
        "agentName": "Comate",
        "agentImage": "zulu",
        "description": "具备读取、编写、执行命令与联网能力，可灵活适配多种任务与场景。",
        "strategy": "TODOS",
        "canInvokeAgents": True,
        "canUseMcp": True,
        "visibility": "PUBLIC",
        "sortOrder": 1,
        "reportAgentName": "Zulu",
        "enable": True,
        "subagents": [],
    },
    "code": {
        "agentId": 2,
        "agentName": "Comate",
        "agentImage": "zulu",
        "description": "专注于代码生成、重构和调试。",
        "strategy": "CODE",
        "canInvokeAgents": True,
        "canUseMcp": True,
        "visibility": "PUBLIC",
        "sortOrder": 2,
        "reportAgentName": "Zulu",
        "enable": True,
        "subagents": [],
    },
    "design": {
        "agentId": 3,
        "agentName": "Comate",
        "agentImage": "zulu",
        "description": "专注于架构设计、方案评审和文档编写。",
        "strategy": "DESIGN",
        "canInvokeAgents": True,
        "canUseMcp": True,
        "visibility": "PUBLIC",
        "sortOrder": 3,
        "reportAgentName": "Zulu",
        "enable": True,
        "subagents": [],
    },
}


def _discover_kernel_port() -> Optional[int]:
    """从 ctrl-servers.json 发现内核端口"""
    ctrl_path = os.path.join(_DUMATE_CONFIG_DIR, "ctrl-servers.json")
    if not os.path.exists(ctrl_path):
        return None
    try:
        with open(ctrl_path, "r", encoding="utf-8") as f:
            servers = json.load(f)
        for server in servers:
            m = re.search(r"comate-kernel-(\d+)", server.get("socketPath", ""))
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return None


def _get_kernel_log_file() -> Optional[str]:
    """找到最新的内核日志文件

    兼容两种命名：旧式 ``kernel-*.log`` 与新式日期命名 ``YYYY-MM-DD.log``。
    Comate 在 2026-08 起改为按天滚动日志，旧代码只匹配 kernel-* 会导致日志
    路径永远为 None，进而使基于日志的会话→任务映射失效。
    """
    if not os.path.isdir(_KERNEL_LOG_DIR):
        return None
    logs: list[str] = []
    for f in os.listdir(_KERNEL_LOG_DIR):
        if (f.startswith("kernel-") and f.endswith(".log")) or \
           re.fullmatch(r"\d{4}-\d{2}-\d{2}\.log", f):
            logs.append(f)
    if not logs:
        return None
    logs.sort(reverse=True)
    return os.path.join(_KERNEL_LOG_DIR, logs[0])


def _discover_workspaces() -> list[dict]:
    """从内核日志发现可用的工作目录

    Returns:
        [{"path": "g:\\jikuai", "name": "jikuai"}, ...]
    """
    workspaces = {}
    log_file = _get_kernel_log_file()
    if log_file:
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    for m in re.finditer(
                        r'"workspaceId":"([^"]+)"',
                        line,
                    ):
                        wid = m.group(1)
                        if wid and wid not in workspaces:
                            workspaces[wid] = {
                                "path": wid,
                                "name": os.path.basename(wid) if wid else wid,
                            }
        except Exception:
            pass
    return list(workspaces.values())


class DuMateBridge(AIAdapter):
    """搭子桥 - DuMate 内核通讯桥（持久连接版）

    通过命名管道连接到 DuMate 内核，维持持久连接，并在后台
    线程读取内核响应。支持实时流式输出、会话管理和任务类型。

    实现了 AIAdapter 统一接口，可注册到 AIAdapterRegistry，
    也能作为独立类使用（向后兼容）。

    Attributes:
        port: 内核端口号
        pipe_path: 命名管道路径
        connected: 是否已连接
        session_status: 最新会话状态缓存
        response_queue: 内核响应队列（用于 SSE 流式推送）
    """

    # ── AIAdapter 元信息 ──────────────────────────────────────
    AI_ID = "dumate"
    AI_NAME = "DuMate (文心快码)"
    AI_VERSION = "1.0.0"
    DESCRIPTION = "通过命名管道连接 DuMate 内核，实现任务创建、管理和实时监控"

    # ── 协议常量 ──────────────────────────────────────────────
    CMD_START_CHAT = "COMATE_AGENT_START_NEW_CHAT"
    CMD_NEW_MSG = "COMATE_AGENT_NEW_MESSAGE"
    CMD_SET_FOREGROUND = "COMATE_AGENT_SET_FOREGROUND_CONVERSATION"
    CMD_STOP = "COMATE_AGENT_STOP"

    def __init__(self, port: Optional[int] = None, auto_register: bool = True):
        if port is None:
            port = _discover_kernel_port()
        self.port = port or 0
        self.pipe_path = f"\\\\.\\pipe\\comate-kernel-{self.port}"
        self._handle: Optional[int] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # 内核响应队列（用于流式推送）
        self.response_queue: queue.Queue[dict] = queue.Queue()

        # 会话状态缓存
        self.session_status: dict[str, dict] = {}

        # 会话 UUID → 数字 taskId 的精确映射
        # 修复缺陷②：新建会话后通过"创建前快照 / 创建后探测"定位内核实际写入的
        # .output 文件，避免读回时回退到"最近修改的文件"而返回他人任务的内容。
        self._conv_output_map: dict[str, str] = {}

        # 回调注册（向后兼容旧接口）
        self._on_response_callbacks: list[Callable] = []

        super().__init__()

        # 自动注册到注册表
        if auto_register:
            try:
                registry = get_adapter_registry()
                registry.register(self)
            except Exception as e:
                self._logger.warning("注册到适配器注册表失败: %s", e)

    # ── AIAdapter 接口实现 ─────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._handle is not None and self._running

    def connect(self) -> bool:
        """连接到 DuMate 内核命名管道并启动后台读取线程"""
        if self.connected:
            return True
        if not HAS_PYWIN32:
            logger.warning("DuMateBridge: pywin32 未安装")
            return False

        try:
            handle = win32file.CreateFile(
                self.pipe_path,
                win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                0, None, win32con.OPEN_EXISTING,
                win32con.FILE_ATTRIBUTE_NORMAL | win32con.FILE_FLAG_OVERLAPPED,
                None,
            )
            self._handle = handle
            self._running = True

            # 启动后台读取线程
            self._reader_thread = threading.Thread(
                target=self._pipe_reader_loop,
                daemon=True,
                name="dumate-pipe-reader",
            )
            self._reader_thread.start()

            logger.info("DuMateBridge: 已连接到内核管道 %s", self.pipe_path)
            return True
        except Exception as e:
            logger.warning("DuMateBridge: 连接失败: %s", e)
            self._handle = None
            return False

    def disconnect(self):
        """断开连接"""
        self._running = False
        with self._lock:
            if self._handle:
                try:
                    win32file.CloseHandle(self._handle)
                except Exception:
                    pass
                self._handle = None
        logger.info("DuMateBridge: 已断开连接")

    def close(self):
        """别名：断开连接（向后兼容）"""
        self.disconnect()

    def on_response(self, callback: Callable[[dict], None]):
        """注册内核响应回调（向后兼容）"""
        self._on_response_callbacks.append(callback)

    # ── AIAdapter 任务管理接口 ──────────────────────────────

    def create_task(
        self,
        prompt: str,
        workspace_id: str = "",
        task_type: str = "work",
        agent_name: str = "Comate",
        **kwargs,
    ) -> dict:
        """创建并运行新任务（一键操作）

        组合 create_conversation + send_user_message。
        使用 PC 端真实消息格式。

        按照 PC 端实际时序：
        1. START_NEW_CHAT - 创建会话
        2. SET_FOREGROUND_CONVERSATION - 设置前台
        3. 短暂等待让内核完成初始化
        4. NEW_MESSAGE - 发送用户消息

        Args:
            prompt: 任务提示词
            workspace_id: 工作目录
            task_type: 任务类型（work/code/design）
            agent_name: Agent 名称

        Returns:
            {"success": bool, "conversation_id": str, "message": str}
        """
        # 创建前快照，用于创建后精确探测本次会话的输出文件
        before = self._snapshot_output_files()

        conv_id = self.create_conversation(
            workspace_id=workspace_id,
            task_type=task_type,
        )
        if not conv_id:
            return {
                "success": False,
                "conversation_id": "",
                "message": "创建会话失败",
            }

        # PC 端实际操作顺序：创建会话 → 设置前台 → 等待初始化 → 发送消息
        self.set_foreground_conversation(conv_id)
        # 短暂等待内核完成会话初始化（匹配 PC 端时序）
        time.sleep(0.3)

        ok = self.send_user_message(
            text=prompt,
            conversation_id=conv_id,
            task_type=task_type,
        )
        if not ok:
            return {
                "success": False,
                "conversation_id": conv_id,
                "message": "发送消息失败",
            }

        # 创建后探测内核写入的 .output 文件，建立会话→taskId 精确映射
        # （修复缺陷②：之前无映射时会回退到"最近修改的文件"返回他人任务内容）
        # 后台线程探测，避免阻塞创建请求（最长 12s）；映射就绪前前端轮询会收到
        # found=False，就绪后自然命中。
        threading.Thread(
            target=self._capture_output_for_conv,
            args=(conv_id, before),
            daemon=True,
            name=f"dumate-output-capture-{conv_id[:8]}",
        ).start()

        logger.info(
            "DuMateBridge: 任务已启动 %s (%s) workspace=%s",
            conv_id[:8], task_type, workspace_id or "(default)",
        )

        return {
            "success": True,
            "conversation_id": conv_id,
            "message": f"已向 {agent_name} 发送任务 ({task_type}), 会话: {conv_id[:8]}...",
        }

    def stop_task(self, task_id: str) -> bool:
        """停止指定任务

        Args:
            task_id: 会话 ID（与 DuMate 内核通信使用当前会话停止）

        Returns:
            True 表示已发送停止命令
        """
        return self.stop_generation()

    def get_task_output(
        self,
        task_id: str,
        max_lines: int = 200,
    ) -> Optional[str]:
        """获取任务输出内容

        从 Agent 输出目录中查找与指定会话关联的输出文件。

        Args:
            task_id: 会话 UUID 或数字 taskId
            max_lines: 最大读取行数

        Returns:
            输出内容文本，如果未找到则返回 None
        """
        return self.get_conversation_output(task_id, max_lines=max_lines)

    def get_status(self) -> str:
        """检测 DuMate 内核当前状态

        Returns:
            'idle' | 'generating' | 'unknown' | 'offline'
        """
        if not self.is_alive():
            return "offline"

        # 检查缓存中的会话状态
        for suuid, status in self.session_status.items():
            if status.get("status") == "running":
                return "generating"

        # 检查 Agent 输出目录是否有活跃的任务
        output_dir = Path(_AGENT_OUTPUT_DIR)
        if output_dir.is_dir():
            for f in output_dir.glob("*.output"):
                age = time.time() - os.path.getmtime(f)
                if age < 30:
                    return "generating"

        # 检查内核日志
        log_file = _get_kernel_log_file()
        if log_file:
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    last_lines = f.readlines()[-200:]
                for line in reversed(last_lines):
                    if "ParameterCollector finished" in line:
                        return "idle"
                    if "start analyze" in line:
                        return "generating"
            except Exception:
                pass

        return "idle"

    def list_conversations(self) -> list[dict]:
        """获取所有会话列表。

        权威来源是会话索引 ``store/comate_chat_sessions.jsonl``（内核写入，
        按 sessionUuid 去重取最新）。管道事件缓存 ``session_status`` 作为
        补充叠加（若 reader 线程恰好收到过实时状态）。
        """
        sessions: dict = {}

        # 1. 会话索引（权威、离线可读，不依赖管道存活）
        for rec in read_session_index():
            suuid = rec.get("sessionUuid")
            if not suuid:
                continue
            sessions[suuid] = {
                "conversation_id": suuid,
                "title": rec.get("title", ""),
                "status": rec.get("status", "unknown"),
                "workspace_id": rec.get("workspaceId")
                or rec.get("workspaceDirectory", ""),
                "workspace_name": rec.get("workspaceName", ""),
                "ctime": rec.get("ctime", 0),
                "utime": rec.get("utime", 0),
            }

        # 2. 管道事件缓存叠加（实时状态优先覆盖）
        for suuid, status in self.session_status.items():
            merged = sessions.get(suuid, {"conversation_id": suuid})
            merged.update({
                "title": status.get("title", merged.get("title", "")),
                "status": status.get("status", merged.get("status", "unknown")),
                "workspace_id": status.get(
                    "workspaceId", merged.get("workspace_id", "")),
                "workspace_name": status.get(
                    "workspaceName", merged.get("workspace_name", "")),
                "ctime": status.get("ctime", merged.get("ctime", 0)),
                "utime": status.get("utime", merged.get("utime", 0)),
            })
            sessions[suuid] = merged

        return sorted(
            sessions.values(), key=lambda s: s.get("utime", 0), reverse=True
        )


    def get_capabilities(self) -> list[AICapability]:
        """获取 DuMate 支持的能力列表"""
        return [
            AICapability("create_task", "1.0", "创建并运行新任务"),
            AICapability("stop_task", "1.0", "停止正在运行的任务"),
            AICapability("get_task_output", "1.0", "获取任务输出内容"),
            AICapability("list_conversations", "1.0", "列出所有会话"),
            AICapability("stream_events", "1.0", "实时事件流推送"),
            AICapability("task_types", "1.0", "支持 work/code/design 三种任务类型"),
        ]

    # ── 连接管理 ──────────────────────────────────────────────

    def is_alive(self) -> bool:
        """探测 DuMate 内核是否可达"""
        if not HAS_PYWIN32:
            return False
        try:
            handle = win32file.CreateFile(
                self.pipe_path,
                win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                0, None, win32con.OPEN_EXISTING,
                win32con.FILE_ATTRIBUTE_NORMAL, None,
            )
            win32file.CloseHandle(handle)
            return True
        except Exception:
            return False

    # ── 后台管道读取线程 ────────────────────────────────────

    def _pipe_reader_loop(self):
        """后台线程：持续读取内核管道响应"""
        buf = b""
        while self._running and self._handle:
            try:
                overlapped = pywintypes.OVERLAPPED()
                overlapped.hEvent = win32event.CreateEvent(None, False, False, None)
                read_buf = win32file.AllocateReadBuffer(8192)
                hr, _ = win32file.ReadFile(self._handle, read_buf, overlapped)

                if hr == win32con.ERROR_IO_PENDING:
                    rc = win32event.WaitForSingleObject(overlapped.hEvent, 1000)
                    if rc == win32con.WAIT_OBJECT_0:
                        bytes_read = win32file.GetOverlappedResult(
                            self._handle, overlapped, False)
                        chunk = read_buf[:bytes_read].decode("utf-8", errors="ignore")
                        buf += chunk.encode("utf-8")
                        self._process_incoming(chunk)
                    elif rc == win32con.WAIT_TIMEOUT:
                        win32file.CancelIo(self._handle)
                        continue
                elif hr == 0:
                    chunk = read_buf.decode("utf-8", errors="ignore").rstrip("\x00")
                    if chunk:
                        self._process_incoming(chunk)
                else:
                    time.sleep(0.1)

            except pywintypes.error as e:
                if e.winerror == 109:  # 管道已关闭
                    logger.info("DuMateBridge: 管道已关闭")
                    break
                elif e.winerror == 232:  # 管道正在被关闭
                    # 写端可能触发关闭，给内核一点时间重建管道后继续读
                    time.sleep(0.2)
                    if not self._running:
                        break
                    continue
                else:
                    logger.debug("DuMateBridge: 读取错误 %s", e)
                    time.sleep(0.5)
            except Exception as e:
                logger.debug("DuMateBridge: 读取异常 %s", e)
                time.sleep(0.5)

        self._running = False
        logger.info("DuMateBridge: 读取线程已退出")

    def _process_incoming(self, text: str):
        """处理内核发来的响应文本"""
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            event = {"raw": line, "timestamp": time.time()}

            # 解析 KERNEL_SPEC_STATE_CHANGED
            if line.startswith("KERNEL_SPEC_STATE_CHANGED:"):
                try:
                    payload_str = line[len("KERNEL_SPEC_STATE_CHANGED:"):].strip()
                    payload = json.loads(payload_str)
                    event["type"] = "session_status_changed"
                    event["data"] = payload

                    # 更新会话状态缓存
                    if payload.get("type") == "SESSION_STATUS_UPDATED":
                        suuid = payload.get("payload", {}).get("sessionUuid")
                        if suuid:
                            self.session_status[suuid] = payload["payload"]
                except json.JSONDecodeError:
                    event["type"] = "unknown"

            # 解析 ENGINE SEND
            elif line.startswith("<--------- ENGINE SEND:"):
                try:
                    # 格式: <--------- ENGINE SEND: EVENT_NAME {...}
                    rest = line[len("<--------- ENGINE SEND:"):].strip()
                    space_idx = rest.find(" ")
                    if space_idx > 0:
                        event_name = rest[:space_idx]
                        data_str = rest[space_idx:].strip()
                        data = json.loads(data_str)
                        event["type"] = "engine_send"
                        event["event_name"] = event_name
                        event["data"] = data
                    else:
                        event["type"] = "engine_send"
                        event["event_name"] = rest
                        event["data"] = {}
                except json.JSONDecodeError:
                    event["type"] = "engine_send_raw"
                    event["data"] = {"text": rest}

            # 其他原始响应
            else:
                event["type"] = "raw"

            # 放入队列并通知回调
            self.response_queue.put(event)
            for cb in self._on_response_callbacks:
                try:
                    cb(event)
                except Exception:
                    pass

    # ── 底层发送 ──────────────────────────────────────────────

    def _send_raw(self, text: str) -> bool:
        """发送原始文本到内核管道

        Comate 内核会在一次命令交互后关闭命名管道（winerror 109/232）。
        因此发送失败时需断开并重连一次再重试，避免"只能创建一次任务"
        的可用性问题。

        Args:
            text: 要发送的文本（会自动加 \n）

        Returns:
            True 如果发送成功
        """
        if not self.connected and not self.connect():
            return False
        try:
            with self._lock:
                win32file.WriteFile(self._handle, (text + "\n").encode("utf-8"))
            return True
        except pywintypes.error as e:
            if e.winerror in (109, 232):  # 管道已关闭 / 正在关闭
                logger.warning(
                    "DuMateBridge: 管道已关闭 (winerror=%s)，重连后重试", e.winerror)
                self.disconnect()
                if self.connect():
                    try:
                        with self._lock:
                            win32file.WriteFile(
                                self._handle, (text + "\n").encode("utf-8"))
                        return True
                    except Exception as e2:
                        logger.warning("DuMateBridge: 重连后发送仍失败: %s", e2)
                        return False
                return False
            logger.warning("DuMateBridge: 发送失败: %s", e)
            return False
        except Exception as e:
            logger.warning("DuMateBridge: 发送失败: %s", e)
            return False

    # ── 核心 API ──────────────────────────────────────────────

    def create_conversation(
        self,
        workspace_id: str = "",
        task_type: str = "work",
        conversation_id: Optional[str] = None,
    ) -> Optional[str]:
        """创建新会话

        发送 COMATE_AGENT_START_NEW_CHAT 到内核。

        Args:
            workspace_id: 工作目录路径（如 "g:\\jikuai"）
            task_type: 任务类型（work/code/design）
            conversation_id: 会话 UUID，不指定则自动生成

        Returns:
            会话 UUID，失败返回 None
        """
        conv_id = conversation_id or str(uuid.uuid4())
        payload = json.dumps({
            "agentPayload": {
                "conversationId": conv_id,
                "conversationType": "AgentConversation",
                "payload": {
                    "isSpec": False,
                    "workspaceId": workspace_id,
                },
                "messageType": "rebuild-conversation",
            },
        })
        msg = f"{self.CMD_START_CHAT} {payload}"

        if not self._send_raw(msg):
            return None

        logger.info(
            "DuMateBridge: 已创建会话 %s (workspace=%s, type=%s)",
            conv_id, workspace_id or "(默认)", task_type,
        )

        return conv_id

    def send_user_message(
        self,
        text: str,
        conversation_id: str,
        task_type: str = "work",
        model_id: str = "auto_invite_v1",
    ) -> bool:
        """发送用户消息到指定会话（使用 PC 端真实消息格式）

        使用 COMATE_AGENT_NEW_MESSAGE 命令，消息类型为
        "add-message"，与 PC 端 Comate 发送消息的格式完全一致。

        Args:
            text: 消息内容
            conversation_id: 会话 UUID
            task_type: 任务类型（work/code/design），影响 agent 配置
            model_id: 模型 ID

        Returns:
            True 如果发送成功
        """
        agent_config = TASK_TYPE_AGENTS.get(task_type, TASK_TYPE_AGENTS["work"])

        payload = json.dumps({
            "agentPayload": {
                "messageType": "add-message",
                "conversationId": conversation_id,
                "payload": {
                    "query": text,
                    "rawMessage": text,
                    "model": {
                        "displayName": "Auto",
                        "modelId": model_id,
                        "requestType": "COMATE_DEFAULT_MODE",
                        "mode": "NORMAL",
                    },
                    "agent": agent_config,
                    "knowledgeList": [],
                    "isCurrentFileSelected": False,
                    "localPermissionMode": "approval-required",
                },
            },
        })
        msg = f"{self.CMD_NEW_MSG} {payload}"

        if not self._send_raw(msg):
            return False

        logger.info(
            "DuMateBridge: 已发送消息到会话 %s (type=%s, %d chars)",
            conversation_id[:8], task_type, len(text),
        )
        return True

    def _snapshot_output_files(self) -> dict[str, float]:
        """快照当前 store/agents 下所有 .output 文件的 mtime（用于创建后定位）"""
        out: dict[str, float] = {}
        d = Path(_AGENT_OUTPUT_DIR)
        if d.is_dir():
            for f in d.glob("*.output"):
                try:
                    out[f.name] = os.path.getmtime(f)
                except OSError:
                    pass
        return out

    def _capture_output_for_conv(
        self,
        conv_id: str,
        before: dict[str, float],
        timeout: float = 12.0,
    ) -> Optional[str]:
        """创建任务后探测内核实际写入的 .output 文件，建立会话 UUID→taskId 映射。

        原理：发送 START_NEW_CHAT + NEW_MESSAGE 后，内核会为本次会话创建（或更新）
        一个 ``<类型>_<taskId>.output`` 文件。创建前先快照目录 mtime，创建后轮询
        一段时间，优先选择"快照中不存在的新文件"，否则选择"mtime 晚于快照时刻的文件"，
        取其中最新者作为本次会话的输出文件。

        返回数字 taskId（文件名中下划线之后的部分），若探测窗口内未出现则返回 None。
        """
        snapshot_time = max(before.values()) if before else 0.0
        start = time.time()
        while time.time() - start < timeout:
            d = Path(_AGENT_OUTPUT_DIR)
            if d.is_dir():
                new_file = None          # 快照中不存在的文件（最强信号）
                newest_updated = None    # mtime 晚于快照时刻的文件
                newest_new_mtime = 0.0
                newest_upd_mtime = 0.0
                for f in d.glob("*.output"):
                    try:
                        mtime = os.path.getmtime(f)
                    except OSError:
                        continue
                    if f.name not in before:
                        if mtime > newest_new_mtime:
                            newest_new_mtime = mtime
                            new_file = f.name
                    elif mtime > before[f.name] + 0.001:
                        if mtime > newest_upd_mtime:
                            newest_upd_mtime = mtime
                            newest_updated = f.name
                chosen = new_file or newest_updated
                if chosen:
                    m = re.match(r"\w+_(\d+)\.output", chosen)
                    if m:
                        task_id = m.group(1)
                        self._conv_output_map[conv_id] = task_id
                        logger.info(
                            "DuMateBridge: 会话 %s → 输出文件 taskId=%s (%s)",
                            conv_id[:8], task_id, chosen,
                        )
                        return task_id
            time.sleep(0.5)
        logger.warning(
            "DuMateBridge: 会话 %s 在 %.0fs 内未定位到输出文件（内核可能未写入 .output）",
            conv_id[:8], timeout,
        )
        return None

    def set_foreground_conversation(self, conversation_id: str) -> bool:
        """设置前台会话"""
        payload = json.dumps({
            "agentPayload": {
                "conversationId": conversation_id,
            },
        })
        return self._send_raw(f"{self.CMD_SET_FOREGROUND} {payload}")

    def stop_generation(self) -> bool:
        """停止当前 AI 生成

        发送 COMATE_AGENT_STOP 到内核。
        """
        if not self._send_raw(self.CMD_STOP):
            return False
        logger.info("DuMateBridge: 已发送停止生成命令")
        return True

    # ── 会话与任务查询 ──────────────────────────────────────

    def get_session_status(self, conversation_id: str) -> Optional[dict]:
        """获取指定会话的最新状态"""
        return self.session_status.get(conversation_id)

    def get_conversation_output(
        self,
        conversation_id: str,
        max_lines: int = 200,
    ) -> Optional[str]:
        """获取指定会话的 Agent 输出内容

        映射优先级：
        0. 会话存储直读（权威来源）：``store/chat_session_<uuid>`` 里最后一条
           assistant 消息的可见正文。内核就是把结果写在这里的。
        1. 数字 taskId 直达：直接匹配 ``*_<taskId>.output``
        2. 会话 UUID 精确映射：使用创建任务时建立的 ``conversation_id → taskId`` 映射
        3. 内核日志回退：若映射未命中，扫描内核日志中 ``conversation_id`` 关联的行，
           提取 ``taskId`` 后再匹配 .output 文件
        4. 以上都未命中 → 返回 None（调用方据此返回 found=False，而非他人任务内容）

        Args:
            conversation_id: 会话 UUID 或数字 taskId
            max_lines: 最大读取行数

        Returns:
            输出内容文本，如果未找到则返回 None
        """
        def _read_output_file(fname: str) -> Optional[str]:
            try:
                lines = []
                with open(fname, "r", encoding="utf-8", errors="ignore") as fh:
                    for i, line in enumerate(fh):
                        if i >= max_lines:
                            break
                        lines.append(line.rstrip("\n"))
                return "\n".join(lines)
            except Exception:
                return None

        # 0. 会话存储直读：内核把会话正文写在 store/chat_session_<uuid>
        reply = extract_session_reply(conversation_id)
        if reply and reply["text"]:
            lines = reply["text"].split("\n")
            return "\n".join(lines[:max_lines]) if max_lines else reply["text"]

        output_dir = Path(_AGENT_OUTPUT_DIR)

        # 1. 数字 taskId 直达
        if re.match(r'^\d+$', conversation_id):
            if output_dir.is_dir():
                for f in output_dir.glob(f"*_{conversation_id}.output"):
                    content = _read_output_file(str(f))
                    if content is not None:
                        return content
            return None

        # 2. 会话 UUID 精确映射（创建任务时建立，最可靠）
        mapped_task_id = self._conv_output_map.get(conversation_id)
        if mapped_task_id and output_dir.is_dir():
            for f in output_dir.glob(f"*_{mapped_task_id}.output"):
                content = _read_output_file(str(f))
                if content is not None:
                    return content

        # 3. 内核日志回退：扫描 conversation_id 关联行提取 taskId
        task_id = None
        log_file = _get_kernel_log_file()
        if log_file:
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if conversation_id in line:
                            m = re.search(r'taskId=(\d+)', line)
                            if m:
                                task_id = m.group(1)
                                break
            except Exception:
                pass
        if task_id and output_dir.is_dir():
            for f in output_dir.glob(f"*_{task_id}.output"):
                content = _read_output_file(str(f))
                if content is not None:
                    # 命中日志回退，也记入映射以加速后续读回
                    self._conv_output_map[conversation_id] = task_id
                    return content

        # 4. 未命中：诚实返回 None（found=False），绝不串用他人任务内容
        return None

    def wait_for_completion(
        self,
        conversation_id: str,
        timeout: float = 120.0,
        poll_interval: float = 1.0,
    ) -> Optional[dict]:
        """等待会话完成

        Args:
            conversation_id: 会话 UUID
            timeout: 超时秒数
            poll_interval: 轮询间隔

        Returns:
            最终会话状态，超时返回 None
        """
        start = time.time()
        while time.time() - start < timeout:
            status = self.session_status.get(conversation_id)
            if status and status.get("status") in ("completed", "failed", "error"):
                return status
            time.sleep(poll_interval)
        return None


def discover_dumate() -> dict:
    """发现系统上的 DuMate 安装信息"""
    result = {
        "found": False,
        "kernel_online": False,
        "port": None,
        "pipe_path": None,
        "agent_output_dir": None,
        "kernel_log_dir": None,
        "workspaces": [],
    }

    if os.path.isdir(_DUMATE_CONFIG_DIR):
        result["found"] = True
        result["agent_output_dir"] = _AGENT_OUTPUT_DIR
        result["kernel_log_dir"] = _KERNEL_LOG_DIR

    port = _discover_kernel_port()
    if port:
        result["port"] = port
        result["pipe_path"] = f"\\\\.\\pipe\\comate-kernel-{port}"
        bridge = DuMateBridge(port=port, auto_register=False)
        result["kernel_online"] = bridge.is_alive()
        bridge.close()

    result["workspaces"] = _discover_workspaces()

    return result