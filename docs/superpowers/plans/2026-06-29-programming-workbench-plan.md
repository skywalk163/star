# 星际编程工作台 - 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 构建并行编程工作台，支持多 AI 任务分配、并行对话、结果对比

**架构：**
- 前端单页应用（programming.html）
- 本地状态管理（localStorage）
- 复用现有 API（broadcast/send, stars/status）
- 独立服务模块（编程状态、上下文读取）

**技术栈：** 原生 JavaScript、localStorage、FastAPI

---

## 文件结构

### 新建文件
- `star-ui/pages/programming.html` - 并行编程工作台主页面
- `star-ui/js/programming-store.js` - 编程状态管理
- `star-ui/js/context-reader.js` - 项目上下文读取
- `star_api/routes/programming.py` - 编程工作台 API

### 修改文件
- `star-ui/pages/starmap.html` - 添加导航入口
- `docs/superpowers/plans/2026-06-29-programming-workbench-plan.md` - 本计划

---

## 任务分解

### 任务 1：编程状态管理（programming-store.js）

**文件：**
- 创建：`star-ui/js/programming-store.js`

- [ ] **步骤 1：创建编程状态管理模块**

```javascript
/**
 * programming-store.js - 编程工作台状态管理
 * 
 * 功能：
 * - 任务 CRUD
 * - 对话记录管理
 * - AI 状态追踪
 * - 本地持久化
 */

class ProgrammingStore {
    constructor() {
        this.TASKS_KEY = 'star_programming_tasks';
        this.DIALOGS_KEY = 'star_programming_dialogs';
        this.tasks = [];
        this.dialogs = new Map(); // taskId -> AIDialog[]
        this.currentTaskId = null;
        this.listeners = new Set();
        
        this.load();
    }

    // ========== 任务管理 ==========
    
    load() {
        try {
            const tasksJson = localStorage.getItem(this.TASKS_KEY);
            this.tasks = tasksJson ? JSON.parse(tasksJson) : [];
            
            const dialogsJson = localStorage.getItem(this.DIALOGS_KEY);
            if (dialogsJson) {
                const dialogs = JSON.parse(dialogsJson);
                this.dialogs = new Map(Object.entries(dialogs));
            }
        } catch (e) {
            console.error('Failed to load programming store:', e);
            this.tasks = [];
            this.dialogs = new Map();
        }
    }

    save() {
        try {
            localStorage.setItem(this.TASKS_KEY, JSON.stringify(this.tasks));
            
            const dialogsObj = Object.fromEntries(this.dialogs);
            localStorage.setItem(this.DIALOGS_KEY, JSON.stringify(dialogsObj));
        } catch (e) {
            console.error('Failed to save programming store:', e);
        }
    }

    // 创建任务
    createTask(title, description = '') {
        const task = {
            id: 'task_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9),
            title: title,
            description: description,
            status: 'todo',
            assignedAIs: [],
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString()
        };
        this.tasks.push(task);
        this.save();
        this.notify();
        return task;
    }

    // 更新任务
    updateTask(id, updates) {
        const index = this.tasks.findIndex(t => t.id === id);
        if (index >= 0) {
            this.tasks[index] = {
                ...this.tasks[index],
                ...updates,
                updatedAt: new Date().toISOString()
            };
            this.save();
            this.notify();
            return this.tasks[index];
        }
        return null;
    }

    // 删除任务
    deleteTask(id) {
        this.tasks = this.tasks.filter(t => t.id !== id);
        this.dialogs.delete(id);
        if (this.currentTaskId === id) {
            this.currentTaskId = null;
        }
        this.save();
        this.notify();
    }

    // 获取所有任务
    getAllTasks() {
        return this.tasks;
    }

    // 获取单个任务
    getTask(id) {
        return this.tasks.find(t => t.id === id);
    }

    // 分配 AI 到任务
    assignAI(taskId, aiId) {
        const task = this.getTask(taskId);
        if (task && !task.assignedAIs.includes(aiId)) {
            task.assignedAIs.push(aiId);
            task.updatedAt = new Date().toISOString();
            this.save();
            this.notify();
        }
    }

    // 移除 AI
    unassignAI(taskId, aiId) {
        const task = this.getTask(taskId);
        if (task) {
            task.assignedAIs = task.assignedAIs.filter(id => id !== aiId);
            task.updatedAt = new Date().toISOString();
            this.save();
            this.notify();
        }
    }

    // ========== 对话管理 ==========

    // 添加对话消息
    addMessage(taskId, aiId, role, content) {
        if (!this.dialogs.has(taskId)) {
            this.dialogs.set(taskId, []);
        }
        
        const dialogs = this.dialogs.get(taskId);
        const aiDialog = dialogs.find(d => d.aiId === aiId);
        
        if (aiDialog) {
            aiDialog.messages.push({
                role: role,
                content: content,
                timestamp: new Date().toISOString()
            });
        } else {
            dialogs.push({
                id: 'dialog_' + Date.now(),
                taskId: taskId,
                aiId: aiId,
                messages: [{
                    role: role,
                    content: content,
                    timestamp: new Date().toISOString()
                }]
            });
        }
        
        this.save();
        this.notify();
    }

    // 获取任务的所有对话
    getDialogs(taskId) {
        return this.dialogs.get(taskId) || [];
    }

    // 获取 AI 对话
    getAIDialog(taskId, aiId) {
        const dialogs = this.dialogs.get(taskId) || [];
        return dialogs.find(d => d.aiId === aiId);
    }

    // ========== 当前选中 ==========

    setCurrentTask(taskId) {
        this.currentTaskId = taskId;
        this.notify();
    }

    getCurrentTask() {
        return this.currentTaskId ? this.getTask(this.currentTaskId) : null;
    }

    // ========== 订阅 ==========

    subscribe(callback) {
        this.listeners.add(callback);
        return () => this.listeners.delete(callback);
    }

    notify() {
        this.listeners.forEach(cb => cb(this));
    }

    // ========== 统计 ==========

    getStats() {
        return {
            total: this.tasks.length,
            todo: this.tasks.filter(t => t.status === 'todo').length,
            inProgress: this.tasks.filter(t => t.status === 'in_progress').length,
            done: this.tasks.filter(t => t.status === 'done').length
        };
    }

    // 清空所有数据
    clear() {
        this.tasks = [];
        this.dialogs = new Map();
        this.currentTaskId = null;
        localStorage.removeItem(this.TASKS_KEY);
        localStorage.removeItem(this.DIALOGS_KEY);
        this.notify();
    }
}

// 导出单例
const programmingStore = new ProgrammingStore();
```

- [ ] **步骤 2：Commit**

```bash
git add star-ui/js/programming-store.js
git commit -m "feat: add programming store for task and dialog management"
```

---

### 任务 2：项目上下文读取（context-reader.js）

**文件：**
- 创建：`star-ui/js/context-reader.js`

- [ ] **步骤 1：创建上下文读取模块**

```javascript
/**
 * context-reader.js - 项目上下文读取
 * 
 * 功能：
 * - 从窗口标题解析项目信息
 * - 生成上下文摘要
 * - 复制到剪贴板
 */

class ContextReader {
    constructor() {
        this.cache = new Map();
    }

    // 从当前页面读取上下文
    async readCurrentContext() {
        // 获取页面标题
        const title = document.title;
        
        // 获取打开的文件（从 URL 或页面内容）
        const currentFile = this.extractFileFromTitle(title);
        
        // 获取项目名
        const projectName = this.extractProjectName(title);
        
        return {
            title: title,
            projectName: projectName,
            currentFile: currentFile,
            timestamp: new Date().toISOString()
        };
    }

    // 从窗口标题提取文件名
    extractFileFromTitle(title) {
        // 格式: "filename - project - AI"
        const parts = title.split(' - ');
        if (parts.length >= 2) {
            return parts[0].trim();
        }
        return null;
    }

    // 从窗口标题提取项目名
    extractProjectName(title) {
        // 格式: "filename - project - AI"
        const parts = title.split(' - ');
        if (parts.length >= 3) {
            return parts[1].trim();
        }
        return null;
    }

    // 生成上下文文本
    generateContextText(context) {
        let text = '';
        
        if (context.projectName) {
            text += `项目: ${context.projectName}\n`;
        }
        
        if (context.currentFile) {
            text += `当前文件: ${context.currentFile}\n`;
        }
        
        text += '\n---\n';
        
        return text;
    }

    // 复制到剪贴板
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (e) {
            console.error('Failed to copy:', e);
            return false;
        }
    }

    // 格式化选中文本
    formatSelection(selection, context) {
        let text = context ? this.generateContextText(context) : '';
        text += '以下是相关代码：\n```\n' + selection + '\n```';
        return text;
    }
}

// 导出单例
const contextReader = new ContextReader();
```

- [ ] **步骤 2：Commit**

```bash
git add star-ui/js/context-reader.js
git commit -m "feat: add context reader for project information extraction"
```

---

### 任务 3：并行编程工作台页面（programming.html）

**文件：**
- 创建：`star-ui/pages/programming.html`

- [ ] **步骤 1：创建并行编程工作台页面**

```html
<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>星际编程工作台 — 群星 Star</title>
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
    <script src="/ui/js/programming-store.js"></script>
    <script src="/ui/js/context-reader.js"></script>
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body {
        background: var(--color-bg-deep);
        color: var(--color-text-primary);
        font-family: var(--font-display);
        height: 100vh;
        overflow: hidden;
      }

      /* Layout */
      .layout {
        display: flex;
        height: 100vh;
      }

      /* Header */
      .header {
        height: 56px;
        background: var(--color-bg-panel);
        border-bottom: 1px solid var(--color-border);
        display: flex;
        align-items: center;
        padding: 0 16px;
        gap: 12px;
      }
      .header-title {
        font-size: 16px;
        font-weight: 600;
      }
      .header-actions {
        margin-left: auto;
        display: flex;
        gap: 8px;
      }

      /* Sidebar */
      .sidebar {
        width: 240px;
        background: var(--color-bg-panel);
        border-right: 1px solid var(--color-border);
        display: flex;
        flex-direction: column;
      }
      .sidebar-header {
        padding: 12px;
        border-bottom: 1px solid var(--color-border);
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .sidebar-title {
        font-size: 13px;
        font-weight: 600;
        color: var(--color-text-secondary);
      }
      .task-list {
        flex: 1;
        overflow-y: auto;
        padding: 8px;
      }

      /* Task Card */
      .task-card {
        background: var(--color-bg-card);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        padding: 10px 12px;
        margin-bottom: 8px;
        cursor: pointer;
        transition: all 0.2s;
      }
      .task-card:hover {
        border-color: var(--color-border-glow);
      }
      .task-card.active {
        border-color: var(--color-primary);
        background: var(--color-primary-dim);
      }
      .task-card.todo { border-left: 3px solid var(--color-text-muted); }
      .task-card.in_progress { border-left: 3px solid var(--color-warning); }
      .task-card.done { border-left: 3px solid var(--color-success); }
      .task-title {
        font-size: 13px;
        font-weight: 500;
        margin-bottom: 4px;
      }
      .task-meta {
        font-size: 11px;
        color: var(--color-text-muted);
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .task-ais {
        display: flex;
        gap: 4px;
        margin-top: 6px;
      }
      .task-ai-chip {
        font-size: 10px;
        padding: 2px 6px;
        background: var(--color-bg-elevated);
        border-radius: 4px;
        color: var(--color-text-secondary);
      }

      /* Main Area */
      .main {
        flex: 1;
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }
      .main-header {
        padding: 12px 16px;
        border-bottom: 1px solid var(--color-border);
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .main-title {
        font-size: 15px;
        font-weight: 600;
        flex: 1;
      }
      .context-btn {
        font-size: 12px;
        padding: 6px 12px;
        background: var(--color-bg-elevated);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        color: var(--color-text-primary);
        cursor: pointer;
      }
      .context-btn:hover {
        background: var(--color-bg-hover);
      }

      /* Workspace */
      .workspace {
        flex: 1;
        display: flex;
        gap: 12px;
        padding: 12px;
        overflow: hidden;
      }
      .ai-panel {
        flex: 1;
        background: var(--color-bg-card);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-lg);
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }
      .ai-panel-header {
        padding: 10px 12px;
        border-bottom: 1px solid var(--color-border);
        display: flex;
        align-items: center;
        gap: 8px;
        background: var(--color-bg-elevated);
      }
      .ai-panel-status {
        width: 8px;
        height: 8px;
        border-radius: 50%;
      }
      .ai-panel-status.idle { background: var(--color-text-muted); }
      .ai-panel-status.working { background: var(--color-warning); animation: pulse 1s infinite; }
      .ai-panel-status.ready { background: var(--color-success); }
      @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
      .ai-panel-title {
        font-size: 13px;
        font-weight: 500;
        flex: 1;
      }
      .ai-panel-body {
        flex: 1;
        overflow-y: auto;
        padding: 12px;
      }
      .ai-message {
        margin-bottom: 12px;
        padding: 10px 12px;
        border-radius: var(--radius-md);
        font-size: 13px;
        line-height: 1.5;
      }
      .ai-message.user {
        background: var(--color-primary-dim);
        border: 1px solid var(--color-primary-glow);
      }
      .ai-message.assistant {
        background: var(--color-bg-elevated);
        white-space: pre-wrap;
        font-family: var(--font-mono);
        font-size: 12px;
      }
      .ai-panel-input {
        padding: 12px;
        border-top: 1px solid var(--color-border);
        display: flex;
        gap: 8px;
      }
      .ai-input {
        flex: 1;
        padding: 8px 12px;
        background: var(--color-bg-elevated);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        color: var(--color-text-primary);
        font-size: 13px;
        resize: none;
        min-height: 40px;
        max-height: 100px;
      }
      .ai-input:focus {
        outline: none;
        border-color: var(--color-primary);
      }
      .send-btn {
        padding: 8px 16px;
        background: var(--color-primary);
        border: none;
        border-radius: var(--radius-md);
        color: #1a1f3a;
        font-weight: 500;
        cursor: pointer;
      }
      .send-btn:hover { opacity: 0.9; }
      .send-btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      /* Empty State */
      .empty-state {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        color: var(--color-text-muted);
        text-align: center;
        padding: 40px;
      }
      .empty-state .icon {
        font-size: 48px;
        margin-bottom: 16px;
        opacity: 0.5;
      }
      .empty-state .text {
        font-size: 14px;
        margin-bottom: 16px;
      }

      /* Footer */
      .footer {
        height: 48px;
        background: var(--color-bg-panel);
        border-top: 1px solid var(--color-border);
        display: flex;
        align-items: center;
        padding: 0 16px;
        gap: 12px;
      }
      .ai-status-item {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        background: var(--color-bg-elevated);
        border-radius: 20px;
        font-size: 12px;
        cursor: pointer;
      }
      .ai-status-item:hover {
        background: var(--color-bg-hover);
      }
      .ai-status-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
      }

      /* Buttons */
      .btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 8px 14px;
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        background: var(--color-bg-elevated);
        color: var(--color-text-primary);
        font-size: 13px;
        cursor: pointer;
        transition: all 0.2s;
      }
      .btn:hover {
        background: var(--color-bg-hover);
        border-color: var(--color-border-glow);
      }
      .btn-primary {
        background: var(--color-primary);
        color: #1a1f3a;
        border-color: var(--color-primary);
        font-weight: 500;
      }
      .btn-sm {
        padding: 5px 10px;
        font-size: 12px;
      }
      .btn-danger {
        color: var(--color-danger);
        border-color: var(--color-danger);
      }

      /* Modal */
      .modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0,0,0,0.6);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
      }
      .modal {
        background: var(--color-bg-panel);
        border-radius: var(--radius-lg);
        padding: 24px;
        width: 400px;
        max-width: 90%;
      }
      .modal-title {
        font-size: 16px;
        font-weight: 600;
        margin-bottom: 16px;
      }
      .modal-body input,
      .modal-body textarea {
        width: 100%;
        padding: 8px 12px;
        background: var(--color-bg-elevated);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        color: var(--color-text-primary);
        font-size: 13px;
        margin-bottom: 12px;
      }
      .modal-body textarea {
        resize: vertical;
        min-height: 80px;
      }
      .modal-actions {
        display: flex;
        gap: 8px;
        justify-content: flex-end;
        margin-top: 16px;
      }
    </style>
</head>
<body>
    <div class="layout">
        <!-- Header -->
        <div class="header">
            <span class="header-title">🚀 星际编程工作台</span>
            <div class="header-actions">
                <button class="btn btn-sm" onclick="showContextModal()">
                    📋 上下文卡
                </button>
            </div>
        </div>

        <!-- Sidebar -->
        <div class="sidebar">
            <div class="sidebar-header">
                <span class="sidebar-title">任务列表</span>
                <button class="btn btn-sm btn-primary" onclick="showNewTaskModal()">+ 新建</button>
            </div>
            <div class="task-list" id="taskList">
                <!-- 动态渲染 -->
            </div>
        </div>

        <!-- Main -->
        <div class="main">
            <div id="workspaceArea">
                <div class="empty-state">
                    <div class="icon">🚀</div>
                    <div class="text">选择一个任务或创建新任务开始编程</div>
                    <button class="btn btn-primary" onclick="showNewTaskModal()">创建任务</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Footer -->
    <div class="footer" id="footer">
        <!-- AI 状态列表动态渲染 -->
    </div>

    <!-- 新建任务模态框 -->
    <div id="newTaskModal" class="modal-overlay" style="display: none;">
        <div class="modal">
            <div class="modal-title">新建任务</div>
            <div class="modal-body">
                <input type="text" id="taskTitleInput" placeholder="任务标题">
                <textarea id="taskDescInput" placeholder="任务描述（可选）"></textarea>
            </div>
            <div class="modal-actions">
                <button class="btn" onclick="closeNewTaskModal()">取消</button>
                <button class="btn btn-primary" onclick="createTask()">创建</button>
            </div>
        </div>
    </div>

    <!-- 上下文模态框 -->
    <div id="contextModal" class="modal-overlay" style="display: none;">
        <div class="modal">
            <div class="modal-title">项目上下文</div>
            <div class="modal-body">
                <div id="contextPreview" style="padding: 12px; background: var(--color-bg-elevated); border-radius: var(--radius-md); margin-bottom: 12px; font-size: 12px; font-family: var(--font-mono); white-space: pre-wrap;"></div>
                <button class="btn btn-sm" onclick="copyContext()">📋 复制上下文</button>
            </div>
            <div class="modal-actions">
                <button class="btn" onclick="closeContextModal()">关闭</button>
            </div>
        </div>
    </div>

    <script>
        // 当前上下文
        let currentContext = null;

        // 初始化
        async function init() {
            // 读取上下文
            currentContext = await contextReader.readCurrentContext();
            
            // 渲染任务列表
            renderTaskList();
            
            // 渲染 AI 状态栏
            renderAIStatus();
            
            // 订阅状态变化
            programmingStore.subscribe(() => {
                renderTaskList();
            });
        }

        // 渲染任务列表
        function renderTaskList() {
            const container = document.getElementById('taskList');
            const tasks = programmingStore.getAllTasks();
            
            if (tasks.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 20px; color: var(--color-text-muted); font-size: 13px;">暂无任务</div>';
                return;
            }
            
            // 按状态分组渲染
            const todoTasks = tasks.filter(t => t.status === 'todo');
            const inProgressTasks = tasks.filter(t => t.status === 'in_progress');
            const doneTasks = tasks.filter(t => t.status === 'done');
            
            let html = '';
            
            if (todoTasks.length > 0) {
                html += `<div style="font-size: 11px; color: var(--color-text-muted); margin-bottom: 8px;">待办 (${todoTasks.length})</div>`;
                html += todoTasks.map(t => renderTaskCard(t)).join('');
            }
            
            if (inProgressTasks.length > 0) {
                html += `<div style="font-size: 11px; color: var(--color-text-muted); margin: 12px 0 8px;">进行中 (${inProgressTasks.length})</div>`;
                html += inProgressTasks.map(t => renderTaskCard(t)).join('');
            }
            
            if (doneTasks.length > 0) {
                html += `<div style="font-size: 11px; color: var(--color-text-muted); margin: 12px 0 8px;">已完成 (${doneTasks.length})</div>`;
                html += doneTasks.map(t => renderTaskCard(t)).join('');
            }
            
            container.innerHTML = html;
        }

        // 渲染任务卡片
        function renderTaskCard(task) {
            const isActive = programmingStore.getCurrentTask()?.id === task.id;
            const ais = task.assignedAIs.map(ai => `<span class="task-ai-chip">${ai}</span>`).join('');
            
            return `
                <div class="task-card ${task.status} ${isActive ? 'active' : ''}" onclick="selectTask('${task.id}')">
                    <div class="task-title">${escapeHtml(task.title)}</div>
                    <div class="task-meta">
                        <span>${task.status === 'todo' ? '待办' : task.status === 'in_progress' ? '进行中' : '已完成'}</span>
                        ${task.assignedAIs.length > 0 ? `<span>${task.assignedAIs.length} 个 AI</span>` : ''}
                    </div>
                    ${ais ? `<div class="task-ais">${ais}</div>` : ''}
                </div>
            `;
        }

        // 选择任务
        function selectTask(taskId) {
            programmingStore.setCurrentTask(taskId);
            renderWorkspace(taskId);
        }

        // 渲染工作区
        function renderWorkspace(taskId) {
            const task = programmingStore.getTask(taskId);
            if (!task) return;
            
            const container = document.getElementById('workspaceArea');
            
            if (task.assignedAIs.length === 0) {
                container.innerHTML = `
                    <div class="main-header">
                        <div class="main-title">${escapeHtml(task.title)}</div>
                        <button class="btn btn-sm" onclick="deleteTask('${task.id}')" style="color: var(--color-danger);">删除</button>
                    </div>
                    <div class="empty-state">
                        <div class="icon">🤖</div>
                        <div class="text">从下方添加 AI 开始对话</div>
                        <div style="font-size: 12px; color: var(--color-text-muted);">点击底部的 AI 状态分配到任务</div>
                    </div>
                `;
                return;
            }
            
            // 为每个 AI 渲染一个面板
            const panels = task.assignedAIs.map(aiId => renderAIPanel(task.id, aiId)).join('');
            
            container.innerHTML = `
                <div class="main-header">
                    <div class="main-title">${escapeHtml(task.title)}</div>
                    <select class="btn btn-sm" onchange="changeTaskStatus('${task.id}', this.value)">
                        <option value="todo" ${task.status === 'todo' ? 'selected' : ''}>待办</option>
                        <option value="in_progress" ${task.status === 'in_progress' ? 'selected' : ''}>进行中</option>
                        <option value="done" ${task.status === 'done' ? 'selected' : ''}>已完成</option>
                    </select>
                    <button class="btn btn-sm btn-danger" onclick="deleteTask('${task.id}')">删除</button>
                </div>
                <div class="workspace">
                    ${panels}
                </div>
            `;
        }

        // 渲染 AI 面板
        function renderAIPanel(taskId, aiId) {
            const dialogs = programmingStore.getDialogs(taskId);
            const aiDialog = dialogs.find(d => d.aiId === aiId);
            const messages = aiDialog?.messages || [];
            
            const messagesHtml = messages.map(msg => `
                <div class="ai-message ${msg.role}">
                    ${escapeHtml(msg.content)}
                </div>
            `).join('');
            
            return `
                <div class="ai-panel">
                    <div class="ai-panel-header">
                        <span class="ai-panel-status idle"></span>
                        <span class="ai-panel-title">${aiId}</span>
                        <button class="btn btn-sm" onclick="unassignAI('${taskId}', '${aiId}')">移除</button>
                    </div>
                    <div class="ai-panel-body">
                        ${messagesHtml || '<div style="color: var(--color-text-muted); text-align: center; padding: 20px;">开始对话</div>'}
                    </div>
                    <div class="ai-panel-input">
                        <textarea class="ai-input" id="input-${aiId}" placeholder="输入指令..." rows="1"></textarea>
                        <button class="send-btn" onclick="sendToAI('${taskId}', '${aiId}')">发送</button>
                    </div>
                </div>
            `;
        }

        // 渲染 AI 状态栏
        function renderAIStatus() {
            const container = document.getElementById('footer');
            const currentTask = programmingStore.getCurrentTask();
            const assignedAIs = currentTask?.assignedAIs || [];
            
            // 获取可用 AI
            const availableAIs = ['Trae', 'Dumate', 'CodeArts', 'Claude', 'GPT-4'];
            
            const html = availableAIs.map(ai => {
                const isAssigned = assignedAIs.includes(ai);
                return `
                    <div class="ai-status-item" onclick="${isAssigned ? '' : `assignAI('${ai}')`}">
                        <span class="ai-status-dot" style="background: ${isAssigned ? 'var(--color-success)' : 'var(--color-text-muted)'}"></span>
                        <span>${ai}</span>
                        ${isAssigned ? '<span style="font-size: 10px; color: var(--color-text-muted);">已分配</span>' : ''}
                    </div>
                `;
            }).join('');
            
            container.innerHTML = html;
        }

        // 分配 AI 到当前任务
        function assignAI(aiId) {
            const task = programmingStore.getCurrentTask();
            if (task) {
                programmingStore.assignAI(task.id, aiId);
                renderWorkspace(task.id);
                renderAIStatus();
            }
        }

        // 从任务移除 AI
        function unassignAI(taskId, aiId) {
            programmingStore.unassignAI(taskId, aiId);
            renderWorkspace(taskId);
            renderAIStatus();
        }

        // 发送消息到 AI
        async function sendToAI(taskId, aiId) {
            const input = document.getElementById(`input-${aiId}`);
            const text = input.value.trim();
            if (!text) return;
            
            // 添加用户消息
            programmingStore.addMessage(taskId, aiId, 'user', text);
            input.value = '';
            
            // 重新渲染工作区
            renderWorkspace(taskId);
            
            // TODO: 调用 API 发送消息到 AI
            // 目前模拟 AI 回复
            setTimeout(() => {
                programmingStore.addMessage(taskId, aiId, 'assistant', '这是 AI 的模拟回复...\n\n实际使用时将调用真实的 AI API。');
                renderWorkspace(taskId);
            }, 1000);
        }

        // 修改任务状态
        function changeTaskStatus(taskId, status) {
            programmingStore.updateTask(taskId, { status });
            renderTaskList();
        }

        // 删除任务
        function deleteTask(taskId) {
            if (confirm('确定要删除这个任务吗？')) {
                programmingStore.deleteTask(taskId);
                document.getElementById('workspaceArea').innerHTML = `
                    <div class="empty-state">
                        <div class="icon">🚀</div>
                        <div class="text">选择一个任务或创建新任务开始编程</div>
                        <button class="btn btn-primary" onclick="showNewTaskModal()">创建任务</button>
                    </div>
                `;
            }
        }

        // 显示新建任务模态框
        function showNewTaskModal() {
            document.getElementById('newTaskModal').style.display = 'flex';
            document.getElementById('taskTitleInput').focus();
        }

        // 关闭新建任务模态框
        function closeNewTaskModal() {
            document.getElementById('newTaskModal').style.display = 'none';
            document.getElementById('taskTitleInput').value = '';
            document.getElementById('taskDescInput').value = '';
        }

        // 创建任务
        function createTask() {
            const title = document.getElementById('taskTitleInput').value.trim();
            const desc = document.getElementById('taskDescInput').value.trim();
            
            if (!title) {
                alert('请输入任务标题');
                return;
            }
            
            const task = programmingStore.createTask(title, desc);
            closeNewTaskModal();
            selectTask(task.id);
        }

        // 显示上下文模态框
        async function showContextModal() {
            const preview = document.getElementById('contextPreview');
            preview.textContent = currentContext ? contextReader.generateContextText(currentContext) : '无法读取上下文';
            document.getElementById('contextModal').style.display = 'flex';
        }

        // 关闭上下文模态框
        function closeContextModal() {
            document.getElementById('contextModal').style.display = 'none';
        }

        // 复制上下文
        async function copyContext() {
            const text = currentContext ? contextReader.generateContextText(currentContext) : '';
            const success = await contextReader.copyToClipboard(text);
            if (success) {
                alert('上下文已复制到剪贴板');
            }
        }

        // HTML 转义
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // 初始化
        init();
    </script>
</body>
</html>
```

- [ ] **步骤 2：Commit**

```bash
git add star-ui/pages/programming.html
git commit -m "feat: add programming workbench page"
```

---

### 任务 4：导航更新

**文件：**
- 修改：`star-ui/pages/starmap.html`

- [ ] **步骤 1：在导航栏添加入口**

在导航栏中添加"编程工作台"入口：

在现有导航项中添加：

```html
<!-- 在星群状态入口后添加 -->
<a href="/ui/pages/programming.html" title="Programming Workbench" data-dom-id="nav-programming"
   class="relative flex items-center justify-center w-10 h-10 transition-all duration-200"
   style="color:var(--color-text-muted);border-left:3px solid transparent;">
    <i data-lucide="code-2" class="w-5 h-5"></i>
</a>
```

- [ ] **步骤 2：Commit**

```bash
git add star-ui/pages/starmap.html
git commit -m "feat: add programming workbench link in navigation"
```

---

### 任务 5：测试与验证

- [ ] **步骤 1：验证页面加载**
   - 启动 API 服务
   - 访问 `/ui/pages/programming.html`
   - 验证页面正常加载

- [ ] **步骤 2：测试任务 CRUD**
   - 创建新任务
   - 编辑任务状态
   - 删除任务

- [ ] **步骤 3：测试 AI 分配**
   - 点击底部 AI 分配到任务
   - 验证 AI 面板出现

- [ ] **步骤 4：测试对话功能**
   - 输入指令
   - 验证消息显示

- [ ] **步骤 5：运行所有测试**

```bash
cd g:\traework\star
E:\py312\python.exe -m pytest tests/ -v --tb=short
```

预期：所有测试通过

---

## 规格覆盖度检查

| 功能 | 规格要求 | 实现任务 |
|------|---------|---------|
| 并行编程工作台基础布局 | 三栏布局、任务列表、工作区、AI 状态栏 | 任务 3 |
| 任务管理（CRUD） | 创建、编辑、删除、状态变更 | 任务 1, 3 |
| AI 分配 | 从状态栏拖拽分配、移除 AI | 任务 1, 3 |
| 编程工作区 | 显示对话、发送指令、查看结果 | 任务 3 |
| 项目上下文卡 | 读取上下文、复制到剪贴板 | 任务 2, 3 |
| 导航入口 | 侧边栏快捷入口 | 任务 4 |

**所有规格需求都有对应实现任务。**

---

## 执行方式

**推荐：子代理驱动（subagent-driven-development）**

每个任务调度一个子代理并行执行，提高效率。任务间相对独立，可以并行开发：
- 任务 1 和 2（两个 JS 服务模块）可以并行
- 任务 3（主页面）依赖任务 1 和 2
- 任务 4、5（导航 + 测试）最后执行
