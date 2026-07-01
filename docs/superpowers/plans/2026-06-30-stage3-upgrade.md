# 阶段 3：升级（持续）实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 完成群星系统的三大升级方向——前端工程化统一、插件化深度整合、可观测性完善，提升系统的可维护性、可扩展性和可观测性。

**架构：**
- 前端：不引入 Vue/React 框架，基于现有原生 JS + ui-common.js 做工程化统一，完善公共组件库和状态管理
- 插件化：完善 PluginManager 的生命周期管理，深化与核心引擎的钩子集成，增加插件配置持久化
- 可观测性：建立统一指标体系，完善健康检查，增加性能监控和结构化日志

**技术栈：** Python 3.12+ / FastAPI / SQLite / 原生 JavaScript / CSS

---

## 文件结构总览

### 前端工程化统一（方向 7）
- 修改：`star-ui/js/ui-common.js` - 扩展公共组件库（Toast、Modal、Table、Form 等）
- 新增：`star-ui/js/state.js` - 前端全局状态管理
- 新增：`star-ui/js/components/` - 公共组件目录
  - `toast.js` - Toast 提示组件
  - `modal.js` - Modal 弹窗组件
  - `table.js` - 数据表格组件
  - `loading.js` - 加载状态组件
- 修改：`star-ui/pages/*.html` - 统一引用公共组件

### 插件化深度整合（方向 8）
- 修改：`star_core/plugin_system.py` - 完善插件生命周期、配置管理、钩子系统
- 新增：`star_core/plugin_hooks.py` - 统一的钩子分发器
- 修改：`star_core/orbit_engine.py` - 集成插件钩子
- 修改：`star_api/routes/plugins.py` - 完善插件管理 API
- 新增：`tests/test_plugin_system.py` - 插件系统测试

### 可观测性完善（方向 9）
- 新增：`star_core/observability/` - 可观测性模块
  - `__init__.py`
  - `metrics.py` - 指标收集与管理
  - `health.py` - 健康检查
  - `tracing.py` - 请求追踪（简化版）
- 修改：`star_api/main.py` - 集成可观测性中间件
- 新增：`star_api/routes/observability.py` - 可观测性 API 路由
- 新增：`tests/test_observability.py` - 可观测性测试

---

## 方向 7：前端工程化统一

### 任务 7.1：完善公共组件库 - Toast & Modal

**文件：**
- 新增：`star-ui/js/components/toast.js`
- 新增：`star-ui/js/components/modal.js`
- 修改：`star-ui/js/ui-common.js` - 集成组件

- [ ] **步骤 1：创建 Toast 组件**

```javascript
// star-ui/js/components/toast.js
(function() {
    const Toast = {
        container: null,
        
        _ensureContainer: function() {
            if (!this.container) {
                this.container = document.createElement('div');
                this.container.id = 'toast-container';
                this.container.className = 'toast-container';
                document.body.appendChild(this.container);
            }
        },
        
        show: function(message, type, duration) {
            type = type || 'info';
            duration = duration || 3000;
            this._ensureContainer();
            
            const toast = document.createElement('div');
            toast.className = 'toast toast-' + type;
            toast.innerHTML = `
                <span class="toast-icon">${this._getIcon(type)}</span>
                <span class="toast-message">${UICommon.escapeHtml(message)}</span>
            `;
            
            this.container.appendChild(toast);
            
            requestAnimationFrame(() => {
                toast.classList.add('show');
            });
            
            if (duration > 0) {
                setTimeout(() => {
                    toast.classList.remove('show');
                    setTimeout(() => {
                        if (toast.parentNode) {
                            toast.parentNode.removeChild(toast);
                        }
                    }, 300);
                }, duration);
            }
            
            return toast;
        },
        
        _getIcon: function(type) {
            const icons = {
                success: '✓',
                error: '✕',
                warning: '⚠',
                info: 'ℹ'
            };
            return icons[type] || icons.info;
        },
        
        success: function(msg, dur) { return this.show(msg, 'success', dur); },
        error: function(msg, dur) { return this.show(msg, 'error', dur); },
        warning: function(msg, dur) { return this.show(msg, 'warning', dur); },
        info: function(msg, dur) { return this.show(msg, 'info', dur); }
    };
    
    if (typeof window !== 'undefined') {
        window.Toast = Toast;
    }
})();
```

- [ ] **步骤 2：创建 Modal 组件**

```javascript
// star-ui/js/components/modal.js
(function() {
    const Modal = {
        _stack: [],
        
        show: function(options) {
            options = options || {};
            const id = 'modal_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5);
            
            const modal = document.createElement('div');
            modal.id = id;
            modal.className = 'modal-overlay';
            modal.innerHTML = `
                <div class="modal-dialog ${options.size || ''}">
                    <div class="modal-header">
                        <h3 class="modal-title">${UICommon.escapeHtml(options.title || '提示')}</h3>
                        ${options.closable !== false ? '<button class="modal-close">&times;</button>' : ''}
                    </div>
                    <div class="modal-body">
                        ${options.content || ''}
                    </div>
                    ${options.footer !== false ? `
                    <div class="modal-footer">
                        ${options.footer || `
                            <button class="btn btn-secondary modal-cancel">取消</button>
                            <button class="btn btn-primary modal-confirm">确定</button>
                        `}
                    </div>` : ''}
                </div>
            `;
            
            document.body.appendChild(modal);
            this._stack.push(id);
            
            const self = this;
            
            const closeBtn = modal.querySelector('.modal-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => self.close(id));
            }
            
            const cancelBtn = modal.querySelector('.modal-cancel');
            if (cancelBtn) {
                cancelBtn.addEventListener('click', () => {
                    if (options.onCancel) options.onCancel();
                    self.close(id);
                });
            }
            
            const confirmBtn = modal.querySelector('.modal-confirm');
            if (confirmBtn) {
                confirmBtn.addEventListener('click', () => {
                    if (options.onConfirm) {
                        const result = options.onConfirm();
                        if (result !== false) self.close(id);
                    } else {
                        self.close(id);
                    }
                });
            }
            
            if (options.closable !== false) {
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) self.close(id);
                });
            }
            
            requestAnimationFrame(() => {
                modal.classList.add('show');
            });
            
            return id;
        },
        
        close: function(id) {
            const modal = document.getElementById(id);
            if (!modal) return;
            
            modal.classList.remove('show');
            setTimeout(() => {
                if (modal.parentNode) {
                    modal.parentNode.removeChild(modal);
                }
            }, 300);
            
            const idx = this._stack.indexOf(id);
            if (idx > -1) this._stack.splice(idx, 1);
        },
        
        confirm: function(message, onConfirm) {
            return this.show({
                title: '确认',
                content: `<p>${UICommon.escapeHtml(message)}</p>`,
                onConfirm: onConfirm
            });
        },
        
        alert: function(message, onClose) {
            return this.show({
                title: '提示',
                content: `<p>${UICommon.escapeHtml(message)}</p>`,
                footer: '<button class="btn btn-primary modal-confirm">知道了</button>',
                onConfirm: onClose
            });
        }
    };
    
    if (typeof window !== 'undefined') {
        window.Modal = Modal;
    }
})();
```

- [ ] **步骤 3：在 ui-common.js 中集成组件引用**

在 `ui-common.js` 末尾添加：

```javascript
// 组件
window.UIComponents = {
    Toast: window.Toast || null,
    Modal: window.Modal || null,
};
```

- [ ] **步骤 4：添加组件样式到公共 CSS**

创建/更新 `star-ui/css/components.css`：

```css
/* Toast */
.toast-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 10px;
}
.toast {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 20px;
    background: var(--color-bg-elevated, #212647);
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    border-left: 4px solid var(--color-info, #42a5f5);
    color: var(--color-text-primary, #e8eaf6);
    font-size: 14px;
    transform: translateX(120%);
    transition: transform 0.3s ease;
    min-width: 250px;
    max-width: 400px;
}
.toast.show { transform: translateX(0); }
.toast-success { border-left-color: var(--state-success, #66bb6a); }
.toast-error { border-left-color: var(--state-error, #ef5350); }
.toast-warning { border-left-color: var(--state-warning, #ffa726); }
.toast-info { border-left-color: var(--state-info, #42a5f5); }
.toast-icon { font-weight: bold; font-size: 16px; }

/* Modal */
.modal-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9998;
    opacity: 0;
    transition: opacity 0.3s ease;
}
.modal-overlay.show { opacity: 1; }
.modal-dialog {
    background: var(--color-bg-panel, #1a1f3a);
    border-radius: 12px;
    width: 90%;
    max-width: 500px;
    max-height: 85vh;
    display: flex;
    flex-direction: column;
    transform: scale(0.9) translateY(-20px);
    transition: transform 0.3s ease;
    box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}
.modal-overlay.show .modal-dialog {
    transform: scale(1) translateY(0);
}
.modal-header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--color-border, rgba(255,255,255,0.1));
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.modal-title { margin: 0; font-size: 16px; color: var(--color-text-primary); }
.modal-close {
    background: none; border: none; color: var(--color-text-secondary);
    font-size: 24px; cursor: pointer; padding: 0; line-height: 1;
}
.modal-close:hover { color: var(--color-text-primary); }
.modal-body { padding: 20px; overflow-y: auto; flex: 1; color: var(--color-text-secondary); }
.modal-footer {
    padding: 12px 20px;
    border-top: 1px solid var(--color-border, rgba(255,255,255,0.1));
    display: flex;
    justify-content: flex-end;
    gap: 10px;
}
```

- [ ] **步骤 5：验证组件可用**

在浏览器控制台测试：
```javascript
Toast.success('测试成功提示');
Modal.alert('测试弹窗');
```

---

### 任务 7.2：前端全局状态管理

**文件：**
- 新增：`star-ui/js/state.js`

- [ ] **步骤 1：创建前端状态管理器**

```javascript
// star-ui/js/state.js
(function() {
    /**
     * AppState - 前端全局状态管理
     * 
     * 特性：
     * - 响应式：状态变更时触发事件
     * - 持久化：关键状态自动保存到 localStorage
     * - 命名空间：按模块隔离状态
     */
    class AppState {
        constructor() {
            this._state = {};
            this._listeners = {};
            this._persistKeys = new Set();
            this._storageKey = 'star_app_state';
            
            this._loadPersisted();
        }
        
        _loadPersisted() {
            try {
                const saved = localStorage.getItem(this._storageKey);
                if (saved) {
                    const data = JSON.parse(saved);
                    Object.assign(this._state, data);
                }
            } catch (e) {
                console.warn('Failed to load persisted state:', e);
            }
        }
        
        _savePersisted() {
            try {
                const data = {};
                for (const key of this._persistKeys) {
                    if (key in this._state) {
                        data[key] = this._state[key];
                    }
                }
                localStorage.setItem(this._storageKey, JSON.stringify(data));
            } catch (e) {
                console.warn('Failed to persist state:', e);
            }
        }
        
        get(key, defaultValue) {
            if (defaultValue === undefined) defaultValue = null;
            const keys = key.split('.');
            let value = this._state;
            for (const k of keys) {
                if (value == null) return defaultValue;
                value = value[k];
            }
            return value !== undefined ? value : defaultValue;
        }
        
        set(key, value) {
            const keys = key.split('.');
            let obj = this._state;
            for (let i = 0; i < keys.length - 1; i++) {
                if (!(keys[i] in obj)) {
                    obj[keys[i]] = {};
                }
                obj = obj[keys[i]];
            }
            obj[keys[keys.length - 1]] = value;
            
            if (this._persistKeys.has(keys[0])) {
                this._savePersisted();
            }
            
            this._emit(key, value);
            return value;
        }
        
        toggle(key) {
            return this.set(key, !this.get(key, false));
        }
        
        increment(key, amount) {
            amount = amount || 1;
            return this.set(key, (this.get(key, 0) || 0) + amount);
        }
        
        subscribe(key, callback) {
            if (!this._listeners[key]) {
                this._listeners[key] = [];
            }
            this._listeners[key].push(callback);
            
            return () => {
                const idx = this._listeners[key].indexOf(callback);
                if (idx > -1) this._listeners[key].splice(idx, 1);
            };
        }
        
        _emit(key, value) {
            const parts = key.split('.');
            let current = '';
            
            for (let i = 0; i < parts.length; i++) {
                current = current ? current + '.' + parts[i] : parts[i];
                if (this._listeners[current]) {
                    for (const cb of this._listeners[current]) {
                        try {
                            cb(value, key);
                        } catch (e) {
                            console.error('State listener error:', e);
                        }
                    }
                }
            }
        }
        
        persist(key) {
            this._persistKeys.add(key);
            this._savePersisted();
        }
        
        unpersist(key) {
            this._persistKeys.delete(key);
        }
        
        reset() {
            this._state = {};
            this._savePersisted();
            this._emit('*', null);
        }
    }
    
    const appState = new AppState();
    
    appState.persist('settings');
    appState.persist('ui');
    
    if (typeof window !== 'undefined') {
        window.AppState = appState;
    }
})();
```

- [ ] **步骤 2：验证状态管理功能**

```javascript
// 设置状态
AppState.set('user.theme', 'dark');

// 获取状态
const theme = AppState.get('user.theme'); // 'dark'

// 订阅变化
AppState.subscribe('user.theme', (val) => {
    console.log('Theme changed to:', val);
});

// 持久化
AppState.persist('user');
```

---

### 任务 7.3：前端事件总线与模块组织

**文件：**
- 修改：`star-ui/js/ui-common.js` - 添加事件总线

- [ ] **步骤 1：在 ui-common.js 中添加 EventBus**

```javascript
// 事件总线
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
```

- [ ] **步骤 2：更新 ui-common.js 的导出结构**

确保所有功能统一挂载到 `UICommon` 命名空间下，同时保留全局快捷访问。

---

## 方向 8：插件化深度整合

### 任务 8.1：插件生命周期管理完善

**文件：**
- 修改：`star_core/plugin_system.py` - 完善插件生命周期
- 修改：`star_core/database.py` - 添加插件配置表

- [ ] **步骤 1：在数据库中添加插件配置表**

在 `database.py` 的 `_create_tables` 方法中添加：

```python
cursor.execute("""
    CREATE TABLE IF NOT EXISTS plugin_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plugin_name TEXT NOT NULL UNIQUE,
        enabled INTEGER DEFAULT 0,
        config TEXT DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
""")
```

添加对应的 CRUD 方法：

```python
def get_plugin_config(self, plugin_name: str) -> Optional[Dict]:
    with self.get_cursor() as cur:
        cur.execute("SELECT * FROM plugin_configs WHERE plugin_name = ?", (plugin_name,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get('config'):
            try:
                d['config'] = json.loads(d['config'])
            except Exception:
                pass
        return d

def list_plugin_configs(self) -> List[Dict]:
    with self.get_cursor() as cur:
        cur.execute("SELECT * FROM plugin_configs")
        rows = []
        for row in cur.fetchall():
            d = dict(row)
            if d.get('config'):
                try:
                    d['config'] = json.loads(d['config'])
                except Exception:
                    pass
            rows.append(d)
        return rows

def save_plugin_config(self, plugin_name: str, enabled: bool, config: Dict = None) -> None:
    now = datetime.now().isoformat()
    config_json = json.dumps(config or {}, ensure_ascii=False)
    with self.get_cursor() as cur:
        cur.execute("SELECT id FROM plugin_configs WHERE plugin_name = ?", (plugin_name,))
        existing = cur.fetchone()
        if existing:
            cur.execute("""
                UPDATE plugin_configs SET enabled = ?, config = ?, updated_at = ?
                WHERE plugin_name = ?
            """, (1 if enabled else 0, config_json, now, plugin_name))
        else:
            cur.execute("""
                INSERT INTO plugin_configs (plugin_name, enabled, config, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (plugin_name, 1 if enabled else 0, config_json, now, now))
```

- [ ] **步骤 2：完善 PluginManager 的生命周期方法**

在 `PluginManager` 类中添加：

```python
def enable_plugin(self, plugin_name: str) -> bool:
    """启用插件"""
    if plugin_name not in self._plugin_infos:
        return False
    
    info = self._plugin_infos[plugin_name]
    if info.status == PluginStatus.ACTIVE:
        return True
    
    try:
        if plugin_name not in self._plugins:
            self._load_plugin(plugin_name)
        
        self._activate_plugin(plugin_name)
        
        # 保存到数据库
        try:
            from star_core.database import get_db_service
            db = get_db_service()
            db.save_plugin_config(plugin_name, True, self._get_plugin_config(plugin_name))
        except Exception:
            pass
        
        return True
    except Exception as e:
        logger.error(f"Failed to enable plugin {plugin_name}: {e}")
        info.status = PluginStatus.ERROR
        info.error_message = str(e)
        return False

def disable_plugin(self, plugin_name: str) -> bool:
    """禁用插件"""
    if plugin_name not in self._plugin_infos:
        return False
    
    try:
        self._deactivate_plugin(plugin_name)
        
        # 保存到数据库
        try:
            from star_core.database import get_db_service
            db = get_db_service()
            db.save_plugin_config(plugin_name, False, self._get_plugin_config(plugin_name))
        except Exception:
            pass
        
        return True
    except Exception as e:
        logger.error(f"Failed to disable plugin {plugin_name}: {e}")
        return False

def configure_plugin(self, plugin_name: str, config: dict) -> bool:
    """配置插件"""
    try:
        if plugin_name in self._plugins:
            plugin = self._plugins[plugin_name]
            if hasattr(plugin, 'configure'):
                plugin.configure(config)
        
        # 保存到数据库
        try:
            from star_core.database import get_db_service
            db = get_db_service()
            enabled = self._plugin_infos.get(plugin_name, PluginInfo(
                name=plugin_name, version='0', author='', description='',
                plugin_type=PluginType.EXTENSION
            )).status == PluginStatus.ACTIVE
            db.save_plugin_config(plugin_name, enabled, config)
        except Exception:
            pass
        
        return True
    except Exception as e:
        logger.error(f"Failed to configure plugin {plugin_name}: {e}")
        return False

def get_plugin_config(self, plugin_name: str) -> dict:
    """获取插件配置"""
    try:
        from star_core.database import get_db_service
        db = get_db_service()
        cfg = db.get_plugin_config(plugin_name)
        return cfg.get('config', {}) if cfg else {}
    except Exception:
        return {}
```

- [ ] **步骤 3：添加启动时自动启用已配置插件**

在 `PluginManager.__init__` 或初始化方法中添加：

```python
def _load_enabled_plugins_from_db(self):
    """从数据库加载已启用的插件"""
    try:
        from star_core.database import get_db_service
        db = get_db_service()
        configs = db.list_plugin_configs()
        for cfg in configs:
            if cfg.get('enabled'):
                try:
                    self.enable_plugin(cfg['plugin_name'])
                except Exception:
                    pass
    except Exception:
        pass
```

---

### 任务 8.2：插件钩子系统完善

**文件：**
- 新增：`star_core/plugin_hooks.py` - 统一钩子分发器
- 修改：`star_core/orbit_engine.py` - 集成钩子点

- [ ] **步骤 1：创建钩子分发器**

```python
"""
plugin_hooks.py - 插件钩子分发器

统一管理插件钩子的注册和调用，
避免各模块直接依赖 PluginManager。
"""

from typing import Any, Optional, List, Callable
from enum import Enum


class HookPoint(Enum):
    """钩子点枚举"""
    # 新星生命周期
    NOVA_CREATE = "nova_create"
    NOVA_LAUNCH = "nova_launch"
    NOVA_SHINE = "nova_shine"
    NOVA_COMPLETE = "nova_complete"
    NOVA_FADE = "nova_fade"
    
    # 星体生命周期
    STAR_DISCOVERED = "star_discovered"
    STAR_LOST = "star_lost"
    
    # 星辉接收
    STARLIGHT_RECEIVED = "starlight_received"
    
    # 星座生命周期
    CONSTELLATION_CREATE = "constellation_create"
    CONSTELLATION_COMPLETE = "constellation_complete"
    
    # 系统事件
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"


class HookDispatcher:
    """
    钩子分发器
    
    负责：
    - 注册钩子处理器
    - 分发钩子事件
    - 处理钩子异常
    """
    
    def __init__(self):
        self._handlers: dict[str, List[Callable]] = {}
    
    def register(self, hook_point: str | HookPoint, handler: Callable):
        """注册钩子处理器"""
        key = hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        if key not in self._handlers:
            self._handlers[key] = []
        self._handlers[key].append(handler)
    
    def unregister(self, hook_point: str | HookPoint, handler: Callable):
        """注销钩子处理器"""
        key = hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        if key in self._handlers:
            try:
                self._handlers[key].remove(handler)
            except ValueError:
                pass
    
    def dispatch(self, hook_point: str | HookPoint, *args, **kwargs) -> list:
        """
        分发钩子事件
        
        Returns:
            所有处理器的返回值列表
        """
        key = hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        results = []
        
        if key not in self._handlers:
            return results
        
        for handler in self._handlers[key]:
            try:
                result = handler(*args, **kwargs)
                results.append(result)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Hook handler error for {key}: {e}")
                results.append(None)
        
        return results
    
    def dispatch_until_false(self, hook_point: str | HookPoint, *args, **kwargs) -> bool:
        """
        分发钩子事件，直到返回 False
        
        Returns:
            False 表示有处理器阻止了事件，True 表示全部通过
        """
        key = hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        
        if key not in self._handlers:
            return True
        
        for handler in self._handlers[key]:
            try:
                result = handler(*args, **kwargs)
                if result is False:
                    return False
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Hook handler error for {key}: {e}")
        
        return True
    
    def clear(self):
        """清空所有钩子"""
        self._handlers.clear()


# 全局钩子分发器实例
_global_dispatcher: Optional[HookDispatcher] = None


def get_hook_dispatcher() -> HookDispatcher:
    """获取全局钩子分发器"""
    global _global_dispatcher
    if _global_dispatcher is None:
        _global_dispatcher = HookDispatcher()
    return _global_dispatcher
```

- [ ] **步骤 2：在 PluginManager 中集成钩子**

在 `PluginManager` 中添加方法，将 HookPlugin 的钩子注册到全局分发器：

```python
def _register_plugin_hooks(self, plugin_name: str, plugin):
    """注册插件钩子到全局分发器"""
    from star_core.plugin_hooks import get_hook_dispatcher, HookPoint
    
    dispatcher = get_hook_dispatcher()
    
    hook_mappings = {
        'on_nova_create': HookPoint.NOVA_CREATE,
        'on_nova_launch': HookPoint.NOVA_LAUNCH,
        'on_nova_shine': HookPoint.NOVA_SHINE,
        'on_starlight_received': HookPoint.STARLIGHT_RECEIVED,
        'on_nova_complete': HookPoint.NOVA_COMPLETE,
        'on_nova_fade': HookPoint.NOVA_FADE,
    }
    
    for method_name, hook_point in hook_mappings.items():
        if hasattr(plugin, method_name):
            handler = getattr(plugin, method_name)
            dispatcher.register(hook_point, handler)
```

- [ ] **步骤 3：在 OrbitEngine 中添加钩子点**

在 `OrbitEngine` 的关键位置添加钩子调用：

```python
# 在 launch_nova 方法中
from star_core.plugin_hooks import get_hook_dispatcher, HookPoint

dispatcher = get_hook_dispatcher()

# 创建时
dispatcher.dispatch(HookPoint.NOVA_CREATE, nova)

# 发射前
if not dispatcher.dispatch_until_false(HookPoint.NOVA_LAUNCH, nova, star_body):
    return False

# 完成时
dispatcher.dispatch(HookPoint.NOVA_COMPLETE, nova)

# 收到星辉时
dispatcher.dispatch(HookPoint.STARLIGHT_RECEIVED, nova, content)
```

---

## 方向 9：可观测性完善

### 任务 9.1：统一指标体系

**文件：**
- 新增：`star_core/observability/__init__.py`
- 新增：`star_core/observability/metrics.py` - 指标管理
- 新增：`star_core/observability/health.py` - 健康检查

- [ ] **步骤 1：创建指标管理器**

```python
"""
metrics.py - 指标收集与管理

提供统一的指标收集接口，支持：
- Counter（计数器）
- Gauge（仪表盘）
- Histogram（直方图，简化版）
"""

import time
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class MetricValue:
    """指标值"""
    value: float = 0.0
    labels: Dict[str, str] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)


class Counter:
    """计数器 - 只增不减"""
    
    def __init__(self, name: str, description: str = "", label_names: List[str] = None):
        self.name = name
        self.description = description
        self.label_names = label_names or []
        self._values: Dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def inc(self, amount: float = 1.0, labels: Dict[str, str] = None):
        key = self._labels_to_key(labels)
        with self._lock:
            self._values[key] += amount
    
    def get(self, labels: Dict[str, str] = None) -> float:
        key = self._labels_to_key(labels)
        with self._lock:
            return self._values.get(key, 0.0)
    
    def _labels_to_key(self, labels: Dict[str, str] = None) -> str:
        if not labels:
            return ''
        return ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
    
    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            values = dict(self._values)
        return {
            'name': self.name,
            'type': 'counter',
            'description': self.description,
            'values': values,
            'label_names': self.label_names,
        }


class Gauge:
    """仪表盘 - 可增可减"""
    
    def __init__(self, name: str, description: str = "", label_names: List[str] = None):
        self.name = name
        self.description = description
        self.label_names = label_names or []
        self._values: Dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def set(self, value: float, labels: Dict[str, str] = None):
        key = self._labels_to_key(labels)
        with self._lock:
            self._values[key] = value
    
    def inc(self, amount: float = 1.0, labels: Dict[str, str] = None):
        key = self._labels_to_key(labels)
        with self._lock:
            self._values[key] += amount
    
    def dec(self, amount: float = 1.0, labels: Dict[str, str] = None):
        key = self._labels_to_key(labels)
        with self._lock:
            self._values[key] -= amount
    
    def get(self, labels: Dict[str, str] = None) -> float:
        key = self._labels_to_key(labels)
        with self._lock:
            return self._values.get(key, 0.0)
    
    def _labels_to_key(self, labels: Dict[str, str] = None) -> str:
        if not labels:
            return ''
        return ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
    
    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            values = dict(self._values)
        return {
            'name': self.name,
            'type': 'gauge',
            'description': self.description,
            'values': values,
            'label_names': self.label_names,
        }


class Histogram:
    """直方图 - 统计分布（简化版）"""
    
    def __init__(self, name: str, description: str = "", 
                 buckets: List[float] = None, label_names: List[str] = None):
        self.name = name
        self.description = description
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self.label_names = label_names or []
        self._sum: Dict[str, float] = defaultdict(float)
        self._count: Dict[str, int] = defaultdict(int)
        self._bucket_counts: Dict[str, List[int]] = defaultdict(lambda: [0] * len(self.buckets))
        self._lock = threading.Lock()
    
    def observe(self, value: float, labels: Dict[str, str] = None):
        key = self._labels_to_key(labels)
        with self._lock:
            self._sum[key] += value
            self._count[key] += 1
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    self._bucket_counts[key][i] += 1
    
    def _labels_to_key(self, labels: Dict[str, str] = None) -> str:
        if not labels:
            return ''
        return ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
    
    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'name': self.name,
                'type': 'histogram',
                'description': self.description,
                'buckets': self.buckets,
                'sum': dict(self._sum),
                'count': dict(self._count),
                'bucket_counts': {k: list(v) for k, v in self._bucket_counts.items()},
                'label_names': self.label_names,
            }


class MetricsRegistry:
    """指标注册表"""
    
    def __init__(self):
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._lock = threading.Lock()
    
    def counter(self, name: str, description: str = "", label_names: List[str] = None) -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description, label_names)
            return self._counters[name]
    
    def gauge(self, name: str, description: str = "", label_names: List[str] = None) -> Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description, label_names)
            return self._gauges[name]
    
    def histogram(self, name: str, description: str = "", 
                  buckets: List[float] = None, label_names: List[str] = None) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description, buckets, label_names)
            return self._histograms[name]
    
    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'counters': {name: c.to_dict() for name, c in self._counters.items()},
                'gauges': {name: g.to_dict() for name, g in self._gauges.items()},
                'histograms': {name: h.to_dict() for name, h in self._histograms.items()},
            }


# 全局指标注册表
_global_registry: Optional[MetricsRegistry] = None


def get_metrics_registry() -> MetricsRegistry:
    """获取全局指标注册表"""
    global _global_registry
    if _global_registry is None:
        _global_registry = MetricsRegistry()
    return _global_registry
```

- [ ] **步骤 2：创建健康检查模块**

```python
"""
health.py - 健康检查

提供系统健康状态检查功能，包括：
- 数据库连通性
- 核心服务状态
- 资源使用情况
"""

import time
import os
import psutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class HealthStatus(str, Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    name: str
    status: HealthStatus
    details: Dict[str, Any] = None
    duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'status': self.status.value,
            'details': self.details or {},
            'duration_ms': round(self.duration_ms, 2),
        }


class HealthChecker:
    """健康检查器"""
    
    def __init__(self):
        self._checks = {}
    
    def register(self, name: str, check_func):
        """注册健康检查"""
        self._checks[name] = check_func
    
    def check_all(self) -> Dict[str, Any]:
        """执行所有健康检查"""
        results = []
        overall_status = HealthStatus.HEALTHY
        total_start = time.time()
        
        for name, check_func in self._checks.items():
            start = time.time()
            try:
                result = check_func()
                if isinstance(result, tuple):
                    status, details = result
                else:
                    status = result
                    details = {}
                
                if status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED
                    
            except Exception as e:
                status = HealthStatus.UNHEALTHY
                details = {'error': str(e)}
                overall_status = HealthStatus.UNHEALTHY
            
            duration = (time.time() - start) * 1000
            results.append(HealthCheckResult(
                name=name,
                status=status,
                details=details or {},
                duration_ms=duration,
            ))
        
        total_duration = (time.time() - total_start) * 1000
        
        return {
            'status': overall_status.value,
            'total_duration_ms': round(total_duration, 2),
            'checks': [r.to_dict() for r in results],
            'timestamp': time.time(),
        }
    
    def check(self, name: str) -> Optional[Dict[str, Any]]:
        """执行单个健康检查"""
        if name not in self._checks:
            return None
        
        start = time.time()
        try:
            result = self._checks[name]()
            if isinstance(result, tuple):
                status, details = result
            else:
                status = result
                details = {}
        except Exception as e:
            status = HealthStatus.UNHEALTHY
            details = {'error': str(e)}
        
        duration = (time.time() - start) * 1000
        return HealthCheckResult(
            name=name,
            status=status,
            details=details or {},
            duration_ms=duration,
        ).to_dict()


def _check_database():
    """数据库健康检查"""
    try:
        from star_core.database import get_db_service
        db = get_db_service()
        if db.health_check():
            return HealthStatus.HEALTHY, {'database': 'ok'}
        else:
            return HealthStatus.UNHEALTHY, {'database': 'failed'}
    except Exception as e:
        return HealthStatus.UNHEALTHY, {'error': str(e)}


def _check_system_resources():
    """系统资源健康检查"""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        
        status = HealthStatus.HEALTHY
        details = {
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'disk_percent': disk.percent,
        }
        
        if cpu_percent > 90 or memory.percent > 90:
            status = HealthStatus.DEGRADED
        if disk.percent > 95:
            status = HealthStatus.DEGRADED
        
        return status, details
    except Exception as e:
        return HealthStatus.DEGRADED, {'error': str(e)}


# 全局健康检查器
_global_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """获取全局健康检查器"""
    global _global_health_checker
    if _global_health_checker is None:
        _global_health_checker = HealthChecker()
        _global_health_checker.register('database', _check_database)
        _global_health_checker.register('system_resources', _check_system_resources)
    return _global_health_checker
```

- [ ] **步骤 3：创建 observability 包的 __init__.py**

```python
"""
star_core.observability - 可观测性模块

提供指标收集、健康检查、请求追踪等功能。
"""

from star_core.observability.metrics import (
    MetricsRegistry,
    Counter,
    Gauge,
    Histogram,
    get_metrics_registry,
)
from star_core.observability.health import (
    HealthChecker,
    HealthStatus,
    HealthCheckResult,
    get_health_checker,
)

__all__ = [
    'MetricsRegistry',
    'Counter',
    'Gauge',
    'Histogram',
    'get_metrics_registry',
    'HealthChecker',
    'HealthStatus',
    'HealthCheckResult',
    'get_health_checker',
]
```

---

### 任务 9.2：API 层可观测性集成

**文件：**
- 新增：`star_api/routes/observability.py` - 可观测性 API
- 修改：`star_api/main.py` - 添加请求指标中间件

- [ ] **步骤 1：创建可观测性 API 路由**

```python
"""
可观测性路由

提供指标查询、健康检查等 API。
"""

from fastapi import APIRouter, HTTPException
from star_core.observability import get_metrics_registry, get_health_checker

router = APIRouter(tags=["可观测性"])


@router.get("/metrics")
async def get_metrics():
    """获取所有指标"""
    registry = get_metrics_registry()
    return registry.get_all()


@router.get("/health")
async def health_check():
    """健康检查"""
    checker = get_health_checker()
    result = checker.check_all()
    status_code = 200 if result['status'] == 'healthy' else 503 if result['status'] == 'unhealthy' else 200
    return result


@router.get("/health/{check_name}")
async def health_check_single(check_name: str):
    """单个健康检查"""
    checker = get_health_checker()
    result = checker.check(check_name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Health check '{check_name}' not found")
    return result
```

- [ ] **步骤 2：添加 API 请求指标中间件**

在 `star_api/main.py` 中添加：

```python
from star_core.observability import get_metrics_registry

# 初始化指标
metrics = get_metrics_registry()
request_counter = metrics.counter(
    'http_requests_total', 
    'Total HTTP requests',
    ['method', 'path', 'status']
)
request_duration = metrics.histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    label_names=['method', 'path']
)
active_requests = metrics.gauge(
    'http_active_requests',
    'Active HTTP requests',
    ['method', 'path']
)
```

在 FastAPI app 中添加中间件：

```python
import time
from fastapi import Request

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    method = request.method
    path = request.url.path
    
    active_requests.inc(labels={'method': method, 'path': path})
    
    start_time = time.time()
    try:
        response = await call_next(request)
        status = str(response.status_code)
        
        duration = time.time() - start_time
        request_counter.inc(labels={'method': method, 'path': path, 'status': status})
        request_duration.observe(duration, labels={'method': method, 'path': path})
        
        return response
    finally:
        active_requests.dec(labels={'method': method, 'path': path})
```

- [ ] **步骤 3：在 main.py 中注册可观测性路由**

```python
from star_api.routes.observability import router as observability_router

app.include_router(observability_router, prefix="/api/observability", tags=["可观测性"])
```

---

## 测试与验证

### 任务 10：测试覆盖补充

**文件：**
- 新增：`tests/test_plugin_system.py`
- 新增：`tests/test_observability.py`
- 新增：`tests/test_frontend_components.py`（可选，前端单元测试）

- [ ] **步骤 1：编写插件系统测试**
- [ ] **步骤 2：编写可观测性测试**
- [ ] **步骤 3：运行所有测试验证**

---

### 总体验证清单

- [ ] 前端公共组件库（Toast、Modal）功能正常
- [ ] 前端状态管理（AppState）功能正常
- [ ] 前端事件总线（EventBus）功能正常
- [ ] 插件启用/禁用/配置功能正常
- [ ] 插件钩子系统正常工作
- [ ] 指标收集功能正常
- [ ] 健康检查接口正常
- [ ] 所有现有测试仍然通过（130+）
- [ ] 新增测试通过
