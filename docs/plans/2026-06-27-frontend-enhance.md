# 星图增强 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将星图面板升级为系统主入口，增加右侧详情面板实现「选星体→发指令→看响应」的完整交互闭环，补齐 loading/错误提示/日志展示等用户体验基础设施。

**架构：** 在 starmap.html 中增加左右分栏布局 + 4 Tab 详情面板，在 api-bridge.js 中新增日志 API/通知系统/全局状态，orbits.html/starlight.html 做导航联动。

**技术栈：** 原生 JavaScript + Tailwind CSS（CDN）+ Lucide 图标（CDN），无框架依赖。

---

## 文件职责

| 文件 | 职责 |
|------|------|
| `star-ui/js/api-bridge.js` | 通知系统、日志 API 调用、全局状态管理 |
| `star-ui/pages/starmap.html` | 主入口页面：星体网格 + 右侧详情面板（4 Tab） |
| `star-ui/pages/orbit.html` | 接收 hash 参数自动选中星体 |
| `star-ui/pages/starlight.html` | 响应项增加日志来源标签 |

## 不修改的文件

- `star_core/` 下所有文件（后端逻辑不动）
- `star_api/` 下所有文件（API 不动）
- `config.yaml` / `scripts/*.ps1`（系统配置不动）

---

### 任务 1：api-bridge.js — 新增通知系统 + 日志 API + 全局状态

**文件：** 修改 `star-ui/js/api-bridge.js`

- [ ] **步骤 1：在 api-bridge.js 末尾追加通知系统函数**

```javascript
// ==================== 通知系统 ====================
(function() {
  let notifEl = null;
  
  function ensureContainer() {
    if (notifEl && document.body.contains(notifEl)) return notifEl;
    const existing = document.getElementById('star-notification');
    if (existing) { notifEl = existing; return notifEl; }
    notifEl = document.createElement('div');
    notifEl.id = 'star-notification';
    notifEl.style.cssText = 'position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:9999;display:none;max-width:600px;width:90%;padding:10px 16px;border-radius:8px;font-size:14px;font-family:var(--font-body,sans-serif);transition:opacity .3s,transform .3s;text-align:center;';
    document.body.appendChild(notifEl);
    return notifEl;
  }
  
  window.showNotification = function(msg, type, duration) {
    const el = ensureContainer();
    const colors = { success: '#66bb6a', warning: '#ffa726', error: '#ef5350', info: '#42a5f5' };
    el.style.background = colors[type] || colors.info;
    el.style.color = '#fff';
    el.textContent = msg;
    el.style.display = 'block';
    el.style.opacity = '1';
    el.style.transform = 'translateX(-50%) translateY(0)';
    const dur = duration !== null ? duration : (type === 'success' ? 3000 : 0);
    if (dur > 0) setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(-50%) translateY(-10px)'; setTimeout(() => el.style.display = 'none', 300); }, dur);
  };
  
  window.hideNotification = function() {
    const el = ensureContainer();
    el.style.display = 'none';
  };
})();
```

- [ ] **步骤 2：在 api-bridge.js 末尾追加日志 API + 全局状态**

```javascript
// ==================== 日志 API ====================
emissaryApi.logs = (starId) => apiFetch(`/api/emissary/${starId}/logs`);
emissaryApi.logRecent = (starId, lines) => apiFetch(`/api/emissary/${starId}/logs/recent?max_lines=${lines || 30}`);
emissaryApi.discoverLogs = () => apiFetch('/api/emissary/logs/discover');
emissaryApi.history = (starId, limit) => apiFetch(`/api/emissary/${starId}/history?limit=${limit || 20}`);

// ==================== 全局状态 ====================
const appState = {
  selectedStarId: null,
  selectedStar: null,
  setSelectedStar(star) {
    this.selectedStarId = star ? (star.pid || star.star_id) : null;
    this.selectedStar = star;
    if (star) sessionStorage.setItem('selectedStarId', String(star.pid || star.star_id));
    else sessionStorage.removeItem('selectedStarId');
  },
  getSavedStarId() {
    return sessionStorage.getItem('selectedStarId');
  }
};
```

- [ ] **步骤 3：重启后端服务，用浏览器打开前端页面确认 js 加载无 404**

运行：`curl -s http://localhost:8767/ui/js/api-bridge.js | findstr "showNotification"` 预期：返回包含 `showNotification` 函数定义

---

### 任务 2：starmap.html — 布局改造：左右分栏 + 详情面板骨架

**文件：** 修改 `star-ui/pages/starmap.html`

- [ ] **步骤 1：将主内容区域 `<div class="flex-1 overflow-y-auto ...">` 改为左右 flex 容器**

原代码（约第 236 行）：
```html
<div class="flex-1 overflow-y-auto p-4 lg:p-6" style="background:var(--color-bg-deep);">
  <!-- Stats Summary Strip -->
  <!-- Filter Bar -->
  <!-- Main Grid: Star Field + Details Panel -->
  <div class="flex flex-col lg:flex-row gap-4">
    <!-- Star Field Grid -->
    <div class="flex-1 min-w-0 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 auto-rows-min">
```

改为：
```html
<div class="flex-1 flex overflow-hidden">
  <!-- Left: scrollable star area -->
  <div class="flex-1 overflow-y-auto p-4 lg:p-6 min-w-0" id="star-list-area">
    <!-- Stats Summary Strip -->
    <!-- Filter Bar -->
    <!-- Main Grid: Star Field -->
    <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 auto-rows-min" id="star-grid">
```

- [ ] **步骤 2：在左侧区域后面追加右侧详情面板（隐藏/显示由 JS 控制）**

```html
  </div>
  <!-- Right: Detail Panel (hidden by default) -->
  <div id="detail-panel" class="hidden w-[420px] shrink-0 border-l overflow-y-auto" style="background:var(--color-bg-panel);border-color:var(--color-border);">
    <!-- Empty state -->
    <div id="detail-empty" class="flex flex-col items-center justify-center h-full text-center px-6" style="color:var(--color-text-muted);">
      <i data-lucide="mouse-pointer-click" class="w-12 h-12 mb-3" style="color:var(--color-text-muted);"></i>
      <p class="text-sm">选择一个星体查看详情</p>
    </div>
    <!-- Panel content (hidden by default) -->
    <div id="detail-content" class="hidden flex flex-col h-full">
      <!-- Tab Bar -->
      <div class="flex border-b shrink-0" style="border-color:var(--color-border);">
        <button class="detail-tab flex-1 py-3 text-sm font-medium text-center transition-colors duration-200" data-tab="info" style="color:#ffd700;border-bottom:2px solid #ffd700;">信息</button>
        <button class="detail-tab flex-1 py-3 text-sm font-medium text-center transition-colors duration-200" data-tab="command" style="color:var(--color-text-muted);border-bottom:2px solid transparent;">指令</button>
        <button class="detail-tab flex-1 py-3 text-sm font-medium text-center transition-colors duration-200" data-tab="logs" style="color:var(--color-text-muted);border-bottom:2px solid transparent;">日志</button>
        <button class="detail-tab flex-1 py-3 text-sm font-medium text-center transition-colors duration-200" data-tab="history" style="color:var(--color-text-muted);border-bottom:2px solid transparent;">历史</button>
      </div>
      <!-- Tab Content -->
      <div class="flex-1 overflow-y-auto p-4" id="detail-tab-content">
        <!-- Content will be rendered by JS -->
      </div>
    </div>
  </div>
</div>
```

- [ ] **步骤 3：JS 部分 — 添加星体点击选中 + 详情面板显示/切换逻辑**

在现有 `<script>` 标签内（约第 662 行之后），`loadStarMapData` 函数之前或之后：

```javascript
// ===== 详情面板控制 =====
let currentTab = 'info';

function showDetailPanel(star) {
  appState.setSelectedStar(star);
  document.getElementById('detail-empty').classList.add('hidden');
  document.getElementById('detail-content').classList.remove('hidden');
  document.getElementById('detail-panel').classList.remove('hidden');
  switchTab('info');
  renderDetailTab('info', star);
}

function hideDetailPanel() {
  appState.setSelectedStar(null);
  document.getElementById('detail-panel').classList.add('hidden');
}

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.detail-tab').forEach(btn => {
    const isActive = btn.dataset.tab === tab;
    btn.style.color = isActive ? '#ffd700' : 'var(--color-text-muted)';
    btn.style.borderBottom = isActive ? '2px solid #ffd700' : '2px solid transparent';
  });
}

// 点击星体卡片
document.addEventListener('click', function(e) {
  const card = e.target.closest('[data-star-pid]');
  if (card) {
    const pid = card.dataset.starPid;
    starApi.list().then(res => {
      const star = (res.stars || []).find(s => String(s.pid) === pid);
      if (star) showDetailPanel(star);
    }).catch(() => showNotification('获取星体信息失败', 'error'));
  }
});

// Tab 切换
document.addEventListener('click', function(e) {
  const tabBtn = e.target.closest('.detail-tab');
  if (tabBtn && appState.selectedStar) {
    switchTab(tabBtn.dataset.tab);
    renderDetailTab(tabBtn.dataset.tab, appState.selectedStar);
  }
});
```

同时在动态生成的星体卡片模板中，给最外层 div 加上 `data-star-pid` 属性：
```javascript
// 在 grid.innerHTML = stars.map(...) 中
// 将 <div class="group relative ..."> 改为
<div class="group relative flex flex-col p-4 rounded-lg border cursor-pointer transition-all duration-200 ${isShining ? 'star-card-shining' : ''}"
     data-star-pid="${star.pid}"
     style="...">
```

- [ ] **步骤 4：重启服务，浏览器打开星图页，点击星体卡片验证右侧面板出现**

运行 Powershell 命令停掉旧服务再启动新服务。

---

### 任务 3：详情面板 — Tab "信息"

**文件：** 修改 `star-ui/pages/starmap.html`

- [ ] **步骤 1：实现 renderDetailTab('info') 函数**

在现有 `<script>` 中追加：

```javascript
async function renderDetailTab(tab, star) {
  const container = document.getElementById('detail-tab-content');
  container.innerHTML = '<div class="flex items-center justify-center py-8" style="color:var(--color-text-muted);"><i data-lucide="loader" class="w-5 h-5 animate-spin mr-2"></i>加载中…</div>';
  lucide.createIcons();
  
  try {
    if (tab === 'info') {
      // 获取状态 + 日志信息
      const [statusRes, logsRes] = await Promise.all([
        emissaryApi.status(star.pid).catch(() => ({})),
        emissaryApi.logs(star.pid).catch(() => ({ count: 0, files: [] })),
      ]);
      
      const status = statusRes.status || 'unknown';
      const responseSource = statusRes.last_turn?.response_source || '--';
      const logCount = logsRes.count || 0;
      const logFiles = logsRes.files || [];
      const lastLogTime = logFiles.length > 0 ? (logFiles[0].modified || '').slice(0, 16).replace('T', ' ') : '--';
      
      container.innerHTML = `
        <div class="space-y-4">
          <div class="flex items-start gap-3">
            <div class="flex items-center justify-center w-12 h-12 shrink-0 rounded-full text-lg font-bold" style="background:linear-gradient(135deg,#1e88e5,#42a5f5);color:#fff;">${(star.title || '?')[0].toUpperCase()}</div>
            <div class="min-w-0 flex-1">
              <div class="text-base font-semibold truncate" style="color:var(--color-text-primary);">${escapeHtml(star.title || '')}</div>
              <div class="text-xs font-mono mt-0.5" style="color:var(--color-text-muted);">PID: ${star.pid}  ·  类型: ${escapeHtml(star.star_type || '--')}</div>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="px-3 py-2 rounded-lg" style="background:var(--color-bg-card);">
              <div class="text-xs" style="color:var(--color-text-muted);">状态</div>
              <div class="text-sm font-semibold mt-0.5" style="color:${status === 'idle' ? 'var(--color-star-dim)' : 'var(--color-status-shining)'};">${status}</div>
            </div>
            <div class="px-3 py-2 rounded-lg" style="background:var(--color-bg-card);">
              <div class="text-xs" style="color:var(--color-text-muted);">响应来源</div>
              <div class="text-sm font-semibold mt-0.5" style="color:var(--color-text-primary);">${responseSource === 'log' ? '⚡ 日志' : (responseSource === 'ocr' ? '📷 OCR' : '--')}</div>
            </div>
          </div>
          <div class="px-3 py-2 rounded-lg" style="background:var(--color-bg-card);">
            <div class="text-xs" style="color:var(--color-text-muted);">日志文件</div>
            <div class="text-sm font-semibold mt-0.5" style="color:var(--color-text-primary);">${logCount} 个文件</div>
            ${lastLogTime !== '--' ? `<div class="text-xs mt-0.5" style="color:var(--color-text-muted);">最近更新: ${lastLogTime}</div>` : ''}
          </div>
          <button class="w-full py-2 text-sm rounded-lg border transition-colors duration-200 cursor-pointer" style="border-color:var(--color-border);color:var(--color-text-secondary);" onclick="switchTab('logs');renderDetailTab('logs', appState.selectedStar);">
            <i data-lucide="file-text" class="w-4 h-4 inline mr-1"></i>查看日志
          </button>
        </div>
      `;
    }
    // ... 其他 tab 将在后续任务中实现
    lucide.createIcons();
  } catch(e) {
    container.innerHTML = `<div class="flex items-center justify-center py-8" style="color:var(--state-error);">加载失败: ${e.message}</div>`;
  }
}
```

---

### 任务 4：详情面板 — Tab "指令"

**文件：** 修改 `star-ui/pages/starmap.html`

- [ ] **步骤 1：在 renderDetailTab 函数中添加 tab === 'command' 分支**

```javascript
if (tab === 'command') {
  container.innerHTML = `
    <div class="space-y-4">
      <div>
        <label class="text-xs mb-1 block" style="color:var(--color-text-muted);">适配器</label>
        <select id="cmd-adapter" class="w-full px-3 py-2 text-sm border rounded-lg focus:outline-none" style="background:var(--color-bg-card);border-color:var(--color-border);color:var(--color-text-primary);">
          <option value="">默认</option>
        </select>
      </div>
      <div>
        <label class="text-xs mb-1 block" style="color:var(--color-text-muted);">指令内容</label>
        <textarea id="cmd-input" rows="3" class="w-full px-3 py-2 text-sm border rounded-lg focus:outline-none resize-none" style="background:var(--color-bg-card);border-color:var(--color-border);color:var(--color-text-primary);" placeholder="输入发送给星体的指令…"></textarea>
      </div>
      <div class="flex gap-2">
        <button id="btn-send-fast" class="flex-1 flex items-center justify-center gap-1.5 py-2 text-sm font-medium rounded-lg cursor-pointer transition-all duration-200 hover:brightness-110" style="background:var(--color-primary);color:var(--color-bg-deep);">
          <i data-lucide="zap" class="w-4 h-4"></i>⚡ 发送
        </button>
        <button id="btn-send-ocr" class="flex-1 flex items-center justify-center gap-1.5 py-2 text-sm font-medium rounded-lg border cursor-pointer transition-all duration-200" style="border-color:var(--color-border);color:var(--color-text-secondary);">
          <i data-lucide="camera" class="w-4 h-4"></i>📷 OCR 发送
        </button>
      </div>
      <div id="cmd-response" class="hidden">
        <hr style="border-color:var(--color-border);">
        <div class="mt-3">
          <div class="text-xs mb-1" style="color:var(--color-text-muted);">响应结果</div>
          <div id="cmd-response-text" class="px-3 py-2 text-sm rounded-lg whitespace-pre-wrap" style="background:var(--color-bg-card);color:var(--color-text-primary);min-height:40px;"></div>
          <div id="cmd-response-meta" class="flex items-center gap-3 mt-2 text-xs" style="color:var(--color-text-muted);"></div>
          <button id="btn-copy-response" class="mt-2 px-3 py-1 text-xs rounded-lg border cursor-pointer transition-colors duration-200" style="border-color:var(--color-border);color:var(--color-text-secondary);">复制响应</button>
        </div>
      </div>
    </div>
  `;
  
  // 加载适配器列表
  emissaryApi.adapters().then(res => {
    const sel = document.getElementById('cmd-adapter');
    (res.adapters || []).forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.name; opt.textContent = a.name;
      sel.appendChild(opt);
    });
  }).catch(() => {});
  
  // 绑定发送按钮
  document.getElementById('btn-send-fast').onclick = async () => {
    const prompt = document.getElementById('cmd-input').value.trim();
    if (!prompt) return showNotification('请输入指令内容', 'warning');
    const btn = document.getElementById('btn-send-fast');
    btn.disabled = true; btn.innerHTML = '<i data-lucide="loader" class="w-4 h-4 animate-spin"></i> 发送中…';
    try {
      const adapter = document.getElementById('cmd-adapter').value || undefined;
      const res = await emissaryApi.ask(star.pid, prompt, adapter);
      showResponse(res.response || '(无响应)', res.duration || 0, res.status === 'completed' ? '⚡' : '📷', star);
    } catch(e) {
      showResponse(`错误: ${e.message}`, 0, '!', star);
      showNotification('指令发送失败', 'error');
    }
    btn.disabled = false; btn.innerHTML = '<i data-lucide="zap" class="w-4 h-4"></i>⚡ 发送';
    lucide.createIcons();
  };
  
  document.getElementById('btn-send-ocr').onclick = async () => {
    const prompt = document.getElementById('cmd-input').value.trim();
    if (!prompt) return showNotification('请输入指令内容', 'warning');
    const btn = document.getElementById('btn-send-ocr');
    btn.disabled = true; btn.innerHTML = '<i data-lucide="loader" class="w-4 h-4 animate-spin"></i> OCR 发送中…';
    try {
      const adapter = document.getElementById('cmd-adapter').value || undefined;
      await emissaryApi.send(star.pid, prompt, adapter);
      // 轮询等待
      const startTime = Date.now();
      let lastResponse = '';
      while (Date.now() - startTime < 120000) {
        await new Promise(r => setTimeout(r, 2000));
        const resp = await emissaryApi.response(star.pid);
        if (resp.response && resp.response !== lastResponse) {
          lastResponse = resp.response;
          showResponse(resp.response, (Date.now() - startTime) / 1000, '📷', star);
          if (resp.status !== 'waiting' && resp.status !== 'sending') break;
        }
      }
    } catch(e) {
      showNotification(`OCR 发送失败: ${e.message}`, 'error');
    }
    btn.disabled = false; btn.innerHTML = '<i data-lucide="camera" class="w-4 h-4"></i>📷 OCR 发送';
    lucide.createIcons();
  };
}
```

- [ ] **步骤 2：添加辅助函数 showResponse 和 escapeHtml**

```javascript
function showResponse(text, duration, source, star) {
  const respDiv = document.getElementById('cmd-response');
  const textDiv = document.getElementById('cmd-response-text');
  const metaDiv = document.getElementById('cmd-response-meta');
  respDiv.classList.remove('hidden');
  textDiv.textContent = text || '(空响应)';
  const sourceLabel = source === '⚡' ? '⚡ 日志' : (source === '📷' ? '📷 OCR' : source);
  metaDiv.innerHTML = `<span>来源: ${sourceLabel}</span><span>耗时: ${duration.toFixed(1)}s</span>`;
  document.getElementById('btn-copy-response').onclick = () => {
    navigator.clipboard.writeText(text).then(() => showNotification('已复制', 'success', 1500)).catch(() => {});
  };
  // 刷新左侧星体列表（更新状态）
  loadStarMapData();
}

function escapeHtml(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
```

---

### 任务 5：详情面板 — Tab "日志"

**文件：** 修改 `star-ui/pages/starmap.html`

- [ ] **步骤 1：在 renderDetailTab 函数中添加 tab === 'logs' 分支**

```javascript
if (tab === 'logs') {
  container.innerHTML = '<div class="flex items-center justify-center py-8" style="color:var(--color-text-muted);"><i data-lucide="loader" class="w-5 h-5 animate-spin mr-2"></i>读取日志中…</div>';
  lucide.createIcons();
  
  try {
    const [logsRes, recentRes] = await Promise.all([
      emissaryApi.logs(star.pid).catch(() => ({ count: 0, files: [] })),
      emissaryApi.logRecent(star.pid, 30).catch(() => ({})),
    ]);
    
    const logCount = logsRes.count || 0;
    const elapsed = recentRes.elapsed_ms || 0;
    const aiResponses = recentRes.ai_responses || [];
    const rawLines = recentRes.raw_lines || [];
    const files = logsRes.files || [];
    
    let html = `<div class="space-y-3">
      <div class="flex items-center justify-between">
        <div class="text-sm font-medium" style="color:var(--color-text-primary);">日志文件: ${logCount} 个</div>
        <div class="text-xs" style="color:var(--color-text-muted);">读取耗时: ${elapsed}ms</div>
      </div>`;
    
    // AI 响应解析结果
    html += `<div class="px-3 py-2 rounded-lg" style="background:var(--color-bg-card);">
      <div class="text-xs mb-1" style="color:var(--color-text-muted);">AI 响应解析</div>`;
    if (aiResponses.length > 0) {
      aiResponses.forEach(r => {
        html += `<div class="text-sm py-1" style="color:var(--color-text-primary);word-break:break-all;">${escapeHtml(r)}</div>`;
      });
    } else {
      html += `<div class="text-sm" style="color:var(--color-text-muted);">(当前日志中未发现 AI 响应)</div>`;
    }
    html += `</div>`;
    
    // 最近日志行
    html += `<div class="px-3 py-2 rounded-lg" style="background:var(--color-bg-card);">
      <div class="text-xs mb-1" style="color:var(--color-text-muted);">最近日志 (${rawLines.length} 行)</div>
      <div class="max-h-[300px] overflow-y-auto font-mono text-xs leading-relaxed" style="color:var(--color-text-secondary);">`;
    rawLines.slice(0, 30).forEach(line => {
      html += `<div class="truncate hover:text-clip">${escapeHtml(line)}</div>`;
    });
    html += `</div></div>`;
    
    // 文件列表
    if (files.length > 0) {
      html += `<button class="w-full py-2 text-xs rounded-lg border transition-colors duration-200 cursor-pointer" style="border-color:var(--color-border);color:var(--color-text-secondary);" onclick="toggleLogFileList()">
        <i data-lucide="list" class="w-3 h-3 inline mr-1"></i>显示全部日志文件列表
      </button>
      <div id="log-file-list" class="hidden space-y-1 max-h-[200px] overflow-y-auto px-1">`;
      files.slice(0, 50).forEach(f => {
        html += `<div class="text-xs py-1 px-2 rounded truncate" style="color:var(--color-text-muted);background:var(--color-bg-card);">${escapeHtml(f.path)} <span class="opacity-50">(${f.size_kb}KB)</span></div>`;
      });
      if (files.length > 50) html += `<div class="text-xs text-center py-1" style="color:var(--color-text-muted);">…还有 ${files.length - 50} 个文件</div>`;
      html += `</div>`;
    }
    
    html += `<button class="w-full py-2 text-sm rounded-lg border transition-colors duration-200 cursor-pointer mt-2" style="border-color:var(--color-border);color:var(--color-text-secondary);" onclick="refreshLogTab()">
      <i data-lucide="refresh-cw" class="w-3 h-3 inline mr-1"></i>刷新
    </button>`;
    html += `</div>`;
    
    container.innerHTML = html;
    window._refreshLogStar = star;
  } catch(e) {
    container.innerHTML = `<div class="flex items-center justify-center py-8" style="color:var(--state-error);">日志加载失败: ${e.message}</div>`;
  }
}

// 辅助函数：切换日志文件列表
window.toggleLogFileList = function() {
  const el = document.getElementById('log-file-list');
  if (el) el.classList.toggle('hidden');
};

// 辅助函数：刷新日志
window.refreshLogTab = function() {
  if (window._refreshLogStar) renderDetailTab('logs', window._refreshLogStar);
};
```

---

### 任务 6：详情面板 — Tab "历史"

**文件：** 修改 `star-ui/pages/starmap.html`

- [ ] **步骤 1：在 renderDetailTab 函数中添加 tab === 'history' 分支**

```javascript
if (tab === 'history') {
  container.innerHTML = '<div class="flex items-center justify-center py-8" style="color:var(--color-text-muted);"><i data-lucide="loader" class="w-5 h-5 animate-spin mr-2"></i>加载中…</div>';
  lucide.createIcons();
  
  try {
    const res = await emissaryApi.history(star.pid, 20).catch(() => ({ history: [] }));
    const history = res.history || [];
    
    if (history.length === 0) {
      container.innerHTML = `<div class="flex flex-col items-center justify-center py-12" style="color:var(--color-text-muted);">
        <i data-lucide="history" class="w-10 h-10 mb-2"></i>
        <p class="text-sm">暂无对话历史</p>
      </div>`;
    } else {
      let html = `<div class="space-y-2"><div class="text-xs mb-2" style="color:var(--color-text-muted);">共 ${res.total || history.length} 条记录</div>`;
      history.forEach((h, idx) => {
        const status = h.status === 'completed' ? '✅' : (h.status === 'error' ? '❌' : '⏳');
        const source = h.response_preview ? '⚡' : '📷';
        html += `<div class="px-3 py-2 rounded-lg" style="background:var(--color-bg-card);">
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs font-mono" style="color:var(--color-text-muted);">#${history.length - idx}</span>
            <span class="text-xs">${status} ${h.duration ? h.duration.toFixed(1) + 's' : '--'}</span>
          </div>
          <div class="text-sm truncate" style="color:var(--color-text-primary);">${escapeHtml(h.prompt)}</div>
          <div class="text-xs mt-1 truncate" style="color:var(--color-text-secondary);">${escapeHtml((h.response_preview || '(空)').slice(0, 80))}</div>
        </div>`;
      });
      html += `</div>`;
      container.innerHTML = html;
    }
  } catch(e) {
    container.innerHTML = `<div class="flex items-center justify-center py-8" style="color:var(--state-error);">历史加载失败: ${e.message}</div>`;
  }
}
```

---

### 任务 7：基础设施 — 侧边栏导航修复 + 连接状态增强

**文件：** 修改 `star-ui/pages/starmap.html`，`star-ui/pages/orbit.html`，`star-ui/pages/starlight.html`

- [ ] **步骤 1：修复 starmap.html 侧边栏导航链接**

将侧边栏中 3 个导航链接的 `href="#"` 改为实际的页面 URL，并添加选中星体传递：

```html
<!-- 约第 178 行 -->
<a href="/ui/pages/starmap.html" title="Star Map" ...>...</a>
<a href="/ui/pages/orbit.html" title="Orbit Console" ...>...</a>
<a href="/ui/pages/starlight.html" title="Starlight Review" ...>...</a>
```

- [ ] **步骤 2：增强 starmap.html 的连接状态指示器**

在右上角状态区域增加悬浮详情：

```html
<!-- 约第 223 行，替换已连接指示灯 -->
<div class="relative group flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-default" style="background:var(--color-bg-card);">
  <span class="w-2 h-2 rounded-full shrink-0" id="status-dot" style="background:var(--color-status-shining);box-shadow:0 0 6px var(--color-status-shining);"></span>
  <span class="text-sm whitespace-nowrap" id="status-text" style="color:var(--color-text-secondary);">已连接</span>
  <!-- 悬浮提示 -->
  <div class="absolute top-full right-0 mt-2 px-3 py-2 rounded-lg text-xs whitespace-nowrap hidden group-hover:block z-50" style="background:var(--color-bg-elevated);color:var(--color-text-secondary);border:1px solid var(--color-border);">
    <div>API: http://localhost:8767</div>
    <div id="ws-status">WebSocket: 已连接</div>
  </div>
</div>
```

同时更新加载数据后的 WebSocket 回调代码，连接/断线时更新指示器：
```javascript
// connectWebSocket 回调中
onConnected: () => {
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  if (dot) { dot.style.background = 'var(--color-status-shining)'; dot.style.boxShadow = '0 0 6px var(--color-status-shining)'; }
  if (txt) txt.textContent = '已连接';
},
onClose: () => {
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  if (dot) { dot.style.background = 'var(--color-status-faded)'; dot.style.boxShadow = 'none'; }
  if (txt) txt.textContent = '重新连接中…';
}
```

- [ ] **步骤 3：修复 orbit.html 和 starlight.html 的导航链接**

```html
<!-- orbit.html: 导航栏 -->
<a href="/ui/pages/starmap.html" ...>...</a>
<a href="/ui/pages/orbit.html" ...>...</a>
<a href="/ui/pages/starlight.html" ...>...</a>
```

```html
<!-- starlight.html: 导航栏 -->
<a href="/ui/pages/starmap.html" ...>...</a>
<a href="/ui/pages/orbit.html" ...>...</a>
<a href="/ui/pages/starlight.html" ...>...</a>
```

- [ ] **步骤 4：orbit.html 页面加载时读取 sessionStorage 中的选中星体**

在 orbit.html 的 `<script>` 中（约页面底部）：

```javascript
// 读取上一页选中的星体
const savedId = appState.getSavedStarId();
if (savedId) {
  // 在星体中高亮显示
  const cards = document.querySelectorAll('[data-star-pid]');
  cards.forEach(c => {
    if (c.dataset.starPid === savedId) {
      c.style.borderColor = '#ffd700';
      c.style.boxShadow = '0 0 16px rgba(255,215,0,0.08)';
    }
  });
}
```

- [ ] **步骤 5：starlight.html 页面中响应卡片增加来源标签**

在 starlight.html 的响应流卡片模板中，在每个响应项旁边增加来源标签：

```html
<!-- 在 starlight.html 中，响应卡片的 HTML 模板内添加 -->
<span class="text-xs px-1.5 py-0.5 rounded" style="background:var(--color-bg-card);color:var(--color-text-muted);">⚡ 日志</span>
```

---

### 任务 8：骨架屏加载状态

**文件：** 修改 `star-ui/pages/starmap.html`

- [ ] **步骤 1：在星体网格区域添加骨架屏（静态 HTML + JS 控制显示/隐藏）**

在 `id="star-grid"` 内部，添加骨架屏 HTML：

```html
<!-- 骨架屏：6 个灰色占位卡片 -->
<div id="skeleton-grid" class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
  ${[1,2,3,4,5,6].map(() => `
    <div class="p-4 rounded-lg border animate-pulse" style="background:var(--color-bg-card);border-color:var(--color-border);">
      <div class="flex items-start gap-3 mb-3">
        <div class="w-10 h-10 rounded-full" style="background:var(--color-bg-elevated);"></div>
        <div class="flex-1">
          <div class="h-4 w-24 rounded" style="background:var(--color-bg-elevated);"></div>
          <div class="h-3 w-16 rounded mt-2" style="background:var(--color-bg-elevated);"></div>
        </div>
      </div>
      <div class="h-3 w-full rounded mb-3" style="background:var(--color-bg-elevated);"></div>
      <div class="flex gap-2">
        <div class="flex-1 h-7 rounded-lg" style="background:var(--color-bg-elevated);"></div>
        <div class="flex-1 h-7 rounded-lg" style="background:var(--color-bg-elevated);"></div>
      </div>
    </div>
  `).join('')}
</div>
```

在 `loadStarMapData` 函数开始时显示骨架屏，数据加载完成后隐藏骨架屏并显示真实数据：

```javascript
async function loadStarMapData() {
  document.getElementById('skeleton-grid')?.classList.remove('hidden');
  const grid = document.getElementById('star-grid');
  if (grid) grid.innerHTML = '';
  // ... 原有的加载逻辑
  // 数据渲染完成后：
  document.getElementById('skeleton-grid')?.classList.add('hidden');
}
```