"""DuMate 桌面端（DuMate.exe / 百度搭子）聊天面板 CDP 发送通道。

命名与产品澄清见 :mod:`star_core.dumate_app_launcher`。本模块驱动的是独立安装的
DuMate 桌面端，**不是** 仓库里历史命名为 ``dumate`` 的 Comate。

DOM 拓扑（2026-08-16 实测 DuMate 1.0.69；2026-08-17 静态复核 1.0.70 / Electron 43）
------------------------------------------------------------------------------
与 Comate 不同，DuMate 的调试端口下**只有一个 page target**
（``file://.../app.asar/frontend/index.html``，title「百度搭子」），聊天 UI 就在
这个顶层文档里，无 webview / iframe 外壳，可直接 evaluate::

    [data-lexical-editor="true"]   ← 输入框（Lexical 富文本，非原生 textarea）
    button[title="发送"]            ← 发送按钮，空输入时 disabled
    [data-markdown-body]           ← 每条消息渲染后的正文（无哈希，首选）
    button[aria-label="新任务"]     ← 新建任务（开新会话）

CSS-module 类名带构建哈希，且**每次发版都会变**：``markdownBody`` 在 1.0.69 是
``markdownBody-YMvJCu``、1.0.70 变成 ``markdownBody-AfTAIf``（旧哈希作为遗留模块
仍留在同一份 bundle 里，所以"能搜到旧类名"不代表页面用的是旧类名）。因此：

1. 一律不写死哈希后缀，用 ``[class*="前缀"]`` 子串匹配；
2. 更进一步——凡是有语义属性的地方优先用属性。正文容器上有
   ``data-markdown-body``（1.0.70 确认：``className:cx(markdownBody,
   {markdownBodyLight:light===codeTheme})`` 与该属性同元素，所以子串匹配
   不会因浅色主题类名而重复计数），消息角色有 ``data-message-role``，
   按钮有 ``title`` / ``aria-label``。
3. 每个角色都配**按优先级排序的候选选择器**（见 ``_*_SELS``），逐个 try 而不是
   拼成一条逗号选择器——``querySelector('a,b')`` 返回的是**文档顺序**最靠前的
   元素，不是选择器顺序，拼在一起会让"优先用精确选择器"的意图失效。

版本升级后先跑 :meth:`DuMateAppCDPBridge.probe_selectors` 体检，一次看清每个角色
命中了哪条候选、命中几个，比等发送失败再回溯快得多。

输入注入：Lexical 把内容存在自己的 model 里，直接改 DOM 不被感知。必须
**聚焦后走 CDP ``Input.insertText``**（浏览器真实输入管线），实测生效且发送按钮
随即从 disabled 解禁。清空则聚焦 + ``selectAll`` + Backspace。

状态检测：空闲时只有 ``button[title="发送"]``；生成中会额外出现
``button[title="停止"]``，生成结束后「停止」消失、换成「分享」。实测一次约 18 秒的
长回答，:meth:`get_status` 在 +2s~+16s 稳定返回 ``generating``、+18s 转 ``idle``，
判据可靠。（短问答若 3 秒内答完，轮询可能整段错过 ``generating`` 窗口，所以"是否
写完"更稳妥的判据是 :meth:`get_latest_response` 文本不再增长。）

消息角色：助手回复所在容器带 ``data-message-role="assistant"`` 与
``data-assistant-block-id``，外层列表容器带 ``data-message-list-content="true"``，
因此可以精确取助手回复，不必赌"最后一条消息"。用户自己发的消息不在
``markdownBody`` 里。

**旧回答残留这个坑必须绕**：上一轮的助手回复一直留在 DOM 里，所以"发完立刻读最后
一条"会拿到上一轮的答案——看起来像秒回，实际新回答还没开始生成（真实踩过：一次
测试里问 A 得到的是上一次问 B 的答案，却被当成通过）。:meth:`DuMateAppCDPBridge.
send_message` 因此会记录发送前的回复条数基线，:meth:`DuMateAppCDPBridge.
get_new_response` 只在条数超过基线时才返回文本。判断"写完"仍以文本长度不再增长为准。
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

# 每个角色一组**按优先级排序**的候选选择器：语义属性（跨版本最稳）在前，
# 类名子串兜底在后。逐个 try（见 _first_matching_js），不拼成一条逗号选择器——
# querySelector('a,b') 取文档顺序最靠前者而非选择器顺序，会让优先级失效。

#: 输入框（Lexical 富文本编辑器）
_INPUT_SELS = (
    '[data-lexical-editor="true"]',
    '[contenteditable="true"][data-lexical-editor]',
    '[contenteditable="true"]',
)

#: 发送按钮
_SEND_SELS = (
    'button[title="发送"]',
    'button[aria-label="发送"]',
    'button[class*="sendButton"]',
)

#: 停止按钮（生成中出现）
_STOP_SELS = (
    'button[title*="停止"]',
    'button[aria-label*="停止"]',
    'button[title*="中止"]',
    'button[aria-label*="中止"]',
    'button[title*="Stop"]',
    'button[aria-label*="Stop"]',
    'button[class*="stopButton"]',
)

#: 每条消息正文（markdown 渲染容器）。data-markdown-body 无哈希、跨版本稳定，首选。
_MSG_SELS = (
    '[data-markdown-body]',
    '[class*="markdownBody"]',
)

#: 助手回复容器标记（外层带 data-message-role="assistant"）
_ASSISTANT_MSG_SELS = (
    '[data-message-role="assistant"] [data-markdown-body]',
    '[data-message-role="assistant"] [class*="markdownBody"]',
    '[data-assistant-block-id] [data-markdown-body]',
    '[data-assistant-block-id] [class*="markdownBody"]',
)

#: 新建任务按钮
_NEW_TASK_SELS = (
    'button[aria-label="新任务"]',
    'button[title="新任务"]',
)

# --- 供体检/日志展示的首选选择器（每组第 0 条），保持旧变量名兼容 ---
_INPUT_SEL = _INPUT_SELS[0]
_SEND_SEL = _SEND_SELS[0]
_MSG_SEL = _MSG_SELS[0]
_ASSISTANT_MSG_SEL = _ASSISTANT_MSG_SELS[0]
_NEW_TASK_SEL = _NEW_TASK_SELS[0]


def _js_sel_list(sels: tuple[str, ...]) -> str:
    """把候选选择器组渲染成 JS 数组字面量。"""
    return "[" + ",".join(json.dumps(s) for s in sels) + "]"


def _js(expr_body: str) -> str:
    """包一层 IIFE，片段内可直接 return。"""
    return "(() => {" + expr_body + "})()"


# JS 侧公共助手：按候选顺序返回首个命中的元素 / 全部命中的最长列表。
# 注入到每段脚本前部，避免每处重复实现。
_JS_HELPERS = (
    "const _q=(sels)=>{for(const s of sels){const el=document.querySelector(s);"
    "if(el)return el;}return null;};"
    "const _qa=(sels)=>{for(const s of sels){const els=document.querySelectorAll(s);"
    "if(els.length)return els;}return document.querySelectorAll('#__none__');};"
)

_INPUT_JS_ARR = _js_sel_list(_INPUT_SELS)
_SEND_JS_ARR = _js_sel_list(_SEND_SELS)
_STOP_JS_ARR = _js_sel_list(_STOP_SELS)
_MSG_JS_ARR = _js_sel_list(_MSG_SELS)
_ASSISTANT_JS_ARR = _js_sel_list(_ASSISTANT_MSG_SELS)
_NEW_TASK_JS_ARR = _js_sel_list(_NEW_TASK_SELS)


#: JS：读取输入框文本（Lexical 用 innerText）
_GET_INPUT_JS = _js(
    _JS_HELPERS
    + "const el=_q(" + _INPUT_JS_ARR + ");"
    "if(!el)return null;"
    "return {text:(el.innerText||'').replace(/\\n$/,'')};"
)

#: JS：聚焦输入框（供 Input.insertText 前置）
_FOCUS_INPUT_JS = _js(
    _JS_HELPERS
    + "const el=_q(" + _INPUT_JS_ARR + ");"
    "if(!el)return false;"
    "el.focus();"
    "return document.activeElement===el;"
)

#: JS：全选输入框内容（清空前置）
_SELECT_ALL_JS = _js(
    _JS_HELPERS
    + "const el=_q(" + _INPUT_JS_ARR + ");"
    "if(!el)return false;"
    "el.focus();"
    "document.execCommand('selectAll');"
    "return true;"
)

#: JS：点击发送按钮
_CLICK_SEND_JS = _js(
    _JS_HELPERS
    + "const b=_q(" + _SEND_JS_ARR + ");"
    "if(!b)return {clicked:false,reason:'no-button'};"
    "if(b.disabled)return {clicked:false,reason:'disabled'};"
    "b.click();"
    "return {clicked:true};"
)

#: JS：发送按钮是否已解禁（可点击）
_SEND_ENABLED_JS = _js(
    _JS_HELPERS
    + "const b=_q(" + _SEND_JS_ARR + ");"
    "return !!b && !b.disabled;"
)

#: JS：读取最后一条助手回复正文
#:
#: 优先取带 data-message-role="assistant" 的回复；取不到（DOM 变体）再退回全部
#: markdownBody 的最后一条。用户自己发的消息不在 markdownBody 里，故不会误取。
_READ_LATEST_JS = _js(
    _JS_HELPERS
    + "let items=_qa(" + _ASSISTANT_JS_ARR + ");"
    "if(!items.length)items=_qa(" + _MSG_JS_ARR + ");"
    "if(!items.length)return {text:'',count:0};"
    "const last=items[items.length-1];"
    "return {text:(last.innerText||'').trim().slice(0,8000),count:items.length};"
)

#: JS：状态检测（停止按钮出现 => 生成中）
_DETECT_STATUS_JS = _js(
    _JS_HELPERS
    + "const stop=_q(" + _STOP_JS_ARR + ");"
    "if(stop)return {status:'generating',via:'stop-button'};"
    "const inp=_q(" + _INPUT_JS_ARR + ");"
    "if(!inp)return {status:'unknown',via:'no-input'};"
    "return {status:'idle',via:'no-stop-button'};"
)

#: JS：点击停止按钮
_CLICK_STOP_JS = _js(
    _JS_HELPERS
    + "const stop=_q(" + _STOP_JS_ARR + ");"
    "if(!stop)return {clicked:false};"
    "stop.click();"
    "return {clicked:true};"
)

#: JS：点击「新任务」开新会话
_CLICK_NEW_TASK_JS = _js(
    _JS_HELPERS
    + "const b=_q(" + _NEW_TASK_JS_ARR + ");"
    "if(!b)return {clicked:false};"
    "b.click();"
    "return {clicked:true};"
)

#: JS：选择器体检——每个角色报告命中的候选与数量，供版本升级时快速定位。
_PROBE_SELECTORS_JS = _js(
    "const groups={"
    "input:" + _INPUT_JS_ARR + ","
    "send:" + _SEND_JS_ARR + ","
    "stop:" + _STOP_JS_ARR + ","
    "message:" + _MSG_JS_ARR + ","
    "assistant:" + _ASSISTANT_JS_ARR + ","
    "new_task:" + _NEW_TASK_JS_ARR
    + "};"
    "const out={};"
    "for(const role in groups){"
    "  let hit=null,total=0;"
    "  for(const s of groups[role]){"
    "    const n=document.querySelectorAll(s).length;"
    "    if(n&&hit===null){hit=s;total=n;}"
    "  }"
    "  out[role]={matched:hit,count:total,"
    "    candidates:groups[role].map(s=>({sel:s,count:document.querySelectorAll(s).length}))};"
    "}"
    "return out;"
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
        #: 最近一次 send_message 前的助手回复条数基线。
        #: 用于区分"本轮的新回复"与"上一轮的残留回复"——DOM 里旧回答一直在，
        #: 发完就读会拿到旧的（曾导致误判发送成功）。None 表示尚未发过。
        self._response_baseline: int | None = None


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

    def probe_selectors(self) -> dict:
        """选择器体检：报告每个角色命中了哪条候选、各候选各命中几个。

        DuMate 每次发版都会换 CSS-module 哈希、偶尔调 DOM 结构，届时故障现象往往
        是"发送无反应"或"读不到回复"这种间接症状。升级后先调这个方法，一次看清
        哪个角色 ``matched`` 为 None，比等失败再回溯快得多。

        Returns:
            ``{"ok": True, "roles": {role: {"matched": sel|None, "count": int,
            "candidates": [{"sel": str, "count": int}, ...]}}}``；
            页面不可达时 ``{"ok": False, "reason": "no-target"}``。
        """
        target = self.find_chat_target()
        if not target:
            return {"ok": False, "reason": "no-target"}
        result = self._cdp.evaluate(target, _PROBE_SELECTORS_JS)
        if not isinstance(result, dict):
            return {"ok": False, "reason": "evaluate-failed"}
        missing = [role for role, info in result.items() if not info.get("matched")]
        if missing:
            logger.warning("DuMateAppCDP: 选择器体检失配角色: %s", ", ".join(missing))
        return {"ok": not missing, "roles": result, "missing": missing}


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

        # 记录回复条数基线。必须在「新任务」点击之后取——开新会话会把消息列表清空，
        # 用旧会话的条数当基线会导致新回复被误判为"还没出现"。
        snap = self._cdp.evaluate(target, _READ_LATEST_JS)
        baseline = snap.get("count", 0) if isinstance(snap, dict) else 0

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
        self._response_baseline = baseline
        return True

    # ------------------------------------------------------------------
    # 读取与状态
    # ------------------------------------------------------------------

    def read_latest(self) -> dict:
        """读取最后一条助手回复及当前回复条数。

        Returns:
            ``{"text": str, "count": int}``；页面不可达时 count 为 -1，
            以便与"页面正常但还没有任何回复"（count=0）区分。
        """
        target = self.find_chat_target()
        if not target:
            return {"text": "", "count": -1}
        result = self._cdp.evaluate(target, _READ_LATEST_JS)
        if not isinstance(result, dict):
            return {"text": "", "count": -1}
        return {"text": result.get("text", ""), "count": int(result.get("count", 0))}

    def get_latest_response(self) -> str:
        """读取最后一条**助手回复**正文，不区分是哪一轮的。

        依据 ``data-message-role="assistant"`` 定位，不会把用户自己发的消息当成
        回复。但**旧回答一直留在 DOM 里**，所以刚发完就调用会拿到上一轮的回答。
        要确认"本轮"的回复，用 :meth:`get_new_response`。
        """
        return self.read_latest()["text"]

    def get_new_response(self) -> str | None:
        """只返回**本次 send_message 之后新出现**的助手回复；尚未出现返回 None。

        判据是回复条数超过 :meth:`send_message` 记录的基线。这是为了消除一个真实
        踩过的坑：发完立刻读会拿到上一轮的旧回答，看起来像"秒回"，实际新回答还
        没开始生成。

        还没调用过 send_message（无基线）时退化为 :meth:`get_latest_response`。
        生成中调用会拿到已流式渲染出的片段，需要完整回答请等文本长度不再增长。
        """
        snap = self.read_latest()
        if snap["count"] < 0:
            return None
        if self._response_baseline is None:
            return snap["text"] or None
        if snap["count"] <= self._response_baseline:
            return None
        return snap["text"] or None

    def get_status(self) -> str:
        """检测状态：``idle`` / ``generating`` / ``unknown``。

        生成中会出现 ``button[title="停止"]``，实测长回答期间稳定命中；短问答若在
        一次轮询间隔内答完，可能整段错过 ``generating``，"是否写完"更稳妥的判据是
        :meth:`get_latest_response` 文本不再增长。
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
