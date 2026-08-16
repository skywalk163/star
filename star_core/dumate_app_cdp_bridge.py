"""DuMate 桌面端（DuMate.exe / 百度搭子）聊天面板 CDP 发送通道。

命名与产品澄清见 :mod:`star_core.dumate_app_launcher`。本模块驱动的是独立安装的
DuMate 桌面端，**不是** 仓库里历史命名为 ``dumate`` 的 Comate。

DOM 拓扑（2026-08-16 实测，DuMate 1.0.69 / Electron 43）
--------------------------------------------------------
与 Comate 不同，DuMate 的调试端口下**只有一个 page target**
（``file://.../app.asar/frontend/index.html``，title「百度搭子」），聊天 UI 就在
这个顶层文档里，无 webview / iframe 外壳，可直接 evaluate::

    [data-lexical-editor="true"]   ← 输入框（Lexical 富文本，非原生 textarea）
    button[title="发送"]            ← 发送按钮，空输入时 disabled
    [class*="markdownBody"]        ← 每条消息渲染后的正文
    [class*="sessionItem"]         ← 左侧最近会话项
    button[aria-label="新任务"]     ← 新建任务（开新会话）

CSS-module 类名带构建哈希（``markdownBody-YMvJCu``），跨版本会变，故一律用
``[class*="前缀"]`` 子串匹配，不写死哈希后缀；语义明确的 ``title`` /
``aria-label`` / ``data-*`` 属性优先。

输入注入：Lexical 把内容存在自己的 model 里，直接改 DOM 不被感知。必须
**聚焦后走 CDP ``Input.insertText``**（浏览器真实输入管线），实测生效且发送按钮
随即从 disabled 解禁。清空则聚焦 + ``selectAll`` + Backspace。

状态检测：空闲时只有 ``button[title="发送"]``。生成中的判据用「出现停止按钮」
（``title``/``aria-label`` 含「停止/中止/Stop」）——**此判据尚未在真实生成过程中
观测到命中**：实测用例（短问答）在 3 秒内就回完了，全程 :meth:`get_status` 都是
``idle``。因此 ``generating`` 目前不可依赖，轮询完成请以「最后一条消息文本停止增长」
为准，不要只看 :meth:`get_status`。
"""

from __future__ import annotations

import json
import logging
import time

from star_core.cdp_bridge import CDPBridge
from star_core.dumate_app_launcher import DEFAULT_DUMATE_APP_CDP_PORT

logger = logging.getLogger(__name__)

#: 顶层页面 URL 特征（用于在 /json 里定位聊天页）
_PAGE_URL_HINT = "index.html"

#: 输入框选择器（Lexical 富文本编辑器）
_INPUT_SEL = '[data-lexical-editor="true"]'

#: 发送按钮选择器
_SEND_SEL = 'button[title="发送"]'

#: 停止按钮选择器（生成中出现）
_STOP_SEL = (
    'button[title*="停止"],button[aria-label*="停止"],'
    'button[title*="中止"],button[aria-label*="中止"],'
    'button[title*="Stop"],button[aria-label*="Stop"]'
)

#: 每条消息正文（markdown 渲染容器）
_MSG_SEL = '[class*="markdownBody"]'

#: 新建任务按钮
_NEW_TASK_SEL = 'button[aria-label="新任务"]'


def _js(expr_body: str) -> str:
    """包一层 IIFE，片段内可直接 return。"""
    return "(() => {" + expr_body + "})()"


#: JS：读取输入框文本（Lexical 用 innerText）
_GET_INPUT_JS = _js(
    "const el=document.querySelector(" + json.dumps(_INPUT_SEL) + ");"
    "if(!el)return null;"
    "return {text:(el.innerText||'').replace(/\\n$/,'')};"
)

#: JS：聚焦输入框（供 Input.insertText 前置）
_FOCUS_INPUT_JS = _js(
    "const el=document.querySelector(" + json.dumps(_INPUT_SEL) + ");"
    "if(!el)return false;"
    "el.focus();"
    "return document.activeElement===el;"
)

#: JS：全选输入框内容（清空前置）
_SELECT_ALL_JS = _js(
    "const el=document.querySelector(" + json.dumps(_INPUT_SEL) + ");"
    "if(!el)return false;"
    "el.focus();"
    "document.execCommand('selectAll');"
    "return true;"
)

#: JS：点击发送按钮
_CLICK_SEND_JS = _js(
    "const b=document.querySelector(" + json.dumps(_SEND_SEL) + ");"
    "if(!b)return {clicked:false,reason:'no-button'};"
    "if(b.disabled)return {clicked:false,reason:'disabled'};"
    "b.click();"
    "return {clicked:true};"
)

#: JS：发送按钮是否已解禁（可点击）
_SEND_ENABLED_JS = _js(
    "const b=document.querySelector(" + json.dumps(_SEND_SEL) + ");"
    "return !!b && !b.disabled;"
)

#: JS：读取最后一条消息正文
_READ_LATEST_JS = _js(
    "const items=document.querySelectorAll(" + json.dumps(_MSG_SEL) + ");"
    "if(!items.length)return {text:'',count:0};"
    "const last=items[items.length-1];"
    "return {text:(last.innerText||'').trim().slice(0,8000),count:items.length};"
)

#: JS：状态检测（停止按钮出现 => 生成中）
_DETECT_STATUS_JS = _js(
    "const stop=document.querySelector(" + json.dumps(_STOP_SEL) + ");"
    "if(stop)return {status:'generating',via:'stop-button'};"
    "const inp=document.querySelector(" + json.dumps(_INPUT_SEL) + ");"
    "if(!inp)return {status:'unknown',via:'no-input'};"
    "return {status:'idle',via:'no-stop-button'};"
)

#: JS：点击停止按钮
_CLICK_STOP_JS = _js(
    "const stop=document.querySelector(" + json.dumps(_STOP_SEL) + ");"
    "if(!stop)return {clicked:false};"
    "stop.click();"
    "return {clicked:true};"
)

#: JS：点击「新任务」开新会话
_CLICK_NEW_TASK_JS = _js(
    "const b=document.querySelector(" + json.dumps(_NEW_TASK_SEL) + ");"
    "if(!b)return {clicked:false};"
    "b.click();"
    "return {clicked:true};"
)


#: 发送按钮解禁等待上限（秒）
#:
#: 实测：``Input.insertText`` 落到 DOM 后，Lexical -> React 还要一次状态传播才会把
#: 发送按钮从 disabled 解禁。0.4s 时仍 disabled、0.8s 时已解禁，故固定 sleep 容易
#: 抢跑（曾导致点击返回 reason='disabled'），改为轮询。
_SEND_ENABLE_TIMEOUT = 5.0

#: 轮询间隔（秒）
_POLL_INTERVAL = 0.2


class DuMateAppCDPBridge:
    """DuMate 桌面端聊天面板的 CDP 发送通道。

    需要 DuMate 已带 ``--remote-debugging-port`` 启动（见
    :func:`star_core.dumate_app_launcher.launch_dumate_app_with_cdp`）。

    Attributes:
        port: CDP 端口（默认 9225）。
    """

    def __init__(self, port: int = DEFAULT_DUMATE_APP_CDP_PORT):
        self.port = port
        self._cdp = CDPBridge(port=port)

    # ------------------------------------------------------------------
    # 连接与 target 发现
    # ------------------------------------------------------------------

    def is_alive(self) -> bool:
        """探测 DuMate CDP 端口是否可达。"""
        return self._cdp.is_alive()

    def find_chat_target(self) -> dict | None:
        """定位聊天页 target；未找到返回 None。"""
        tab = self._cdp.find_tab(_PAGE_URL_HINT)
        if tab and tab.get("webSocketDebuggerUrl"):
            return {"webSocketDebuggerUrl": tab["webSocketDebuggerUrl"]}
        return None

    # ------------------------------------------------------------------
    # 输入框读写
    # ------------------------------------------------------------------

    def get_input_content(self) -> str:
        """读取输入框当前文本；不可达返回空串。"""
        target = self.find_chat_target()
        if not target:
            return ""
        result = self._cdp.evaluate(target, _GET_INPUT_JS)
        return result.get("text", "") if isinstance(result, dict) else ""

    def set_input(self, text: str) -> bool:
        """写入输入框（不发送）；先清空再插入，回读校验一致才返回 True。

        走 ``Input.insertText`` 而非改 DOM —— Lexical 编辑器只认前者。
        """
        target = self.find_chat_target()
        if not target:
            return False
        if not self._replace_input(target, text):
            return False
        after = self._cdp.evaluate(target, _GET_INPUT_JS)
        return isinstance(after, dict) and after.get("text", "") == text

    def clear_input(self) -> bool:
        """清空输入框。"""
        target = self.find_chat_target()
        if not target:
            return False
        return self._replace_input(target, "")

    def _replace_input(self, target: dict, text: str) -> bool:
        """把输入框内容整体替换为 text（含清空既有内容）。"""
        # 聚焦 + 全选 + 删除既有内容
        if self._cdp.evaluate(target, _SELECT_ALL_JS) is not True:
            return False
        self._cdp.send_key(target, "Backspace")
        if text:
            if self._cdp.evaluate(target, _FOCUS_INPUT_JS) is not True:
                return False
            if not self._cdp.insert_text(target, text):
                return False
        return True

    def _wait_send_enabled(self, target: dict, timeout: float = _SEND_ENABLE_TIMEOUT) -> bool:
        """轮询等待发送按钮解禁；超时返回 False。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._cdp.evaluate(target, _SEND_ENABLED_JS) is True:
                return True
            time.sleep(_POLL_INTERVAL)
        return False

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------

    def send_message(
        self,
        text: str,
        new_chat: bool = False,
        overwrite: bool = False,
    ) -> bool:
        """向 DuMate 聊天面板发送一条消息。

        流程：定位页面 →（可选）开新任务 → 检查草稿 → 注入并回读校验 →
        点击发送 → 回读确认输入框已清空。

        Args:
            text: 消息文本；空串直接返回 False。
            new_chat: 发送前先点「新任务」开一个干净会话。
            overwrite: 输入框已有草稿时是否覆盖。默认 False，即放弃发送，
                以免抹掉用户手输的内容。

        Returns:
            True 表示发送按钮已点击且输入框已清空。
        """
        if not text:
            return False

        target = self.find_chat_target()
        if not target:
            logger.warning("DuMateAppCDP: 未找到聊天页（端口 %s）", self.port)
            return False

        if new_chat:
            self._cdp.evaluate(target, _CLICK_NEW_TASK_JS)
            time.sleep(0.6)

        draft = self._cdp.evaluate(target, _GET_INPUT_JS)
        if isinstance(draft, dict) and draft.get("text") and not overwrite:
            logger.warning(
                "DuMateAppCDP: 输入框已有草稿(%d 字)，放弃发送；"
                "如需覆盖请传 overwrite=True",
                len(draft["text"]),
            )
            return False

        if not self._replace_input(target, text):
            logger.warning("DuMateAppCDP: 文本注入失败")
            return False

        after_set = self._cdp.evaluate(target, _GET_INPUT_JS)
        if not (isinstance(after_set, dict) and after_set.get("text") == text):
            logger.warning("DuMateAppCDP: 注入回读不一致: %s", after_set)
            return False

        # Lexical -> React 需要一次状态传播才会把发送按钮解禁，轮询等待而非固定 sleep
        if not self._wait_send_enabled(target):
            logger.warning("DuMateAppCDP: 等待发送按钮解禁超时，放弃发送")
            self.clear_input()
            return False

        clicked = self._cdp.evaluate(target, _CLICK_SEND_JS)
        if not (isinstance(clicked, dict) and clicked.get("clicked")):
            logger.warning("DuMateAppCDP: 发送按钮点击失败: %s", clicked)
            self.clear_input()
            return False

        time.sleep(0.5)
        tail = self._cdp.evaluate(target, _GET_INPUT_JS)
        if isinstance(tail, dict) and tail.get("text"):
            logger.warning(
                "DuMateAppCDP: 已点击发送但输入框仍有内容(%d 字)，可能未提交",
                len(tail["text"]),
            )
            return False

        logger.info("DuMateAppCDP: 消息已发送 (%d 字)", len(text))
        return True

    # ------------------------------------------------------------------
    # 读取与状态
    # ------------------------------------------------------------------

    def get_latest_response(self) -> str:
        """读取最后一条消息正文（尽力而为）。

        DOM 上无稳定的 user/assistant 角色标记，返回的「最后一条」可能是刚发出
        的用户消息。需要区分角色时应结合 :meth:`get_status` 轮询到 idle 后再读。
        """
        target = self.find_chat_target()
        if not target:
            return ""
        result = self._cdp.evaluate(target, _READ_LATEST_JS)
        return result.get("text", "") if isinstance(result, dict) else ""

    def get_status(self) -> str:
        """检测状态：``idle`` / ``generating`` / ``unknown``。

        ``generating`` 依赖「停止按钮出现」这一判据，尚未在真实生成过程中观测到
        命中（见模块 docstring）。判断回答是否写完，请以
        :meth:`get_latest_response` 的文本不再增长为准。
        """
        target = self.find_chat_target()
        if not target:
            return "unknown"
        result = self._cdp.evaluate(target, _DETECT_STATUS_JS)
        return result.get("status", "unknown") if isinstance(result, dict) else "unknown"

    def stop_generation(self) -> bool:
        """点击停止按钮中断生成；找不到停止按钮返回 False。"""
        target = self.find_chat_target()
        if not target:
            return False
        result = self._cdp.evaluate(target, _CLICK_STOP_JS)
        return isinstance(result, dict) and result.get("clicked") is True
