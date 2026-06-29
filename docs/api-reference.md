# API 参考

本文档详细列出群星（Star）调度中心的所有 API 接口。

## 基础信息

- **Base URL**：`http://localhost:8765`
- **默认端口**：`8765`
- **数据格式**：`application/json`
- **API 文档**：`/docs`（Swagger UI）、`/redoc`（ReDoc）

---

## 系统接口

### 健康检查

```
GET /health
```

**响应示例**：

```json
{
  "status": "ok"
}
```

### 服务信息

```
GET /
```

**响应示例**：

```json
{
  "name": "群星 Star API",
  "version": "0.1.0",
  "status": "shining"
}
```

### 调度统计

```
GET /api/stats
```

**响应示例**：

```json
{
  "total_novas": 10,
  "queue_size": 2,
  "by_status": {
    "nascent": 2,
    "orbiting": 0,
    "shining": 3,
    "awaiting": 1,
    "constellated": 3,
    "faded": 1,
    "darkened": 0
  },
  "by_star": {
    "trae": 4,
    "cursor": 3,
    "codearts_atomcode": 2,
    "copilot": 1
  },
  "shining_stars": 3,
  "idle_stars": 2
}
```

---

## 星体接口

### 列出所有星体

```
GET /api/stars
```

**响应**：

```json
{
  "stars": [
    {
      "pid": 12345,
      "star_type": "trae",
      "title": "Trae - main.py",
      "is_shining": false,
      "last_activity": 1234567890.123
    }
  ],
  "total": 1,
  "shining": 0,
  "idle": 1
}
```

### 列出支持的星体类型

```
GET /api/stars/types
```

**响应**：

```json
{
  "trae": {
    "description": "字节跳动 AI 编程助手",
    "process_names": ["Trae.exe", "trae.exe"]
  },
  "cursor": {
    "description": "Cursor AI IDE",
    "process_names": ["Cursor.exe"]
  }
}
```

### 获取星体详情

```
GET /api/stars/{pid}
```

**参数**：
- `pid` (int) - 进程 ID

**响应**：

```json
{
  "pid": 12345,
  "star_type": "trae",
  "title": "Trae - main.py",
  "hwnd": 987654,
  "is_shining": false,
  "last_activity": 1234567890.123
}
```

**错误**：
- `404` - 星体未发现

### 刷新星体信息

```
POST /api/stars/{pid}/refresh
```

**参数**：
- `pid` (int) - 进程 ID

**响应**：更新后的星体信息

**错误**：
- `404` - 星体未发现或已熄灭

### 获取空闲星体

```
GET /api/stars/idle?star_type=trae
```

**查询参数**：
- `star_type` (string, 可选) - 星体类型过滤

**响应**：

```json
{
  "stars": [
    {
      "pid": 12345,
      "star_type": "trae",
      "title": "Trae - project"
    }
  ],
  "total": 1
}
```

---

## 新星（任务）接口

### 创建任务

```
POST /api/novas
```

**请求体**：

```json
{
  "title": "生成登录模块",
  "description": "用 Python 编写用户登录验证模块",
  "starlight": "请用 Python 实现一个用户登录模块，包含密码哈希和 JWT 生成。",
  "context_files": ["src/auth.py"],
  "assigned_star": "trae",
  "priority": 1
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | 是 | 任务标题 |
| `description` | string | 是 | 任务描述 |
| `starlight` | string | 是 | 发送给 Agent 的指令 |
| `context_files` | string[] | 否 | 上下文文件列表 |
| `assigned_star` | string | 否 | 指定星体类型，不填则自动路由 |
| `priority` | int | 否 | 优先级：0=DIM, 1=NORMAL, 2=BRIGHT, 3=SUPERNOVA |

**响应**：

```json
{
  "id": "a1b2c3d4",
  "title": "生成登录模块",
  "status": "nascent",
  "assigned_star": "trae",
  "message": "新星已诞生，等待入轨"
}
```

### 列出所有任务

```
GET /api/novas?status=shining&star_type=trae
```

**查询参数**：
- `status` (string, 可选) - 状态过滤：`nascent`, `orbiting`, `shining`, `awaiting`, `constellated`, `faded`, `darkened`
- `star_type` (string, 可选) - 星体类型过滤

**响应**：

```json
{
  "novas": [
    {
      "id": "a1b2c3d4",
      "title": "生成登录模块",
      "description": "用 Python 编写用户登录验证模块",
      "status": "shining",
      "priority": 1,
      "assigned_star": "trae",
      "created_at": "2024-01-01T12:00:00",
      "updated_at": "2024-01-01T12:01:00",
      "result_starlight": "正在生成...",
      "error": null
    }
  ],
  "total": 1
}
```

**排序**：按优先级降序、创建时间升序

### 获取任务详情

```
GET /api/novas/{nova_id}
```

**参数**：
- `nova_id` (string) - 任务 ID

**响应**：

```json
{
  "id": "a1b2c3d4",
  "title": "生成登录模块",
  "description": "用 Python 编写用户登录验证模块",
  "starlight": "请用 Python 实现一个用户登录模块...",
  "status": "shining",
  "priority": 1,
  "assigned_star": "trae",
  "created_at": "2024-01-01T12:00:00",
  "updated_at": "2024-01-01T12:01:00",
  "result_starlight": "生成的代码如下...",
  "starlight_log": [
    {
      "timestamp": "2024-01-01T12:00:00",
      "role": "user",
      "content": "请用 Python 实现..."
    }
  ],
  "echo": null,
  "error": null
}
```

**错误**：
- `404` - 任务未发现

### 发射任务

```
POST /api/novas/{nova_id}/launch
```

手动将任务分配给星体执行（通常由队列自动处理）。

**参数**：
- `nova_id` (string) - 任务 ID

**响应**：

```json
{
  "id": "a1b2c3d4",
  "status": "shining",
  "message": "新星已发射，正在闪耀"
}
```

**错误**：
- `400` - 发射失败（无可用星体或发送失败）

### 调整星轨

```
POST /api/novas/{nova_id}/adjust
```

修改运行中任务的指令。

**请求体**：

```json
{
  "new_starlight": "请修改为使用 bcrypt 加密而不是 SHA256"
}
```

**响应**：

```json
{
  "id": "a1b2c3d4",
  "starlight": "请修改为使用 bcrypt 加密...",
  "message": "星轨已调整"
}
```

**错误**：
- `400` - 调整失败（任务未运行或无可用星体）

### 添加回响

```
POST /api/novas/{nova_id}/echo
```

用户对结果的反馈，支持继续迭代。

**请求体**：

```json
{
  "echo": "很好，但请添加单元测试"
}
```

**响应**：

```json
{
  "id": "a1b2c3d4",
  "status": "constellated",
  "message": "回响已添加"
}
```

> **说明**：如果回响中包含"继续"等关键词，会自动触发新一轮迭代。

### 标记失败

```
POST /api/novas/{nova_id}/fade?reason=超时
```

**查询参数**：
- `reason` (string) - 失败原因

**响应**：

```json
{
  "id": "a1b2c3d4",
  "status": "faded",
  "message": "新星已暗淡: 超时"
}
```

### 取消任务

```
POST /api/novas/{nova_id}/darken
```

**响应**：

```json
{
  "id": "a1b2c3d4",
  "status": "darkened",
  "message": "新星已熄灭"
}
```

### 获取观星历史

```
GET /api/novas/{nova_id}/gaze
```

**响应**：

```json
{
  "nova_id": "a1b2c3d4",
  "history": [
    {
      "timestamp": "2024-01-01T12:00:00",
      "role": "user",
      "content": "请用 Python 实现..."
    },
    {
      "timestamp": "2024-01-01T12:01:00",
      "role": "trae",
      "content": "好的，这是实现..."
    }
  ]
}
```

---

## 星座接口

### 创建星座

```
POST /api/constellations
```

创建多星协同任务。

**请求体**：

```json
{
  "name": "全栈登录系统",
  "description": "由不同 Agent 协同完成一个登录系统",
  "nova_specs": [
    {
      "title": "后端 API",
      "description": "实现后端登录 API",
      "starlight": "用 FastAPI 实现登录接口...",
      "assigned_star": "trae"
    },
    {
      "title": "代码审查",
      "description": "审查后端代码",
      "starlight": "审查以下登录代码的安全性...",
      "assigned_star": "codearts_atomcode"
    }
  ]
}
```

**响应**：

```json
{
  "id": "c5d6e7f8",
  "name": "全栈登录系统",
  "description": "由不同 Agent 协同完成一个登录系统",
  "status": "pending",
  "nova_count": 2,
  "nova_ids": ["a1b2c3d4", "e5f6a7b8"],
  "message": "星座已形成，等待群星闪耀"
}
```

---

## WebSocket 接口

### 连接

```
WS /ws/starlight
```

### 消息类型

#### 连接成功

服务端在连接建立后发送：

```json
{
  "type": "connected",
  "data": {
    "stats": { ... }
  }
}
```

#### 星体更新

```json
{
  "type": "stars_updated",
  "data": [
    {
      "pid": 12345,
      "star_type": "trae",
      "title": "Trae",
      "is_shining": false
    }
  ]
}
```

#### 任务状态变化

```json
{
  "type": "nova_status_change",
  "data": {
    "id": "a1b2c3d4",
    "status": "shining",
    "title": "生成登录模块",
    "updated_at": "2024-01-01T12:00:00"
  }
}
```

#### 收到星辉

```json
{
  "type": "starlight_received",
  "data": {
    "nova_id": "a1b2c3d4",
    "content": "好的，这是实现代码...",
    "timestamp": "2024-01-01T12:01:00"
  }
}
```

### 心跳

客户端每 30 秒发送：

```
ping
```

服务端回复：

```
pong
```

### Python 客户端示例

```python
import asyncio
import websockets
import json

async def listen():
    uri = "ws://localhost:8765/ws/starlight"
    async with websockets.connect(uri) as ws:
        while True:
            message = await ws.recv()
            data = json.loads(message)
            msg_type = data["type"]
            
            if msg_type == "starlight_received":
                print(f"[{data['data']['nova_id']}] {data['data']['content'][:50]}...")
            elif msg_type == "nova_status_change":
                print(f"任务 {data['data']['id']}: {data['data']['status']}")

asyncio.run(listen())
```

---

## 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 404 | 资源未找到 |
| 500 | 服务器内部错误 |
| 501 | 功能未实现 |
| 503 | 星核未初始化 |

---

## 状态枚举

### StarStatus（星芒状态）

| 值 | 说明 |
|----|------|
| `nascent` | 初生（新创建） |
| `orbiting` | 入轨（已分配） |
| `shining` | 闪耀（Agent 正在处理） |
| `awaiting` | 待回响（等待用户审查） |
| `constellated` | 成星（完成） |
| `faded` | 暗淡（失败） |
| `darkened` | 熄灭（取消） |

### StarPriority（星等）

| 值 | 名称 | 说明 |
|----|------|------|
| 0 | DIM | 暗星（低） |
| 1 | NORMAL | 常星（正常） |
| 2 | BRIGHT | 亮星（高） |
| 3 | SUPERNOVA | 超新星（紧急） |
