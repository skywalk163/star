/**
 * ui-common.js - 前端公共工具库
 * 
 * 所有页面共用的工具函数、组件、常量
 * 用法：<script src="/ui/js/ui-common.js"></script>
 * 使用 window.UICommon 访问
 */

(function() {
    'use strict';

    // ========== DOM 工具 ==========
    
    const $ = (selector, scope) => (scope || document).querySelector(selector);
    const $$ = (selector, scope) => Array.from((scope || document).querySelectorAll(selector));
    
    // ========== 字符串工具 ==========
    
    function escapeHtml(text) {
        if (!text && text !== '') return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    function escapeRegExp(string) {
        return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }
    
    function truncate(str, maxLen, suffix) {
        suffix = suffix || '...';
        if (!str || str.length <= maxLen) return str || '';
        return str.slice(0, maxLen) + suffix;
    }
    
    function formatTime(timestamp) {
        const date = new Date(timestamp * 1000);
        return date.toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }
    
    function formatDuration(seconds) {
        if (seconds < 60) return Math.floor(seconds) + '秒';
        if (seconds < 3600) return Math.floor(seconds / 60) + '分' + Math.floor(seconds % 60) + '秒';
        return Math.floor(seconds / 3600) + '时' + Math.floor((seconds % 3600) / 60) + '分';
    }
    
    // ========== HTTP 工具 ==========
    
    const API_BASE = '/api';
    
    async function apiGet(path, params) {
        params = params || {};
        const url = new URL(API_BASE + path, window.location.origin);
        Object.entries(params).forEach(([k, v]) => {
            if (v !== undefined && v !== null) url.searchParams.append(k, v);
        });
        
        const res = await fetch(url.toString());
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
    }
    
    async function apiPost(path, data) {
        data = data || {};
        const res = await fetch(API_BASE + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
    }
    
    async function apiPut(path, data) {
        data = data || {};
        const res = await fetch(API_BASE + path, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
    }
    
    async function apiDelete(path) {
        const res = await fetch(API_BASE + path, { method: 'DELETE' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
    }
    
    // ========== 存储工具 ==========
    
    const storage = {
        get(key, defaultValue) {
            if (defaultValue === undefined) defaultValue = null;
            try {
                const val = localStorage.getItem(key);
                return val ? JSON.parse(val) : defaultValue;
            } catch (e) {
                return defaultValue;
            }
        },
        
        set(key, value) {
            try {
                localStorage.setItem(key, JSON.stringify(value));
                return true;
            } catch (e) {
                console.error('Storage set error:', e);
                return false;
            }
        },
        
        remove(key) {
            localStorage.removeItem(key);
        },
        
        clear() {
            localStorage.clear();
        }
    };
    
    // ========== 事件总线 ==========
    
    class EventBus {
        constructor() {
            this._listeners = new Map();
        }
        
        on(event, callback) {
            if (!this._listeners.has(event)) {
                this._listeners.set(event, new Set());
            }
            this._listeners.get(event).add(callback);
            return () => this.off(event, callback);
        }
        
        off(event, callback) {
            this._listeners.get(event)?.delete(callback);
        }
        
        emit(event, data) {
            this._listeners.get(event)?.forEach(cb => {
                try { cb(data); } catch (e) { console.error(e); }
            });
        }
    }
    
    const eventBus = new EventBus();
    
    // ========== 通知工具 ==========
    
    function showToast(message, type, duration) {
        type = type || 'info';
        duration = duration || 3000;
        
        const toast = document.createElement('div');
        let bgColor = 'rgba(59, 130, 246, 0.9)';
        if (type === 'success') bgColor = 'rgba(16, 185, 129, 0.9)';
        if (type === 'error') bgColor = 'rgba(239, 68, 68, 0.9)';
        if (type === 'warning') bgColor = 'rgba(245, 158, 11, 0.9)';
        
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 8px;
            font-size: 14px;
            z-index: 99999;
            transform: translateX(120%);
            transition: transform 0.3s ease;
            pointer-events: none;
            background: ${bgColor};
            color: white;
        `;
        toast.textContent = message;
        document.body.appendChild(toast);
        
        requestAnimationFrame(() => {
            toast.style.transform = 'translateX(0)';
        });
        
        setTimeout(() => {
            toast.style.transform = 'translateX(120%)';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
    
    // ========== 主题工具 ==========
    
    const theme = {
        getCurrent() {
            return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
        },
        
        set(mode) {
            if (mode === 'dark') {
                document.documentElement.classList.add('dark');
            } else {
                document.documentElement.classList.remove('dark');
            }
            storage.set('ui_theme', mode);
            eventBus.emit('theme:change', mode);
        },
        
        toggle() {
            this.set(this.getCurrent() === 'dark' ? 'light' : 'dark');
        },
        
        init() {
            const saved = storage.get('ui_theme');
            if (saved) this.set(saved);
        }
    };
    
    // ========== 剪贴板工具 ==========
    
    async function copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (e) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                return true;
            } catch (e2) {
                return false;
            } finally {
                textarea.remove();
            }
        }
    }
    
    // ========== 防抖节流 ==========
    
    function debounce(fn, delay) {
        delay = delay || 300;
        let timer = null;
        return function() {
            const args = arguments;
            const ctx = this;
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(ctx, args), delay);
        };
    }
    
    function throttle(fn, limit) {
        limit = limit || 300;
        let inThrottle = false;
        return function() {
            if (!inThrottle) {
                fn.apply(this, arguments);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
    
    // ========== 导出 ==========
    
    window.UICommon = {
        $: $,
        $$: $$,
        escapeHtml: escapeHtml,
        escapeRegExp: escapeRegExp,
        truncate: truncate,
        formatTime: formatTime,
        formatDuration: formatDuration,
        apiGet: apiGet,
        apiPost: apiPost,
        apiPut: apiPut,
        apiDelete: apiDelete,
        API_BASE: API_BASE,
        storage: storage,
        eventBus: eventBus,
        showToast: showToast,
        theme: theme,
        copyToClipboard: copyToClipboard,
        debounce: debounce,
        throttle: throttle,
    };

    // 组件
    window.UIComponents = {
        Toast: window.Toast || null,
        Modal: window.Modal || null,
    };

    // 全局事件总线
    window.EventBus = {
        _handlers: {},
        
        on: function(event, handler) {
            if (!this._handlers[event]) {
                this._handlers[event] = [];
            }
            this._handlers[event].push(handler);
            return () => this.off(event, handler);
        },
        
        off: function(event, handler) {
            if (!this._handlers[event]) return;
            const idx = this._handlers[event].indexOf(handler);
            if (idx > -1) this._handlers[event].splice(idx, 1);
        },
        
        emit: function(event, data) {
            if (!this._handlers[event]) return;
            for (const handler of this._handlers[event]) {
                try {
                    handler(data);
                } catch (e) {
                    console.error('EventBus handler error:', e);
                }
            }
        },
        
        once: function(event, handler) {
            const wrapper = (data) => {
                handler(data);
                this.off(event, wrapper);
            };
            this.on(event, wrapper);
        },
        
        clear: function(event) {
            if (event) {
                delete this._handlers[event];
            } else {
                this._handlers = {};
            }
        }
    };

})();
