# 阶段 3 升级报告

> 版本：v3.0.0  
> 日期：2026-06-30 ~ 2026-07-01  
> 主题：前端工程化统一 · 插件化深度整合 · 可观测性完善

---

## 升级概述

阶段 3 升级围绕三大方向展开，全面提升项目的工程化水平、扩展能力和运行时可观测性：

1. **前端工程化统一** — 基于原生 JS 建立公共组件库、全局状态管理和事件总线
2. **插件化深度整合** — 完善插件生命周期管理、配置持久化和统一钩子分发系统
3. **可观测性完善** — 建立 Prometheus 风格指标体系，集成健康检查和请求监控

### 升级收益

| 维度 | 升级前 | 升级后 |
|------|--------|--------|
| 前端组件 | 分散实现，无统一规范 | Toast/Modal 统一组件，XSS 防护 + 无障碍支持 |
| 前端状态 | 无全局状态管理 | AppState - 命名空间 + 响应式 + 持久化 |
| 前端通信 | 零散事件绑定 | EventBus - 订阅发布 + 异常隔离 |
| 插件生命周期 | 仅 load/unload | enable/disable/configure + 启动自动加载 |
| 插件配置 | 内存存储，重启丢失 | 数据库持久化（plugin_configs 表） |
| 钩子系统 | 分散调用，无统一管理 | HookDispatcher - 12 个钩子点 + 线程安全 |
| 指标监控 | 无 | Counter/Gauge/Histogram + HTTP 请求指标 |
| 健康检查 | 简单 `/health` 返回 ok | 数据库 + 系统资源 + 可扩展检查框架 |
| 测试覆盖 | 130 个 | 303 个（+175） |

---

## 一、前端工程化统一

### 1.1 公共组件库

**文件：**
- `star-ui/js/components/toast.js` — Toast 提示组件
- `star-ui/js/components/modal.js` — Modal 弹窗组件
- `star-ui/css/components.css` — 组件样式（CSS 变量主题）

#### Toast 组件

支持 4 种类型：`success`、`error`、`warning`、`info`

```javascript
Toast.success('操作成功');
Toast.error('操作失败，请重试');
Toast.warning('请注意保存');
Toast.info('这是一条提示信息', 3000); // 自定义时长
```

**特性：**
- 自动消失（默认 3 秒）
- 防 XSS：使用 `UICommon.escapeHtml()` 转义消息
- 无障碍：`role="alert"`
- IIFE 模式，避免全局污染

#### Modal 组件

```javascript
// 普通弹窗
Modal.show({
    title: '提示',
    content: '这是弹窗内容',
    onClose: () => console.log('关闭了')
});

// 确认弹窗
Modal.confirm({
    title: '确认删除',
    content: '确定要删除这条记录吗？',
    onConfirm: () => console.log('确认删除'),
    onCancel: () => console.log('取消')
});

// 警告弹窗
Modal.alert('操作失败，请重试');
```

**特性：**
- 动画效果（淡入淡出 + 缩放）
- ESC 键关闭
- 点击遮罩关闭
- ARIA 属性（`role="dialog"`、`aria-modal`、`aria-labelledby`）
- 防 XSS：content 和 footer 自动转义

### 1.2 全局状态管理

**文件：** `star-ui/js/state.js`

`AppState` 提供全局状态管理，支持命名空间、响应式和本地持久化。

#### 基本操作

```javascript
// 设置状态
AppState.set('user.name', '张三');
AppState.set('settings.theme', 'dark');

// 获取状态
const name = AppState.get('user.name');
const theme = AppState.get('settings.theme', 'light'); // 带默认值

// 快捷操作
AppState.toggle('settings.darkMode');
AppState.increment('stats.visitCount');
AppState.increment('stats.score', 10);
```

#### 响应式订阅

```javascript
// 订阅状态变化
const unsubscribe = AppState.subscribe('settings.theme', (newValue, oldValue) => {
    console.log(`主题从 ${oldValue} 变为 ${newValue}`);
    document.body.dataset.theme = newValue;
});

// 取消订阅
unsubscribe();
```

#### 持久化

```javascript
// 标记需要持久化的键（自动保存到 localStorage）
AppState.persist('settings');
AppState.persist('user.preferences');

// 取消持久化
AppState.unpersist('settings');

// 重置所有状态
AppState.reset();
```

**特性：**
- 命名空间：点号分隔的键（如 `settings.theme`）
- 响应式：订阅/发布模式
- 持久化：localStorage 自动保存/恢复
- 快捷操作：`toggle()`、`increment()`

### 1.3 事件总线

**文件：** `star-ui/js/ui-common.js`（集成 UICommon.EventBus）

```javascript
// 订阅事件
const unsubscribe = UICommon.EventBus.on('nova.created', (data) => {
    console.log('新任务创建:', data);
});

// 发布事件
UICommon.EventBus.emit('nova.created', { id: 'nova_123', title: '任务标题' });

// 一次性订阅
UICommon.EventBus.once('plugin.loaded', (data) => {
    console.log('插件加载完成');
});

// 取消订阅
unsubscribe();
// 或按名称取消
UICommon.EventBus.off('nova.created', handler);

// 清空所有事件
UICommon.EventBus.clear();
```

**特性：**
- 异常隔离：单个监听器异常不影响其他监听器
- 返回取消订阅函数，使用方便
- 支持 `once` 一次性订阅

---

## 二、插件化深度整合

### 2.1 插件生命周期管理

**文件：** `star_core/plugin_system.py`

新增插件生命周期方法，支持启用/禁用/配置持久化。

#### API 概览

| 方法 | 说明 |
|------|------|
| `enable_plugin(name)` | 启用插件（激活 + 注册钩子 + 保存状态） |
| `disable_plugin(name)` | 禁用插件（注销钩子 + 保存状态） |
| `configure_plugin(name, config)` | 配置插件（调用 configure + 保存配置） |
| `get_plugin_config(name)` | 获取插件配置（从数据库读取） |
| `load_enabled_plugins_from_db()` | 启动时加载所有已启用插件 |

#### 使用示例

```python
from star_core.plugin_system import PluginManager

pm = PluginManager(plugin_dir="star_plugins")

# 发现并加载
pm.discover_plugins()
pm.load_plugin("my_plugin")

# 启用插件（状态持久化到数据库）
pm.enable_plugin("my_plugin")

# 配置插件（配置持久化）
pm.configure_plugin("my_plugin", {"api_key": "xxx", "interval": 30})

# 获取配置
config = pm.get_plugin_config("my_plugin")

# 禁用插件
pm.disable_plugin("my_plugin")

# 启动时自动加载已启用的插件
pm.load_enabled_plugins_from_db()
```

### 2.2 配置持久化

**文件：** `star_core/database.py`

新增 `plugin_configs` 表，存储插件配置和启用状态。

#### 表结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `plugin_name` | TEXT (主键) | 插件名称 |
| `config` | TEXT (JSON) | 插件配置（JSON 字符串） |
| `enabled` | INTEGER | 是否启用（0/1） |
| `created_at` | TEXT | 创建时间 |
| `updated_at` | TEXT | 更新时间 |

#### CRUD 方法

```python
from star_core.database import get_db_service

db = get_db_service()

# 保存配置
db.save_plugin_config("my_plugin", {"key": "value"}, enabled=True)

# 获取配置
config = db.get_plugin_config("my_plugin")
# {"plugin_name": "my_plugin", "config": {...}, "enabled": True, ...}

# 列出所有
all_configs = db.list_plugin_configs()

# 获取已启用的
enabled = db.list_enabled_plugin_configs()

# 删除
db.delete_plugin_config("my_plugin")
```

### 2.3 统一钩子分发系统

**文件：** `star_core/plugin_hooks.py`

提供统一的钩子分发器 `HookDispatcher`，支持 12 个钩子点，线程安全，异常隔离。

#### HookPoint 枚举

| 钩子点 | 触发时机 |
|--------|----------|
| `NOVA_CREATED` | 新星创建时 |
| `NOVA_LAUNCHED` | 任务发射时 |
| `NOVA_STATUS_CHANGED` | 任务状态变化时 |
| `NOVA_COMPLETED` | 任务完成时 |
| `NOVA_FAILED` | 任务失败时 |
| `STAR_DISCOVERED` | 发现新星体时 |
| `STAR_LOST` | 星体消失时 |
| `STARLIGHT_RECEIVED` | 收到星辉时 |
| `CONSTELLATION_CREATED` | 星座创建时 |
| `CONSTELLATION_COMPLETED` | 星座完成时 |
| `SYSTEM_STARTUP` | 系统启动时 |
| `SYSTEM_SHUTDOWN` | 系统关闭时 |

#### 使用示例

```python
from star_core.plugin_hooks import HookPoint, get_hook_dispatcher

dispatcher = get_hook_dispatcher()

# 注册钩子
def on_nova_created(nova):
    print(f"新任务: {nova.title}")
    return True

dispatcher.register(HookPoint.NOVA_CREATED, on_nova_created)

# 分发钩子
results = dispatcher.dispatch(HookPoint.NOVA_CREATED, nova=my_nova)

# 分发直到返回 False（短路）
cont = dispatcher.dispatch_until_false(HookPoint.NOVA_CREATED, nova=my_nova)

# 注销钩子
dispatcher.unregister(HookPoint.NOVA_CREATED, on_nova_created)

# 清空某个钩子点的所有处理器
dispatcher.clear(HookPoint.NOVA_CREATED)
```

**特性：**
- 全局单例：`get_hook_dispatcher()`
- 线程安全：`threading.RLock()` 双重检查锁定
- 异常隔离：单个处理器异常不影响其他
- 两种分发模式：全部分发（`dispatch`）、短路分发（`dispatch_until_false`）

#### HookPlugin 集成

`HookPlugin` 基类自动注册所有钩子方法到分发器：

```python
from star_core.plugin_system import HookPlugin

class MyHookPlugin(HookPlugin):
    PLUGIN_NAME = "my_hook"
    PLUGIN_VERSION = "1.0.0"
    
    def on_nova_created(self, nova):
        # 自动注册到 NOVA_CREATED 钩子点
        print(f"新任务: {nova.title}")
    
    def on_nova_completed(self, nova):
        # 自动注册到 NOVA_COMPLETED 钩子点
        print(f"任务完成: {nova.title}")
```

### 2.4 服务容器集成

**文件：** `star_core/service_container.py`

`hook_dispatcher` 已注册到服务容器，可通过容器访问：

```python
from star_core.service_container import get_service_container

container = get_service_container()
dispatcher = container.get('hook_dispatcher')
```

---

## 三、可观测性完善

### 3.1 统一指标体系

**文件：** `star_core/observability/metrics.py`

提供 Prometheus 风格的三类核心指标。

#### Counter（计数器）

只增不减的指标，适用于请求计数、错误计数等。

```python
from star_core.observability import get_metrics_registry

registry = get_metrics_registry()

# 创建计数器
request_counter = registry.counter(
    'http_requests_total',
    'Total HTTP requests',
    label_names=['method', 'path', 'status']
)

# 递增
request_counter.inc(labels={'method': 'GET', 'path': '/api/stars', 'status': '200'})
request_counter.inc(5, labels={'method': 'POST', 'path': '/api/novas', 'status': '201'})

# 获取值
count = request_counter.get(labels={'method': 'GET', 'path': '/api/stars', 'status': '200'})
```

#### Gauge（仪表盘）

可增可减可设置的指标，适用于活跃连接数、队列长度等。

```python
active_requests = registry.gauge(
    'http_active_requests',
    'Active HTTP requests',
    label_names=['method', 'path']
)

active_requests.inc(labels={'method': 'GET', 'path': '/api/stars'})
active_requests.dec(labels={'method': 'GET', 'path': '/api/stars'})
active_requests.set(42, labels={'method': 'POST', 'path': '/api/novas'})
```

#### Histogram（直方图）

统计分布的指标，适用于请求耗时、响应大小等。

```python
request_duration = registry.histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    label_names=['method', 'path']
)

request_duration.observe(0.03, labels={'method': 'GET', 'path': '/api/stars'})
```

#### 获取所有指标

```python
all_metrics = registry.get_all()
# {
#   'counters': { ... },
#   'gauges': { ... },
#   'histograms': { ... }
# }
```

### 3.2 健康检查

**文件：** `star_core/observability/health.py`

可扩展的健康检查框架，内置数据库和系统资源检查。

#### 健康状态

| 状态 | 说明 |
|------|------|
| `HEALTHY` | 正常 |
| `DEGRADED` | 降级（部分功能不可用） |
| `UNHEALTHY` | 异常 |

#### 内置检查项

| 名称 | 检查内容 |
|------|----------|
| `database` | 数据库连通性 |
| `system_resources` | CPU、内存、磁盘使用率 |

#### 使用示例

```python
from star_core.observability import get_health_checker

checker = get_health_checker()

# 全部检查
result = checker.check_all()
# {
#   'status': 'healthy',
#   'total_duration_ms': 15.2,
#   'checks': [
#       {'name': 'database', 'status': 'healthy', 'details': {...}, 'duration_ms': 2.1},
#       {'name': 'system_resources', 'status': 'healthy', 'details': {...}, 'duration_ms': 13.1}
#   ],
#   'timestamp': 1234567890.0
# }

# 单个检查
db_result = checker.check('database')

# 列出所有检查项
checks = checker.list_checks()
# ['database', 'system_resources']
```

#### 自定义检查项

```python
def check_my_service():
    # 返回 (status, details) 或 仅 status
    if my_service.is_alive():
        return HealthStatus.HEALTHY, {'connections': 42}
    else:
        return HealthStatus.UNHEALTHY, {'error': 'connection refused'}

checker.register('my_service', check_my_service)
```

### 3.3 API 层集成

**文件：** `star_api/routes/observability.py`、`star_api/main.py`

#### 可观测性 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/observability/metrics` | 获取所有指标 |
| GET | `/api/observability/health` | 全部健康检查 |
| GET | `/api/observability/health/list` | 列出健康检查项 |
| GET | `/api/observability/health/{check_name}` | 单个健康检查 |

#### HTTP 请求指标中间件

自动记录所有 HTTP 请求的指标：

| 指标 | 类型 | 标签 | 说明 |
|------|------|------|------|
| `http_requests_total` | Counter | method, path, status | 请求总数 |
| `http_request_duration_seconds` | Histogram | method, path | 请求耗时 |
| `http_active_requests` | Gauge | method, path | 活跃请求数 |

中间件特性：
- 异常请求也会被记录（status = 500）
- `finally` 块确保活跃请求计数正确减少
- 异常隔离，不影响业务逻辑

---

## 四、新增文件清单

### 前端工程化
```
star-ui/
├── css/
│   └── components.css              # 组件样式
└── js/
    ├── components/
    │   ├── toast.js                # Toast 组件
    │   └── modal.js                # Modal 组件
    └── state.js                    # AppState 状态管理
```

### 插件化
```
star_core/
├── plugin_hooks.py                 # 钩子分发器
├── service_container.py            # 服务容器
└── models/                         # 数据模型（新增目录）
```

### 可观测性
```
star_core/
└── observability/
    ├── __init__.py                 # 包导出
    ├── metrics.py                  # 指标管理
    └── health.py                   # 健康检查

star_api/
└── routes/
    └── observability.py            # 可观测性 API
```

### 测试
```
tests/
├── test_plugin_hooks.py            # 钩子系统测试（44 个）
├── test_observability.py           # 可观测性测试（76 个）
├── test_plugin_lifecycle.py        # 插件生命周期测试（55 个）
├── test_service_container.py       # 服务容器测试
├── test_database.py                # 数据库测试
├── test_config_service.py          # 配置服务测试
└── test_models.py                  # 模型测试
```

### 文档
```
docs/
├── stage3-upgrade.md               # 本文件
└── superpowers/plans/
    └── 2026-06-30-stage3-upgrade.md  # 升级计划
```

---

## 五、测试结果

### 全量测试

```
303 passed, 2 skipped
```

- 原有 130 个测试全部通过（0 回归）
- 新增 175 个测试全部通过
- 2 skipped 为原有的 async 测试（环境插件冲突）

### 新增测试覆盖

| 测试文件 | 测试数 | 覆盖模块 |
|---------|--------|---------|
| test_plugin_hooks.py | 44 | 钩子分发器注册/分发/异常隔离/线程安全 |
| test_observability.py | 76 | Counter/Gauge/Histogram/HealthChecker/单例/线程安全 |
| test_plugin_lifecycle.py | 55 | 启用/禁用/配置/钩子注册/集成场景 |

---

## 六、升级指南

### 后端升级

无需额外操作，所有新模块随项目一起加载。

启动服务时：
1. `plugin_configs` 表自动创建（如果不存在）
2. `load_enabled_plugins_from_db()` 自动加载已启用的插件
3. 健康检查器自动注册数据库和系统资源检查
4. HTTP 指标中间件自动启用

### 前端升级

在 HTML 中引入新增的 JS 和 CSS：

```html
<!-- 组件样式 -->
<link rel="stylesheet" href="css/components.css">

<!-- 组件脚本 -->
<script src="js/components/toast.js"></script>
<script src="js/components/modal.js"></script>

<!-- 状态管理 -->
<script src="js/state.js"></script>

<!-- ui-common.js 已包含 EventBus -->
<script src="js/ui-common.js"></script>
```

### 插件迁移

如果已有自定义插件，建议：

1. **配置持久化**：将插件配置迁移到 `plugin_configs` 表
2. **启用状态**：通过 `enable_plugin()` 管理启用状态，而非手动加载
3. **钩子注册**：使用 `HookPlugin` 基类，自动注册到统一分发器

---

## 七、后续规划

阶段 3 完成后，可考虑以下后续优化方向：

1. **前端框架引入**：当复杂度提升时，考虑 Vue/React 框架
2. **Prometheus 导出**：将指标导出为 Prometheus 格式，接入 Grafana
3. **分布式追踪**：添加 OpenTelemetry 追踪支持
4. **插件市场**：插件发现和安装的中心化管理
5. **告警系统**：基于健康检查和指标阈值的告警通知

---

> "群星闪耀，各司其职。调度有序，光芒汇聚。"
