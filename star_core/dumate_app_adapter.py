"""
DuMate 桌面端适配器（DuMateAppAdapter）- 通过 CDP 协议连接 DuMate.exe

DuMate（百度搭子 / DuMate.exe）是基于 Electron 的桌面应用，单实例运行，
必须带 ``--remote-debugging-port`` 启动才暴露 CDP。本模块把
:class:`~star_core.dumate_app_cdp_bridge.DuMateAppCDPBridge` 封装为群星
插件化架构里的 :class:`~star_core.ai_adapter.AIAdapter`，让群星像管理
Trae Work 一样管理 DuMate 桌面端。

== 命名澄清 ==============================================================

  本仓库历史上的 ``dumate`` 标识符指的其实是 **Comate（文心快码）**——
  ``dumate_bridge.py`` 走命名管道连 Comate 内核，``dumate_cdp_bridge.py``
  是 Comate 的 CDP 兜底通道（端口 9224）。**真正的 DuMate 桌面端** 用
  ``dumate_app_`` 前缀区分，即本模块与 ``dumate_app_cdp_bridge.py`` /
  ``dumate_app_launcher.py``（端口 9225）。

== 插件化架构中的位置 =====================================================

  AIAdapterRegistry (注册表)
  ├── DuMateBridge (dumate_bridge.py)              ← 其实是 Comate，命名管道
  ├── TraeWorkAdapter (trae_work_adapter.py)       ← Trae，CDP
  └── DuMateAppAdapter (dumate_app_adapter.py)     ← 本模块，DuMate 桌面端 CDP
      └── 底层: DuMateAppCDPBridge (dumate_app_cdp_bridge.py)
          └── 底层: CDPBridge (cdp_bridge.py)
              └── CDP WebSocket → DuMate 渲染器 JS

== 与 DuMate（命名管道那套 Comate）/ Trae 的差异 ==
  - 与 Comate 命名管道不同：DuMate 桌面端没有内核任务生命周期 API，
    只能通过 CDP 操控聊天 UI（注入文本 + 点发送 + 读 DOM），更像"模拟用户"。
  - 与 Trae 相同：都是 CDP 操控型，能力集近似（发消息 / 读回复 / 停止 /
    读输入框 / 状态检测）。
  - DuMate 单实例且不读 argv.json，只能命令行直传端口并重启才能开 CDP
    （见 dumate_app_launcher.py）。启动器会剔除 ELECTRON_* 环境变量，否则
    DuMate.exe 会退化为纯 Node 而启动即退出。
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from star_core.ai_adapter import (
    AIAdapter,
    AICapability,
    get_adapter_registry,
)
from star_core.dumate_app_cdp_bridge import (
    DEFAULT_DUMATE_APP_CDP_PORT,
    DuMateAppCDPBridge,
)

logger = logging.getLogger(__name__)


class DuMateAppAdapter(AIAdapter):
    """DuMate 桌面端适配器

    通过 CDP 协议连接 DuMate.exe 的 Electron 渲染器，实现群星对 DuMate
    桌面端的接入。底层使用 :class:`DuMateAppCDPBridge` 的具体 CDP 操作，
    本层负责：

    - 实现 AIAdapter 统一接口
    - 管理连接生命周期（含端口不通时自动带调试端口重启 DuMate）
    - 能力声明
    - 自动注册到 AIAdapterRegistry

    DuMate 桌面端没有命名管道内核 API，故通过 CDP 模拟用户操作，某些高级
    功能（任务类型切换、工作目录选择、文件输出读取）不支持，但"发消息、
    读回复、停止、读输入框、状态检测"完整。

    Attributes:
        port: CDP 端口号（默认 9225）。
        _bridge: 底层的 DuMateAppCDPBridge 实例。
        _connected: 连接状态标志。
    """

    # ── AIAdapter 元信息 ──────────────────────────────────────
    AI_ID = "dumate_app"
    AI_NAME = "DuMate 桌面端 (百度搭子)"
    AI_VERSION = "1.0.0"
    DESCRIPTION = "通过 CDP 协议连接 DuMate.exe 的 Electron 渲染器，支持消息发送、响应读取和生成停止"

    def __init__(
        self,
        port: int = DEFAULT_DUMATE_APP_CDP_PORT,
        auto_register: bool = True,
    ):
        self.port = port
        self._bridge = DuMateAppCDPBridge(port=port)
        self._connected = False
        self._last_response = ""

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
        return self._connected

    def connect(self, auto_launch: bool = True, launch_timeout: float = 40.0) -> bool:
        """连接到 DuMate 桌面端的 CDP 端口

        若端口不可达且 ``auto_launch`` 为 True，会带调试端口拉起 DuMate。
        **但绝不会杀掉用户正在用的 DuMate**：DuMate 单实例，已在运行却没开
        调试端口时本方法直接失败并提示，需显式调用 :meth:`restart_with_cdp`
        才会重启——"要不要打断用户"这个决定留给调用方。

        Args:
            auto_launch: 端口不通且 DuMate 未在运行时，是否自动拉起（默认 True）。
            launch_timeout: 等待 DuMate 调试端口就绪的最长秒数。

        Returns:
            True 表示连接成功
        """
        if self._connected:
            return True

        # 端口已通：直接校验聊天目标
        if self._bridge.is_alive():
            return self._connect_to_target()

        if not auto_launch:
            logger.warning(
                "DuMateAppAdapter: CDP 端口 %d 不可达。"
                "请以 --remote-debugging-port=%d 启动 DuMate，或调用带 "
                "auto_launch=True 的 connect()。",
                self.port, self.port,
            )
            return False

        logger.info(
            "DuMateAppAdapter: CDP 端口 %d 不可达，尝试自动启动 DuMate...",
            self.port,
        )
        try:
            from star_core.dumate_app_launcher import launch_dumate_app_with_cdp
        except Exception as e:  # pragma: no cover
            logger.warning("DuMateAppAdapter: 无法加载 DuMate 启动器: %s", e)
            return False

        if not launch_dumate_app_with_cdp(
            self.port, timeout=launch_timeout, restart_if_running=False
        ):
            logger.warning(
                "DuMateAppAdapter: 自动启动 DuMate 失败（未找到 DuMate.exe，"
                "或 DuMate 已在运行但没开调试端口——那需要重启，请调用 "
                "restart_with_cdp()；或启动后 CDP 端口 %d 仍不可用）",
                self.port,
            )
            return False

        if not self._bridge.is_alive():
            logger.warning(
                "DuMateAppAdapter: 已尝试启动 DuMate，但 CDP 端口 %d 仍不可达",
                self.port,
            )
            return False

        return self._connect_to_target()

    def _connect_to_target(self) -> bool:
        """校验聊天目标并完成连接（端口已被认为可达）。"""
        target = self._bridge.find_chat_target()
        if not target:
            logger.warning("DuMateAppAdapter: 未找到聊天页 target")
            return False
        self._connected = True
        logger.info(
            "DuMateAppAdapter: 已连接到 DuMate 桌面端 (port=%d)", self.port
        )
        return True

    def restart_with_cdp(self, launch_timeout: float = 40.0) -> bool:
        """关闭正在运行的 DuMate，再以 CDP 调试端口重启并连接。

        专治"DuMate 已运行但没开调试端口"的场景：单实例锁使带新开关的进程
        无法与旧实例并存，必须先彻底退出旧实例再拉起。

        Args:
            launch_timeout: 等待新实例 CDP 端口就绪的最长秒数。

        Returns:
            True 表示重启并连接成功
        """
        self._connected = False
        try:
            from star_core.dumate_app_launcher import launch_dumate_app_with_cdp
        except Exception as e:  # pragma: no cover
            logger.warning("DuMateAppAdapter: 无法加载 DuMate 启动器: %s", e)
            return False

        if not launch_dumate_app_with_cdp(
            self.port, timeout=launch_timeout, restart_if_running=True
        ):
            logger.warning(
                "DuMateAppAdapter: 重启 DuMate 失败（未找到 DuMate.exe，"
                "或重启后 CDP 端口 %d 仍不可用）",
                self.port,
            )
            return False

        return self._connect_to_target()

    def disconnect(self) -> None:
        """断开连接"""
        self._connected = False
        self._last_response = ""
        logger.info("DuMateAppAdapter: 已断开连接")

    def is_alive(self) -> bool:
        """探测 DuMate 是否可达

        Returns:
            True 如果 CDP 端口可达
        """
        return self._bridge.is_alive()

    # ── 任务管理 ──────────────────────────────────────────────

    def create_task(
        self,
        prompt: str,
        workspace_id: str = "",
        task_type: str = "work",
        **kwargs,
    ) -> dict:
        """向 DuMate 发送消息（创建新任务）

        DuMate 桌面端没有 Comate 那样的"任务"概念，这里通过 CDP 向聊天输入框
        注入文本并点击发送来触发 AI 响应。``workspace_id`` / ``task_type`` 被忽略。

        额外关键字参数：
            new_chat (bool): 发送前先点「新任务」开一个干净会话。默认 False。
            overwrite (bool): 输入框已有草稿时是否覆盖。默认 False（放弃发送，
                以免抹掉用户手输的内容）。

        Args:
            prompt: 消息内容
            workspace_id: 忽略（DuMate 桌面端不支持）
            task_type: 忽略（DuMate 统一模式）

        Returns:
            {"success": bool, "conversation_id": str, "message": str}
        """
        if not self._connected:
            return {"success": False, "conversation_id": "", "message": "未连接"}

        if workspace_id:
            logger.info("DuMateAppAdapter: workspace_id=%s 被忽略（不支持）", workspace_id)
        if task_type != "work":
            logger.info("DuMateAppAdapter: task_type=%s 被忽略（统一模式）", task_type)

        new_chat = bool(kwargs.get("new_chat", False))
        overwrite = bool(kwargs.get("overwrite", False))

        ok = self._bridge.send_message(prompt, new_chat=new_chat, overwrite=overwrite)
        if not ok:
            return {
                "success": False,
                "conversation_id": "",
                "message": "发送消息失败（CDP 操作失败，或输入框有草稿且未传 overwrite）",
            }

        conv_id = f"dumate_app_{int(time.time())}"
        logger.info("DuMateAppAdapter: 消息已发送 (%d chars)", len(prompt))
        return {
            "success": True,
            "conversation_id": conv_id,
            "message": f"消息已发送到 DuMate 桌面端 ({len(prompt)} 字符)",
        }

    def stop_task(self, task_id: str) -> bool:
        """停止 DuMate 的 AI 生成

        Args:
            task_id: 忽略（DuMate 统一管理当前生成）

        Returns:
            True 表示停止操作已执行
        """
        if not self._connected:
            return False
        return self._bridge.stop_generation()

    def get_task_output(
        self,
        task_id: str,
        max_lines: int = 200,
    ) -> Optional[str]:
        """获取**本轮**任务的 AI 响应

        通过 CDP 的 DOM 查询获取助手回复（依据 ``data-message-role="assistant"``），
        并且只返回 :meth:`create_task` 之后**新出现**的那条——旧回答一直留在 DOM
        里，不做这层判别的话刚发完就读会拿到上一轮的回答，看起来像"秒回"。

        Args:
            task_id: 忽略（DuMate 桌面端没有任务 id，按"本轮"语义读取）
            max_lines: 最大行数

        Returns:
            响应文本；本轮回复尚未出现（仍在等生成）返回 None
        """
        if not self._connected:
            return None

        text = self._bridge.get_new_response()
        if not text:
            return None

        self._last_response = text
        lines = text.split("\n")
        return "\n".join(lines[:max_lines])

    def get_status(self) -> str:
        """检测 DuMate 当前状态

        Returns:
            'idle' | 'generating' | 'unknown' | 'offline'
        """
        if not self._connected:
            return "offline"

        if not self._bridge.is_alive():
            self._connected = False
            return "offline"

        return self._bridge.get_status()

    # ── 信息查询 ──────────────────────────────────────────────

    def list_conversations(self) -> list[dict]:
        """列出 DuMate 的聊天会话

        DuMate 桌面端暂无稳定的会话枚举通道，返回空列表。

        Returns:
            空列表
        """
        return []

    def get_capabilities(self) -> list[AICapability]:
        """获取 DuMate 桌面端支持的能力列表

        Returns:
            能力列表
        """
        return [
            AICapability("send_message", "1.0", "向聊天发送消息"),
            AICapability("stop_generation", "1.0", "停止 AI 生成"),
            AICapability("read_latest_response", "1.0", "读取最新助手回复"),
            AICapability("get_status", "1.0", "检测 idle/generating 状态"),
            AICapability("input_management", "1.0", "清空/检查输入框内容"),
        ]

    # ── DuMate 特有方法（非 AIAdapter 接口，但对外暴露） ──────

    def get_input_content(self) -> str:
        """获取当前输入框中的文本内容

        Returns:
            输入框文本，空字符串表示无内容
        """
        if not self._connected:
            return ""
        return self._bridge.get_input_content()

    def clear_input(self) -> bool:
        """清空聊天输入框

        Returns:
            True 表示成功清空
        """
        if not self._connected:
            return False
        return self._bridge.clear_input()
