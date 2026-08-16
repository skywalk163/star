"""Comate（文心快码）CDP 发送通道。

命名说明：本仓库把 Comate 记作 ``dumate``（``AI_ID="dumate"``、命名管道
``comate-kernel-<port>``），本模块沿用该历史命名，驱动的是 **Comate**（端口
9224）。独立安装的 DuMate 桌面端（``DuMate.exe``）是另一个产品，其 CDP 通道
见 ``star_core/dumate_app_launcher.py``。

与 Trae 的关键差异（2026-08-16 实测）
------------------------------------
Trae 的渲染器暴露了 ``__SOLO_LITE_PORT_REGISTRY__`` / ``InputPort`` 内部 API，
可直接调用；**Comate 没有任何同类注册表**——内层 window 上只有
``acquireVsCodeApi`` / ``isComateIDE`` / ``isComateOverview``。因此本通道
只能走 DOM。

DOM 拓扑（实测）::

    CDP target (type=iframe, extensionId=BaiduComate.comate)   ← 只是 webview 外壳
      └── <iframe id="active-frame">                            ← 真正的聊天 UI
            title = "Comate 对话"
            <textarea id="zulu-chat-input">                     ← 输入框（React 受控）
            <button>  ...  var(--comate-agent-mode-submit)      ← 发送按钮（圆形上箭头）
            <button>  ...  bg-blue-500                          ← 语音输入（勿点）
            .message-content                                    ← 消息条目

外壳与内层同源（同为 ``vscode-webview://<authority>``），故可用
``document.getElementById('active-frame').contentDocument`` 直接穿透，
不需要 ``Page.getFrameTree`` + 独立执行上下文。

输入框是 React 受控组件：直接赋 ``el.value`` 不会同步到 React state。
必须用原型链上的 native setter 再派发 ``input`` 事件（已实测生效）。

两个面板
--------
Comate 通常同时存在两个聊天 webview，用 ``window.isComateOverview`` 区分：

  - ``True``  → Mission 总览面板（``PANEL_OVERVIEW``）
  - ``False`` → 编辑器侧边栏对话（``PANEL_SIDEBAR``）

**默认发往总览面板**：侧边栏那个很可能正是驱动群星本进程的会话，向它注入
消息会污染调用方自己的对话上下文。
"""

from __future__ import annotations

import json
import logging
import time

from star_core.cdp_bridge import CDPBridge
from star_core.dumate_launcher import DEFAULT_DUMATE_CDP_PORT, list_targets

logger = logging.getLogger(__name__)

#: Mission 总览面板（isComateOverview === true）
PANEL_OVERVIEW = "overview"

#: 编辑器侧边栏对话面板（isComateOverview === false）
PANEL_SIDEBAR = "sidebar"

#: 聊天输入框 id（Comate 内部组件名 zulu-chat-input）
_INPUT_ID = "zulu-chat-input"

#: webview 外壳中承载真实聊天 UI 的内层 iframe id
_FRAME_ID = "active-frame"

#: 发送按钮图标使用的 CSS 变量，用于把它和相邻的语音按钮区分开
_SUBMIT_VAR = "--comate-agent-mode-submit"

#: target 缓存有效期（秒）
_TARGET_CACHE_TTL = 30.0


def _in_frame(body: str) -> str:
    """把 JS 片段包进「穿透到 active-frame 内层文档」的序言里。

    片段内可直接使用 ``d``（内层 document）、``w``（内层 window）、
    ``ta``（输入框，可能为 null）。外壳里找不到内层文档时整体返回 None，
    调用方 evaluate 得到 None 即视为不可用。
    """
    return (
        "(() => {"
        f"const f=document.getElementById({json.dumps(_FRAME_ID)});"
        "if(!f||!f.contentDocument)return null;"
        "const d=f.contentDocument,w=f.contentWindow;"
        f"const ta=d.getElementById({json.dumps(_INPUT_ID)});"
        f"{body}"
        "})()"
    )


#: JS：面板身份与状态快照
_PANEL_INFO_JS = _in_frame(
    "return {"
    "panel: w.isComateOverview ? 'overview' : 'sidebar',"
    "hasInput: !!ta,"
    "inputText: ta ? ta.value : '',"
    "msgCount: d.querySelectorAll('[class*=\"message-content\"]').length,"
    "};"
)

#: JS：读取输入框内容
_GET_INPUT_JS = _in_frame("return ta ? {text: ta.value} : null;")


def _set_input_js(text: str) -> str:
    """构造「按 React 受控组件规范写入输入框」的 JS。"""
    return _in_frame(
        "if(!ta)return null;"
        "const v=" + json.dumps(text) + ";"
        "const setter=Object.getOwnPropertyDescriptor("
        "w.HTMLTextAreaElement.prototype,'value').set;"
        "ta.focus();"
        "setter.call(ta,v);"
        "ta.dispatchEvent(new w.Event('input',{bubbles:true}));"
        "return {text: ta.value, ok: ta.value === v};"
    )


#: JS：点击发送按钮
#:
#: 输入框往上 5 层是 .composer-input-container；其中的按钮里，图标 span 的
#: inline style 含 --comate-agent-mode-submit 的那个才是发送，相邻的
#: bg-blue-500 圆钮是语音输入，误点会打开录音。
_CLICK_SUBMIT_JS = _in_frame(
    "if(!ta)return null;"
    "let box=ta;"
    "for(let i=0;i<5&&box.parentElement;i++)box=box.parentElement;"
    "const btns=Array.from(box.querySelectorAll('button'));"
    "const hit=btns.find(b=>b.querySelector('span[style*=" + json.dumps(_SUBMIT_VAR) + "]'));"
    "if(!hit)return {clicked:false, buttons:btns.length};"
    "if(hit.disabled)return {clicked:false, disabled:true};"
    "hit.click();"
    "return {clicked:true};"
)

#: JS：读取最后一条消息文本
#:
#: 严格限定在内层文档的 .message-content 集合内，不做「全文档取最大文本块」
#: 之类的猜测——命中不到就诚实返回空串。
_READ_LATEST_JS = _in_frame(
    "const items=d.querySelectorAll('[class*=\"message-content\"]');"
    "if(!items.length)return {text:'', count:0};"
    "const last=items[items.length-1];"
    "return {text:(last.innerText||'').trim().slice(0,8000), count:items.length};"
)

#: JS：状态检测（生成中的判据是出现了停止按钮）
_DETECT_STATUS_JS = _in_frame(
    "const stop=d.querySelector("
    "'[aria-label*=\"停止\"],[aria-label*=\"Stop\"],[title*=\"停止\"]');"
    "if(stop)return {status:'generating', via:'stop-button'};"
    "if(!ta)return {status:'unknown', via:'no-input'};"
    "return {status:'idle', via:'no-stop-button'};"
)

#: JS：点击停止按钮
_CLICK_STOP_JS = _in_frame(
    "const stop=d.querySelector("
    "'[aria-label*=\"停止\"],[aria-label*=\"Stop\"],[title*=\"停止\"]');"
    "if(!stop)return {clicked:false};"
    "stop.click();"
    "return {clicked:true};"
)


class DuMateCDPBridge:
    """Comate 聊天面板的 CDP 发送通道。

    与命名管道通道（:class:`star_core.dumate_bridge.DuMateBridge`）并列：
    管道走内核 IPC，本通道走渲染器 DOM。管道不可用（内核端口未知、协议变更）
    时本通道是兜底；反之本通道要求用户已重启过 Comate 让调试端口生效。

    Attributes:
        port: CDP 端口（默认 9224）。
    """

    def __init__(self, port: int = DEFAULT_DUMATE_CDP_PORT):
        self.port = port
        self._cdp = CDPBridge(port=port)
        self._panel_cache: dict[str, dict] = {}
        self._cache_time: float = 0.0

    # ------------------------------------------------------------------
    # 连接与面板发现
    # ------------------------------------------------------------------

    def is_alive(self) -> bool:
        """探测 Comate CDP 端口是否可达。"""
        return self._cdp.is_alive()

    def list_chat_panels(self) -> list[dict]:
        """枚举所有可用的 Comate 聊天面板。

        Returns:
            每项含 ``panel``（overview/sidebar）、``target_id``、``msg_count``、
            ``input_text``；无聊天输入框的 target 会被过滤掉。
        """
        panels = []
        for target in list_targets(self.port):
            ws_url = target.get("webSocketDebuggerUrl")
            if target.get("type") != "iframe" or not ws_url:
                continue
            tab = {"webSocketDebuggerUrl": ws_url}
            info = self._cdp.evaluate(tab, _PANEL_INFO_JS)
            if not isinstance(info, dict) or not info.get("hasInput"):
                continue
            panels.append(
                {
                    "panel": info.get("panel"),
                    "target_id": target.get("id"),
                    "webSocketDebuggerUrl": ws_url,
                    "msg_count": info.get("msgCount", 0),
                    "input_text": info.get("inputText", ""),
                }
            )
        return panels

    def find_chat_target(
        self,
        panel: str = PANEL_OVERVIEW,
        force_refresh: bool = False,
    ) -> dict | None:
        """定位指定面板的 CDP target；未找到返回 None。

        Args:
            panel: :data:`PANEL_OVERVIEW` 或 :data:`PANEL_SIDEBAR`。
            force_refresh: 忽略缓存重新枚举。
        """
        expired = time.monotonic() - self._cache_time > _TARGET_CACHE_TTL
        if force_refresh or expired or not self._panel_cache:
            self._panel_cache = {p["panel"]: p for p in self.list_chat_panels()}
            self._cache_time = time.monotonic()

        found = self._panel_cache.get(panel)
        if not found:
            return None
        return {"webSocketDebuggerUrl": found["webSocketDebuggerUrl"]}

    # ------------------------------------------------------------------
    # 输入框读写
    # ------------------------------------------------------------------

    def get_input_content(self, panel: str = PANEL_OVERVIEW) -> str:
        """读取输入框当前文本；面板不可达返回空串。"""
        target = self.find_chat_target(panel)
        if not target:
            return ""
        result = self._cdp.evaluate(target, _GET_INPUT_JS)
        return result.get("text", "") if isinstance(result, dict) else ""

    def set_input(self, text: str, panel: str = PANEL_OVERVIEW) -> bool:
        """写入输入框（不发送）；写入后回读校验一致才返回 True。"""
        target = self.find_chat_target(panel)
        if not target:
            return False
        result = self._cdp.evaluate(target, _set_input_js(text))
        return isinstance(result, dict) and result.get("ok") is True

    def clear_input(self, panel: str = PANEL_OVERVIEW) -> bool:
        """清空输入框。"""
        return self.set_input("", panel)

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------

    def send_message(
        self,
        text: str,
        panel: str = PANEL_OVERVIEW,
        overwrite: bool = False,
    ) -> bool:
        """向 Comate 聊天面板发送一条消息。

        流程：定位面板 → 检查草稿 → 注入并回读校验 → 点击发送按钮 →
        回读确认输入框已清空。

        Args:
            text: 消息文本；空串直接返回 False。
            panel: 目标面板，默认 Mission 总览（避免污染侧边栏会话）。
            overwrite: 输入框已有用户草稿时是否覆盖。默认 False，即放弃发送，
                以免抹掉用户手输的内容。

        Returns:
            True 表示发送按钮已点击且输入框已清空。
        """
        if not text:
            return False

        target = self.find_chat_target(panel)
        if not target:
            logger.warning("DumateCDP: 未找到面板 %s（端口 %s）", panel, self.port)
            return False

        draft = self._cdp.evaluate(target, _GET_INPUT_JS)
        if isinstance(draft, dict) and draft.get("text") and not overwrite:
            logger.warning(
                "DumateCDP: 面板 %s 输入框已有草稿(%d 字)，放弃发送；"
                "如需覆盖请传 overwrite=True",
                panel,
                len(draft["text"]),
            )
            return False

        injected = self._cdp.evaluate(target, _set_input_js(text))
        if not (isinstance(injected, dict) and injected.get("ok")):
            logger.warning("DumateCDP: 文本注入失败: %s", injected)
            return False

        # React 需要一次渲染周期才会把发送按钮从 disabled 切回可用
        time.sleep(0.2)

        clicked = self._cdp.evaluate(target, _CLICK_SUBMIT_JS)
        if not (isinstance(clicked, dict) and clicked.get("clicked")):
            logger.warning("DumateCDP: 发送按钮点击失败: %s", clicked)
            self.clear_input(panel)
            return False

        time.sleep(0.5)
        after = self._cdp.evaluate(target, _GET_INPUT_JS)
        if isinstance(after, dict) and after.get("text"):
            logger.warning(
                "DumateCDP: 已点击发送但输入框仍有内容(%d 字)，可能未提交",
                len(after["text"]),
            )
            return False

        logger.info("DumateCDP: 消息已发送到 %s 面板 (%d 字)", panel, len(text))
        return True

    # ------------------------------------------------------------------
    # 读取与状态
    # ------------------------------------------------------------------

    def get_latest_response(self, panel: str = PANEL_OVERVIEW) -> str:
        """读取面板中最后一条消息文本（尽力而为）。

        DOM 上没有可靠的 user/assistant 角色标记，因此这里只返回「最后一条
        消息」，可能是刚发出的用户消息。权威的输出读取路径仍是
        :meth:`star_core.dumate_bridge.DuMateBridge.get_conversation_output`
        （直读会话存储）。
        """
        target = self.find_chat_target(panel)
        if not target:
            return ""
        result = self._cdp.evaluate(target, _READ_LATEST_JS)
        return result.get("text", "") if isinstance(result, dict) else ""

    def get_status(self, panel: str = PANEL_OVERVIEW) -> str:
        """检测面板状态：``idle`` / ``generating`` / ``unknown``。"""
        target = self.find_chat_target(panel)
        if not target:
            return "unknown"
        result = self._cdp.evaluate(target, _DETECT_STATUS_JS)
        return result.get("status", "unknown") if isinstance(result, dict) else "unknown"

    def stop_generation(self, panel: str = PANEL_OVERVIEW) -> bool:
        """点击停止按钮中断生成；找不到停止按钮返回 False。

        不降级为 Escape：Comate 的 Escape 在编辑器上下文里另有含义
        （关闭面板/取消选择），误发可能产生副作用。
        """
        target = self.find_chat_target(panel)
        if not target:
            return False
        result = self._cdp.evaluate(target, _CLICK_STOP_JS)
        return isinstance(result, dict) and result.get("clicked") is True
