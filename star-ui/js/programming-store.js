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
