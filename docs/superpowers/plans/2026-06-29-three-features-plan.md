# 三个核心功能实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为群星 Star 系统添加任务完成通知、批量群发指令、快捷指令模板三个核心功能

**架构：**
- 通知服务：独立的 notification-service.js 模块，提供统一的浏览器 Notification API 封装
- 模板服务：独立的 template-service.js 模块，管理 localStorage 中的模板数据
- 批量发送：后端 broadcast API + 前端 broadcast.html 页面
- 状态监控：复用 starfleet.html 的轮询机制，集成通知检测

**技术栈：** 原生 JavaScript、Browser Notification API、localStorage、FastAPI

---

## 文件结构

### 新建文件
- `star-ui/js/notification-service.js` - 通知服务模块
- `star-ui/js/template-service.js` - 模板服务模块
- `star-ui/pages/broadcast.html` - 批量群发指令页面

### 修改文件
- `star-ui/pages/starfleet.html` - 集成通知服务、添加批量选择 UI
- `star-ui/pages/settings.html` - 添加模板管理界面
- `star_api/routes/remote.py` - 添加批量发送 API
- `docs/superpowers/plans/2026-06-29-three-features-plan.md` - 本计划

---

## 任务分解

### 任务 1：通知服务模块（notification-service.js）

**文件：**
- 创建：`star-ui/js/notification-service.js`

- [ ] **步骤 1：创建通知服务模块**

```javascript
/**
 * notification-service.js - 任务完成通知服务
 * 
 * 功能：
 * - 请求通知权限
 * - 发送浏览器通知
 * - 音频提示
 * - 通知去重（5分钟内不重复）
 * - 状态变化检测
 */

class NotificationService {
    constructor() {
        this.enabled = false;
        this.soundEnabled = true;
        this.notifiedStars = new Map(); // star_id -> last_notify_time
        this.notifyCooldown = 5 * 60 * 1000; // 5分钟
        this.previousStatuses = new Map(); // 记录上一个状态
    }

    // 请求通知权限
    async requestPermission() {
        if (!('Notification' in window)) {
            console.warn('浏览器不支持通知');
            return false;
        }
        
        if (Notification.permission === 'granted') {
            this.enabled = true;
            return true;
        }
        
        if (Notification.permission !== 'denied') {
            const permission = await Notification.requestPermission();
            this.enabled = permission === 'granted';
            return this.enabled;
        }
        
        return false;
    }

    // 检查状态变化并发送通知
    checkAndNotify(starsData) {
        if (!this.enabled) return;
        
        for (const star of starsData.stars || []) {
            const starId = `${star.star_type}_${star.pid}`;
            const previousStatus = this.previousStatuses.get(starId);
            const currentStatus = star.overall_status;
            
            // 检测状态从工作/等待变为完成
            if (previousStatus && 
                (previousStatus === 'working' || previousStatus === 'waiting') &&
                currentStatus === 'completed') {
                
                // 检查是否在冷却期内
                if (this.isInCooldown(starId)) continue;
                
                // 发送通知
                this.notify(star);
                this.markNotified(starId);
            }
            
            // 更新状态记录
            this.previousStatuses.set(starId, currentStatus);
        }
    }

    // 发送通知
    notify(star) {
        const title = `${star.description || star.star_type} 任务完成`;
        
        // 获取任务摘要
        const taskPreview = star.windows?.[0]?.current_task || '未知任务';
        const body = taskPreview.length > 100 
            ? taskPreview.substring(0, 100) + '...' 
            : taskPreview;
        
        // 浏览器通知
        if (this.enabled) {
            const notification = new Notification(title, {
                body: body,
                icon: '/ui/icon.png',
                tag: `star_${star.star_type}_${star.pid}`,
                requireInteraction: true
            });
            
            notification.onclick = () => {
                window.focus();
                window.location.href = `/remote?hwnd=${star.windows?.[0]?.hwnd || ''}`;
                notification.close();
            };
        }
        
        // 音频提示
        if (this.soundEnabled) {
            this.playSound();
        }
    }

    // 播放提示音（使用 Web Audio API 生成简单音效）
    playSound() {
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.value = 800;
            oscillator.type = 'sine';
            gainNode.gain.value = 0.3;
            
            oscillator.start();
            
            setTimeout(() => {
                oscillator.stop();
                audioContext.close();
            }, 200);
        } catch (e) {
            console.warn('播放提示音失败:', e);
        }
    }

    isInCooldown(starId) {
        const lastNotify = this.notifiedStars.get(starId);
        if (!lastNotify) return false;
        return Date.now() - lastNotify < this.notifyCooldown;
    }

    markNotified(starId) {
        this.notifiedStars.set(starId, Date.now());
    }

    // 设置管理
    setEnabled(enabled) {
        this.enabled = enabled;
        localStorage.setItem('star_notification_enabled', enabled);
    }

    setSoundEnabled(enabled) {
        this.soundEnabled = enabled;
        localStorage.setItem('star_notification_sound', enabled);
    }

    loadSettings() {
        this.enabled = localStorage.getItem('star_notification_enabled') === 'true';
        this.soundEnabled = localStorage.getItem('star_notification_sound') !== 'false';
    }
}

// 导出单例
const notificationService = new NotificationService();
notificationService.loadSettings();
```

- [ ] **步骤 2：Commit**

```bash
git add star-ui/js/notification-service.js
git commit -m "feat: add notification service module for task completion alerts"
```

---

### 任务 2：模板服务模块（template-service.js）

**文件：**
- 创建：`star-ui/js/template-service.js`

- [ ] **步骤 1：创建模板服务模块**

```javascript
/**
 * template-service.js - 快捷指令模板服务
 * 
 * 功能：
 * - 预设模板
 * - 用户自定义模板 CRUD
 * - 变量替换
 * - 导入导出
 */

class TemplateService {
    constructor() {
        this.storageKey = 'star_command_templates';
        this.defaultTemplates = [
            {
                id: 'explain',
                name: '解释代码',
                content: '解释以下代码的作用：\n{selection}',
                variables: ['selection']
            },
            {
                id: 'optimize',
                name: '优化函数',
                content: '优化以下函数，提高性能和可读性：\n{selection}',
                variables: ['selection']
            },
            {
                id: 'review',
                name: '代码审查',
                content: '对以下代码进行审查，指出潜在问题和改进建议：\n{selection}',
                variables: ['selection']
            },
            {
                id: 'test',
                name: '生成测试',
                content: '为以下代码生成单元测试：\n{selection}',
                variables: ['selection']
            },
            {
                id: 'translate',
                name: '翻译注释',
                content: '将以下代码的注释翻译成中文：\n{selection}',
                variables: ['selection']
            },
            {
                id: 'fixbug',
                name: '修复 Bug',
                content: '修复以下代码中的 Bug：\n{selection}',
                variables: ['selection']
            }
        ];
    }

    // 获取所有模板
    getAll() {
        const stored = localStorage.getItem(this.storageKey);
        if (stored) {
            try {
                return JSON.parse(stored);
            } catch {
                return this.defaultTemplates;
            }
        }
        return this.defaultTemplates;
    }

    // 保存所有模板
    saveAll(templates) {
        localStorage.setItem(this.storageKey, JSON.stringify(templates));
    }

    // 获取单个模板
    getById(id) {
        const templates = this.getAll();
        return templates.find(t => t.id === id);
    }

    // 添加模板
    add(template) {
        const templates = this.getAll();
        template.id = 'custom_' + Date.now();
        templates.push(template);
        this.saveAll(templates);
        return template;
    }

    // 更新模板
    update(id, updates) {
        const templates = this.getAll();
        const index = templates.findIndex(t => t.id === id);
        if (index >= 0) {
            templates[index] = { ...templates[index], ...updates };
            this.saveAll(templates);
            return templates[index];
        }
        return null;
    }

    // 删除模板
    delete(id) {
        const templates = this.getAll();
        const filtered = templates.filter(t => t.id !== id);
        this.saveAll(filtered);
    }

    // 替换变量
    render(template, context = {}) {
        let content = template.content;
        for (const [key, value] of Object.entries(context)) {
            const regex = new RegExp(`\\{${key}\\}`, 'g');
            content = content.replace(regex, value);
        }
        return content;
    }

    // 导出模板
    export() {
        const templates = this.getAll();
        const customTemplates = templates.filter(t => t.id.startsWith('custom_'));
        return JSON.stringify(customTemplates, null, 2);
    }

    // 导入模板
    import(jsonString) {
        try {
            const imported = JSON.parse(jsonString);
            if (Array.isArray(imported)) {
                const templates = this.getAll();
                for (const t of imported) {
                    t.id = 'custom_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
                    templates.push(t);
                }
                this.saveAll(templates);
                return { success: true, count: imported.length };
            }
            return { success: false, error: 'Invalid format' };
        } catch (e) {
            return { success: false, error: e.message };
        }
    }

    // 重置为默认模板
    reset() {
        localStorage.removeItem(this.storageKey);
    }
}

// 导出单例
const templateService = new TemplateService();
```

- [ ] **步骤 2：Commit**

```bash
git add star-ui/js/template-service.js
git commit -m "feat: add template service module for command templates"
```

---

### 任务 3：后端批量发送 API

**文件：**
- 修改：`star_api/routes/remote.py`

- [ ] **步骤 1：添加批量发送 API**

在 remote.py 末尾添加：

```python
# ==================== 批量群发指令 ====================

@router.post("/broadcast/send", dependencies=[Depends(require_control)])
async def broadcast_send(
    hwids: list[int],
    text: str,
    parallel: bool = True,
):
    """
    批量发送指令到多个窗口
    
    Args:
        hwids: 窗口句柄列表
        text: 要发送的指令文本
        parallel: 是否并行发送（默认 True）
    """
    from star_core.star_emissary import StarEmissary
    from star_core.star_seeker import StarSeeker
    import asyncio

    if state.orbit_engine is None or state.orbit_engine.star_seeker is None:
        raise HTTPException(status_code=503, detail="星核未初始化")

    seeker = state.orbit_engine.star_seeker
    results = []

    async def send_to_hwnd(hwnd: int):
        try:
            star = seeker.get_star(hwnd)
            if not star:
                return {"hwnd": hwnd, "success": False, "error": "Star not found"}

            # 获取适配器
            from star_core.star_emissary import StarAdapter
            adapter = StarAdapter.from_star_type(star.star_type)
            emissary = StarEmissary(star=star, adapter_name=adapter.config.name)

            # 发送指令
            success = emissary.send_prompt(text)
            audit('broadcast_send', hwnd=hwnd, params={'text_length': len(text)})

            return {
                "hwnd": hwnd,
                "success": success,
                "star_type": star.star_type,
                "title": star.title
            }
        except Exception as e:
            return {"hwnd": hwnd, "success": False, "error": str(e)}

    # 并行或串行执行
    if parallel:
        tasks = [send_to_hwnd(hwnd) for hwnd in hwids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # 处理异常
        results = [
            r if not isinstance(r, Exception) else {"error": str(r)}
            for r in results
        ]
    else:
        for hwnd in hwids:
            results.append(await send_to_hwnd(hwnd))

    return {
        "success": True,
        "total": len(hwids),
        "sent": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "results": results
    }


@router.get("/broadcast/status/{hwnd}", dependencies=[Depends(require_read)])
async def get_broadcast_status(hwnd: int):
    """
    获取窗口当前状态（用于轮询批量指令结果）
    """
    try:
        from star_core.ocr_gazer import OCRGazer
        from star_core.star_seeker import StarSeeker

        if state.orbit_engine is None:
            raise HTTPException(status_code=503, detail="星核未初始化")

        seeker = state.orbit_engine.star_seeker
        star = seeker.get_star(hwnd)

        if not star:
            raise HTTPException(status_code=404, detail="窗口未找到")

        ocr = OCRGazer()
        status = ocr.get_current_status(star)

        return {
            "hwnd": hwnd,
            "status": status.get("status", "unknown"),
            "is_active": status.get("is_active", False),
            "current_task": status.get("current_task"),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"hwnd": hwnd, "status": "error", "error": str(e)}
```

- [ ] **步骤 2：Commit**

```bash
git add star_api/routes/remote.py
git commit -m "feat: add broadcast API for sending commands to multiple AIs"
```

---

### 任务 4：星群状态页增强（starfleet.html）

**文件：**
- 修改：`star-ui/pages/starfleet.html`

- [ ] **步骤 1：添加勾选框和通知集成**

在页面顶部添加选择工具栏和通知状态指示器：

```html
<!-- 在 <div class="main-content"> 之前添加 -->
<div class="toolbar" style="
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 24px;
    background: var(--color-bg-panel);
    border-bottom: 1px solid var(--color-border);
">
    <div class="selection-controls">
        <label style="display: flex; align-items: center; gap: 6px; cursor: pointer;">
            <input type="checkbox" id="selectAll" onchange="toggleSelectAll()">
            <span style="font-size: 13px;">全选</span>
        </label>
        <span id="selectedCount" style="font-size: 12px; color: var(--color-text-muted); margin-left: 8px;">
            已选 0 个
        </span>
    </div>
    <div style="flex: 1;"></div>
    <button id="broadcastBtn" class="btn btn-primary btn-sm" onclick="openBroadcast()" disabled>
        <i data-icon="radio" style="width:14px;height:14px;"></i>
        批量发送指令
    </button>
    <div class="notification-status" id="notifStatus" style="
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        color: var(--color-text-muted);
    ">
        <span class="status-dot" style="
            width: 8px; height: 8px; border-radius: 50%;
            background: var(--color-text-muted);
        "></span>
        <span>通知已关闭</span>
        <button onclick="requestNotification()" class="btn btn-sm" style="margin-left: 4px;">
            开启
        </button>
    </div>
</div>
```

- [ ] **步骤 2：添加通知状态指示器样式**

在 `<style>` 中添加：

```css
.notification-status .status-dot.allowed {
    background: var(--color-success);
}
.notification-status .status-dot.denied {
    background: var(--color-danger);
}
```

- [ ] **步骤 3：修改 JavaScript**

在 `<script>` 中添加：

```javascript
// 添加到 script 开头
let selectedStars = new Set();
let notificationService = null;

// 修改 fetchStarsStatus 函数
async function fetchStarsStatus() {
    try {
        const resp = await fetch('/api/remote/stars/status');
        const data = await resp.json();

        if (data.success) {
            lastData = data;
            
            // 检查状态变化并发送通知
            if (notificationService) {
                notificationService.checkAndNotify(data);
            }
            
            renderStarsStatus(data);
        }
    } catch (err) {
        console.error('Failed to fetch stars status:', err);
    }
}

// 修改 renderStarsStatus 函数，在 star-card-header 中添加 checkbox
// 找到 <div class="star-status-dot ${statusClass}"></div> 
// 在其后面添加：
const isSelected = selectedStars.has(`${star.star_type}_${star.pid}`);
return `
<div class="star-card ${statusClass}">
    <div class="star-card-header">
        <input type="checkbox" 
            ${isSelected ? 'checked' : ''} 
            onchange="toggleStarSelection('${star.star_type}_${star.pid}')"
            style="margin-right: 8px; cursor: pointer;">
        <div class="star-status-dot ${statusClass}"></div>
        ...
`;

// 添加新函数
function toggleStarSelection(starId) {
    if (selectedStars.has(starId)) {
        selectedStars.delete(starId);
    } else {
        selectedStars.add(starId);
    }
    updateSelectionUI();
}

function toggleSelectAll() {
    const selectAll = document.getElementById('selectAll');
    if (selectAll.checked) {
        lastData?.stars?.forEach(s => {
            selectedStars.add(`${s.star_type}_${s.pid}`);
        });
    } else {
        selectedStars.clear();
    }
    updateSelectionUI();
    renderStarsStatus(lastData);
}

function updateSelectionUI() {
    const count = selectedStars.size;
    document.getElementById('selectedCount').textContent = `已选 ${count} 个`;
    document.getElementById('broadcastBtn').disabled = count === 0;
    
    // 更新全选框状态
    const selectAll = document.getElementById('selectAll');
    if (lastData?.stars) {
        selectAll.checked = selectedStars.size === lastData.stars.length;
        selectAll.indeterminate = selectedStars.size > 0 && selectedStars.size < lastData.stars.length;
    }
}

function openBroadcast() {
    if (selectedStars.size === 0) return;
    
    // 构建选中的 hwnd 列表
    const hwids = [];
    lastData?.stars?.forEach(s => {
        const starId = `${s.star_type}_${s.pid}`;
        if (selectedStars.has(starId)) {
            hwids.push(s.windows?.[0]?.hwnd);
        }
    });
    
    // 打开广播页面
    window.open(`/ui/pages/broadcast.html?hwids=${hwids.join(',')}`, '_blank', 'width=800,height=600');
}

// 通知相关
async function requestNotification() {
    try {
        const resp = await fetch('/ui/js/notification-service.js');
        const text = await resp.text();
        eval(text);
        
        // 重新加载通知服务
        const script = document.createElement('script');
        script.textContent = text + '; notificationService.requestPermission().then(granted => { updateNotifStatus(granted); });';
        document.head.appendChild(script);
        
        // 初始化通知服务
        if (typeof notificationService === 'undefined' || notificationService === null) {
            // 从全局获取
            notificationService = window.notificationService || new NotificationService();
        }
        
        await notificationService.requestPermission();
        updateNotifStatus(notificationService.enabled);
    } catch (err) {
        console.error('Failed to init notification:', err);
    }
}

function updateNotifStatus(enabled) {
    const statusEl = document.getElementById('notifStatus');
    const dot = statusEl.querySelector('.status-dot');
    const text = statusEl.querySelector('span:last-child');
    const btn = statusEl.querySelector('button');
    
    if (enabled) {
        dot.className = 'status-dot allowed';
        text.textContent = '通知已开启';
        btn.style.display = 'none';
    } else {
        dot.className = 'status-dot denied';
        text.textContent = '通知未开启';
        btn.textContent = '重试';
    }
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', async () => {
    // 尝试加载通知服务
    try {
        const resp = await fetch('/ui/js/notification-service.js');
        const text = await resp.text();
        const script = document.createElement('script');
        script.textContent = text;
        document.head.appendChild(script);
        notificationService = window.notificationService;
        
        if (notificationService?.enabled) {
            updateNotifStatus(true);
        }
    } catch (err) {
        console.warn('Notification service not available');
    }
});
```

- [ ] **步骤 4：Commit**

```bash
git add star-ui/pages/starfleet.html
git commit -m "feat: enhance starfleet page with batch selection and notifications"
```

---

### 任务 5：批量发送页面（broadcast.html）

**文件：**
- 创建：`star-ui/pages/broadcast.html`

- [ ] **步骤 1：创建批量发送页面**

```html
<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>批量发送指令 — 群星 Star</title>
    <style id="theme-vars">
:root {
  --color-bg-deep: #0a0e27;
  --color-bg-panel: #1a1f3a;
  --color-bg-card: #151934;
  --color-bg-elevated: #212647;
  --color-bg-hover: #2a3058;
  --color-primary: #ffd700;
  --color-primary-dim: rgba(255, 215, 0, 0.15);
  --color-success: #10b981;
  --color-warning: #f59e0b;
  --color-danger: #ef4444;
  --color-text-primary: #e8eaf6;
  --color-text-secondary: #9fa8da;
  --color-text-muted: #616885;
  --color-border: rgba(255, 255, 255, 0.08);
  --font-display: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Consolas', monospace;
  --radius-md: 8px;
  --radius-lg: 12px;
}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4.3.1/dist/index.global.js"></script>
    <script src="/ui/js/template-service.js"></script>
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body {
        background: var(--color-bg-deep);
        color: var(--color-text-primary);
        font-family: var(--font-display);
        padding: 20px;
      }
      .header {
        margin-bottom: 20px;
      }
      .header h1 {
        font-size: 18px;
        font-weight: 600;
        margin-bottom: 8px;
      }
      .selected-stars {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 16px;
      }
      .star-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        background: var(--color-bg-elevated);
        border-radius: 20px;
        font-size: 12px;
      }
      .input-section {
        margin-bottom: 16px;
      }
      .input-section label {
        display: block;
        font-size: 13px;
        color: var(--color-text-secondary);
        margin-bottom: 8px;
      }
      .template-select {
        margin-bottom: 8px;
      }
      .template-select select {
        padding: 8px 12px;
        background: var(--color-bg-elevated);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        color: var(--color-text-primary);
        font-size: 13px;
        min-width: 200px;
      }
      textarea {
        width: 100%;
        min-height: 120px;
        padding: 12px;
        background: var(--color-bg-elevated);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        color: var(--color-text-primary);
        font-family: var(--font-mono);
        font-size: 13px;
        resize: vertical;
      }
      textarea:focus {
        outline: none;
        border-color: var(--color-primary);
      }
      .btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 10px 20px;
        border-radius: var(--radius-md);
        font-size: 14px;
        cursor: pointer;
        border: none;
        transition: opacity 0.2s;
      }
      .btn:hover { opacity: 0.9; }
      .btn-primary {
        background: var(--color-primary);
        color: #1a1f3a;
        font-weight: 500;
      }
      .btn-secondary {
        background: var(--color-bg-elevated);
        color: var(--color-text-primary);
        border: 1px solid var(--color-border);
      }
      .results-section {
        margin-top: 24px;
      }
      .results-section h2 {
        font-size: 14px;
        color: var(--color-text-secondary);
        margin-bottom: 12px;
      }
      .results-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 12px;
      }
      .result-card {
        background: var(--color-bg-card);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-lg);
        padding: 12px;
      }
      .result-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
      }
      .result-status {
        width: 8px;
        height: 8px;
        border-radius: 50%;
      }
      .result-status.pending { background: var(--color-text-muted); }
      .result-status.sending { background: var(--color-warning); animation: pulse 1s infinite; }
      .result-status.completed { background: var(--color-success); }
      .result-status.error { background: var(--color-danger); }
      @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
      .result-title {
        font-size: 13px;
        font-weight: 500;
        flex: 1;
      }
      .result-body {
        font-size: 12px;
        color: var(--color-text-secondary);
        line-height: 1.5;
        max-height: 100px;
        overflow: hidden;
      }
      .result-time {
        font-size: 11px;
        color: var(--color-text-muted);
        margin-top: 6px;
      }
      .variable-hint {
        font-size: 11px;
        color: var(--color-text-muted);
        margin-top: 4px;
      }
    </style>
</head>
<body>
    <div class="header">
        <h1>批量发送指令</h1>
        <div class="selected-stars" id="selectedStars"></div>
    </div>

    <div class="input-section">
        <label>快捷模板</label>
        <div class="template-select">
            <select id="templateSelect" onchange="loadTemplate()">
                <option value="">— 选择模板（可选）—</option>
            </select>
        </div>
        
        <label>指令内容</label>
        <textarea id="commandInput" placeholder="输入要发送给所有选中 AI 的指令..."></textarea>
        <div class="variable-hint">
            支持变量：{selection} 选中文本、{file} 当前文件、{project} 项目名
        </div>
    </div>

    <div style="display: flex; gap: 12px;">
        <button class="btn btn-primary" onclick="sendCommands()">
            📡 发送指令
        </button>
        <button class="btn btn-secondary" onclick="window.close()">
            关闭
        </button>
    </div>

    <div class="results-section" id="resultsSection" style="display: none;">
        <h2>发送结果</h2>
        <div class="results-grid" id="resultsGrid"></div>
    </div>

    <script>
        let hwids = [];
        let starsInfo = [];

        // 初始化
        async function init() {
            // 解析 URL 参数
            const params = new URLSearchParams(window.location.search);
            hwids = (params.get('hwids') || '').split(',').filter(h => h).map(Number);
            
            if (hwids.length === 0) {
                alert('没有选择任何 AI');
                window.close();
                return;
            }

            // 加载模板
            loadTemplates();
            
            // 获取 AI 信息
            await loadStarsInfo();
            
            // 显示选中的 AI
            renderSelectedStars();
        }

        function loadTemplates() {
            const select = document.getElementById('templateSelect');
            const templates = templateService.getAll();
            
            templates.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.name;
                select.appendChild(opt);
            });
        }

        function loadTemplate() {
            const select = document.getElementById('templateSelect');
            const textarea = document.getElementById('commandInput');
            
            if (select.value) {
                const template = templateService.getById(select.value);
                if (template) {
                    textarea.value = template.content;
                }
            }
        }

        async function loadStarsInfo() {
            try {
                const resp = await fetch('/api/remote/stars/status');
                const data = await resp.json();
                
                if (data.success) {
                    starsInfo = [];
                    for (const star of data.stars) {
                        for (const window of star.windows || []) {
                            if (hwids.includes(window.hwnd)) {
                                starsInfo.push({
                                    hwnd: window.hwnd,
                                    name: star.description || star.star_type,
                                    title: star.title,
                                    status: 'pending'
                                });
                            }
                        }
                    }
                }
            } catch (err) {
                console.error('Failed to load stars info:', err);
            }
        }

        function renderSelectedStars() {
            const container = document.getElementById('selectedStars');
            container.innerHTML = starsInfo.map(s => `
                <span class="star-chip">
                    <span style="width:6px;height:6px;border-radius:50%;background:var(--color-primary);"></span>
                    ${s.name}
                </span>
            `).join('');
        }

        async function sendCommands() {
            const text = document.getElementById('commandInput').value.trim();
            if (!text) {
                alert('请输入指令内容');
                return;
            }

            // 显示结果区域
            document.getElementById('resultsSection').style.display = 'block';
            
            // 渲染初始状态
            const grid = document.getElementById('resultsGrid');
            grid.innerHTML = starsInfo.map(s => `
                <div class="result-card" id="result-${s.hwnd}">
                    <div class="result-header">
                        <span class="result-status pending"></span>
                        <span class="result-title">${s.name}</span>
                    </div>
                    <div class="result-body">等待发送...</div>
                    <div class="result-time"></div>
                </div>
            `).join('');

            // 发送指令
            for (const star of starsInfo) {
                const card = document.getElementById(`result-${star.hwnd}`);
                const statusDot = card.querySelector('.result-status');
                const body = card.querySelector('.result-body');
                const time = card.querySelector('.result-time');

                // 更新状态为发送中
                statusDot.className = 'result-status sending';
                body.textContent = '正在发送...';

                try {
                    const resp = await fetch('/api/remote/broadcast/send', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            hwids: [star.hwnd],
                            text: text,
                            parallel: false
                        })
                    });
                    
                    const result = await resp.json();
                    
                    if (result.success && result.results?.[0]?.success) {
                        statusDot.className = 'result-status completed';
                        body.textContent = '指令已发送，等待响应...';
                        star.status = 'sent';
                    } else {
                        statusDot.className = 'result-status error';
                        body.textContent = '发送失败: ' + (result.results?.[0]?.error || '未知错误');
                    }
                } catch (err) {
                    statusDot.className = 'result-status error';
                    body.textContent = '发送失败: ' + err.message;
                }

                time.textContent = `发送时间: ${new Date().toLocaleTimeString()}`;
            }
        }

        init();
    </script>
</body>
</html>
```

- [ ] **步骤 2：Commit**

```bash
git add star-ui/pages/broadcast.html
git commit -m "feat: add broadcast page for batch command sending"
```

---

### 任务 6：设置页模板管理（settings.html）

**文件：**
- 修改：`star-ui/pages/settings.html`

- [ ] **步骤 1：添加模板管理界面**

在 settings.html 中找到合适的位置（通知设置附近），添加：

```html
<!-- 添加到通知设置之后 -->

<div class="settings-section" style="margin-top: 32px;">
    <h3 style="font-size: 15px; font-weight: 600; margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
        <span>📋</span> 快捷指令模板
    </h3>
    
    <div style="background: var(--color-bg-card); border-radius: 12px; padding: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <span style="font-size: 13px; color: var(--color-text-secondary);">
                自定义快捷指令，一键发送
            </span>
            <button class="btn btn-sm" onclick="showAddTemplateModal()" style="
                background: var(--color-primary);
                color: #1a1f3a;
                border: none;
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 12px;
                cursor: pointer;
            ">+ 添加模板</button>
        </div>
        
        <div id="templateList" style="display: flex; flex-direction: column; gap: 8px;">
            <!-- 动态渲染 -->
        </div>
        
        <div style="display: flex; gap: 12px; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--color-border);">
            <button class="btn btn-sm" onclick="exportTemplates()" style="
                background: var(--color-bg-elevated);
                color: var(--color-text-primary);
                border: 1px solid var(--color-border);
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 12px;
                cursor: pointer;
            ">导出模板</button>
            <label class="btn btn-sm" style="
                background: var(--color-bg-elevated);
                color: var(--color-text-primary);
                border: 1px solid var(--color-border);
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 12px;
                cursor: pointer;
            ">
                导入模板
                <input type="file" accept=".json" onchange="importTemplates(event)" style="display: none;">
            </label>
            <button class="btn btn-sm" onclick="resetTemplates()" style="
                background: transparent;
                color: var(--color-danger);
                border: 1px solid var(--color-danger);
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 12px;
                cursor: pointer;
                margin-left: auto;
            ">重置为默认</button>
        </div>
    </div>
</div>

<!-- 添加/编辑模板模态框 -->
<div id="templateModal" style="
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.6);
    z-index: 1000;
    align-items: center;
    justify-content: center;
">
    <div style="
        background: var(--color-bg-panel);
        border-radius: 12px;
        padding: 24px;
        width: 480px;
        max-width: 90%;
    ">
        <h3 id="modalTitle" style="font-size: 16px; font-weight: 600; margin-bottom: 16px;">添加模板</h3>
        
        <div style="margin-bottom: 12px;">
            <label style="display: block; font-size: 12px; color: var(--color-text-muted); margin-bottom: 4px;">模板名称</label>
            <input type="text" id="templateName" style="
                width: 100%;
                padding: 8px 12px;
                background: var(--color-bg-elevated);
                border: 1px solid var(--color-border);
                border-radius: 6px;
                color: var(--color-text-primary);
                font-size: 13px;
            ">
        </div>
        
        <div style="margin-bottom: 16px;">
            <label style="display: block; font-size: 12px; color: var(--color-text-muted); margin-bottom: 4px;">
                指令内容 <span style="color: var(--color-text-muted); font-size: 11px;">（支持 {selection}、{file}、{project} 变量）</span>
            </label>
            <textarea id="templateContent" rows="5" style="
                width: 100%;
                padding: 8px 12px;
                background: var(--color-bg-elevated);
                border: 1px solid var(--color-border);
                border-radius: 6px;
                color: var(--color-text-primary);
                font-size: 13px;
                font-family: var(--font-mono);
                resize: vertical;
            "></textarea>
        </div>
        
        <div style="display: flex; gap: 12px; justify-content: flex-end;">
            <button onclick="closeTemplateModal()" style="
                padding: 8px 16px;
                background: var(--color-bg-elevated);
                border: 1px solid var(--color-border);
                border-radius: 6px;
                color: var(--color-text-primary);
                cursor: pointer;
            ">取消</button>
            <button onclick="saveTemplate()" style="
                padding: 8px 16px;
                background: var(--color-primary);
                border: none;
                border-radius: 6px;
                color: #1a1f3a;
                font-weight: 500;
                cursor: pointer;
            ">保存</button>
        </div>
    </div>
</div>
```

- [ ] **步骤 2：添加模板管理 JavaScript**

在 settings.html 的 `<script>` 部分添加：

```javascript
// 模板管理
let editingTemplateId = null;

function loadTemplateList() {
    const container = document.getElementById('templateList');
    if (!container) return;
    
    const templates = templateService.getAll();
    container.innerHTML = templates.map(t => `
        <div style="
            display: flex;
            align-items: center;
            padding: 10px 12px;
            background: var(--color-bg-elevated);
            border-radius: 8px;
            gap: 12px;
        ">
            <span style="font-size: 13px; flex: 1;">${escapeHtml(t.name)}</span>
            <span style="font-size: 11px; color: var(--color-text-muted); flex: 2; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(t.content)}">
                ${escapeHtml(t.content.substring(0, 40))}...
            </span>
            <div style="display: flex; gap: 4px;">
                <button onclick="editTemplate('${t.id}')" style="
                    padding: 4px 8px;
                    background: transparent;
                    border: 1px solid var(--color-border);
                    border-radius: 4px;
                    color: var(--color-text-secondary);
                    font-size: 11px;
                    cursor: pointer;
                ">编辑</button>
                <button onclick="deleteTemplate('${t.id}')" style="
                    padding: 4px 8px;
                    background: transparent;
                    border: 1px solid var(--color-danger);
                    border-radius: 4px;
                    color: var(--color-danger);
                    font-size: 11px;
                    cursor: pointer;
                ">删除</button>
            </div>
        </div>
    `).join('');
}

function showAddTemplateModal() {
    editingTemplateId = null;
    document.getElementById('modalTitle').textContent = '添加模板';
    document.getElementById('templateName').value = '';
    document.getElementById('templateContent').value = '';
    document.getElementById('templateModal').style.display = 'flex';
}

function editTemplate(id) {
    const template = templateService.getById(id);
    if (!template) return;
    
    editingTemplateId = id;
    document.getElementById('modalTitle').textContent = '编辑模板';
    document.getElementById('templateName').value = template.name;
    document.getElementById('templateContent').value = template.content;
    document.getElementById('templateModal').style.display = 'flex';
}

function closeTemplateModal() {
    document.getElementById('templateModal').style.display = 'none';
    editingTemplateId = null;
}

function saveTemplate() {
    const name = document.getElementById('templateName').value.trim();
    const content = document.getElementById('templateContent').value.trim();
    
    if (!name || !content) {
        alert('请填写名称和内容');
        return;
    }
    
    if (editingTemplateId) {
        templateService.update(editingTemplateId, { name, content });
    } else {
        templateService.add({ name, content, variables: [] });
    }
    
    closeTemplateModal();
    loadTemplateList();
}

function deleteTemplate(id) {
    if (!confirm('确定要删除这个模板吗？')) return;
    templateService.delete(id);
    loadTemplateList();
}

function exportTemplates() {
    const json = templateService.export();
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'star-templates.json';
    a.click();
    URL.revokeObjectURL(url);
}

function importTemplates(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const reader = new FileReader();
    reader.onload = function(e) {
        const result = templateService.import(e.target.result);
        if (result.success) {
            alert(`成功导入 ${result.count} 个模板`);
            loadTemplateList();
        } else {
            alert('导入失败: ' + result.error);
        }
    };
    reader.readAsText(file);
    event.target.value = '';
}

function resetTemplates() {
    if (!confirm('确定要重置为默认模板吗？这将删除所有自定义模板。')) return;
    templateService.reset();
    loadTemplateList();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
    // 加载模板列表
    loadTemplateList();
    
    // 加载通知设置
    loadNotificationSettings();
});
```

- [ ] **步骤 3：Commit**

```bash
git add star-ui/pages/settings.html
git commit -m "feat: add template management UI in settings page"
```

---

### 任务 7：导航更新

**文件：**
- 修改：`star-ui/pages/starmap.html`

- [ ] **步骤 1：在导航栏添加批量发送入口**

在星图面板的导航栏添加批量发送快捷入口：

在现有导航项中添加：

```html
<!-- 在星群状态入口后添加 -->
<a href="/ui/pages/broadcast.html" title="Batch Send" data-dom-id="nav-broadcast"
   class="relative flex items-center justify-center w-10 h-10 transition-all duration-200"
   style="color:var(--color-text-muted);border-left:3px solid transparent;">
    <i data-lucide="radio" class="w-5 h-5"></i>
</a>
```

- [ ] **步骤 2：Commit**

```bash
git add star-ui/pages/starmap.html
git commit -m "feat: add broadcast page link in navigation"
```

---

### 任务 8：功能测试与集成

- [ ] **步骤 1：测试通知服务**
   - 启动 API 服务
   - 访问 starfleet.html
   - 开启通知权限
   - 观察控制台是否有错误

- [ ] **步骤 2：测试批量发送**
   - 在星群状态页选择多个 AI
   - 点击批量发送
   - 验证指令是否正确发送

- [ ] **步骤 3：测试模板管理**
   - 在设置页添加/编辑/删除模板
   - 导出/导入模板
   - 重置为默认

- [ ] **步骤 4：运行所有测试**

```bash
cd g:\traework\star
E:\py312\python.exe -m pytest tests/ -v --tb=short
```

预期：所有测试通过

---

## 规格覆盖度检查

| 功能 | 规格要求 | 实现任务 |
|------|---------|---------|
| 任务完成通知 | 浏览器通知 + 声音 + 去重 | 任务 1, 4 |
| 批量群发指令 | 多选 + 统一指令 + 结果展示 | 任务 3, 4, 5 |
| 快捷指令模板 | 预设模板 + 自定义 + 变量替换 | 任务 2, 6 |
| 导航入口 | 侧边栏快捷入口 | 任务 7 |

**所有规格需求都有对应实现任务。**

---

## 执行方式

**推荐：子代理驱动（subagent-driven-development）**

每个任务调度一个子代理并行执行，提高效率。任务间相对独立，可以并行开发：
- 任务 1 和 2（两个 JS 服务模块）可以并行
- 任务 3（后端 API）独立
- 任务 4, 5, 6（前端页面）可以并行
- 任务 7, 8（导航 + 测试）最后执行
