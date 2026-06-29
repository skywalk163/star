# 架构设计

本文档详细描述群星（Star）调度中心的技术架构与核心模块设计。

## 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                    表示层 (Presentation)                 │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐    │
│  │  Web UI     │  │  Desktop    │  │  CLI / SDK   │    │
│  │  (React)    │  │  (Electron) │  │  (Python)    │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘    │
└─────────┼────────────────┼────────────────┼────────────┘
          │                │                │
          └────────────────┼────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   接口层 (API Layer)                     │
│  ┌───────────────────────────────────────────────────┐  │
│  │                  FastAPI                           │  │
│  │  REST Routes  │  WebSocket  │  事件广播          │  │
│  └───────────────────────┬───────────────────────────┘  │
└──────────────────────────┼──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   核心层 (Core Layer)                    │
│                                                          │
│  ┌──────────────┐     ┌──────────────┐                 │
│  │  StarSeeker  │     │ OrbitEngine  │                 │
│  │  寻星者       │     │  星轨引擎     │                 │
│  └──────┬───────┘     └──────┬───────┘                 │
│         │                    │                          │
│  ┌──────▼───────┐     ┌──────▼───────┐                 │
│  │ StarAssigner │     │  StarGazer   │                 │
│  │  授星者       │     │  观星者       │                 │
│  └──────┬───────┘     └──────┬───────┘                 │
│         │                    │                          │
└─────────┼────────────────────┼──────────────────────────┘
          │                    │
          └─────────┬──────────┘
                    ▼
┌─────────────────────────────────────────────────────────┐
│              系统接入层 (System Access)                   │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Observatory (观星台)                   │  │
│  │  Win32 API │ UIAutomation │ 输入模拟 │ 剪贴板     │  │
│  └───────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────┐
│              目标层 (Target Layer)                        │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐              │
│  │ Trae │  │Cursor│  │ Atom │  │Copilot│  ...        │
│  │  ☆   │  │  ☆   │  │  ☆   │  │  ☆   │              │
│  └──────┘  └──────┘  └──────┘  └──────┘              │
└─────────────────────────────────────────────────────────┘
```

## 核心模块

### 1. Observatory（观星台）

**职责**：封装所有 Windows 系统级 API 调用，为上层提供统一的系统访问接口。

**位置**：`star_core/observatory.py`

**核心能力**：

| 能力分类 | 功能 |
|----------|------|
| 窗口管理 | 查找窗口、获取信息、置前、获取矩形 |
| 进程管理 | 按名查找、状态检查、PID 解析 |
| 文本输入 | UIA 控件设置、SendMessage、SendInput、剪贴板 |
| 文本读取 | UIA 控件读取、窗口标题、剪贴板 |
| 坐标转换 | 屏幕/客户区坐标互转 |

**设计原则**：
- 所有系统调用集中管理，便于维护
- 提供统一的异常处理
- 支持多种实现策略（UIA、消息、API）

### 2. StarSeeker（寻星者）

**职责**：发现并管理系统中的 AI Agent 进程。

**位置**：`star_core/star_seeker.py`

**核心流程**：

```
scan_skies()
    │
    ├─ 遍历 STAR_SIGNATURES
    │
    ├─ 按进程名查找进程 (psutil)
    │
    ├─ 按 PID 查找主窗口 (Observatory)
    │
    └─ 创建 StarBody 实例并缓存
```

**星体签名（STAR_SIGNATURES）**：

每个星体类型定义了识别特征：

```python
{
    'process_names': ['Trae.exe'],        # 进程名匹配
    'window_class': ['Chrome_WidgetWin_1'],  # 窗口类名
    'window_title_patterns': ['Trae'],     # 标题关键词
    'description': '...'
}
```

**缓存机制**：
- 首次扫描结果缓存
- 后续验证有效性（进程是否仍在运行）
- 支持 `force=True` 强制重新扫描

### 3. StarAssigner（授星者）

**职责**：向目标 Agent 发送指令文本。

**位置**：`star_core/star_assigner.py`

**注入策略链**：

```
UIA  ──失败──▶  剪贴板  ──失败──▶  窗口消息  ──失败──▶  Win32  ──失败──▶ 返回 False
  │              │                 │                │
  └─成功─────────┴─────────────────┴────────────────┘
```

**策略对比**：

| 策略 | 精度 | 速度 | 兼容性 | 风险 |
|------|------|------|--------|------|
| UIA | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | 低 |
| 剪贴板 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 中（干扰用户剪贴板） |
| 窗口消息 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | 低 |
| Win32 SendInput | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | 高（需要前台窗口） |

**剪贴板安全**：
- 注入前备份原内容
- 注入后恢复原内容
- 使用 `finally` 确保恢复

### 4. StarGazer（观星者）

**职责**：监控 Agent 输出，提取对话内容。

**位置**：`star_core/star_gazer.py`

**监控方式**：

1. **轮询模式**：定期读取输出区域内容
2. **增量检测**：与上次结果对比，只返回新增部分
3. **回调机制**：内容变化时触发注册的回调函数

**输出识别策略**：

```
尝试 TextBlock 控件 ──▶ 尝试 TextArea 控件 ──▶ 尝试 MonacoEditor
        │                       │                       │
        └────── 找到最长文本作为主输出 ◀───────────┘
```

**完成检测**：

基于启发式规则判断任务是否完成：
- 输出中包含完成关键词（完成、done、finished、✨ 等）
- 输出在多次采样内保持稳定（无新内容产生）
- 窗口标题中不包含"思考中"等状态词

### 5. OrbitEngine（星轨引擎）

**职责**：任务调度核心，管理任务生命周期。

**位置**：`star_core/orbit_engine.py`

**任务状态机**：

```
          诞生            入轨            闪耀
NASCENT ───────▶ ORBITING ───────▶ SHINING ───────┐
    │                                              │
    │ 取消                                   完成  │
    ▼                                              ▼
DARKENED                                 AWAITING_ECHO
    │                                              │
    │                                        回响  │
    │                                              ▼
    │                                       CONSTELLATED
    │
    └────── 失败 ───────▶ FADED
```

**智能路由算法**：

```
计算星轨 (_calculate_orbit)
    │
    ├─ 构建任务特征文本 (title + description)
    │
    ├─ 遍历 STAR_AFFINITY 亲缘性配置
    │   │
    │   └─ 关键词匹配计分
    │
    ├─ 过滤掉无可用星体的类型
    │
    └─ 返回得分最高的星体类型
```

**队列处理**：

```python
async def process_queue():
    while True:
        nova = await orbit_queue.get()      # 取出队首
        await launch_nova(nova.id)          # 尝试发射
```

**回调机制**：

- `on_nova_status_change`: 任务状态变化时触发
- `on_starlight_received`: 收到 Agent 输出时触发

## 数据模型

### StarBody（星体）

```python
@dataclass
class StarBody:
    star_type: str           # 星体类型
    pid: int                 # 进程 ID
    hwnd: int                # 主窗口句柄
    title: str               # 窗口标题
    process: psutil.Process  # 进程对象
    is_shining: bool         # 是否在处理任务
    last_activity: float     # 最后活跃时间
```

### Nova（新星/任务）

```python
@dataclass
class Nova:
    id: str                          # 唯一标识
    title: str                       # 标题
    description: str                 # 描述
    starlight: str                   # 发送给 Agent 的指令
    context_files: list[str]         # 上下文文件
    assigned_star: Optional[str]     # 分配的星体类型
    status: StarStatus               # 当前状态
    priority: StarPriority           # 优先级
    created_at: datetime             # 创建时间
    updated_at: datetime             # 更新时间
    result_starlight: Optional[str]  # Agent 返回结果
    starlight_log: list[dict]        # 对话历史
    echo: Optional[str]              # 用户反馈
    error: Optional[str]             # 错误信息
```

### Constellation（星座）

```python
@dataclass
class Constellation:
    id: str                    # 星座 ID
    name: str                  # 名称
    description: str           # 描述
    novas: list[Nova]          # 组成的新星列表
    status: str                # 整体状态
    created_at: datetime       # 创建时间
```

## 接口层架构

### REST API 设计

```
/api/stars/*          星体管理
/api/novas/*          任务管理
/api/constellations/* 星座协同
/api/stats            统计信息
```

### WebSocket 设计

- 单连接多路复用：通过 `type` 字段区分消息类型
- 服务端主动推送：状态变化、输出更新、星体变化
- 心跳机制：客户端发送 `ping`，服务端回复 `pong`

## 扩展性设计

### 新增星体类型

只需两步：
1. 在 `STAR_SIGNATURES` 添加识别特征
2. 在 `STAR_AFFINITY` 添加亲缘性关键词

### 新增注入策略

1. 继承现有模式，添加 `_try_xxx` 方法
2. 在 `AssignStrategy` 枚举中注册
3. 更新默认策略优先级

### 新增状态

1. 在 `StarStatus` 枚举中添加
2. 在状态机转换逻辑中处理
3. 更新 API 文档

## 性能考虑

| 方面 | 策略 |
|------|------|
| 进程扫描 | 缓存结果，避免频繁 psutil 调用 |
| 输出监控 | 可配置轮询间隔，默认 1s |
| 任务队列 | asyncio 异步队列，非阻塞 |
| WebSocket | 连接池管理，批量广播 |

## 安全考虑

- 剪贴板操作：备份/恢复机制，最小化干扰
- 输入模拟：只对指定窗口生效
- 权限管理：建议以普通用户运行，仅必要时提权
- API 安全：生产环境应启用认证（当前为开发模式）
