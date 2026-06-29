# 群星（Star）- AI Agent 调度中心

> **群星闪耀，各司其职。调度有序，光芒汇聚。**

多个 AI Agent 如同夜空中的群星，各自闪耀着独特的光芒。Star 调度中心就像星座的连线者，将这些独立的光芒串联成完整的图景，让每一颗星的输出都能汇聚成更强大的力量。

**Slogan：让每一个 AI Agent 都成为你的星座**

---

## 目录

- [项目概述](#项目概述)
- [核心功能](#核心功能)
- [术语映射](#术语映射)
- [技术架构](#技术架构)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [API 接口](#api-接口)
- [WebSocket 接口](#websocket-接口)
- [插件系统](#插件系统)
- [历史与统计](#历史与统计)
- [命令行工具](#命令行工具)
- [配置说明](#配置说明)
- [开发指南](#开发指南)
- [实现路线图](#实现路线图)

---

## 项目概述

群星（Star）是一个运行在 Windows 系统上的 AI Agent 统一调度平台。通过系统级 API（句柄、窗口消息、进程监控、UI Automation）实现对多个 AI 编程助手（Trae、CodeArts Atomcode、Cursor、Copilot 等）的统一调度与任务管理。

### 设计理念

- **星图（Agent 发现）**：自动检测正在运行的 AI Agent 进程
- **星轨（任务队列）**：创建、分配、修改、暂停、恢复任务
- **星语（对话监控）**：截获 Agent 的输入/输出流
- **星令（任务干预）**：向运行中的 Agent 注入新指令或修正方向
- **星辉（结果收集）**：汇总各 Agent 输出，统一展示

---

## 核心功能

### 1. 寻星者（StarSeeker）- Agent 发现

自动扫描系统进程，识别正在运行的 AI Agent：

- **支持的星体类型**：Trae、CodeArts Atomcode、Cursor、GitHub Copilot、Windsurf、Claude 等
- **识别方式**：进程名 + 窗口标题 + 窗口类名多重匹配
- **实时更新**：支持定时扫描和手动刷新
- **状态追踪**：空闲 / 闪耀中 状态管理

### 2. 授星者（StarAssigner）- 文本注入

通过多种策略向 Agent 发送指令：

| 策略 | 原理 | 适用场景 | 优先级 |
|------|------|----------|--------|
| **观星术 (UIA)** | UI Automation 精确定位输入框 | Chromium/Electron 应用 | ⭐⭐⭐ |
| **星光传递 (剪贴板)** | 剪贴板复制 + Ctrl+V 粘贴 | 通用可靠 | ⭐⭐ |
| **星波 (消息)** | SendMessage 发送字符消息 | 原生 Windows 控件 | ⭐ |
| **Win32 底层** | SendInput 键盘模拟 | 兜底方案 | - |

### 3. 观星者（StarGazer）- 输出捕获

监控 Agent 输出，实时提取对话内容：

- **多控件识别**：TextBlock、TextArea、Monaco Editor 等
- **增量检测**：只返回新增内容，减少重复
- **持续观星**：线程级异步监控，输出变化时触发回调
- **完成检测**：基于输出模式判断任务是否完成

### 4. 星轨引擎（OrbitEngine）- 任务调度

完整的任务生命周期管理：

- **新星诞生**：创建任务，自动路由到最合适的 Agent
- **智能路由**：基于关键词亲缘性匹配最优星体
- **队列管理**：异步任务队列，支持优先级调度
- **星轨调整**：运行中任务可修改指令方向
- **回响机制**：用户反馈驱动的迭代优化
- **星座协同**：多 Agent 协作完成复杂任务

---

## 术语映射

| 通用术语 | 群星（Star）术语 | 说明 |
|---------|-----------------|------|
| AI Agent | 星（Star） | 每个 Agent 是一颗星 |
| Agent 进程 | 星体（Star Body） | 运行中的 Agent 实例 |
| 任务队列 | 星轨（Orbit） | 任务的流转路径 |
| 新任务 | 新星（Nova） | 新创建的任务 |
| 任务分配 | 授星（Assign） | 将任务交给某颗星 |
| 任务修改 | 调轨（Adjust Orbit） | 修改运行中的任务方向 |
| 结果输出 | 星辉（Starlight） | Agent 的产出 |
| 用户反馈 | 回响（Echo） | 用户对 Agent 输出的回应 |
| 多 Agent 协同 | 星座（Constellation） | 多个星协同完成复杂任务 |

### 星芒状态（StarStatus）

| 状态 | 说明 |
|------|------|
| 🌑 NASCENT | 初生 - 新创建，等待入轨 |
| 🌒 ORBITING | 入轨 - 已分配，准备发射 |
| 💫 SHINING | 闪耀 - Agent 正在处理 |
| ⏳ AWAITING_ECHO | 待回响 - 等待用户审查 |
| ✨ CONSTELLATED | 成星 - 任务完成 |
| 🌑 FADED | 暗淡 - 执行失败 |
| ⚫ DARKENED | 熄灭 - 已取消 |

### 星等（StarPriority）

| 等级 | 名称 | 说明 |
|------|------|------|
| 3 | 超新星 (SUPERNOVA) | 紧急，最高优先级 |
| 2 | 亮星 (BRIGHT) | 高优先级 |
| 1 | 常星 (NORMAL) | 正常优先级（默认） |
| 0 | 暗星 (DIM) | 低优先级 |

---

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                     群星（Star）前端                          │
│   (Web UI: React + Vite, 或 Electron 桌面端)                 │
│   星图面板 │ 星轨队列 │ 星语流 │ 星辉审查                      │
└───────────────────────────┬─────────────────────────────────┘
                            │ WebSocket / IPC
┌───────────────────────────▼─────────────────────────────────┐
│                    星核（Star Core）- Python 3.12             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ 寻星者        │  │ 星轨引擎      │  │ 星语路由         │  │
│  │ StarSeeker   │  │ OrbitEngine  │  │ StarlightRouter │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│  ┌──────▼─────────────────▼────────────────────▼─────────┐  │
│  │              观星台（Observatory）                       │  │
│  │  · Win32 API (句柄/窗口/进程)                          │  │
│  │  · UI Automation (元素定位/文本注入)                   │  │
│  │  · 键盘/鼠标模拟 (SendInput/PostMessage)               │  │
│  │  · 剪贴板监控 (Clipboard API)                          │  │
│  └───────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────┘
                            │ 句柄 / UIA / 消息
┌───────────────────────────▼─────────────────────────────────┐
│                    群星闪耀（Agent 进程）                      │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐              │
│  │  Trae ☆  │  │CodeArts Atom☆│  │ Cursor ☆ │  ...         │
│  └──────────┘  └──────────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────────┘
```

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | **FastAPI** + **Uvicorn** | 异步高性能 Web 框架 |
| 核心引擎 | **Python 3.12** | 星核主语言 |
| Windows API | **pywin32** | Win32 API 封装 |
| UI Automation | **uiautomation** | Windows 界面自动化 |
| 进程管理 | **psutil** | 跨平台进程工具 |
| 输入模拟 | **pyautogui** | 键盘鼠标模拟 |
| 日志系统 | **loguru** | 结构化日志 |
| 数据校验 | **Pydantic v2** | 类型安全 |

---

## 快速开始

### 环境要求

- **操作系统**：Windows 10 / Windows 11
- **Python**：>= 3.12
- **权限**：建议以管理员权限运行（部分 UI Automation 功能需要）

### 安装

```bash
# 克隆项目
cd g:\traework\star

# 安装依赖（推荐使用虚拟环境）
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

### 启动服务

```bash
# 启动 API 服务
uvicorn star_api.main:app --reload --host 0.0.0.0 --port 8765

# 或直接运行
python -m uvicorn star_api.main:app --reload --port 8765
```

### 验证安装

打开浏览器访问：

- **API 文档**：http://localhost:8765/docs
- **健康检查**：http://localhost:8765/health

### 快速体验

```python
import asyncio
from star_core import OrbitEngine, Nova, StarPriority

async def main():
    engine = OrbitEngine()
    
    # 扫描星体
    stars = engine.star_seeker.scan_skies()
    print(f"发现 {len(stars)} 颗星")
    
    # 创建任务
    nova = Nova(
        id="",
        title="生成用户登录模块",
        description="用 Python 编写一个用户登录验证模块",
        starlight="请用 Python 实现一个用户登录模块，包含密码哈希验证和 JWT 令牌生成。",
        priority=StarPriority.NORMAL
    )
    
    nova_id = await engine.birth_nova(nova)
    print(f"新星诞生: {nova_id}")

asyncio.run(main())
```

---

## 项目结构

```
star/
├── star_core/                    # 星核（核心引擎）
│   ├── __init__.py              # 模块导出
│   ├── observatory.py           # 观星台 - Windows API 封装
│   ├── star_seeker.py           # 寻星者 - Agent 发现与注册
│   ├── star_assigner.py         # 授星者 - 文本注入
│   ├── star_gazer.py            # 观星者 - 输出捕获
│   ├── orbit_engine.py          # 星轨引擎 - 任务调度
│   ├── plugin_system.py         # 插件系统 - 可扩展架构
│   ├── analytics.py             # 统计分析 - 历史与多维统计
│   └── cli.py                   # 命令行工具入口
│
├── star_api/                     # 星光接口（后端 API）
│   ├── __init__.py
│   ├── main.py                  # FastAPI 入口 + WebSocket
│   ├── routes/
│   │   ├── stars.py             # 星体管理接口
│   │   ├── novas.py             # 新星（任务）接口
│   │   ├── constellations.py    # 星座（协同）接口
│   │   ├── history.py           # 历史与统计接口
│   │   └── plugins.py           # 插件管理接口
│   └── websocket/
│       └── __init__.py          # WebSocket 相关
│
├── star_plugins/                 # 插件目录
│   ├── __init__.py
│   ├── demo_star.py             # 自定义星体示例插件
│   └── demo_hook.py             # 任务钩子示例插件
│
├── examples/                     # 示例脚本
│   └── quickstart.py            # 快速入门示例
│
├── docs/                         # 文档目录
│   ├── architecture.md          # 架构设计文档
│   └── api-design.md            # API 设计文档
│
├── pyproject.toml               # 项目配置与依赖
└── README.md                    # 项目文档
```

---

## API 接口

### 星体管理（/api/stars）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/stars` | 列出所有已发现的星体 |
| GET | `/api/stars/types` | 列出支持的星体类型 |
| GET | `/api/stars/{pid}` | 获取指定星体详情 |
| POST | `/api/stars/{pid}/refresh` | 刷新星体信息 |
| GET | `/api/stars/idle` | 获取空闲星体 |

### 新星管理（/api/novas）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/novas` | 创建新任务（诞生新星） |
| GET | `/api/novas` | 列出所有任务 |
| GET | `/api/novas/{id}` | 获取任务详情 |
| POST | `/api/novas/{id}/launch` | 发射任务（分配给星体执行） |
| POST | `/api/novas/{id}/adjust` | 调整星轨（修改运行中任务） |
| POST | `/api/novas/{id}/echo` | 添加回响（用户反馈） |
| POST | `/api/novas/{id}/fade` | 标记失败（星光暗淡） |
| POST | `/api/novas/{id}/darken` | 取消任务（新星熄灭） |
| GET | `/api/novas/{id}/gaze` | 获取观星历史 |

### 星座管理（/api/constellations）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/constellations` | 创建星座（多星协同任务） |
| GET | `/api/constellations` | 列出所有星座 |
| GET | `/api/constellations/{id}` | 获取星座详情 |
| POST | `/api/constellations/{id}/launch` | 发射星座 |
| POST | `/api/constellations/{id}/compare` | 对比星座中各新星结果 |
| GET | `/api/constellations/{id}/novas/{nova_id}` | 获取星座中指定新星详情 |

### 插件管理（/api/plugins）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/plugins` | 列出所有插件 |
| GET | `/api/plugins/{name}` | 获取插件详情 |
| POST | `/api/plugins/{name}/load` | 加载插件 |
| POST | `/api/plugins/{name}/enable` | 启用插件 |
| POST | `/api/plugins/{name}/disable` | 禁用插件 |
| GET | `/api/plugins/types/available` | 获取插件类型列表 |

### 历史与统计（/api/history）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/history/novas` | 查询历史任务记录 |
| GET | `/api/history/novas/{id}` | 获取历史任务详情 |
| GET | `/api/history/overview` | 概览统计数据 |
| GET | `/api/history/by-star-type` | 按星体类型统计 |
| GET | `/api/history/daily` | 按日统计 |
| GET | `/api/history/hourly` | 按小时分布统计 |
| GET | `/api/history/by-priority` | 按优先级统计 |
| GET | `/api/history/top` | TOP 任务排行 |
| GET | `/api/history/report` | 完整统计报告 |

### 系统接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 根路径 - 服务信息 |
| GET | `/health` | 健康检查 |
| GET | `/api/stats` | 调度统计 |

---

## WebSocket 接口

### 连接地址

```
ws://localhost:8765/ws/starlight
```

### 消息类型

| 类型 | 说明 | 数据结构 |
|------|------|----------|
| `connected` | 连接成功 | `{ stats }` |
| `stars_updated` | 星体列表更新 | `{ stars: [...] }` |
| `nova_status_change` | 任务状态变化 | `{ id, status, title, updated_at }` |
| `starlight_received` | 收到星辉输出 | `{ nova_id, content, timestamp }` |
| `constellation_status_change` | 星座状态变化 | `{ id, name, status, completed_count, shining_count, total_novas }` |
| `constellation_complete` | 星座完成 | `{ id, name, status, completed_novas }` |

### 客户端示例

```javascript
const ws = new WebSocket('ws://localhost:8765/ws/starlight');

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    
    switch (msg.type) {
        case 'stars_updated':
            console.log('星体更新:', msg.data);
            break;
        case 'nova_status_change':
            console.log('任务状态变化:', msg.data);
            break;
        case 'starlight_received':
            console.log('收到星辉:', msg.data);
            break;
    }
};

// 心跳
setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
    }
}, 30000);
```

---

## 插件系统

群星支持通过插件扩展功能，包括自定义星体、注入策略、观星策略、任务钩子和扩展功能。

### 插件类型

| 类型 | 基类 | 说明 |
|------|------|------|
| `star` | `StarPlugin` | 自定义星体类型，扩展 Agent 发现能力 |
| `injector` | `InjectorPlugin` | 自定义文本注入策略 |
| `gazer` | `GazerPlugin` | 自定义输出观察策略 |
| `hook` | `HookPlugin` | 任务生命周期钩子 |
| `extension` | `ExtensionPlugin` | 通用扩展功能 |

### 插件目录结构

```
star_plugins/
├── __init__.py
├── demo_star.py        # 自定义星体示例
├── demo_hook.py        # 任务钩子示例
└── your_plugin.py      # 你的插件
```

### 编写自定义星体插件

```python
from star_core.plugin_system import StarPlugin

class MyAgentPlugin(StarPlugin):
    PLUGIN_NAME = "my_agent"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_AUTHOR = "Your Name"
    PLUGIN_DESCRIPTION = "我的自定义 Agent 支持"
    STAR_TYPE = "my_agent"
    
    PROCESS_NAMES = ["MyAgent.exe", "MyAgentApp.exe"]
    WINDOW_TITLE_PATTERNS = ["My Agent", "MyAgent"]
    WINDOW_CLASS_PATTERNS = ["Chrome_WidgetWin_1"]
    
    def get_star_signature(self) -> dict:
        return {
            "process_names": self.PROCESS_NAMES,
            "window_title_patterns": self.WINDOW_TITLE_PATTERNS,
            "window_class_patterns": self.WINDOW_CLASS_PATTERNS,
            "description": self.PLUGIN_DESCRIPTION,
            "affinity_keywords": ["custom", "my_agent"]
        }
```

### 编写任务钩子插件

```python
from star_core.plugin_system import HookPlugin, Nova, StarStatus

class LoggingHook(HookPlugin):
    PLUGIN_NAME = "logging_hook"
    PLUGIN_VERSION = "1.0.0"
    
    def on_nova_created(self, nova: Nova):
        print(f"[Hook] 新星诞生: {nova.title}")
    
    def on_nova_status_changed(self, nova: Nova, old_status: StarStatus):
        print(f"[Hook] {nova.title}: {old_status.value} -> {nova.status.value}")
    
    def on_nova_completed(self, nova: Nova):
        print(f"[Hook] 任务完成: {nova.title}")
```

### 插件管理 API

```python
from star_core.plugin_system import PluginManager

pm = PluginManager(plugin_dir="star_plugins")

# 发现插件
plugins = pm.discover_plugins()

# 加载插件
pm.load_plugin("demo_star")

# 启用/禁用
pm.enable_plugin("demo_star")
pm.disable_plugin("demo_star")

# 列出插件
all_plugins = pm.list_plugins()
```

---

## 历史与统计

### 历史记录

所有执行过的任务都会自动保存到历史记录中，支持多维度查询。

```python
from star_core.analytics import HistoryStore

store = HistoryStore()

# 查询历史
records = store.query_novas(
    status="constellated",      # 按状态过滤
    star_type="trae",           # 按星体类型
    limit=50,                   # 数量限制
    offset=0                    # 分页偏移
)

# 获取详情
detail = store.get_nova_detail("nova_id_here")

# 统计数量
count = store.get_nova_count(status="constellated")
```

### 统计分析

多维统计分析功能，提供概览、分布和趋势数据。

```python
from star_core.analytics import HistoryStore, StarAnalytics

store = HistoryStore()
analytics = StarAnalytics(store)

# 概览统计
overview = analytics.get_overview_stats()
# { total_novas, completed, failed, cancelled, success_rate, avg_duration }

# 按星体类型统计
by_star = analytics.get_star_type_stats()

# 每日统计（近30天）
daily = analytics.get_daily_stats(days=30)

# 24小时分布
hourly = analytics.get_hourly_stats()

# 按优先级统计
by_prio = analytics.get_priority_stats()

# TOP 排行
top_duration = analytics.get_top_novas(by="duration", limit=10)
top_output = analytics.get_top_novas(by="output_length", limit=10)

# 完整报告
report = analytics.generate_report()
```

### 数据持久化

历史数据存储在 SQLite 数据库中：
- 默认位置：`data/history.db`
- 星座历史：`data/constellations.db`
- 可通过 `db_path` 参数自定义路径

---

## 命令行工具

安装后可以直接使用 `star` 命令行工具。

### 安装 CLI

```bash
pip install -e .

# 验证安装
star info
```

### 常用命令

```bash
# 扫描当前运行的 AI Agent
star scan

# 列出支持的星体类型
star types

# 管理插件
star plugins

# 查看统计信息
star stats

# 查看历史记录
star history --limit 20

# 启动 API 服务
star server --port 8765

# 显示版本信息
star info
```

### 服务命令

```bash
# 启动服务（默认端口 8765）
star server

# 指定端口和热重载
star server --host 0.0.0.0 --port 8765 --reload
```

---

## 配置说明

### 星体签名配置

在 `StarSeeker.STAR_SIGNATURES` 中定义了支持的星体类型。如需添加自定义星体：

```python
from star_core import StarSeeker

seeker = StarSeeker()
seeker.STAR_SIGNATURES['my_agent'] = {
    'process_names': ['MyAgent.exe'],
    'window_class': ['Chrome_WidgetWin_1'],
    'window_title_patterns': ['My Agent'],
    'description': '我的自定义 Agent'
}
```

### 注入策略配置

默认注入策略优先级：UIA → 剪贴板 → 窗口消息 → Win32

```python
from star_core import StarAssigner, AssignStrategy

assigner = StarAssigner()
# 自定义策略顺序
success = assigner.send_starlight(
    star=my_star,
    starlight="你好，请帮我...",
    strategy_priority=[
        AssignStrategy.CLIPBOARD,  # 优先用剪贴板
        AssignStrategy.UIA,
    ]
)
```

### 观星参数

```python
from star_core import StarGazer

gazer = StarGazer()

# 自定义轮询间隔
stop_event = gazer.continuous_gaze(
    star=my_star,
    on_starlight_change=my_callback,
    poll_interval=0.5  # 0.5 秒轮询一次
)
```

---

## 开发指南

### 代码规范

- Python 代码遵循 PEP 8 规范
- 类型注解使用 Python 3.12+ 语法
- 行长度限制：100 字符
- 使用 Ruff 进行代码风格检查

```bash
# 代码检查
ruff check star_core star_api

# 类型检查
mypy star_core
```

### 测试

```bash
# 运行测试
pytest

# 带覆盖率
pytest --cov=star_core --cov=star_api
```

### 添加新星体类型

1. 在 `StarSeeker.STAR_SIGNATURES` 中添加签名
2. 在 `OrbitEngine.STAR_AFFINITY` 中添加亲缘性关键词
3. 更新 API 文档

### 核心类关系

```
StarSeeker ──发现──▶ StarBody
    │
    └── 管理 ──┐
                ▼
OrbitEngine ──操作──▶ Nova
    │
    ├── 使用 ──▶ StarAssigner ──注入──▶ StarBody
    │
    └── 使用 ──▶ StarGazer ──观察──▶ StarBody
```

---

## 实现路线图（星图里程碑）

| 阶段 | 里程碑 | 状态 | 内容 |
|------|--------|------|------|
| 🌑 朔月 | **星核初现** | ✅ 完成 | 进程发现、窗口句柄获取、核心 API |
| 🌒 娥眉 | **星光通联** | ✅ 完成 | UI Automation 文本注入/读取 |
| 🌓 上弦 | **星轨流转** | ✅ 完成 | 任务队列、状态管理、星轨引擎 |
| 🌔 盈凸 | **星语交响** | ✅ 完成 | WebSocket 实时推送、对话监控 |
| 🌕 满月 | **群星闪耀** | ✅ 完成 | 多星协同（星座）、结果对比 |
| 🌖 亏凸 | **星图完善** | ✅ 完成 | 插件系统、自定义星体 |
| 🌗 下弦 | **星辉永驻** | ✅ 完成 | 历史记录、统计分析 |
| 🌘 残月 | **星辰大海** | ✅ 完成 | 正式发布、文档完善 |

---

## 颜色系统

- **主色调**：深空蓝黑（`#0a0e27` 背景，`#1a1f3a` 面板）
- **强调色**：星光金（`#ffd700`）
- **星等色**：
  - 超新星：炽白（`#ffffff`）
  - 亮星：亮蓝（`#4fc3f7`）
  - 常星：银白（`#b0bec5`）
  - 暗星：暗灰（`#616161`）
- **星芒色**：
  - 闪耀中：翠绿（`#66bb6a`）
  - 待回响：琥珀（`#ffa726`）
  - 暗淡：赤红（`#ef5350`）

---

## 许可证

MIT License

---

## 星语（日志）

项目使用 loguru 进行日志管理，日志格式：

```
⭐ {时间} | {级别} | {消息}
```

关键事件日志：

- `🌟 新星诞生 | ID: xxx | 目标星: xxx`
- `💫 星光闪耀 | 任务: xxx | 星: xxx`
- `✨ 星座完成 | 任务: xxx`
- `🌑 星光暗淡 | 任务: xxx | 原因: xxx`

---

> "群星闪耀，各司其职。调度有序，光芒汇聚。"
