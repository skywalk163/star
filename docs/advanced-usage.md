# 进阶用法

本文档介绍群星（Star）调度中心的高级功能与使用技巧。

## 自定义星体类型

如果内置的星体类型不满足需求，可以添加自定义类型。

### 方式一：运行时添加

```python
from star_core import StarSeeker

seeker = StarSeeker()

# 添加自定义星体
seeker.STAR_SIGNATURES['my_custom_agent'] = {
    'process_names': ['MyAgent.exe', 'myagent.exe'],
    'window_class': ['Chrome_WidgetWin_1'],
    'window_title_patterns': ['My Agent', 'MyAgent'],
    'description': '我的自定义 AI Agent'
}

# 添加亲缘性配置（影响智能路由）
from star_core import OrbitEngine

engine = OrbitEngine(star_seeker=seeker)
engine.STAR_AFFINITY['my_custom_agent'] = {
    'keywords': ['优化', 'optimize', '性能', 'performance'],
    'weight': 1.0
}
```

### 方式二：继承扩展

```python
from star_core import StarSeeker

class CustomStarSeeker(StarSeeker):
    STAR_SIGNATURES = {
        **StarSeeker.STAR_SIGNATURES,
        'my_agent': {
            'process_names': ['MyAgent.exe'],
            'window_class': ['Chrome_WidgetWin_1'],
            'window_title_patterns': ['My Agent'],
            'description': '我的专属 Agent'
        }
    }
```

## 自定义注入策略

实现自定义的文本注入方式：

```python
from star_core import StarAssigner, StarBody

class CustomAssigner(StarAssigner):
    
    def _try_my_strategy(self, star: StarBody, text: str) -> bool:
        """
        自定义注入策略
        """
        try:
            # 实现你的注入逻辑
            # ...
            star.mark_shining(True)
            return True
        except Exception:
            return False
    
    def send_starlight(self, star, text, strategy_priority=None):
        if strategy_priority is None:
            strategy_priority = [
                AssignStrategy.UIA,
                AssignStrategy.CLIPBOARD,
            ]
        return super().send_starlight(star, text, strategy_priority)
```

## 任务批处理

批量创建和管理多个任务：

```python
import asyncio
from star_core import OrbitEngine, Nova, StarPriority

async def batch_process():
    engine = OrbitEngine()
    asyncio.create_task(engine.process_queue())
    
    tasks = [
        {"title": "模块A", "desc": "实现功能A", "prompt": "请实现A..."},
        {"title": "模块B", "desc": "实现功能B", "prompt": "请实现B..."},
        {"title": "模块C", "desc": "实现功能C", "prompt": "请实现C..."},
    ]
    
    nova_ids = []
    for task in tasks:
        nova = Nova(
            id="",
            title=task["title"],
            description=task["desc"],
            starlight=task["prompt"],
            priority=StarPriority.NORMAL
        )
        nova_id = await engine.birth_nova(nova)
        nova_ids.append(nova_id)
        print(f"提交任务: {nova_id}")
    
    # 等待所有完成
    while True:
        pending = sum(
            1 for nid in nova_ids
            if engine.get_nova(nid).status not in 
            ['constellated', 'faded', 'darkened']
        )
        if pending == 0:
            break
        await asyncio.sleep(2)
    
    print("所有任务完成！")
```

## 事件回调注册

监听任务状态变化和输出更新：

```python
import asyncio
from star_core import OrbitEngine, Nova

async def on_status_change(nova: Nova):
    """任务状态变化回调"""
    print(f"[状态变更] {nova.id}: {nova.status.value} - {nova.title}")
    
    if nova.status.value == 'constellated':
        print(f"  ✨ 任务完成，结果长度: {len(nova.result_starlight or '')}")
    elif nova.status.value == 'faded':
        print(f"  🌑 任务失败: {nova.error}")

async def on_starlight(nova: Nova, content: str):
    """收到星辉回调"""
    print(f"[新输出] {nova.id}: {content[:80]}...")

async def main():
    engine = OrbitEngine()
    
    # 注册回调
    engine.set_callbacks(
        on_status_change=on_status_change,
        on_starlight=on_starlight
    )
    
    # 启动队列处理
    asyncio.create_task(engine.process_queue())
    
    # ... 创建任务等 ...
```

## 多 Agent 协同（星座）

使用星座功能编排多 Agent 工作流：

```python
import asyncio
from star_core import OrbitEngine

async def constellation_demo():
    engine = OrbitEngine()
    asyncio.create_task(engine.process_queue())
    
    # 创建一个代码生成 + 审查的协同任务
    constellation = await engine.create_constellation(
        name="代码生成与审查",
        description="先由 Trae 生成代码，再由 CodeArts 审查",
        nova_specs=[
            {
                "title": "生成登录模块",
                "description": "用 Python 生成登录模块",
                "starlight": "请生成一个 Python 登录模块，包含密码哈希和 JWT。",
                "assigned_star": "trae"
            },
            {
                "title": "安全审查",
                "description": "审查登录模块的安全性",
                "starlight": "请审查以下登录代码的安全性，指出潜在漏洞。",
                "assigned_star": "codearts_atomcode"
            }
        ]
    )
    
    print(f"星座已创建: {constellation.id}")
    print(f"包含任务: {[n.id for n in constellation.novas]}")
```

## 自定义观星策略

修改观星者的输出检测逻辑：

```python
from star_core import StarGazer, StarBody

class CustomGazer(StarGazer):
    
    OUTPUT_CLASS_NAMES = [
        'MyCustomEditor',
        'OutputPanel',
        *StarGazer.OUTPUT_CLASS_NAMES
    ]
    
    def detect_completion(self, star: StarBody) -> bool:
        """
        自定义完成检测逻辑
        """
        current = self.gaze(star)
        
        # 自定义完成关键词
        my_completion_patterns = [
            '完成啦', '搞定', 'over',
            '--- END ---', '任务完成 🎉'
        ]
        
        if any(p in current for p in my_completion_patterns):
            return True
        
        # 调用父类检测
        return super().detect_completion(star)
```

## 与现有系统集成

### FastAPI 应用集成

```python
from fastapi import FastAPI
from star_api.main import app as star_app

main_app = FastAPI()

# 将 Star API 挂载到子路径
main_app.mount("/star", star_app)
```

### 作为 Python 库使用

```python
# 在你的项目中直接使用星核
from star_core import StarSeeker, OrbitEngine, Nova

# 扫描星体
seeker = StarSeeker()
stars = seeker.scan_skies()

# 启动调度
engine = OrbitEngine(star_seeker=seeker)
```

## 性能调优

### 调整轮询间隔

默认观星轮询间隔为 1 秒，可根据需求调整：

```python
# 更高实时性（但更耗资源）
gazer.continuous_gaze(star, callback, poll_interval=0.3)

# 更低资源占用
gazer.continuous_gaze(star, callback, poll_interval=2.0)
```

### 星体扫描频率

默认星体扫描每 5 秒一次，可修改：

```python
# 在 star_api/main.py 中调整
async def _scan_stars_periodically():
    while True:
        await asyncio.sleep(10)  # 改为 10 秒
        # ...
```

### 队列并发

当前实现为单任务串行处理。如需并发：

```python
# 启动多个队列处理协程
for _ in range(3):  # 3 个并发
    asyncio.create_task(engine.process_queue())
```

## 故障排查

### 问题：找不到星体

**诊断步骤**：

```python
from star_core import Observatory

obs = Observatory()

# 检查所有进程
import psutil
for proc in psutil.process_iter(['pid', 'name']):
    if 'trae' in proc.info['name'].lower():
        print(f"找到进程: {proc.info}")
        
        # 查看该进程的所有窗口
        hwnds = obs.find_all_windows_by_pid(proc.info['pid'])
        for hwnd in hwnds:
            info = obs.get_window_info(hwnd)
            print(f"  窗口: {info.title} [{info.class_name}]")
```

**可能原因**：
- 进程名不匹配 → 手动添加签名
- 窗口被最小化 → 某些 Agent 最小化后无主窗口
- 权限不足 → 尝试管理员运行

### 问题：文本注入后无反应

**诊断步骤**：

1. 检查窗口是否被置前
2. 确认输入框有焦点
3. 尝试切换注入策略
4. 检查剪贴板是否正常工作

```python
# 测试剪贴板
from star_core import Observatory
obs = Observatory()
obs.set_clipboard_text("测试文本")
print(obs.get_clipboard_text())  # 应该输出 "测试文本"
```

### 问题：输出捕获为空

**诊断步骤**：

1. 用 Inspect.exe 等工具查看目标窗口的控件树
2. 找到输出区域的正确类名
3. 添加到 `OUTPUT_CLASS_NAMES`

```python
# 列出窗口下的所有文本控件
import uiautomation as uia
window = uia.ControlFromHandle(hwnd)
for ctrl in window.GetChildren():
    if ctrl.ControlTypeName == 'TextControl':
        print(f"{ctrl.ClassName}: {ctrl.Name[:30]}")
```

## 生产部署

### 使用 systemd / Windows 服务

将 API 服务注册为系统服务，开机自启。

### 配置反向代理

使用 Nginx 或 IIS 反向代理到 uvicorn。

### 启用认证

生产环境建议添加 API Key 或 OAuth2 认证：

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != "your-secret-key":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
```

---

更多问题和需求，欢迎提交 Issue 或 PR。
