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
