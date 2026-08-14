"""
AI 适配器（AIAdapter）- 统一的 AI 接入接口

受 DeepSeek Harness "一切皆插件" 架构启发。
每个 AI 软件（DuMate、Trae Work、Cursor 等）实现为一个
AIAdapter 插件，通过注册表统一管理。

AIAdapter 注册表 == Harness 的 Cordis 插件系统核心
每个 AIAdapter == Harness 的一个插件

设计理念:
- 统一接口：所有 AI 通过相同接口操作
- 可替换：切换 AI 只需换适配器，不改调用方
- 可发现：通过注册表查询可用 AI 及其能力
- 可组合：一个任务可指派给不同 AI 执行
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ==================== 能力定义 ====================


@dataclass
class AICapability:
    """AI 能力描述"""
    name: str
    version: str
    description: str


@dataclass
class AIAdapterInfo:
    """AI 适配器信息"""
    ai_id: str
    ai_name: str
    ai_version: str
    description: str
    connected: bool = False
    capabilities: list[AICapability] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "ai_id": self.ai_id,
            "ai_name": self.ai_name,
            "ai_version": self.ai_version,
            "description": self.description,
            "connected": self.connected,
            "capabilities": [
                {"name": c.name, "version": c.version, "description": c.description}
                for c in self.capabilities
            ],
            "error_message": self.error_message,
        }


# ==================== AI 适配器基类 ====================


class AIAdapter(ABC):
    """AI 适配器基类

    所有 AI 软件适配器必须实现此接口。
    这相当于 Harness 中每个插件需要实现的 Service 定义。

    接口设计原则：
    - 异步友好：所有可能阻塞的方法支持同步/异步两种模式
    - 返回值统一：所有方法返回 dict，包含 success 和 message
    - 错误处理：异常被捕获，以 error 字段返回
    """

    # ── 元信息（子类必须重写） ──────────────────────────────
    AI_ID = "unknown"
    AI_NAME = "未知 AI"
    AI_VERSION = "0.0.0"
    DESCRIPTION = "AI 适配器"

    def __init__(self):
        self._logger = logging.getLogger(f"{__name__}.{self.AI_ID}")

    # ── 连接管理 ──────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """连接到 AI 内核/服务

        Returns:
            True 表示连接成功
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
        ...

    @property
    @abstractmethod
    def connected(self) -> bool:
        """是否已连接"""
        ...

    @abstractmethod
    def is_alive(self) -> bool:
        """探测 AI 内核是否可达"""
        ...

    # ── 任务管理 ──────────────────────────────────────────────

    @abstractmethod
    def create_task(
        self,
        prompt: str,
        workspace_id: str = "",
        task_type: str = "work",
        **kwargs,
    ) -> dict:
        """创建并启动新任务

        Returns:
            {"success": bool, "conversation_id": str, "message": str}
        """
        ...

    @abstractmethod
    def stop_task(self, task_id: str) -> bool:
        """停止指定任务

        Args:
            task_id: 任务 ID 或会话 ID

        Returns:
            True 表示已发送停止命令
        """
        ...

    @abstractmethod
    def get_task_output(
        self,
        task_id: str,
        max_lines: int = 200,
    ) -> Optional[str]:
        """获取任务输出内容

        Args:
            task_id: 任务 ID 或会话 ID
            max_lines: 最大行数

        Returns:
            输出文本，None 表示未找到
        """
        ...

    @abstractmethod
    def get_status(self) -> str:
        """获取 AI 内核当前状态

        Returns:
            'idle' | 'generating' | 'unknown' | 'offline'
        """
        ...

    # ── 信息查询 ──────────────────────────────────────────────

    @abstractmethod
    def list_conversations(self) -> list[dict]:
        """列出所有会话"""
        ...

    @abstractmethod
    def get_capabilities(self) -> list[AICapability]:
        """获取该 AI 支持的能力列表

        Returns:
            能力列表，每个元素是 AICapability
        """
        ...

    def get_info(self) -> AIAdapterInfo:
        """获取适配器信息"""
        caps = self.get_capabilities()
        try:
            connected = self.connected
            error = None
        except Exception as e:
            connected = False
            error = str(e)

        return AIAdapterInfo(
            ai_id=self.AI_ID,
            ai_name=self.AI_NAME,
            ai_version=self.AI_VERSION,
            description=self.DESCRIPTION,
            connected=connected,
            capabilities=caps,
            error_message=error,
        )


# ==================== 适配器注册表 ====================


class AIAdapterRegistry:
    """AI 适配器注册表

    相当于 Harness 中 Cordis 的 Context 服务仓库。
    所有 AI 适配器在此注册，其他模块通过注册表发现和使用 AI。

    设计理念：
    - 按需注册：适配器在连接时注册，断开时注销
    - 默认适配器：系统自动选择第一个成功连接的适配器
    - 广播通知：注册/注销时通知监听器
    """

    def __init__(self):
        self._adapters: dict[str, AIAdapter] = {}
        self._lock = threading.RLock()
        self._default_adapter: Optional[str] = None
        self._listeners: list[callable] = []
        self._logger = logging.getLogger(__name__)

    def register(self, adapter: AIAdapter) -> None:
        """注册 AI 适配器

        Args:
            adapter: 适配器实例
        """
        with self._lock:
            ai_id = adapter.AI_ID
            self._adapters[ai_id] = adapter
            if self._default_adapter is None:
                self._default_adapter = ai_id
            self._logger.info("已注册 AI 适配器: %s (%s)", ai_id, adapter.AI_NAME)
            self._notify_listeners("registered", ai_id)

    def unregister(self, ai_id: str) -> None:
        """注销 AI 适配器

        Args:
            ai_id: 适配器 ID
        """
        with self._lock:
            if ai_id in self._adapters:
                try:
                    self._adapters[ai_id].disconnect()
                except Exception as e:
                    self._logger.warning("断开 %s 时出错: %s", ai_id, e)
                del self._adapters[ai_id]
                if self._default_adapter == ai_id:
                    self._default_adapter = next(iter(self._adapters), None)
                self._logger.info("已注销 AI 适配器: %s", ai_id)
                self._notify_listeners("unregistered", ai_id)

    def get(self, ai_id: str) -> Optional[AIAdapter]:
        """获取指定 AI 适配器

        Args:
            ai_id: 适配器 ID

        Returns:
            适配器实例，未找到返回 None
        """
        with self._lock:
            return self._adapters.get(ai_id)

    def get_default(self) -> Optional[AIAdapter]:
        """获取默认 AI 适配器

        Returns:
            默认适配器实例，无可用的返回 None
        """
        with self._lock:
            if self._default_adapter and self._default_adapter in self._adapters:
                return self._adapters[self._default_adapter]
            return None

    def set_default(self, ai_id: str) -> bool:
        """设置默认适配器

        Args:
            ai_id: 适配器 ID

        Returns:
            True 表示设置成功
        """
        with self._lock:
            if ai_id in self._adapters:
                self._default_adapter = ai_id
                self._logger.info("默认 AI 适配器设为: %s", ai_id)
                return True
            return False

    def list_adapters(self) -> list[AIAdapterInfo]:
        """列出所有已注册的适配器信息

        Returns:
            适配器信息列表
        """
        with self._lock:
            return [a.get_info() for a in self._adapters.values()]

    def list_connected(self) -> list[AIAdapterInfo]:
        """列出所有已连接的适配器"""
        with self._lock:
            return [
                a.get_info() for a in self._adapters.values()
                if a.connected
            ]

    def add_listener(self, callback: callable) -> None:
        """注册注册表变更监听器

        Args:
            callback: (action: str, ai_id: str) -> None
        """
        self._listeners.append(callback)

    def remove_listener(self, callback: callable) -> None:
        """注销监听器"""
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    def _notify_listeners(self, action: str, ai_id: str) -> None:
        """通知所有监听器"""
        for cb in self._listeners:
            try:
                cb(action, ai_id)
            except Exception as e:
                self._logger.warning("监听器通知失败: %s", e)

    def clear(self) -> None:
        """清空所有适配器（测试用）"""
        with self._lock:
            for ai_id in list(self._adapters.keys()):
                self.unregister(ai_id)
            self._default_adapter = None


# ==================== 全局单例 ====================

_registry: Optional[AIAdapterRegistry] = None
_init_lock = threading.Lock()


def get_adapter_registry() -> AIAdapterRegistry:
    """获取全局 AI 适配器注册表"""
    global _registry
    if _registry is None:
        with _init_lock:
            if _registry is None:
                _registry = AIAdapterRegistry()
    return _registry


def get_adapter(ai_id: str = "") -> Optional[AIAdapter]:
    """便捷方法：获取 AI 适配器

    Args:
        ai_id: 适配器 ID，为空则返回默认适配器

    Returns:
        适配器实例
    """
    registry = get_adapter_registry()
    if ai_id:
        return registry.get(ai_id)
    return registry.get_default()