"""
Trae Work 适配器（TraeWorkAdapter）- 通过 CDP 协议连接 Trae Work

Trae Work 是基于 VS Code 的 Electron 应用，通过 CDP（Chrome DevTools
Protocol）连接其渲染器。Trae 0.1.50 的 CLI 拒绝 --remote-debugging-port，
故 Star 通过在 user data 目录的 argv.json 写入 remote-debugging-port，
再以零参数启动 Trae 来开启 CDP。

本模块将 TraeCDPBridge 封装为群星插件化架构的 AIAdapter，
实现与 DuMate 统一的接口，让群星可以像管理 DuMate 一样管理 Trae Work。

== 插件化架构中的位置 =====================================================

  AIAdapterRegistry (注册表)
  ├── DuMateAdapter (dumate_bridge.py)          ← 已有
  └── TraeWorkAdapter (trae_work_adapter.py)    ← 本模块
      └── 底层: TraeCDPBridge (trae_cdp_bridge.py)
          └── 底层: CDPBridge (cdp_bridge.py)
              └── CDP WebSocket → Trae 渲染器 JS

===========================================================================

== 通信路径 ==
  Python → CDP WebSocket → Trae 渲染器 JS → __SOLO_LITE_PORT_REGISTRY__
                                                    ↓
                                          InputPort API
                                                    ↓
                                          Lexical 编辑器 (contenteditable)
                                                    ↓
                                          Enter 键提交消息

== 与 DuMate 的差异 ==
  DuMate 通过命名管道直连内核，有完整的任务生命周期管理。
  Trae Work 通过 CDP 操控 UI，更像"模拟用户操作"。
  因此 TraeWorkAdapter 的某些能力（如工作目录、任务类型）较 DuMate 弱。

启动方式:
  在 ~/.trae-cn/argv.json 写入 {"remote-debugging-port": "9223"}，
  再零参数启动 "TRAE SOLO CN.exe"（由主进程读取 argv.json 开启 CDP）。
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from star_core.ai_adapter import (
    AIAdapter,
    AICapability,
    AIAdapterInfo,
    get_adapter_registry,
)
from star_core.trae_cdp_bridge import TraeCDPBridge

logger = logging.getLogger(__name__)

#: Trae CDP 默认端口
_DEFAULT_TRAE_CDP_PORT = 9223


class TraeWorkAdapter(AIAdapter):
    """Trae Work 适配器

    通过 CDP 协议连接 Trae Work 的 Electron 渲染器，实现群星对
    Trae Work 的接入。

    底层使用 TraeCDPBridge 的具体 CDP 操作，本层负责：
    - 实现 AIAdapter 统一接口
    - 管理连接生命周期
    - 能力声明
    - 自动注册到 AIAdapterRegistry

    由于 Trae 没有类似 DuMate 的命名管道内核 API，本适配器
    通过 CDP 模拟用户操作，所以某些高级功能（如任务类型切换、
    工作目录选择）暂不支持，但核心的"发消息、读响应、停止"
    功能完整。

    Attributes:
        port: CDP 端口号（默认 9223）。
        _bridge: 底层的 TraeCDPBridge 实例。
        _connected: 连接状态标志。
    """

    # ── AIAdapter 元信息 ──────────────────────────────────────
    AI_ID = "trae_work"
    AI_NAME = "Trae Work"
    AI_VERSION = "1.0.0"
    DESCRIPTION = "通过 CDP 协议连接 Trae Work 的 Electron 渲染器，支持消息发送、响应读取和生成停止"

    def __init__(self, port: int = _DEFAULT_TRAE_CDP_PORT, auto_register: bool = True):
        self.port = port
        self._bridge = TraeCDPBridge(port=port)
        self._connected = False
        self._last_response = ""
        # 最近一次能力自检结果（connect / restart 成功后自动触发）
        self._last_self_check: dict | None = None

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

    def connect(self, auto_launch: bool = True, launch_timeout: float = 30.0) -> bool:
        """连接到 Trae Work 的 CDP 端口

        若 CDP 端口不可达，且 ``auto_launch`` 为 True，会自动确保 argv.json
        含调试端口并以零参数启动 Trae（像连接 DuMate 一样一键完成），再重试连接。

        Args:
            auto_launch: 端口不通时是否自动拉起 Trae（默认 True）。
            launch_timeout: 等待 Trae 调试端口就绪的最长秒数。

        Returns:
            True 表示连接成功
        """
        if self._connected:
            return True

        # 端口已通：直接校验聊天目标
        if self._bridge.is_alive():
            return self._connect_to_target()

        # 端口不通：尝试自动拉起 Trae
        if not auto_launch:
            logger.warning(
                "TraeWorkAdapter: CDP 端口 %d 不可达。"
                "请先关闭 Trae，再点 Star 的「检测并重启 Trae」按钮以调试端口启动。",
                self.port,
            )
            return False

        logger.info(
            "TraeWorkAdapter: CDP 端口 %d 不可达，尝试自动启动 Trae...",
            self.port,
        )
        try:
            from star_core.trae_launcher import launch_trae_with_cdp
        except Exception as e:  # pragma: no cover
            logger.warning("TraeWorkAdapter: 无法加载 Trae 启动器: %s", e)
            return False

        if not launch_trae_with_cdp(self.port, timeout=launch_timeout):
            logger.warning(
                "TraeWorkAdapter: 自动启动 Trae 失败（未找到 Trae 可执行文件，"
                "或 argv.json 写入失败，或启动后 CDP 端口 %d 仍不可用）",
                self.port,
            )
            return False

        if not self._bridge.is_alive():
            logger.warning(
                "TraeWorkAdapter: 已尝试启动 Trae，但 CDP 端口 %d 仍不可达"
                "（可能已有 Trae 单实例占用，请先关闭 Trae 后重试连接）",
                self.port,
            )
            return False

        return self._connect_to_target()

    def self_check(self) -> dict | None:
        """执行一次能力自检并返回结构化结果（同时缓存到 ``_last_self_check``）。

        仅当已连接（端口可达且命中聊天 target）时有意义；未连接返回 None。
        """
        if not self._connected:
            return None
        try:
            self._last_self_check = self._bridge.self_check()
        except Exception as e:
            logger.warning("TraeWorkAdapter: 能力自检异常: %s", e)
            self._last_self_check = {
                "ok": False, "port": self.port, "cdp_reachable": False,
                "detail": f"自检执行异常: {e}",
            }
        return self._last_self_check

    def get_self_check(self) -> dict | None:
        """返回最近一次自检结果（不重新执行）。"""
        return self._last_self_check

    def _connect_to_target(self) -> bool:
        """校验聊天目标并完成连接（端口已被认为可达）。

        连接成功后自动触发一次能力自检，结果缓存到 ``_last_self_check``，
        供 UI 展示「CDP 是否真实可用 / 渲染器能否被脚本化驱动」。
        """
        target = self._bridge.find_chat_target(force_refresh=True)
        if not target:
            logger.warning("TraeWorkAdapter: 未找到聊天目标 target")
            return False
        self._connected = True
        logger.info(
            "TraeWorkAdapter: 已连接到 Trae Work (target=%s, port=%d)",
            target.get("title", "unknown"), self.port,
        )
        # 连接成功后自动能力自检（非阻塞关键路径，失败只记日志不影响连接状态）
        try:
            self._last_self_check = self._bridge.self_check()
            logger.info("TraeWorkAdapter: 能力自检 %s", self._last_self_check)
        except Exception as e:  # pragma: no cover
            logger.warning("TraeWorkAdapter: 能力自检异常: %s", e)
        return True

    def restart_with_cdp(self, launch_timeout: float = 30.0) -> bool:
        """关闭所有正在运行的 Trae 实例，再以 CDP 调试端口重启并连接。

        专治"Trae 已运行但未开调试端口，单实例锁占用导致 connect
        无法拉起 CDP 实例"的场景。会先彻底退出旧实例（清单实例锁），
        再通过 argv.json + 零参数启动带调试端口的新实例并完成连接。

        Args:
            launch_timeout: 等待新实例 CDP 端口就绪的最长秒数。

        Returns:
            True 表示重启并连接成功
        """
        # 先断开旧连接（指向的端口即将失效）
        self._connected = False

        try:
            from star_core.trae_launcher import restart_trae_with_cdp
        except Exception as e:  # pragma: no cover
            logger.warning("TraeWorkAdapter: 无法加载 Trae 重启器: %s", e)
            return False

        if not restart_trae_with_cdp(self.port, launch_timeout=launch_timeout):
            logger.warning(
                "TraeWorkAdapter: 重启 Trae 失败（未找到 Trae 可执行文件，"
                "或重启后 CDP 端口 %d 仍不可用）",
                self.port,
            )
            return False

        return self._connect_to_target()

    def disconnect(self) -> None:
        """断开连接"""
        self._connected = False
        self._last_response = ""
        logger.info("TraeWorkAdapter: 已断开连接")

    def is_alive(self) -> bool:
        """探测 Trae 是否可达

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
        """向 Trae 发送消息（创建新任务）

        由于 Trae 没有 DuMate 那样的"任务"概念，这里通过 CDP
        向聊天输入框注入文本并发送 Enter 键来触发 AI 响应。

        Trae 的 workspace 和 task_type 概念与 DuMate 不同：
        - workspace_id: Trae 通过窗口管理，不支持切换
        - task_type: Trae 的聊天模式是统一的，不支持区分

        Args:
            prompt: 消息内容
            workspace_id: 忽略（Trae 不支持）
            task_type: 忽略（Trae 统一模式）

        Returns:
            {"success": bool, "conversation_id": str, "message": str}
        """
        if not self._connected:
            return {"success": False, "conversation_id": "", "message": "未连接"}

        if workspace_id:
            logger.info("TraeWorkAdapter: workspace_id=%s 被忽略（Trae 不支持）", workspace_id)
        if task_type != "work":
            logger.info("TraeWorkAdapter: task_type=%s 被忽略（Trae 统一模式）", task_type)

        # 发送消息
        ok = self._bridge.send_message(prompt)
        if not ok:
            return {
                "success": False,
                "conversation_id": "",
                "message": "发送消息失败（CDP 操作失败）",
            }

        # 生成一个伪 conversation_id（基于时间戳）
        conv_id = f"trae_{int(time.time())}"

        logger.info(
            "TraeWorkAdapter: 消息已发送 (%d chars)",
            len(prompt),
        )

        return {
            "success": True,
            "conversation_id": conv_id,
            "message": f"消息已发送到 Trae Work ({len(prompt)} 字符)",
        }

    def stop_task(self, task_id: str) -> bool:
        """停止 Trae 的 AI 生成

        底层尝试点击停止按钮，降级为发送 Escape 键。

        Args:
            task_id: 忽略（Trae 统一管理当前生成）

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
        """获取 Trae 的最新 AI 响应

        通过 CDP 的 DOM 查询获取聊天区域中的最后一条助手消息。
        注意：Trae 没有 DuMate 的 .output 文件，只能获取当前
        可见的聊天内容。

        Args:
            task_id: 忽略（Trae 读取最新响应）
            max_lines: 最大行数

        Returns:
            响应文本，未找到返回 None
        """
        if not self._connected:
            return None

        text = self._bridge.get_latest_response()
        if not text:
            return None

        self._last_response = text
        lines = text.split("\n")
        return "\n".join(lines[:max_lines])

    def get_status(self) -> str:
        """检测 Trae 当前状态

        Returns:
            'idle' | 'generating' | 'unknown' | 'offline'
        """
        if not self._connected:
            return "offline"

        if not self._bridge.is_alive():
            self._connected = False
            return "offline"

        # 刷新 target 缓存
        target = self._bridge.find_chat_target(force_refresh=True)
        if not target:
            return "unknown"

        return self._bridge.get_status()

    # ── 信息查询 ──────────────────────────────────────────────

    def list_conversations(self) -> list[dict]:
        """列出 Trae 的聊天会话

        通过 __CHAT_SESSION_COLLECTOR__ 获取会话列表。

        Returns:
            会话列表，不可用时返回空列表
        """
        sessions = self._bridge.list_sessions()
        if sessions:
            return sessions
        return []

    def get_capabilities(self) -> list[AICapability]:
        """获取 Trae Work 支持的能力列表

        Trae 是 UI 操控型 AI，能力与 DuMate 不同：
        - 支持发送消息、读取响应、停止生成
        - 不支持任务类型切换、工作目录选择、文件输出读取

        Returns:
            能力列表
        """
        return [
            AICapability("send_message", "1.0", "向聊天发送消息"),
            AICapability("stop_generation", "1.0", "停止 AI 生成"),
            AICapability("read_latest_response", "1.0", "读取最新 AI 响应"),
            AICapability("get_status", "1.0", "检测 idle/generating 状态"),
            AICapability("list_sessions", "1.0", "通过 __CHAT_SESSION_COLLECTOR__ 列出会话"),
            AICapability("screenshot", "1.0", "对 Trae 窗口截图"),
            AICapability("input_management", "1.0", "清空/检查输入框内容"),
        ]

    # ── Trae 特有方法（非 AIAdapter 接口，但对外暴露） ──────

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

    def take_screenshot(self) -> Optional[bytes]:
        """对 Trae 窗口截图

        Returns:
            PNG 图片字节，失败返回 None
        """
        if not self._connected:
            return None
        return self._bridge.take_screenshot()

    def probe_globals(self) -> Optional[dict]:
        """探测 Trae 渲染器中可用的全局对象

        用于调试和发现新的内部 API。

        Returns:
            探测结果字典
        """
        return self._bridge.probe_globals()


def ensure_trae_debug_port() -> bool:
    """检查 Trae 是否以调试端口启动

    Returns:
        True 如果 CDP 端口已可用
    """
    adapter = TraeWorkAdapter(auto_register=False)
    ok = adapter.is_alive()
    if not ok:
        logger.info(
            "Trae 未以调试端口启动。Star 将在连接/重启时自动把 "
            "remote-debugging-port=%d 写入 ~/.trae-cn/argv.json 并零参数启动 Trae。",
            _DEFAULT_TRAE_CDP_PORT,
        )
    return ok