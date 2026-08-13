# 群星 v4 混合定位器交互架构设计

> 状态：设计已获用户批准（2026-08-13）
> 目标：将"提交任务"从"坐标比例点击"升级为"GUI 元素识别"，支持桌面 AI Agent（Trae Work / DuMate / WorkBuddy 等）与浏览器网页 AI（文心一言等）的统一 Web 管控

## 1. 概述

群星（Star）当前通过 `StarEmissary` + `StarAdapter` 以**窗口坐标比例**点击输入框完成任务提交，对布局变化（侧边栏折叠、DPI 缩放、Trae Work 模式）极其脆弱。本次升级引入**混合定位器架构**：

- 桌面应用：**UIA 元素识别优先 → 视觉 OCR 定位兜底 → 坐标比例兜底** 的定位器链
- 浏览器网页 AI：**CDP（Chrome DevTools Protocol）直连 DOM** 精确定位与读取输出
- 全部交互特征由 `ai-agents.yaml` **配置驱动**，新增软件只写配置、不改代码
- 配套 **Web 定位器校准器**：截图 + UIA 树可视化，点选即生成配置，解决"每款应用适配成本"

**已确认决策**：
1. 采用混合定位器架构（非纯 UIA、非纯视觉）
2. 接受浏览器以 `--remote-debugging-port` 调试端口方式运行（预置"管控浏览器"）
3. "停止任务"语义 = 停止当前生成（点击停止按钮 / Esc），**永不杀进程**
4. 适配方式 = "先探测、后落库"（校准器实测元素，配置写入 yaml，立即生效）

## 2. 现状与问题

### 2.1 现有链路

```
StarSeeker(进程发现) → StarBody(hwnd) → StarEmissary
    ├─ _click_input_area(): 按 StarAdapter.get_input_click_position() 比例坐标点击
    ├─ _paste_text(): 剪贴板 + Ctrl+V
    ├─ _press_enter(): 回车
    └─ _capture_output(): LogReader(快) → OCRGazer(慢兜底)
```

### 2.2 核心痛点

| 痛点 | 说明 |
|---|---|
| 坐标比例非"识别" | `input_click_x_ratio/y_ratio` 是猜测位置，不是识别元素 |
| 布局敏感 | 侧边栏折叠 / DPI 变化 / 窗口缩放 / Trae Work 模式切换均导致比例失效 |
| 停止无着落 | 无"停止按钮"识别能力，只有键盘兜底 |
| 浏览器 agent 输出不可靠 | 网页 AI 走 OCR 读滚动区，又慢又不准 |
| 适配成本高 | 每款软件需在 `PRESET_ADAPTERS` 改 Python 代码，非配置驱动 |

## 3. 修改范围

### 文件清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `star_core/locators/__init__.py` | 新增 | 定位器注册表与工厂（`create_locator` / `build_chain`） |
| `star_core/locators/base.py` | 新增 | `Locator`/`ElementBox`/`LocatorChain` 抽象与组合执行 |
| `star_core/locators/uia.py` | 新增 | `UIALocator`：控件树查找（ControlType + AutomationId + Name 正则） |
| `star_core/locators/visual.py` | 新增 | `VisualLocator`：截图 + OCR 占位文本 + 模板匹配 |
| `star_core/locators/ratio.py` | 新增 | `RatioLocator`：现有坐标比例方案迁移为兜底 |
| `star_core/locators/cdp.py` | 新增 | `CDPLocator`：CDP DOM 选择器定位与点击 |
| `star_core/interaction.py` | 新增 | 高层动作原语：`submit()` / `stop()` / `read_output()`，包装定位器链 |
| `star_core/cdp_bridge.py` | 新增 | CDP 连接管理（`websockets`）、标签页枚举、DOM 读写、断开重连 |
| `star_core/config_service.py` | 修改 | 加载 `ai-agents.yaml` 的 `interaction` 配置段 → `InteractionConfig` |
| `star_core/star_emissary.py` | 修改 | `send_prompt`/`wait_for_response` 接入定位器链；`stop_current()` 新增 |
| `star_core/star_seeker.py` | 修改 | 发现浏览器 agent 时启动/探测 CDP 通道，`StarBody.category` 支持 `browser` |
| `star_api/routes/locators.py` | 新增 | 校准 API：截图+UIA树 / 试发 / 配置预览与落盘 |
| `star_api/routes/stars.py` | 修改 | 新增 `POST /api/stars/{id}/stop`（停止当前生成） |
| `star_api/main.py` | 修改 | 挂载 locators 路由 |
| `config/ai-agents.yaml` | 修改 | 各 agent 增加 `interaction` 段；新增浏览器 agent 条目 |
| `star-ui/pages/calibrator.html` | 新增 | 定位器校准器页面 |
| `star-ui/js/pages/calibrator.js`（或内联） | 新增 | 校准器交互逻辑 |
| `star-ui/js/nav.js` | 修改 | 增加校准器导航入口 |

### 不改的文件

- `star_core/log_reader.py` — 官方日志读取已完备，直接复用
- `star_core/ocr_gazer.py` — 视觉兜底的 OCR 引擎已完备，直接复用
- `star_core/orbit_engine.py` — 任务队列不涉及
- `config.yaml` — 顶层配置暂不动（OCR 开关等沿用）

## 4. 详细设计

### 4.1 架构总览

```
Web UI (校准器 / 星图 / 星轨)
   │  FastAPI + WebSocket (已有)
   ▼
StarEmissary (改造) ── 提交/停止/读取 ──▶ interaction.py (新增动作原语)
   │                                            │
   │                        ┌───────────────────┼──────────────────┐
   │                        ▼                   ▼                  ▼
   │              UIALocator  →  VisualLocator →  RatioLocator     CDPLocator
   │              (控件树识别)    (截图+OCR)     (坐标比例兜底)      (浏览器DOM)
   │                        │                                      │
   ▼                        ▼                                      ▼
桌面 Agent (Trae/DuMate/WorkBuddy...)                   管控浏览器 (Edge/Chrome --remote-debugging-port)
   │                        │
   ▼                        ▼
输出读取: LogReader(已有) → OCR(已有) → CDP DOM(新增)
```

### 4.2 定位器抽象（`star_core/locators/base.py`）

```python
@dataclass
class ElementBox:
    """定位结果：命中元素的屏幕几何信息"""
    x: int
    y: int                    # 元素左上角(或点击锚点) 屏幕绝对坐标
    width: int
    height: int
    confidence: float         # 0~1，用于同链多命中排序
    source: str               # "uia" / "visual" / "ratio" / "cdp"
    meta: dict                # 调试信息（控件名、AutomationId、selector 等）

class Locator(ABC):
    name: str                 # "uia" / "visual" / "ratio" / "cdp"

    @abstractmethod
    def find(self, target: LocatorTarget, ctx: WindowContext) -> ElementBox | None:
        """在窗口/页面上下文中定位目标元素"""

@dataclass
class LocatorTarget:
    """一次定位请求：找什么"""
    kind: str                 # "input" / "send_button" / "stop_button" / ...
    uia: UIAQuery | None
    visual: VisualQuery | None
    ratio: RatioQuery | None
    cdp: CDPQuery | None

class LocatorChain:
    """按配置顺序执行定位器，返回第一个命中"""
    def __init__(self, targets: dict[str, LocatorTarget], locators: list[Locator]):
        ...
    def locate(self, kind: str, ctx: WindowContext) -> ElementBox | None:
        for locator in self.locators:          # 按配置的 locators 优先级
            target = targets[kind]
            box = locator.find(target, ctx)
            if box and box.confidence >= ctx.min_confidence:
                return box
        return None
```

**降级语义**：链上某定位器异常（控件树不可用、OCR 超时）→ 记 log → 直接进入下一个，不中断整个提交动作。

### 4.3 四种定位器实现

#### UIALocator（`uia.py`）— 优先级最高

```python
@dataclass
class UIAQuery:
    control_type: str | None      # Edit / Button / Document / ...
    automation_id: str | None     # 精确匹配
    name_regex: str | None        # Name 正则（如 "输入|Ask|Message"）
    ancestor: str | None          # 祖先路径约束（可选）
    depth_limit: int = 8
```

- 基于 `uiautomation` 库（已依赖），从 `hwnd` 根控件深度优先遍历
- **关键实践**：Electron/VS Code 系应用的控件树通常需首次 UIA 请求后激活；`Trae` 聊天输入框（Monaco 系）实测可能暴露为 `EditControl` 或 `DocumentControl` 下的子节点——这正是"先探测、后落库"要解决的，校准器负责实测
- 查找 Name 匹配时跳过空 Name，`ControlType` 优先；支持按控件文本精确点击（如"停止/Stop"按钮）

#### VisualLocator（`visual.py`）— 通用兜底

```python
@dataclass
class VisualQuery:
    hint_text: str | None         # OCR 占位文本（如 "输入" / "请输入"）
    template: str | None          # 模板图片路径（如 assets/trae_send.png）
    region: str = "full_window"   # 截取区域（复用 ocr_gazer 区域概念）
    ocr_min_confidence: float = 0.5
```

- 复用 `OCRGazer` 的截图与 OCR 能力（PaddleOCR，可选依赖，未装则跳过本定位器）
- **占位文本命中**：OCR 结果中查找 `hint_text` 命中的文本框中心 → 该框即为输入框锚点（下方若干像素为实际输入区）
- **模板匹配**：OpenCV `matchTemplate` 找 send/stop 图标
- 命中后点击位置 = 文本框中心，并做一次"点击后校验"（可选：截图对比焦点变化）

#### RatioLocator（`ratio.py`）— 最后兜底

- 原 `input_click_x_ratio/y_ratio` 逻辑迁移至此，零行为变化
- 返回 `confidence=0.3`（恒低于前两者，保证在同链中只做兜底）

#### CDPLocator（`cdp.py`）— 浏览器 agent

```python
@dataclass
class CDPQuery:
    selector: str | None          # DOM 选择器（如 "textarea[placeholder*='输入']"）
    text_contains: str | None     # 按可见文本找按钮
    role: str | None              # 可访问性 role（如 "textbox" / "button"）
```

- 依赖 `cdp_bridge.py` 提供的连接与执行能力，`find()` 返回 DOM 节点的**视口坐标 + 页面滚动偏移** → 换算屏幕坐标（复用窗口 rect）
- 注意：浏览器 agent 直接走 CDP 原生动作，`submit/stop` 不依赖坐标而是 DOM 事件，见 4.6

### 4.4 `interaction` 配置 Schema（ai-agents.yaml 扩展）

```yaml
agents:
  - id: trae
    name: Trae AI
    category: ide                     # ide = 桌面应用；browser = 网页应用
    process_names: [...]              # 沿用现有发现特征
    window_class: [...]
    title_patterns: [...]
    interaction:                      # ★ 新增段
      input:
        locators: [uia, visual, ratio]   # 定位器优先级链（最多 3 个）
        uia:
          control_type: Edit
          name_pattern: "输入|Ask|Message"
        visual:
          hint_text: "输入"
        ratio: {x: 0.5, y: 0.93}         # 兜底
        send_on: Enter                    # 提交触发：按键
        # send_on: click                  # 或：点击发送按钮
        # send_button:
        #   uia: {name_pattern: "发送|Send"}
        #   visual: {template: "assets/trae_send.png"}
      stop:
        primary: cancel_button            # 优先：点取消/停止按钮
        cancel_button:
          uia: {name_pattern: "停止|Stop|取消|Cancel"}
          visual: {hint_text: "停止|Stop"}
        fallback_keys: [Esc, Ctrl_C]      # 兜底按键序列
      output:
        - {type: log, paths: ["~/.trae-cn/log/**/*.log"]}
        - {type: ocr, region: center_chat}
        - {type: cdp, selector: ".markdown-body"}   # 仅 category=browser

  - id: browser_yiyan                   # ★ 浏览器网页 AI 示例（category=browser）
    name: 文心一言（管控浏览器）
    category: browser
    cdp: {url_pattern: "yiyan.baidu.com"}  # 标签页匹配
    browser: {profile: "star-control"}     # 管控浏览器用户目录
    interaction:
      input:
        locators: [cdp]
        cdp: {selector: "textarea.qq-input, textarea#textarea"}
        send_on: Enter
      stop:
        primary: cancel_button
        cancel_button: {cdp: {text_contains: "停止生成"}}
        fallback_keys: [Esc]
      output:
        - {type: cdp, selector: ".markdown-body, [class*='message-item']:last-child"}
```

**配置加载**：`config_service.py` 将 `interaction` 段解析为 `InteractionConfig` 数据类；缺失该段的旧 agent 自动回退到"纯 ratio"行为（零配置也可用，保持向后兼容）。

### 4.5 交互动作原语（`star_core/interaction.py`）

```python
class InteractionSession:
    """一个 agent 的一组交互能力，由 StarEmissary 持有"""
    def __init__(self, config: InteractionConfig, bridge: CDPBridge | None, ocr: OCRGazer):
        ...

    def submit(self, prompt: str, ctx: WindowContext) -> SubmitResult:
        """定位输入框 → 聚焦点击 → 注入文本 → 触发发送"""
        box = self.chain.locate("input", ctx)
        if box is None:
            return SubmitResult(ok=False, reason="input_locator_miss")
        self.click(box)                    # 桌面：win32 点击；浏览器：CDP focus
        self.type_text(prompt)             # 桌面：剪贴板+Ctrl+V（已有）；浏览器：CDP 设值+input 事件
        self.trigger_send(box)             # Enter 或点发送按钮
        return SubmitResult(ok=True, source=box.source)

    def stop_current(self, ctx: WindowContext) -> StopResult:
        """停止当前生成：按钮优先，键盘兜底，永不杀进程"""
        box = self.chain.locate("stop_button", ctx)
        if box: self.click(box); return StopResult(ok=True, via="button")
        for key in self.config.stop.fallback_keys:   # Esc → Ctrl+C
            self.press_key(key)
        return StopResult(ok=True, via="keys")

    def read_output(self, ctx: WindowContext) -> str:
        """输出读取链：log → ocr → cdp（与现有 _capture_output 融合）"""
```

桌面注入文本沿用现有 `_paste_text`（剪贴板 + Ctrl+V），因为对 Electron 文本框最稳；UIA `ValuePattern.SetValue()` 作为可选增强（对原生控件）。

### 4.6 管控浏览器与 CDP 桥（`star_core/cdp_bridge.py`）

**启动方式**（Windows）：

```powershell
# 预置 profile，避免与日常浏览器冲突
& "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe" `
    --remote-debugging-port=9222 `
    --user-data-dir="$env:USERPROFILE\.star\browser-profile" `
    --no-first-run --no-default-browser-check
```

- 端口 / profile 路径写入 `config.yaml` 新增段（`cdp: {port: 9222, profile: ...}`），首次自动创建桌面快捷方式"群星管控浏览器"
- **标签页枚举**：`GET http://127.0.0.1:9222/json` 列出全部 target，按 `url_pattern` 匹配为指定 agent 的实例
- **协议**：用已有 `websockets` 库连 `webSocketDebuggerUrl`，封装 `Runtime.evaluate`（设值、dispatch input 事件、读 innerText）与 `Input.dispatchMouseEvent`（点击）
- **断线重连**：CDP 连接断开 → 指数退避重连（1s/2s/4s，共 3 次）→ 仍失败则 agent 标记 `cdp_offline`，提交请求在 UI 明示不可用原因
- 同一浏览器多标签：一个标签页 = 一个 `StarBody`（`category=browser`），与桌面应用同池管理

### 4.7 停止当前生成（StarEmissary 新增 `stop_current()`）

| 场景 | 主路径 | 兜底 1 | 兜底 2 |
|---|---|---|---|
| 桌面应用 | UIA 点"停止/Stop"按钮 | 点击视觉识别的停止图标 | Esc → Ctrl+C 键盘序列 |
| 浏览器网页 AI | CDP 点"停止生成"按钮 | CDP 发 Esc | DOM 点击 aria 停止控件 |
| 均失败 | 返回失败原因，UI 提示手动处理 | — | — |

新增 REST：`POST /api/stars/{star_id}/stop`（`{action: "cancel_generation"}`），校验 agent 非空后调用 `emissary.stop_current()`。

### 4.8 定位器校准器（Web 页面）

**后端 API（`star_api/routes/locators.py`）**：

| 端点 | 功能 |
|---|---|
| `GET /api/locators/candidates` | 列出当前已发现的 agent 及其可用定位能力（uia 可用 / ocr 可用 / cdp 可用） |
| `GET /api/locators/{star_id}/inspect` | 返回窗口截图 base64 + 精简 UIA 树（名称/类型/automationId/坐标），页面渲染为可点选图层 |
| `POST /api/locators/{star_id}/probe` | 按临时定位参数试发测试文本，返回是否命中 + 命中元素信息 |
| `POST /api/locators/preview` | 输入定位参数 → 返回将要写入 yaml 的配置片段 |
| `POST /api/locators/apply` | 将配置写回 `config/ai-agents.yaml`（备份原文件）→ 热生效 |

**前端交互（calibrator.html）**：

1. 选 agent → 显示窗口截图 + UIA 树双视图
2. 在截图/UIA 树上**点选**输入框 → 右侧自动填充 `uia`/`visual` 候选参数
3. 分别标定：输入框 / 发送按钮（可选）/ 停止按钮 / 输出区域
4. "试发测试"验链 → "生成配置" → "应用并生效"
5. 应用后跳转星图页实测提交一次完整任务

**安全**：配置写回前备份 `ai-agents.yaml.bak`；apply 接口复用现有 auth 机制（admin 角色）。

### 4.9 与现有代码的衔接

- `StarEmissary.__init__` 增加 `interaction=InteractionSession(...)`；`send_prompt` 内 `_click_input_area` 替换为 `interaction.submit` 的定位+聚焦部分（保留 `_paste_text/_press_enter` 复用）
- `wait_for_response` 的 `_capture_output` 沿用：LogReader 优先，OCR 兜底；浏览器 agent 额外尝试 CDP 读输出
- `StarBody` 模型扩展 `category: str = "ide"` 与 `cdp_info` 字段；`star_seeker` 扫描时对 `category=browser` 的配置走 CDP 枚举生成实例
- `PRESET_ADAPTERS` 逐步迁移到 yaml（Python 侧保留 generic/trae 作为最小兜底，避免删旧配置导致回归）

## 5. 错误处理

| 错误场景 | 处理 |
|---|---|
| 定位器全链未命中输入框 | 返回 `input_locator_miss`，UI 引导打开校准器标定；绝不猜测坐标继续点击 |
| UIA 控件树异常 | 捕获后跳过，进入 visual 定位器 |
| OCR 未安装 / 模板缺失 | visual 定位器标记不可用，跳过 |
| CDP 端口未开 / 断线 | agent 标记 `cdp_offline`，提交/停止请求返回明确错误，UI 显示修复指引（启动管控浏览器） |
| 停止失败（按钮与按键均无效） | 返回失败原因，**不杀进程**，UI 提示手动处理 |
| yaml 配置损坏 | 加载 fallback 到内置默认（纯 ratio + log 输出），日志告警 |

## 6. 测试计划

| 层级 | 内容 |
|---|---|
| 单元测试 | `LocatorChain` 优先级与降级逻辑（mock 各 locator 返回值）；配置解析（含缺失段回退）；`RatioLocator` 与旧行为一致性 |
| mock 集成 | 用测试窗口（`uiautomation` 可创建的控制）验证 UIA 定位器点击；CDP 用本地临时 HTML 页验证 DOM 提交/读取 |
| 校准流程 | 脚本化测试：inspect → 选点 → preview → apply → 热生效（对 Trae 实测一轮） |
| 回归 | 现有 `tests/` 全量通过；旧配置 agent（无 interaction 段）行为不变 |

## 7. 兼容性与迁移

- **向后兼容**：无 `interaction` 段的 agent 自动使用 `RatioLocator + log 输出`，与 v3 行为完全一致
- **配置迁移路径**：`PRESET_ADAPTERS` 中的 trae/generic 保留为内置兜底；同一 agent 以 yaml `interaction` 优先
- **浏览器 agent**：新概念，不影响既有桌面 agent 任何行为
- **文件级改动**：全部为新增模块 + 少量改造，不动 `log_reader`/`ocr_gazer`/`orbit_engine` 等稳定模块

## 8. 实施阶段建议

| 阶段 | 内容 | 验收 |
|---|---|---|
| P0 | locators 基础 + ratio 迁移 + interaction.py + emissary 接入（纯桌面，无新 UI） | 现有能力零回归，Trae 试提一轮成功 |
| P1 | 校准器 API + 前端页面；Trae/DuMate 实测落库 | 浏览器内点选标定 Trae 输入框并提交成功 |
| P2 | CDP 桥 + 管控浏览器 + 浏览器 agent 条目 | 文心一言网页提交与输出读取成功 |
| P3 | 停止功能全场景（桌面+浏览器）、错误处理强化、测试补全 | 全量测试通过，文档更新 |