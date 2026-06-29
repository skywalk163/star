# 快速开始

本文档将帮助你在 5 分钟内启动群星（Star）调度中心。

## 前置条件

| 要求 | 版本 | 说明 |
|------|------|------|
| Windows | 10 / 11 | 必须 Windows 系统（依赖 Win32 API） |
| Python | >= 3.12 | 建议使用 3.12+ |
| 权限 | 建议管理员 | 部分 UI Automation 操作需要 |

## 第一步：安装依赖

```bash
# 进入项目目录
cd g:\traework\star

# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate

# 安装项目
pip install -e .
```

安装成功后验证：

```bash
python -c "import star_core; print('星核就绪 ✨')"
```

## 第二步：启动 API 服务

```bash
uvicorn star_api.main:app --reload --host 0.0.0.0 --port 8765
```

启动后访问：

- **API 文档（Swagger）**：http://localhost:8765/docs
- **健康检查**：http://localhost:8765/health
- **统计信息**：http://localhost:8765/api/stats

## 第三步：发现星体

确保至少一个 AI Agent（如 Trae、Cursor 等）正在运行，然后：

### 通过 API

```bash
curl http://localhost:8765/api/stars
```

### 通过 Python 代码

```python
from star_core import StarSeeker

seeker = StarSeeker()
stars = seeker.scan_skies()

print(f"发现 {len(stars)} 颗星：")
for star in stars:
    print(f"  - {star.star_type} (PID: {star.pid})")
```

## 第四步：创建任务

### 通过 API 创建任务

```bash
curl -X POST http://localhost:8765/api/novas \
  -H "Content-Type: application/json" \
  -d '{
    "title": "生成登录模块",
    "description": "用 Python 编写用户登录验证模块",
    "starlight": "请用 Python 实现一个用户登录模块，包含密码哈希和 JWT 生成。",
    "priority": 1
  }'
```

### 通过 Python 创建任务

```python
import asyncio
from star_core import OrbitEngine, Nova, StarPriority

async def main():
    engine = OrbitEngine()
    
    # 启动后台队列处理
    asyncio.create_task(engine.process_queue())
    
    # 创建任务
    nova = Nova(
        id="",
        title="生成登录模块",
        description="用 Python 编写用户登录验证模块",
        starlight="请用 Python 实现一个用户登录模块，包含密码哈希和 JWT 生成。",
        priority=StarPriority.NORMAL
    )
    
    nova_id = await engine.birth_nova(nova)
    print(f"新星诞生：{nova_id}")
    
    # 手动发射（如果不想等队列自动处理）
    await engine.launch_nova(nova_id)

asyncio.run(main())
```

## 第五步：监控输出

### WebSocket 实时监控

```javascript
const ws = new WebSocket('ws://localhost:8765/ws/starlight');

ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    
    if (msg.type === 'starlight_received') {
        console.log(`[${msg.data.nova_id}] 新输出：`, msg.data.content);
    }
    
    if (msg.type === 'nova_status_change') {
        console.log(`任务状态：${msg.data.status}`);
    }
};
```

### API 轮询

```bash
# 查看任务详情
curl http://localhost:8765/api/novas/{nova_id}

# 查看所有任务
curl http://localhost:8765/api/novas?status=shining
```

## 常见问题

### Q: 找不到星体怎么办？

1. 确认 AI Agent 正在运行
2. 以管理员权限运行 Python
3. 检查 `STAR_SIGNATURES` 中的进程名是否匹配
4. 手动添加自定义星体类型

### Q: 文本注入失败？

1. 检查目标窗口是否被最小化
2. 确保输入框可见（某些 Agent 需要展开对话）
3. 尝试调整注入策略优先级

### Q: WebSocket 连不上？

1. 确认服务端口正确（默认 8765）
2. 检查防火墙设置
3. 使用 `ws://` 而非 `http://`

## 下一步

- 阅读 [架构设计](architecture.md) 了解系统组成
- 查看 [API 参考](api-reference.md) 了解完整接口
- 学习 [进阶用法](advanced-usage.md) 进行星座协同
