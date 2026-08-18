"""Trae Electron CDP 桥：通过 DevTools Protocol 直连 Trae 内部。

Trae 是基于 VS Code 的 Electron 应用。通过 --remote-debugging-port=9223
启动后，可用 CDP 连接其渲染器，执行 JavaScript 实现：

1. 通过 __SOLO_LITE_PORT_REGISTRY__ 获取 InputPort 实例
2. InputPort.clearInput() + focusInput() 准备输入
3. CDP Input.insertText 注入文本（兼容 Lexical 编辑器）
4. CDP Input.dispatchKeyEvent 发送 Enter 提交消息

已验证的通信路径（2026-08-14）：
  - CDP 端口 9223 可达
  - target: "TraeWork CN [管理员]" (vscode-file://vscode-app/...)
  - __SOLO_LITE_PORT_REGISTRY__.instances 含 InputPort（14 个方法）
  - InputPort.setInputContent 需要 Lexical state 对象（不兼容纯文本）
  - InputPort.focusInput() + CDP Input.insertText = 完美工作
  - Enter 键发送后输入框自动清空（消息已提交）
  - __CHAT_SESSION_COLLECTOR__ 跟踪会话状态

启动方式：
  "TRAE SOLO CN.exe" --remote-debugging-port=9223
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from star_core.cdp_bridge import CDPBridge

logger = logging.getLogger(__name__)

#: Trae Electron 默认 CDP 端口
_DEFAULT_TRAE_CDP_PORT = 9223

#: JS：通过 InputPort 聚焦并清空聊天输入框
_FOCUS_AND_CLEAR_JS = """
(() => {
    const reg = window.__SOLO_LITE_PORT_REGISTRY__;
    if (!reg || !reg.instances) return {ok: false, reason: 'no_registry'};

    for (const [sym, instance] of reg.instances) {
        const name = String(sym);
        if (name.includes('InputPort') && !name.includes('InputBar') && !name.includes('InputAction')) {
            instance.clearInput();
            instance.focusInput();
            return {ok: true, empty: instance.isInputEmpty()};
        }
    }
    return {ok: false, reason: 'no_input_port'};
})()
"""

#: JS：检查输入框状态
_CHECK_INPUT_JS = """
(() => {
    const reg = window.__SOLO_LITE_PORT_REGISTRY__;
    if (!reg || !reg.instances) return {isEmpty: true, error: 'no_registry'};

    for (const [sym, instance] of reg.instances) {
        const name = String(sym);
        if (name.includes('InputPort') && !name.includes('InputBar') && !name.includes('InputAction')) {
            const isEmpty = instance.isInputEmpty();
            const content = instance.getInputContent();
            let text = '';
            if (content && content.root && content.root.children) {
                for (const para of content.root.children) {
                    if (para.children) {
                        for (const child of para.children) {
                            if (child.text) text += child.text;
                        }
                    }
                }
            }
            return {isEmpty, text: text.slice(0, 200)};
        }
    }
    return {isEmpty: true, error: 'no_input_port'};
})()
"""

#: JS：读取最新 AI 响应
#:
#: Trae 的真实类名约定是 `chat-input-v2-*` / `messageInput*` / `initial-chat-panel`，
#: 通用的 `.chat-message` / `.markdown-body` / `[data-role=assistant]` 在 Trae 里
#: 命中数恒为 0。历史实现在全部选择器失配后会退化为"全文档取最大文本块"，
#: 结果把菜单栏、侧栏任务列表、会员广告一起当成 AI 回复返回。
#:
#: 现在的策略：所有查找都限定在聊天面板容器内，绝不扫描整个 document；
#: 找不到就诚实返回空串，由调用方决定如何处理。
_READ_LATEST_RESPONSE_JS = """
(() => {
    // 初始面板 = 尚未开始对话，此时面板里只有欢迎文案，不存在 AI 回复
    if (document.querySelector('.initial-chat-panel, [class*="initial-chat-panel"]')) {
        return {text: '', via: 'empty_panel'};
    }

    // 定位聊天面板根容器
    const rootSelectors = [
        '[class*="chat-panel"]',
        '[class*="conversation"]',
        '[class*="messageList"]',
        '[class*="message-list"]',
    ];
    let root = null;
    for (const sel of rootSelectors) {
        const el = document.querySelector(sel);
        if (el) { root = el; break; }
    }
    // 兜底：从输入框往上找一个足够大的祖先当作聊天区
    if (!root) {
        const input = document.querySelector('[class*="chat-input-v2-container"], [class*="messageInputContainer"]');
        let node = input ? input.parentElement : null;
        while (node && node !== document.body) {
            const r = node.getBoundingClientRect();
            if (r.width > 200 && r.height > 200) { root = node; break; }
            node = node.parentElement;
        }
    }
    if (!root) return {text: '', via: 'no_chat_panel'};

    // 输入区/工具栏不是回复内容，需要排除
    const isChrome = (el) => !!el.closest(
        '[class*="chat-input-v2"], [class*="messageInput"], [class*="Toolbar"], [class*="toolbar"]'
    );

    // 策略1: 面板内的消息/markdown 容器，取最后一个
    const msgSelectors = [
        '[class*="markdown"]',
        '[class*="messageContent"]',
        '[class*="message-content"]',
        '[class*="messageItem"]',
        '[class*="message-item"]',
        '[data-role="assistant"]',
    ];
    for (const sel of msgSelectors) {
        const els = Array.from(root.querySelectorAll(sel)).filter(e => !isChrome(e));
        for (let i = els.length - 1; i >= 0; i--) {
            const t = (els[i].innerText || '').trim();
            if (t.length > 0) return {text: t.slice(0, 8000), via: sel};
        }
    }

    // 策略2: 面板内可见的最大文本块（严格限定在 root 内，排除输入区）
    let best = '';
    for (const el of root.querySelectorAll('div, article, section, p')) {
        if (isChrome(el)) continue;
        const r = el.getBoundingClientRect();
        if (r.width < 200 || r.height < 30) continue;
        if (el.children.length >= 80) continue;
        const t = (el.innerText || '').trim();
        if (t.length > best.length && t.length < 15000) best = t;
    }
    if (best) return {text: best.slice(0, 8000), via: 'panel_scan'};

    // 没有可读回复时诚实返回空，不要拿 UI 文本冒充 AI 输出
    return {text: '', via: 'none'};
})()
"""

#: JS：检测当前状态（idle/thinking/generating）
_DETECT_STATUS_JS = """
(() => {
    const reg = window.__SOLO_LITE_PORT_REGISTRY__;
    
    // 策略1: 检查 InputPort 是否可用（idle 时输入框可用）
    if (reg && reg.instances) {
        let inputAvailable = false;
        for (const [sym, instance] of reg.instances) {
            const name = String(sym);
            if (name.includes('InputPort') && !name.includes('InputBar') && !name.includes('InputAction')) {
                inputAvailable = true;
                break;
            }
        }
    }

    // 策略2: 检查是否有停止按钮（生成中）
    const stopSelectors = [
        '[class*="stop"]', '[class*="cancel"]', '[class*="abort"]',
        '[aria-label*="Stop"]', '[aria-label*="停止"]',
        '[title*="Stop"]', '[title*="停止"]',
    ];
    for (const sel of stopSelectors) {
        const el = document.querySelector(sel);
        if (el && el.offsetParent !== null) {
            return {status: 'generating', via: 'stop_button', selector: sel};
        }
    }

    // 策略3: 检查关键词
    const body = document.body ? document.body.innerText : '';
    const generatingKeywords = [
        '思考中', '生成中', '处理中', '编写中', '搜索中', '分析中',
        'Thinking', 'Generating', 'Processing', 'Running',
    ];
    for (const kw of generatingKeywords) {
        if (body.includes(kw)) {
            return {status: 'generating', via: 'keyword', keyword: kw};
        }
    }

    // 策略4: 检查输入框是否可用（空闲）
    const inputEl = document.querySelector('.chat-input-v2-input-box-editable');
    if (inputEl && inputEl.getAttribute('contenteditable') === 'true') {
        return {status: 'idle', via: 'input_available'};
    }

    return {status: 'unknown', via: 'none'};
})()
"""

#: JS：查找并点击停止按钮
_CLICK_STOP_BUTTON_JS = """
(() => {
    const selectors = [
        '[class*="stop"]:not([style*="display: none"])',
        '[class*="cancel"]:not([style*="display: none"])',
        '[aria-label*="Stop"]',
        '[aria-label*="停止"]',
        '[title*="Stop"]',
        '[title*="停止"]',
        'button[class*="stop"]',
    ];
    for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
            if (el.offsetParent !== null && !el.disabled) {
                el.click();
                return {clicked: true, selector: sel};
            }
        }
    }
    return {clicked: false};
})()
"""

#: JS：探测全局对象（用于发现内部 IPC 接口）
_PROBE_GLOBALS_JS = """
(() => {
    const found = {};
    
    // 1. traeChatCoreVersion
    found.traeChatCoreVersion = (typeof window.traeChatCoreVersion !== 'undefined')
        ? window.traeChatCoreVersion : 'missing';

    // 2. __SOLO_LITE_PORT_REGISTRY__
    if (window.__SOLO_LITE_PORT_REGISTRY__) {
        const reg = window.__SOLO_LITE_PORT_REGISTRY__;
        const portNames = [];
        if (reg.ports instanceof Map) {
            for (const [sym] of reg.ports) {
                portNames.push(String(sym).replace(/Symbol\\(|\\)/g, ''));
            }
        }
        const instanceNames = [];
        if (reg.instances instanceof Map) {
            for (const [sym] of reg.instances) {
                instanceNames.push(String(sym).replace(/Symbol\\(|\\)/g, ''));
            }
        }
        found.portRegistry = {ports: portNames, instances: instanceNames};
    }

    // 3. __CHAT_SESSION_COLLECTOR__
    if (window.__CHAT_SESSION_COLLECTOR__) {
        const csc = window.__CHAT_SESSION_COLLECTOR__;
        found.chatSessionCollector = {
            keys: Object.keys(csc).slice(0, 10),
            sessionsSize: csc.sessions instanceof Map ? csc.sessions.size : 'n/a',
        };
    }

    // 4. 搜索 trae/icube/chat 相关全局变量
    const related = [];
    for (const k of Object.keys(window)) {
        const lower = k.toLowerCase();
        if (lower.includes('trae') || lower.includes('icube') || lower.includes('chat') ||
            lower.includes('aha') || lower.includes('solo') || lower.includes('agent')) {
            related.push(k + ':' + typeof window[k]);
        }
    }
    found.relatedGlobals = related;

    return found;
})()
"""


def _is_blank_target(tab: dict) -> bool:
    """判断一个 CDP target 是否为「空白/未就绪」页（欢迎页、about:blank 等）。

    这类页不是聊天 UI，且在其 JS 执行上下文尚未就绪时对其做
    ``Runtime.evaluate`` 会触发原生层崩溃（曾导致 Star 进程段错误）。
    因此匹配聊天 target 时必须先排除它们。
    """
    url = (tab.get("url") or "").strip()
    title = (tab.get("title") or "").strip()
    if url.startswith("about:"):
        return True
    if not url and not title:
        return True
    return False


class TraeCDPBridge:
    """Trae Electron CDP 桥。

    通过 Chrome DevTools Protocol 连接 Trae 的 Electron 渲染器，
    利用 Trae 内部的 __SOLO_LITE_PORT_REGISTRY__ 和 InputPort API
    实现消息发送、输出读取和状态检测。

    通信架构：
        Python → CDP WebSocket → Trae 渲染器 JS → InputPort API
                                        ↓
                              Lexical 编辑器（contenteditable）

    使用前需通过 --remote-debugging-port=9223 启动 Trae。

    Attributes:
        port: CDP 端口号（默认 9223）。
        _cdp: 底层 CDPBridge 实例。
        _cached_target: 缓存的目标 tab。
    """

    def __init__(self, port: int = _DEFAULT_TRAE_CDP_PORT):
        self.port = port
        self._cdp = CDPBridge(port=port)
        self._cached_target: dict | None = None
        self._target_cache_time: float = 0.0
        self._target_cache_ttl: float = 30.0

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    def is_alive(self) -> bool:
        """探测 Trae CDP 端口是否可达。"""
        return self._cdp.is_alive()

    def find_chat_target(self, force_refresh: bool = False) -> dict | None:
        """在 Trae 的 CDP targets 中找到聊天 UI 的渲染器。

        Trae 启动 --remote-debugging-port 后，/json 会列出多个 target。
        本方法优先找 type=page 且标题/URL 匹配 Trae 的 target。

        .. note::
            先过滤掉空白/未就绪 target（标题与 URL 都为空、或 ``about:`` 页）。
            它们不是聊天 UI，且其 JS 上下文未就绪时 ``Runtime.evaluate`` 会触发
            原生崩溃；过滤后 connect/restart 会正确等待真正的聊天页加载完成。

        Args:
            force_refresh: 强制刷新缓存。

        Returns:
            target dict（含 id/title/url/webSocketDebuggerUrl），未找到返回 None。
        """
        if (
            not force_refresh
            and self._cached_target
            and time.time() - self._target_cache_time < self._target_cache_ttl
        ):
            return self._cached_target

        tabs = self._cdp.list_tabs()
        if not tabs:
            logger.debug("TraeCDP: /json 未返回任何 target")
            return None

        # 过滤空白/未就绪 target，只对真实聊天页匹配（避免对半初始化页求值崩溃）
        real_tabs = [t for t in tabs if not _is_blank_target(t)]
        if not real_tabs:
            logger.debug(
                "TraeCDP: 仅发现空白/未就绪 target（共 %d 个），聊天页尚未加载",
                len(tabs),
            )
            return None

        # 优先策略1: 找 url 含 vscode/file 的
        for tab in real_tabs:
            url = tab.get("url") or ""
            if ("vscode" in url or "file://" in url) and tab.get("id"):
                self._cached_target = tab
                self._target_cache_time = time.time()
                logger.debug("TraeCDP: 选中 target: %s", tab.get("title"))
                return tab

        # 策略2: 找标题含 Trae 的
        for tab in real_tabs:
            title = tab.get("title") or ""
            if "trae" in title.lower() and tab.get("id"):
                self._cached_target = tab
                self._target_cache_time = time.time()
                return tab

        # 策略3: 第一个有 webSocketDebuggerUrl 的（real_tabs 已排除空白页）
        for tab in real_tabs:
            if tab.get("webSocketDebuggerUrl"):
                self._cached_target = tab
                self._target_cache_time = time.time()
                return tab

        logger.warning("TraeCDP: 未找到合适的 target（共 %d 个）", len(tabs))
        return None

    # ------------------------------------------------------------------
    # 探测
    # ------------------------------------------------------------------

    def probe_globals(self) -> dict | None:
        """探测 Trae 渲染器中可用的全局对象。"""
        target = self.find_chat_target()
        if not target:
            return None
        return self._cdp.evaluate(target, _PROBE_GLOBALS_JS)

    # ------------------------------------------------------------------
    # 能力自检（连接成功后自动触发）
    # ------------------------------------------------------------------

    def self_check(self) -> dict:
        """连接成功后的能力自检：确认端口是真实 CDP、浏览器版本、target 数、
        聊天 target 是否命中，以及渲染器是否可被 Star 脚本化驱动。

        Returns:
            结构化结果 dict，含 ``ok`` / ``browser`` / ``protocol`` /
            ``target_count`` / ``chat_target_found`` / ``scriptable`` 等字段。
            即使失败也返回完整 dict（``ok=False``），便于 UI 直接展示排障信息。
        """
        result: dict = {
            "ok": False,
            "port": self.port,
            "cdp_reachable": False,
            "browser": None,
            "protocol": None,
            "web_socket_debugger_url": None,
            "target_count": 0,
            "chat_target_found": False,
            "chat_target_title": None,
            "scriptable": False,
            "scriptable_probe": None,
            "detail": "",
        }
        ver = self._cdp.version()
        if not ver:
            result["detail"] = "CDP /json/version 无响应：端口可能未绑定或绑在死监听上"
            return result
        result["cdp_reachable"] = True
        result["browser"] = ver.get("Browser")
        result["protocol"] = ver.get("Protocol-Version")
        result["web_socket_debugger_url"] = ver.get("webSocketDebuggerUrl")

        tabs = self._cdp.list_tabs()
        result["target_count"] = len(tabs)

        target = self.find_chat_target()
        if not target:
            result["detail"] = "CDP 可达但未找到聊天 target（Trae 窗口可能尚未渲染完成）"
            return result
        result["chat_target_found"] = True
        result["chat_target_title"] = target.get("title")

        # 验证可脚本化：在聊天 target 上做一次最简单、无副作用的 Runtime.evaluate。
        # 返回 2 即代表 CDP 命令链路与渲染器 JS 执行都正常，Star 可下发指令。
        probe = self._cdp.evaluate(target, "1+1")
        result["scriptable_probe"] = probe
        result["scriptable"] = (probe == 2)
        if not result["scriptable"]:
            result["detail"] = "聊天 target 命中但 Runtime.evaluate 未返回预期值，脚本化链路异常"
            return result

        result["ok"] = True
        result["detail"] = "CDP 真实可用，Trae 渲染器可被 Star 脚本化驱动"
        return result

    # ------------------------------------------------------------------
    # 核心操作
    # ------------------------------------------------------------------

    def send_message(self, text: str) -> bool:
        """向 Trae 聊天发送消息。

        已验证的工作流程：
        1. 通过 InputPort.clearInput() 清空输入框
        2. 通过 InputPort.focusInput() 聚焦输入框
        3. 通过 CDP Input.insertText 注入文本（兼容 Lexical 编辑器）
        4. 验证文本已注入（isInputEmpty == False）
        5. 通过 CDP Input.dispatchKeyEvent 发送 Enter 键
        6. 验证消息已发送（isInputEmpty == True）

        Args:
            text: 要发送的消息文本。

        Returns:
            True 如果发送成功。
        """
        target = self.find_chat_target()
        if not target:
            logger.warning("TraeCDP: send_message 失败 - 未找到 target")
            return False

        # 1. 清空并聚焦输入框
        focus_result = self._cdp.evaluate(target, _FOCUS_AND_CLEAR_JS)
        if not isinstance(focus_result, dict) or not focus_result.get("ok"):
            logger.warning("TraeCDP: InputPort 聚焦失败: %s", focus_result)
            return False

        logger.debug("TraeCDP: 输入框已清空并聚焦")
        time.sleep(0.15)

        # 2. CDP 注入文本
        resp = self._cdp._send(target, "Input.insertText", {"text": text})
        if resp is None or "error" in resp:
            logger.warning("TraeCDP: Input.insertText 失败: %s", resp)
            return False

        time.sleep(0.2)

        # 3. 验证文本已注入
        check = self._cdp.evaluate(target, _CHECK_INPUT_JS)
        if isinstance(check, dict) and check.get("isEmpty"):
            logger.warning("TraeCDP: 文本注入后输入仍为空")
            return False

        injected_text = check.get("text", "") if isinstance(check, dict) else ""
        logger.debug("TraeCDP: 文本已注入 (%d chars): %s...", len(injected_text), injected_text[:30])

        # 4. 发送 Enter 键
        ok = self._cdp.send_key(target, "Enter")
        if not ok:
            logger.warning("TraeCDP: Enter 键发送失败")
            return False

        # 5. 等待并验证消息已发送
        time.sleep(0.5)
        verify = self._cdp.evaluate(target, _CHECK_INPUT_JS)
        if isinstance(verify, dict) and verify.get("isEmpty"):
            logger.info("TraeCDP: 消息已发送 (%d chars)", len(text))
            return True

        # 即使输入未清空，Enter 也可能已触发发送（某些情况下输入不会立即清空）
        logger.info("TraeCDP: Enter 已发送 (输入未立即清空，可能仍在处理)")
        return True

    def get_latest_response(self) -> str:
        """读取最新的 AI 响应文本。

        通过 DOM 选择器在聊天区域查找最后一条助手消息。

        Returns:
            响应文本（最多 8000 字符），未找到返回空字符串。
        """
        target = self.find_chat_target()
        if not target:
            return ""

        result = self._cdp.evaluate(target, _READ_LATEST_RESPONSE_JS)
        if isinstance(result, dict):
            text = result.get("text", "")
            via = result.get("via", "none")
            if text:
                logger.debug("TraeCDP: 响应读取成功 via=%s (%d chars)", via, len(text))
            return text
        return ""

    def stop_generation(self) -> bool:
        """停止当前 AI 生成。

        优先查找并点击停止按钮；找不到则发送 Escape 键。

        Returns:
            True 如果停止操作成功。
        """
        target = self.find_chat_target()
        if not target:
            return False

        # 1. 尝试点击停止按钮
        result = self._cdp.evaluate(target, _CLICK_STOP_BUTTON_JS)
        if isinstance(result, dict) and result.get("clicked"):
            logger.info("TraeCDP: 已点击停止按钮 via=%s", result.get("selector"))
            return True

        # 2. 降级：发送 Escape 键
        ok = self._cdp.send_key(target, "Escape")
        if ok:
            logger.info("TraeCDP: 已发送 Escape 键停止生成")
            return True

        logger.warning("TraeCDP: 停止生成失败")
        return False

    def get_status(self) -> str:
        """检测 Trae 当前状态。

        Returns:
            'idle' | 'generating' | 'unknown'
        """
        target = self.find_chat_target()
        if not target:
            return "unknown"

        result = self._cdp.evaluate(target, _DETECT_STATUS_JS)
        if isinstance(result, dict):
            return result.get("status", "unknown")
        return "unknown"

    def get_input_content(self) -> str:
        """获取当前输入框中的文本内容。

        Returns:
            输入框文本，空字符串表示无内容。
        """
        target = self.find_chat_target()
        if not target:
            return ""
        result = self._cdp.evaluate(target, _CHECK_INPUT_JS)
        if isinstance(result, dict):
            return result.get("text", "")
        return ""

    def clear_input(self) -> bool:
        """清空聊天输入框。"""
        target = self.find_chat_target()
        if not target:
            return False
        result = self._cdp.evaluate(target, _FOCUS_AND_CLEAR_JS)
        return isinstance(result, dict) and result.get("ok")

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------

    def list_sessions(self) -> list[dict] | None:
        """列出聊天会话。

        通过 __CHAT_SESSION_COLLECTOR__.sessions 获取会话列表。

        Returns:
            会话列表，或 None 表示不可用。
        """
        target = self.find_chat_target()
        if not target:
            return None

        js = """
        (() => {
            const csc = window.__CHAT_SESSION_COLLECTOR__;
            if (!csc || !csc.sessions) return null;
            
            const sessions = [];
            if (csc.sessions instanceof Map) {
                for (const [k, v] of csc.sessions) {
                    sessions.push({
                        id: String(k).slice(0, 60),
                        keys: Object.keys(v || {}).slice(0, 10),
                    });
                }
            }
            return sessions;
        })()
        """
        result = self._cdp.evaluate(target, js)
        return result if isinstance(result, list) else None

    # ------------------------------------------------------------------
    # 便捷方法
    # ------------------------------------------------------------------

    def evaluate(self, expr: str) -> Any:
        """在 Trae 渲染器中执行任意 JavaScript 表达式。"""
        target = self.find_chat_target()
        if not target:
            return None
        return self._cdp.evaluate(target, expr)

    def take_screenshot(self) -> bytes | None:
        """对 Trae 渲染器截图。

        Returns:
            PNG 图片字节，失败返回 None。
        """
        target = self.find_chat_target()
        if not target:
            return None
        resp = self._cdp._send(target, "Page.captureScreenshot", {"format": "png"})
        if resp and "result" in resp:
            import base64
            data = resp["result"].get("data")
            if data:
                return base64.b64decode(data)
        return None


def ensure_trae_debug_port() -> bool:
    """检查 Trae 是否以调试端口启动；若否，提示用户。

    Returns:
        True 如果 CDP 端口已可用。
    """
    bridge = TraeCDPBridge()
    if bridge.is_alive():
        return True

    logger.info(
        "Trae 未以调试端口启动。请在启动时添加 --remote-debugging-port=9223 参数。\n"
        "示例: \"TRAE SOLO CN.exe\" --remote-debugging-port=9223"
    )
    return False
