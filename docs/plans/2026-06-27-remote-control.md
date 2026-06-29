# AI Agent 远程控制 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 构建网页版 AI Agent 远程控制台，支持窗口截图流、热点点击指令发送，自适应降低刷新频率。

**架构：** 后端基于 FastAPI + win32/pyautogui，前端为单页 HTML。截图采用 MJPEG 流 + 自适应间隔（无变化时间隔翻倍，上限30分钟）。指令发送使用预设热点定位输入框，支持所有已发现的 AI Agent。

**技术栈：** FastAPI、pywin32、Pillow（截图对比）、HTML5 + JS 前端

---

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `star_core/remote_screenshot.py` | 自适应截图调度器（间隔倍增、变化检测） | 新建 |
| `star_core/window_controller.py` | 窗口控制（激活、点击、文本输入、热点配置） | 新建 |
| `star_api/routes/remote.py` | 远程控制 API 路由 | 新建 |
| `star_api/main.py` | 注册 remote 路由、挂载前端页面 | 修改 |
| `star-ui/pages/remote.html` | 远程控制前端页面 | 新建 |
| `star-ui/js/api-bridge.js` | 新增 remoteApi 封装 | 修改 |

---

## 任务 1：自适应截图调度器

**文件：**
- 创建：`star_core/remote_screenshot.py`

### 步骤

- [ ] **步骤 1：定义数据结构**

在 `star_core/remote_screenshot.py` 中定义：

```python
import os
import time
import tempfile
from typing import Optional, Dict
from dataclasses import dataclass, field

from star_core.observatory import Observatory


@dataclass
class WindowScreenshotState:
    hwnd: int
    last_screenshot_path: str = ""
    last_screenshot_time: float = 0.0
    last_hash: int = 0
    current_interval: int = 60  # 秒，初始 1 分钟
    min_interval: int = 60
    max_interval: int = 1800  # 30 分钟
    no_change_count: int = 0


class RemoteScreenshotManager:
    def __init__(self, observatory: Optional[Observatory] = None):
        self.observatory = observatory or Observatory()
        self._states: Dict[int, WindowScreenshotState] = {}
        self._temp_dir = os.path.join(tempfile.gettempdir(), "star_remote")
        os.makedirs(self._temp_dir, exist_ok=True)

    def get_state(self, hwnd: int) -> WindowScreenshotState:
        if hwnd not in self._states:
            self._states[hwnd] = WindowScreenshotState(hwnd=hwnd)
        return self._states[hwnd]

    def _compute_hash(self, img_path: str) -> int:
        """简化的图像哈希：用 Pillow 缩略图平均灰度"""
        try:
            from PIL import Image
            img = Image.open(img_path).convert("L").resize((32, 32))
            pixels = list(img.getdata())
            avg = sum(pixels) / len(pixels)
            bits = [1 if p > avg else 0 for p in pixels]
            h = 0
            for b in bits:
                h = (h << 1) | b
            return h
        except Exception:
            return 0

    def should_refresh(self, hwnd: int) -> bool:
        """判断是否应该刷新截图"""
        state = self.get_state(hwnd)
        if not state.last_screenshot_path:
            return True
        elapsed = time.time() - state.last_screenshot_time
        return elapsed >= state.current_interval

    def capture(self, hwnd: int, force: bool = False) -> Optional[str]:
        """
        捕获窗口截图，自适应间隔
        
        Args:
            hwnd: 窗口句柄
            force: 强制刷新
            
        Returns:
            截图文件路径
        """
        state = self.get_state(hwnd)
        
        if not force and not self.should_refresh(hwnd):
            return state.last_screenshot_path
        
        # 截图
        try:
            from star_core.ocr_gazer import OCRGazer
            gazer = OCRGazer()
            save_path = os.path.join(
                self._temp_dir,
                f"remote_{hwnd}_{int(time.time())}.jpg"
            )
            img_path = gazer.capture_window(hwnd, save_path=save_path)
            if not img_path:
                return state.last_screenshot_path or None
        except Exception:
            return state.last_screenshot_path or None
        
        # 对比变化
        new_hash = self._compute_hash(img_path)
        if state.last_screenshot_path and new_hash == state.last_hash:
            # 无变化，间隔翻倍
            state.no_change_count += 1
            state.current_interval = min(
                state.current_interval * 2,
                state.max_interval
            )
        else:
            # 有变化，重置间隔
            state.no_change_count = 0
            state.current_interval = state.min_interval
            # 清理旧截图
            if state.last_screenshot_path and os.path.exists(state.last_screenshot_path):
                try:
                    os.remove(state.last_screenshot_path)
                except Exception:
                    pass
        
        state.last_hash = new_hash
        state.last_screenshot_path = img_path
        state.last_screenshot_time = time.time()
        
        return img_path

    def get_status(self, hwnd: int) -> dict:
        """获取截图状态"""
        state = self.get_state(hwnd)
        return {
            'hwnd': hwnd,
            'last_screenshot_time': state.last_screenshot_time,
            'current_interval': state.current_interval,
            'no_change_count': state.no_change_count,
            'last_screenshot_path': state.last_screenshot_path,
        }
```

- [ ] **步骤 2：快速验证**

运行：
```
cd g:\traework\star
python -c "
from star_core.remote_screenshot import RemoteScreenshotManager
mgr = RemoteScreenshotManager()
path = mgr.capture(9308954, force=True)
print('screenshot:', path)
status = mgr.get_status(9308954)
print('interval:', status['current_interval'])
print('no_change:', status['no_change_count'])
"
```
预期：截图路径不为空，interval=60

---

## 任务 2：窗口控制器 + 热点配置

**文件：**
- 创建：`star_core/window_controller.py`

### 步骤

- [ ] **步骤 1：热点配置 + 窗口控制器**

```python
import time
import win32gui
import win32con
from typing import Optional, Dict, Tuple
from dataclasses import dataclass


@dataclass
class Hotspot:
    """热点 - 预设的点击区域"""
    name: str          # 标识名，如 "input_box"
    label: str         # 显示名，如 "对话输入框"
    position: str      # 锚点位置: "left_top", "right_bottom", "center_bottom" 等
    width_ratio: float = 0.3    # 相对于窗口宽度的比例
    height_ratio: float = 0.1   # 相对于窗口高度的比例
    offset_x: int = 0           # 相对于锚点的 x 偏移
    offset_y: int = 0           # 相对于锚点的 y 偏移


# 各类型 AI Agent 的预设热点
HOTSPOT_CONFIG = {
    'trae': {
        'input_box': Hotspot(
            name='input_box',
            label='AI 对话输入框',
            position='right_bottom',
            width_ratio=0.35,
            height_ratio=0.08,
            offset_x=-10,
            offset_y=-60,
        ),
        'task_list': Hotspot(
            name='task_list',
            label='任务列表',
            position='left_top',
            width_ratio=0.2,
            height_ratio=0.5,
            offset_x=10,
            offset_y=80,
        ),
    },
    'default': {
        'input_box': Hotspot(
            name='input_box',
            label='输入框',
            position='center_bottom',
            width_ratio=0.5,
            height_ratio=0.1,
            offset_x=0,
            offset_y=-50,
        ),
    },
}


class WindowController:
    """窗口控制器 - 激活、点击、输入"""

    def __init__(self):
        pass

    def activate(self, hwnd: int) -> bool:
        """激活窗口到前台"""
        try:
            # 先还原最小化
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.2)
            return True
        except Exception:
            return False

    def get_window_rect(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        """获取窗口矩形"""
        try:
            return win32gui.GetWindowRect(hwnd)
        except Exception:
            return None

    def calc_hotspot_center(self, hwnd: int, hotspot: Hotspot) -> Optional[Tuple[int, int]]:
        """计算热点中心在屏幕上的坐标"""
        rect = self.get_window_rect(hwnd)
        if not rect:
            return None
        left, top, right, bottom = rect
        w = right - left
        h = bottom - top
        
        hotspot_w = int(w * hotspot.width_ratio)
        hotspot_h = int(h * hotspot.height_ratio)
        
        # 计算锚点
        pos = hotspot.position
        if pos == 'left_top':
            anchor_x = left
            anchor_y = top
        elif pos == 'right_bottom':
            anchor_x = right
            anchor_y = bottom
        elif pos == 'center_bottom':
            anchor_x = left + w // 2
            anchor_y = bottom
        else:
            anchor_x = left + w // 2
            anchor_y = top + h // 2
        
        # 热点中心 = 锚点 + 偏移 + 热点尺寸/2（向内部）
        if 'right' in pos:
            center_x = anchor_x + hotspot.offset_x - hotspot_w // 2
        elif 'left' in pos:
            center_x = anchor_x + hotspot.offset_x + hotspot_w // 2
        else:
            center_x = anchor_x + hotspot.offset_x
        
        if 'bottom' in pos:
            center_y = anchor_y + hotspot.offset_y - hotspot_h // 2
        elif 'top' in pos:
            center_y = anchor_y + hotspot.offset_y + hotspot_h // 2
        else:
            center_y = anchor_y + hotspot.offset_y
        
        return (center_x, center_y)

    def click_at(self, x: int, y: int) -> bool:
        """在屏幕坐标 (x, y) 处点击"""
        try:
            import pyautogui
            pyautogui.click(x, y)
            time.sleep(0.1)
            return True
        except ImportError:
            try:
                import ctypes
                ctypes.windll.user32.SetCursorPos(x, y)
                ctypes.windll.user32.mouse_event(2, 0, 0, 0, 0)  # left down
                ctypes.windll.user32.mouse_event(4, 0, 0, 0, 0)  # left up
                time.sleep(0.1)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def type_text(self, text: str) -> bool:
        """输入文本（需要先激活目标输入框）"""
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=0.01)
            return True
        except ImportError:
            try:
                # 用剪贴板 + Ctrl+V 回退方案
                import subprocess
                subprocess.run(['clip'], input=text.encode('utf-16-le'), check=True, capture_output=True)
                import ctypes
                ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)  # Ctrl down
                ctypes.windll.user32.keybd_event(0x56, 0, 0, 0)  # V down
                ctypes.windll.user32.keybd_event(0x56, 0, 2, 0)  # V up
                ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)  # Ctrl up
                time.sleep(0.1)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def press_enter(self) -> bool:
        """按回车键"""
        try:
            import pyautogui
            pyautogui.press('enter')
            return True
        except ImportError:
            try:
                import ctypes
                ctypes.windll.user32.keybd_event(0x0D, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x0D, 0, 2, 0)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def send_to_hotspot(self, hwnd: int, hotspot: Hotspot, text: str) -> bool:
        """
        向指定热点发送文本指令
        
        流程：激活窗口 → 点击热点 → 输入文本 → 回车
        """
        if not self.activate(hwnd):
            return False
        
        pos = self.calc_hotspot_center(hwnd, hotspot)
        if not pos:
            return False
        
        if not self.click_at(pos[0], pos[1]):
            return False
        
        time.sleep(0.2)
        
        if not self.type_text(text):
            return False
        
        time.sleep(0.1)
        
        # 不自动回车，由调用方决定
        return True

    def get_hotspots(self, star_type: str) -> Dict[str, Hotspot]:
        """获取指定类型的热点配置"""
        if star_type in HOTSPOT_CONFIG:
            return HOTSPOT_CONFIG[star_type]
        return HOTSPOT_CONFIG['default']
```

- [ ] **步骤 2：快速验证**

运行：
```
cd g:\traework\star
python -c "
from star_core.window_controller import WindowController, HOTSPOT_CONFIG
ctrl = WindowController()
hotspots = ctrl.get_hotspots('trae')
print('hotspots:', list(hotspots.keys()))
rect = ctrl.get_window_rect(9308954)
print('window rect:', rect)
hs = hotspots['input_box']
center = ctrl.calc_hotspot_center(9308954, hs)
print('input_box center:', center)
"
```
预期：热点列表有 input_box 和 task_list，窗口矩形和热点中心坐标有效

---

## 任务 3：API 路由

**文件：**
- 创建：`star_api/routes/remote.py`
- 修改：`star_api/main.py`

### 步骤

- [ ] **步骤 1：创建 remote.py 路由**

```python
"""
远程控制路由（Remote Routes）

提供窗口截图、热点点击、指令发送等远程控制接口
"""

import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from star_api import state

router = APIRouter()


def _get_screenshot_manager():
    if not hasattr(state, 'screenshot_manager') or state.screenshot_manager is None:
        from star_core.remote_screenshot import RemoteScreenshotManager
        state.screenshot_manager = RemoteScreenshotManager()
    return state.screenshot_manager


def _get_window_controller():
    if not hasattr(state, 'window_controller') or state.window_controller is None:
        from star_core.window_controller import WindowController
        state.window_controller = WindowController()
    return state.window_controller


@router.get("/screenshot/{hwnd}")
async def get_screenshot(hwnd: int, force: bool = False):
    """
    获取窗口截图
    
    Args:
        hwnd: 窗口句柄
        force: 是否强制刷新截图
        
    Returns:
        截图图片（JPEG）
    """
    mgr = _get_screenshot_manager()
    img_path = mgr.capture(hwnd, force=force)
    
    if not img_path or not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="截图不可用")
    
    return FileResponse(
        img_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache",
            "X-Interval": str(mgr.get_status(hwnd)['current_interval']),
        }
    )


@router.get("/screenshot/{hwnd}/status")
async def get_screenshot_status(hwnd: int):
    """获取截图状态"""
    mgr = _get_screenshot_manager()
    return mgr.get_status(hwnd)


@router.post("/screenshot/{hwnd}/refresh")
async def refresh_screenshot(hwnd: int):
    """强制刷新截图"""
    mgr = _get_screenshot_manager()
    mgr.capture(hwnd, force=True)
    return mgr.get_status(hwnd)


@router.get("/hotspots/{star_type}")
async def get_hotspots(star_type: str):
    """获取指定类型 AI Agent 的预设热点"""
    ctrl = _get_window_controller()
    hotspots = ctrl.get_hotspots(star_type)
    return {
        'star_type': star_type,
        'hotspots': {
            name: {
                'name': hs.name,
                'label': hs.label,
                'position': hs.position,
                'width_ratio': hs.width_ratio,
                'height_ratio': hs.height_ratio,
                'offset_x': hs.offset_x,
                'offset_y': hs.offset_y,
            }
            for name, hs in hotspots.items()
        }
    }


@router.post("/click/{hwnd}")
async def click_window(hwnd: int, x_ratio: float = 0.5, y_ratio: float = 0.5):
    """
    点击窗口的相对位置
    
    Args:
        hwnd: 窗口句柄
        x_ratio: 水平相对位置 (0-1)
        y_ratio: 垂直相对位置 (0-1)
        
    Returns:
        点击结果
    """
    ctrl = _get_window_controller()
    
    if not ctrl.activate(hwnd):
        raise HTTPException(status_code=500, detail="无法激活窗口")
    
    rect = ctrl.get_window_rect(hwnd)
    if not rect:
        raise HTTPException(status_code=500, detail="无法获取窗口位置")
    
    left, top, right, bottom = rect
    x = left + int((right - left) * x_ratio)
    y = top + int((bottom - top) * y_ratio)
    
    if not ctrl.click_at(x, y):
        raise HTTPException(status_code=500, detail="点击失败")
    
    return {"success": True, "x": x, "y": y}


@router.post("/send/{hwnd}")
async def send_to_window(hwnd: int, text: str, hotspot: str = "input_box", press_enter: bool = True):
    """
    向窗口的指定热点发送文本指令
    
    Args:
        hwnd: 窗口句柄
        text: 要发送的文本
        hotspot: 热点名称（如 input_box）
        press_enter: 发送后是否按回车
        
    Returns:
        发送结果
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    star = state.orbit_engine.star_seeker.get_star(hwnd)
    star_type = star.star_type if star else "default"
    
    ctrl = _get_window_controller()
    hotspots = ctrl.get_hotspots(star_type)
    
    if hotspot not in hotspots:
        raise HTTPException(status_code=400, detail=f"未知热点: {hotspot}")
    
    hs = hotspots[hotspot]
    
    success = ctrl.send_to_hotspot(hwnd, hs, text)
    
    if success and press_enter:
        ctrl.press_enter()
    
    if not success:
        raise HTTPException(status_code=500, detail="发送失败")
    
    return {"success": True, "hotspot": hotspot, "text_length": len(text)}
```

- [ ] **步骤 2：在 main.py 中注册路由**

在 `star_api/main.py` 中，在导入路由的地方添加：
```python
from star_api.routes.remote import router as remote_router
```

在 `app.include_router(...)` 区域添加：
```python
app.include_router(remote_router, prefix="/api/remote", tags=["远程控制"])
```

- [ ] **步骤 3：验证 API**

启动服务后运行：
```
curl http://localhost:8767/api/remote/hotspots/trae
curl http://localhost:8767/api/remote/screenshot/9308954/status
```

---

## 任务 4：前端远程控制页面

**文件：**
- 创建：`star-ui/pages/remote.html`
- 修改：`star-ui/js/api-bridge.js`

### 步骤

- [ ] **步骤 1：在 api-bridge.js 中新增 remoteApi**

添加到 `star-ui/js/api-bridge.js` 末尾：

```javascript
const remoteApi = {
  getScreenshot: (hwnd, force = false) => 
    apiBase + '/remote/screenshot/' + hwnd + (force ? '?force=1' : ''),
  getScreenshotStatus: (hwnd) => apiFetch('/remote/screenshot/' + hwnd + '/status'),
  refreshScreenshot: (hwnd) => 
    apiFetch('/remote/screenshot/' + hwnd + '/refresh', { method: 'POST' }),
  getHotspots: (starType) => apiFetch('/remote/hotspots/' + starType),
  clickWindow: (hwnd, xRatio, yRatio) =>
    apiFetch('/remote/click/' + hwnd + '?x_ratio=' + xRatio + '&y_ratio=' + yRatio, { method: 'POST' }),
  sendText: (hwnd, text, hotspot = 'input_box', pressEnter = true) =>
    apiFetch('/remote/send/' + hwnd + '?text=' + encodeURIComponent(text) + 
      '&hotspot=' + hotspot + '&press_enter=' + pressEnter, { method: 'POST' }),
};
```

- [ ] **步骤 2：创建 remote.html 页面**

完整页面结构：
- 左侧：星体/窗口列表（树形，进程下挂窗口）
- 右侧：截图显示区 + 热点叠加层 + 状态栏
- 截图下方：当前间隔、上次刷新时间、强制刷新按钮
- 点击热点区域：弹出指令输入框

风格参考 starmap.html 的星空主题。

核心交互逻辑：
1. 页面加载时获取星体列表，渲染左侧
2. 选中窗口后，加载截图并启动轮询（根据 status 中的 interval 调整频率）
3. 截图上叠加热点高亮框（可点击）
4. 点击热点 → 弹出输入框 → 输入后发送 → 刷新截图

---

## 任务 5：集成与端到端验证

**文件：**
- 修改：`star_api/main.py`（挂载 remote.html 页面）
- 验证：无新文件

### 步骤

- [ ] **步骤 1：挂载远程控制页面**

在 `main.py` 中将 `star-ui/pages/remote.html` 挂载到 `/remote`

- [ ] **步骤 2：端到端验证**

1. 打开 http://localhost:8767/remote
2. 验证左侧显示 2 个星体共 7 个窗口
3. 点击一个窗口，截图加载成功
4. 点击"对话输入框"热点，输入"你好"，点击发送
5. 验证截图中 AI 已收到指令
6. 等待 1 分钟，验证间隔翻倍

---

## 注意事项

1. **pyautogui 是可选依赖**：回退方案用 ctypes 模拟鼠标键盘
2. **截图缓存**：用临时目录，有变化时才删旧图，避免磁盘占用
3. **窗口坐标计算**：要考虑多显示器、DPI 缩放
4. **热点配置**：从简单的比例+偏移开始，后续可以 OCR 校准
5. **安全**：远程控制是高权限功能，仅绑定 localhost
