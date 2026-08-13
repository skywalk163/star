# 群星 v4 混合定位器交互架构 实现计划

> **面向 AI 代理的工作者：** 本计划按并行子代理模式执行。计划内所有接口契约为硬约定，各子代理独立开发、最后统一整合联调。步骤使用复选框（`- [ ]`）语法跟踪。

**目标：** 将 Star 的"提交任务"从坐标比例点击升级为混合定位器架构（UIA→视觉→坐标 桌面链 + CDP 浏览器链），配套 Web 校准器与停止当前生成能力。

**架构：** 新增 `star_core/locators/` 定位器包（`Locator` 抽象 + `LocatorChain` 降级链），新增 `interaction.py` 动作原语，`StarEmissary` 接入；新增 `cdp_bridge.py` 管理浏览器 CDP 连接；新增校准器 API + 前端页面。全部交互特征由 `config/ai-agents.yaml` 的 `interaction` 段配置驱动。

**技术栈：** Python 3.13（`.venv` 已重建）、FastAPI、uiautomation、pywin32、websockets、PyYAML、现有 OCRGazer/LogReader。

**设计规格：** `docs/superpowers/specs/2026-08-13-hybrid-locator-design.md`

---

## 并行任务划分（Wave 1：4 个子代理并行，文件零冲突）

| Agent | 任务 | 负责文件 | 依赖 |
|---|---|---|---|
| A | locators 基础包 | `star_core/locators/*`（base/uia/visual/ratio） | 无（可先行） |
| B | CDP 桥 | `star_core/cdp_bridge.py`、`star_core/locators/cdp.py`、`scripts/launch_control_browser.ps1`、`config.yaml` | 无（可先行） |
| C | interaction + emissary 接入 + 停止 | `star_core/config_service.py`、`star_core/interaction.py`、`star_emissary.py`、`star_api/routes/stars.py`、`config/ai-agents.yaml` | A 的接口契约（计划内定义，可并行写码） |
| D | 校准器 API + 前端 | `star_api/routes/locators.py`、`star_api/main.py`、`star-ui/pages/calibrator.html`、`star-ui/js/calibrator.js`、`star-ui/js/nav.js` | A/C 接口契约（前端可 mock 先行） |

整合顺序：A、B 完成 → C、D 联调（C 需 locators 可 import、D 需 locators+emissary 可 import）→ 全量测试 → 提交。

---

## 全局接口契约（所有子代理必须遵守，禁止改名）

```python
# ===== locators/base.py =====
@dataclass
class ElementBox:
    x: int; y: int; width: int; height: int
    confidence: float; source: str; meta: dict

@dataclass
class UIAQuery:
    control_type: str | None = None      # "Edit" / "Button" / "Document" / "Text" / None=任意
    automation_id: str | None = None
    name_regex: str | None = None
    depth_limit: int = 8

@dataclass
class VisualQuery:
    hint_text: str | None = None
    template: str | None = None          # 相对 star 项目根的图片路径
    region: str = "full_window"
    ocr_min_confidence: float = 0.5

@dataclass
class RatioQuery:
    x_ratio: float = 0.5; y_ratio: float = 0.92

@dataclass
class CDPQuery:
    selector: str | None = None
    text_contains: str | None = None
    role: str | None = None

@dataclass
class LocatorTarget:
    kind: str                            # "input" / "send_button" / "stop_button"
    uia: UIAQuery | None = None
    visual: VisualQuery | None = None
    ratio: RatioQuery | None = None
    cdp: CDPQuery | None = None

class Locator(ABC):
    name: str                            # "uia" / "visual" / "ratio" / "cdp"
    def find(self, target: LocatorTarget, ctx: WindowContext) -> ElementBox | None: ...

@dataclass
class WindowContext:
    hwnd: int | None
    star: StarBody | None
    cdptab: dict | None = None           # {"ws": WebSocket, "page_url": str, "viewport": {...}}
    min_confidence: float = 0.3

class LocatorChain:
    def __init__(self, targets: dict[str, LocatorTarget], order: list[str],
                 registry: dict[str, Locator]): ...
    def locate(self, kind: str, ctx: WindowContext) -> ElementBox | None: ...
    def available(self) -> list[str]: ...

# 工厂（locators/__init__.py）
def create_locator(name: str) -> Locator | None: ...      # 按名称实例化（lazy import）
def default_registry() -> dict[str, Locator]: ...
```

```python
# ===== cdp_bridge.py =====
class CDPBridge:
    def __init__(self, port: int = 9222): ...
    def is_alive(self) -> bool: ...
    def list_tabs(self) -> list[dict]: ...        # [{id,title,url,ws}]
    def find_tab(self, url_pattern: str) -> dict | None: ...
    def evaluate(self, tab: dict, expr: str) -> Any: ...
    def set_value(self, tab: dict, sel: str, text: str) -> bool: ...   # 设值 + dispatch input 事件
    def click_selector(self, tab: dict, sel: str) -> bool: ...
    def get_text(self, tab: dict, sel: str) -> str: ...
    def get_element_rect(self, tab: dict, sel: str) -> dict | None: ...  # {x,y,width,height} 视口坐标
    def send_key(self, tab: dict, key: str) -> bool: ...  # "Enter" / "Escape"
    def find_by_text(self, tab: dict, text: str) -> dict | None: ...  # 返回可选择器或 None
```

```python
# ===== interaction.py =====
@dataclass
class InteractionConfig:        # 解析自 yaml interaction 段
    locators: list[str]                       # 如 ["uia","visual","ratio"]
    input: LocatorTarget; send_on: str        # "Enter" / "click"
    send_button: LocatorTarget | None
    stop: LocatorTarget | None
    stop_fallback_keys: list[str]             # 如 ["Esc","Ctrl_C"]
    output: list[dict]                        # [{type:"log",paths:[...]}, {type:"ocr",region:...}, {type:"cdp",selector:...}]

class InteractionSession:
    def __init__(self, config: InteractionConfig | None, bridge: CDPBridge | None, ocr: OCRGazer | None): ...
    def submit(self, prompt: str, ctx: WindowContext) -> SubmitResult: ...
    def stop_current(self, ctx: WindowContext) -> StopResult: ...
    def read_output(self, ctx: WindowContext) -> str: ...

@dataclass
class SubmitResult: ok: bool; source: str = ""; reason: str = ""
@dataclass
class StopResult: ok: bool; via: str = ""; reason: str = ""
```

```python
# ===== config_service.py 扩展（Agent C 实现） =====
def get_interaction_config(self, agent_id: str) -> InteractionConfig | None: ...

# ===== StarEmissary 扩展（Agent C 实现） =====
# __init__ 增参：interaction: InteractionSession | None = None
def stop_current(self) -> bool: ...           # 包装 interaction.stop_current + 状态更新
# send_prompt 内部：点按改用 interaction.submit 的定位结果（保留剪贴板注入逻辑）

# ===== stars.py 路由（Agent C 实现） =====
@router.post("/{star_id}/stop")
async def stop_current_generation(star_id: str): ...   # {action:"cancel_generation"} → {"ok":bool,"via":str}

# ===== locators.py 校准器 API（Agent D 实现） =====
@router.get("/candidates")
@router.get("/{star_id}/inspect")        # 截图 base64 + 精简 UIA 树
@router.post("/{star_id}/probe")         # 试发测试
@router.post("/preview")                 # 返回 yaml 片段
@router.post("/apply")                   # 写回 ai-agents.yaml（先备份）
```

---

## Task A：locators 基础包（Agent A）

**文件：**
- 创建：`star_core/locators/__init__.py`、`base.py`、`uia.py`、`visual.py`、`ratio.py`
- 测试：`tests/test_locators.py`

- [ ] **A1：编写 base.py（Locator/ElementBox/各类 Query/LocatorTarget/LocatorChain/WindowContext）**，遵循上方接口契约，`WindowContext` 与 `StarBody` 的 import 用 `TYPE_CHECKING` 避免循环依赖；`locate()` 按 order 顺序调用 registry 中的 locator，`confidence < min_confidence` 视为未命中，任一 locator 抛异常记 log 后继续下一个
- [ ] **A2：编写 ratio.py**（`RatioLocator`，`confidence=0.3` 恒值，通过 `WindowContext.star.hwnd` 取窗口 rect 计算绝对坐标，参考 `star_emissary._click_input_area` 的 rect 读取方式）
- [ ] **A3：编写 uia.py**（`UIALocator`，lazy import `uiautomation`；从 `ctx.star.hwnd` 根控件按 `ControlTypeSearchDepth=depth_limit` 遍历；Name 匹配用 `re.search`；返回首个命中元素的 `BoundingRectangle` 屏幕坐标；控件树异常返 None 不抛出）
- [ ] **A4：编写 visual.py**（`VisualLocator`，lazy import OCRGazer 与 PIL；hint_text 模式：对窗口截图 → OCRGazer 文本行 → 找含 hint_text 的行 → 返回其文本框中心为 input 锚点；OCR 不可用返 None）
- [ ] **A5：编写 `__init__.py`**（`create_locator(name)` 按 "uia"/"visual"/"ratio" 映射并 lazy import；`default_registry()` 返回实例字典）
- [ ] **A6：编写 tests/test_locators.py**：用假 `WindowContext`（hwnd=None 或假值）+ monkeypatch 定位器，验证 LocatorChain 的降级顺序（uia miss → visual miss → ratio 命中）、confidence 过滤、异常隔离；RatioLocator 坐标换算单测
- [ ] **A7：运行 `./.venv/Scripts/python.exe -m pytest tests/test_locators.py -v` 全绿**
- [ ] **A8：Commit**（`git add star_core/locators/ tests/test_locators.py && git commit -m "feat: locators 定位器基础包（UIA/视觉/坐标链式降级）"`）

## Task B：CDP 桥（Agent B）

**文件：**
- 创建：`star_core/cdp_bridge.py`、`star_core/locators/cdp.py`、`scripts/launch_control_browser.ps1`
- 修改：`config.yaml`（新增 `cdp: {port: 9222, profile: "~/.star/browser-profile", url_pattern: ""}` 段）
- 测试：`tests/test_cdp_bridge.py`

- [ ] **B1：编写 cdp_bridge.py**：`CDPBridge` 按上方契约；用 `urllib.request` 访问 `http://127.0.0.1:{port}/json` 枚举 tabs（各 tab 含 `webSocketDebuggerUrl`）；evaluate 用 `websockets` 异步封装（`asyncio.run` 包装同步接口），发送 `Runtime.evaluate` 并返回 `result.value`；`set_value` 执行 `el.value=...` + `el.dispatchEvent(new Event('input',{bubbles:true}))`；`get_element_rect` 用 `el.getBoundingClientRect()`；断线时 `is_alive()` 为 False，重连逻辑（指数退避 3 次）
- [ ] **B2：编写 locators/cdp.py**：`CDPLocator`（`name="cdp"`，`find()` 用 `ctx.cdptab` 调 bridge 的 `get_element_rect`/`find_by_text`，返回 ElementBox，source="cdp"，confidence=0.95；bridge 不可用返 None）
- [ ] **B3：在 `locators/__init__.py` 的 `create_locator` 增加 "cdp" 分支**（若 A 已完成该文件则 edit 追加；若不存在则按 A 的契约创建并只含 cdp）
- [ ] **B4：编写 scripts/launch_control_browser.ps1**：启动 Edge（优先 `$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe`，回退 Chrome）带 `--remote-debugging-port=9222 --user-data-dir=<profile> --no-first-run --no-default-browser-check`，若端口已被占用则直接复用
- [ ] **B5：编写 tests/test_cdp_bridge.py**：mock HTTP 响应与 websocket，验证 list_tabs 解析、find_tab 匹配 url_pattern、evaluate 消息构造、set_value 的 JS 片段正确性
- [ ] **B6：运行测试全绿**（`pytest tests/test_cdp_bridge.py -v`）
- [ ] **B7：Commit**

## Task C：interaction + emissary 接入 + 停止（Agent C）

**文件：**
- 创建：`star_core/interaction.py`
- 修改：`star_core/config_service.py`、`star_core/star_emissary.py`、`star_api/routes/stars.py`、`config/ai-agents.yaml`、`tests/test_star_emissary.py`（如需适配）
- 测试：`tests/test_interaction.py`

- [ ] **C1：config_service.py 扩展**：新增 `_interaction_configs: dict[str, InteractionConfig]`；`load()` 中解析各 agent 的 `interaction` 段（缺省 None）；新增 `get_interaction_config(agent_id)`；`InteractionConfig` 从 `star_core.interaction` import（延迟 import 防循环）
- [ ] **C2：编写 interaction.py**：`InteractionSession` 按契约；`submit()`：`chain.locate("input")` → 未命中返回 `ok=False, reason="input_locator_miss"` → 桌面（`ctx.cdptab is None`）用 win32 点击 + 剪贴板注入（复用现有逻辑：点击后在 `ctx.star.hwnd` 上 Ctrl+V 由 emissary 侧做，interaction 只返回 box 与聚焦动作）→ 触发 `send_on`（Enter 按键或点 send_button）；浏览器（`ctx.cdptab` 非空）用 bridge `set_value` + `send_key Enter` 或 `click_selector`；`stop_current()`：有 stop target → locate 并点击/执行 → 否则按 stop_fallback_keys 顺序按键；`read_output()`：按 output 链类型依次：log（调现有 `LogReader`）/ocr（`OCRGazer.gaze_region`）/cdp（bridge get_text）
  **注意**：为保持与 A 解耦，`locators` import 放函数内延迟执行；`WindowContext` 构造由调用方传入
- [ ] **C3：star_emissary.py 接入**：`__init__` 增加 `interaction: InteractionSession | None = None` 参数（None 时由 config_service 取 `get_interaction_config(self.star.star_type)` 构造，无 interaction 段则 None）；`send_prompt` 开头：若 `self.interaction` 存在 → 先 `chain.locate("input")` 得到 box 则按 box 点击（`_click_input_area` 增加可选 `box: ElementBox | None` 参数，优先用 box），保留剪贴板注入与回车逻辑不变；`stop_current()` 新增方法包装 interaction
- [ ] **C4：stars.py 新增 `POST /{star_id}/stop`**：按 design 文档，调用对应 emissary `stop_current()`（无 emissary 时按 `StarAssigner` 发 Esc 兜底并返回 `via:"keys"`）；返回 `{"ok": bool, "via": str, "reason": str}`
- [ ] **C5：config/ai-agents.yaml 增加 interaction 段**：为 `trae` 增加示例段（`input.locators=[uia,visual,ratio]`，uia 用 `control_type:Edit, name_pattern:"输入|Ask|Message"`，visual `hint_text:"输入"`，ratio 沿用现值；`send_on: Enter`；`stop.fallback_keys:[Esc]`）；为新增浏览器条目 `browser_yiyan`（`category: browser`、`cdp.url_pattern: "yiyan.baidu.com"`、interaction 全 cdp 定位）——浏览器条目的 process_names/window 特征留空（由 CDP 枚举）
- [ ] **C6：编写 tests/test_interaction.py**：mock LocatorChain 与 bridge，验证 submit 各分支（桌面命中/未命中/浏览器）、stop 按钮优先与按键兜底、read_output 链顺序；跑现有 `tests/test_star_emissary.py` 确认无回归
- [ ] **C7：全量 `pytest tests/ -v` 通过（或仅新增/受影响的失败，记录并说明）**
- [ ] **C8：Commit**

## Task D：校准器 API + 前端（Agent D）

**文件：**
- 创建：`star_api/routes/locators.py`、`star-ui/pages/calibrator.html`、`star-ui/js/calibrator.js`、`star-ui/js/pages/`（如需要）
- 修改：`star_api/main.py`、`star-ui/js/nav.js`

- [ ] **D1：编写 star_api/routes/locators.py**：
  - `GET /api/locators/candidates`：遍历 `state` 中发现的 stars，返回 `[{star_id, star_type, title, capabilities:{uia,visual,cdp}}]`（capabilities 用探测函数判断：能取到控件树=uia、OCR 可用=visual、`category.browser`=cdp）
  - `GET /api/locators/{star_id}/inspect`：返回 `{screenshot_b64, uia_tree: [{name, control_type, automation_id, rect, depth}]（最多 80 节点）}`
  - `POST /api/locators/{star_id}/probe`：body `{prompt, input_params}` → 构造临时 LocatorTarget 实测定位 + 试发，返回 `{hit: bool, source, box, error}`
  - `POST /api/locators/preview`：body 为定位参数 → 返回将要写入 yaml 的 interaction 片段（YAML 文本）
  - `POST /api/locators/apply`：body 完整 interaction 配置 + agent_id → 备份 `ai-agents.yaml` 为 `.bak` 后写回，重载 config_service，返回 `{ok}`
- [ ] **D2：main.py 挂载** `locators_router`（prefix `/api/locators`）
- [ ] **D3：校准器前端**（calibrator.html + calibrator.js）：参考 `star-ui/pages/remote.html` 风格；左列候选 agent 列表；中间截图 canvas + 点选后标记红框；右侧 UIA 树（可点击联动）；底部四个动作按钮：试发测试 / 生成配置 / 应用生效 / 清空；API 未就绪时以 mock 数据渲染 UI（`window.__MOCK__` 开关）
- [ ] **D4：nav.js 增加"校准器"入口**（参考现有导航项写法）
- [ ] **D5：语法自检**（`python -m py_compile star_api/routes/locators.py`）；前端 HTML/JS 无语法错误
- [ ] **D6：Commit**（若后端依赖 locators 未就绪导致 import 失败，注明"待 A/C 完成后联调"）

---

## Wave 2：整合联调（主协调人执行，非子代理）

- [ ] **I1：** 确认 A/B/C/D 四个 commit 均已合入、文件无冲突（`git status` 干净）
- [ ] **I2：** 安装 OCR 可选依赖（可选）：`pip install opencv-python Pillow`（PaddleOCR 体积大，若视觉定位需真机再装）
- [ ] **I3：** `pytest tests/ -v` 全量回归；修复跨模块接口失配
- [ ] **I4：** 启动服务 `./.venv/Scripts/python.exe -m uvicorn star_api.main:app --port 8765`，验证 `/api/locators/candidates`、`/api/stars`、`/api/locators/{star_id}/inspect` 可访问；无 Trae 运行时的降级行为正常
- [ ] **I5：** 前端 `calibrator.html` 通过静态检查（无 404 资源）
- [ ] **I6：** 真机实测（可选，需本机运行 Trae）：定位 → 试发 → 完整任务提交一次
- [ ] **I7：** 更新 README/architecture 文档（新增 locators 与校准器说明）；最终 Commit

---

## 验收标准（全部完成才可宣称 v4 交付）

1. `pytest tests/ -v` 全绿（新增 + 既有，既有失败需注明原因）
2. `/api/locators/candidates`、`/api/stars/{id}/stop`、`/api/locators/{id}/inspect` 可访问且返回结构正确
3. 桌面 agent（无 interaction 段的）行为与 v3 完全一致（坐标点击+日志读取，回归零变化）
4. Trae 实测：校准器可标定输入框 → 试发成功 → `stop` API 可停止当前生成
5. 浏览器 agent：CDP 桥可枚举 tabs、配置 url_pattern 后可定位提交（有浏览器时）
6. 所有配置项均有向后兼容默认值，无 `interaction` 段不报错