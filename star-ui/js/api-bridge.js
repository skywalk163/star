/**
 * 群星 Star — API 桥接层
 * 连接静态设计页面与后端 API
 */

const API_BASE = '';
const WS_URL = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/starlight`;

// ==================== REST API ====================
let _apiKey = localStorage.getItem('star_api_key') || '';

function setApiKey(key) {
  _apiKey = key || '';
  if (key) {
    localStorage.setItem('star_api_key', key);
  } else {
    localStorage.removeItem('star_api_key');
  }
}

function getApiKey() {
  return _apiKey;
}

async function apiFetch(path, options = {}) {
  const url = API_BASE + path;
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (_apiKey) {
    headers['X-API-Key'] = _apiKey;
  }
  const res = await fetch(url, {
    headers,
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

const starApi = {
  list: () => apiFetch('/api/stars/'),
  types: () => apiFetch('/api/stars/types'),
};

const novaApi = {
  list: (params = '') => apiFetch('/api/novas/' + params),
  create: (data) => apiFetch('/api/novas/', { method: 'POST', body: JSON.stringify(data) }),
  get: (id) => apiFetch(`/api/novas/${id}`),
  launch: (id) => apiFetch(`/api/novas/${id}/launch`, { method: 'POST' }),
  adjust: (id, starlight) => apiFetch(`/api/novas/${id}/adjust`, { method: 'POST', body: JSON.stringify({ starlight }) }),
  echo: (id, message) => apiFetch(`/api/novas/${id}/echo`, { method: 'POST', body: JSON.stringify({ message }) }),
  fade: (id) => apiFetch(`/api/novas/${id}/fade`, { method: 'POST' }),
  darken: (id) => apiFetch(`/api/novas/${id}/darken`, { method: 'POST' }),
  gaze: (id) => apiFetch(`/api/novas/${id}/gaze`),
};

const emissaryApi = {
  status: (starId) => apiFetch(`/api/emissary/${starId}/status`),
  send: (starId, prompt, adapter) => apiFetch(`/api/emissary/${starId}/send`, { method: 'POST', body: JSON.stringify({ prompt, adapter_name: adapter }) }),
  ask: (starId, prompt, adapter, timeout) => apiFetch(`/api/emissary/${starId}/ask`, { method: 'POST', body: JSON.stringify({ prompt, adapter_name: adapter, timeout }) }),
  response: (starId) => apiFetch(`/api/emissary/${starId}/response`),
  history: (starId, limit) => apiFetch(`/api/emissary/${starId}/history?limit=${limit || 20}`),
  tasks: (starId) => apiFetch(`/api/emissary/${starId}/tasks`),
  todos: (starId) => apiFetch(`/api/emissary/${starId}/todos`),
  ocrStatus: (starId) => apiFetch(`/api/emissary/${starId}/ocr-status`),
  screenshot: (starId) => apiFetch(`/api/emissary/${starId}/screenshot`),
  adapters: () => apiFetch('/api/emissary/adapters'),
  regions: () => apiFetch('/api/emissary/regions'),
};

const sysApi = {
  health: () => apiFetch('/health'),
  stats: () => apiFetch('/api/stats'),
};

const constellationApi = {
  list: () => apiFetch('/api/constellations/'),
  create: (data) => apiFetch('/api/constellations/', { method: 'POST', body: JSON.stringify(data) }),
  get: (id) => apiFetch(`/api/constellations/${id}`),
  orchestrate: (id) => apiFetch(`/api/constellations/${id}/orchestrate`, { method: 'POST' }),
  dissolve: (id) => apiFetch(`/api/constellations/${id}/dissolve`, { method: 'POST' }),
};

const configApi = {
  get: () => apiFetch('/api/config'),
  update: (data) => apiFetch('/api/config', { method: 'PUT', body: JSON.stringify(data) }),
};

// ==================== WebSocket 星光流 ====================
let ws = null;
let wsConnected = false;
let heartbeatTimer = null;
let wsCallbacks = {};

function connectWebSocket(handlers) {
  wsCallbacks = handlers || {};
  if (ws) ws.close();
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    wsConnected = true;
    if (wsCallbacks.onConnected) wsCallbacks.onConnected();
    heartbeatTimer = setInterval(() => { try { ws.send('ping'); } catch(e) {} }, 15000);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'connected' && wsCallbacks.onConnected) wsCallbacks.onConnected(msg.data);
      else if (msg.type === 'stars_updated' && wsCallbacks.onStarsUpdated) wsCallbacks.onStarsUpdated(msg.data);
      else if (msg.type === 'nova_status_change' && wsCallbacks.onNovaStatusChange) wsCallbacks.onNovaStatusChange(msg.data);
      else if (msg.type === 'starlight' && wsCallbacks.onStarlight) wsCallbacks.onStarlight(msg.data);
    } catch(e) {}
  };

  ws.onclose = () => {
    wsConnected = false;
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    if (wsCallbacks.onClose) wsCallbacks.onClose();
    setTimeout(() => connectWebSocket(wsCallbacks), 5000);
  };

  ws.onerror = () => {};
}

function disconnectWebSocket() {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  if (ws) { ws.onclose = null; ws.close(); ws = null; }
  wsConnected = false;
}

// ==================== Utility ====================
function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const sec = Math.floor((now - then) / 1000);
  if (sec < 60) return '刚刚';
  if (sec < 3600) return `${Math.floor(sec/60)}分钟前`;
  if (sec < 86400) return `${Math.floor(sec/3600)}小时前`;
  return `${Math.floor(sec/86400)}天前`;
}

function addNavListeners() {
  document.querySelectorAll('[data-dom-id^="nav-"]').forEach(el => {
    const page = el.dataset.domId.replace('nav-', '');
    el.addEventListener('click', (e) => {
      e.preventDefault();
      window.location.href = `/ui/pages/${page}.html`;
    });
  });
}

// ==================== OCR WebSocket ====================
let ocrWs = null;
let ocrWsCallbacks = {};

function connectOcrStream(starId, handlers, interval = 3) {
  if (ocrWs) ocrWs.close();
  ocrWsCallbacks = handlers || {};
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ocrWs = new WebSocket(`${protocol}//${location.host}/ws/ocr/${starId}?interval=${interval}`);
  ocrWs.onopen = () => { if (ocrWsCallbacks.onOpen) ocrWsCallbacks.onOpen(); };
  ocrWs.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'ocr_update' && ocrWsCallbacks.onOcrUpdate) ocrWsCallbacks.onOcrUpdate(msg.data);
      else if (msg.type === 'connected' && ocrWsCallbacks.onConnected) ocrWsCallbacks.onConnected(msg);
    } catch(e) {}
  };
  ocrWs.onclose = () => { if (ocrWsCallbacks.onClose) ocrWsCallbacks.onClose(); };
  ocrWs.onerror = () => {};
}

function disconnectOcrStream() {
  if (ocrWs) { ocrWs.onclose = null; ocrWs.close(); ocrWs = null; }
}

// ==================== 日志 API ====================
emissaryApi.logs = (starId) => apiFetch(`/api/emissary/${starId}/logs`);
emissaryApi.logRecent = (starId, lines) => apiFetch(`/api/emissary/${starId}/logs/recent?max_lines=${lines || 30}`);
emissaryApi.discoverLogs = () => apiFetch('/api/emissary/logs/discover');

// ==================== 通知系统 ====================
const NOTIFICATION_STYLES = {
  success: { bg: '#059669', icon: '✔' },
  warning: { bg: '#d97706', icon: '⚠' },
  error:   { bg: '#dc2626', icon: '✖' },
  info:    { bg: '#2563eb', icon: 'ℹ' },
};

function showNotification(msg, type = 'info', duration) {
  const existing = document.getElementById('star-notification');
  if (existing) existing.remove();

  const style = NOTIFICATION_STYLES[type] || NOTIFICATION_STYLES.info;
  const autoClose = type === 'success' && (duration === undefined || duration !== null);

  const el = document.createElement('div');
  el.id = 'star-notification';
  el.innerHTML = `<span style="margin-right:8px">${style.icon}</span><span>${escapeHtml(msg)}</span>`;
  Object.assign(el.style, {
    position: 'fixed',
    top: '0',
    left: '50%',
    transform: 'translateX(-50%)',
    zIndex: '9999',
    display: 'flex',
    alignItems: 'center',
    padding: '12px 24px',
    borderRadius: '0 0 8px 8px',
    color: '#fff',
    fontSize: '14px',
    lineHeight: '1.4',
    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
    background: style.bg,
    opacity: '0',
    transition: 'opacity 0.3s ease',
    cursor: 'default',
    maxWidth: '600px',
    wordBreak: 'break-word',
  });

  // 关闭按钮（非 success 或显式 duration 为 null 时显示）
  if (!autoClose) {
    const closeBtn = document.createElement('span');
    closeBtn.textContent = '✕';
    Object.assign(closeBtn.style, {
      marginLeft: '16px',
      cursor: 'pointer',
      fontWeight: 'bold',
      fontSize: '16px',
      opacity: '0.8',
    });
    closeBtn.onmouseenter = () => { closeBtn.style.opacity = '1'; };
    closeBtn.onmouseleave = () => { closeBtn.style.opacity = '0.8'; };
    closeBtn.onclick = () => hideNotification();
    el.appendChild(closeBtn);
  }

  document.body.appendChild(el);

  // 触发渐入
  requestAnimationFrame(() => { el.style.opacity = '1'; });

  // success 类型自动 3s 关闭
  if (autoClose) {
    const delay = duration !== undefined ? duration : 3000;
    setTimeout(() => hideNotification(), delay);
  }
}

function hideNotification() {
  const el = document.getElementById('star-notification');
  if (!el) return;
  el.style.opacity = '0';
  setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
}

window.showNotification = showNotification;
window.hideNotification = hideNotification;

// ==================== 全局状态 ====================
const appState = {
  selectedStarId: null,
  selectedStar: null,

  setSelectedStar(star) {
    if (!star) return;
    this.selectedStarId = String(star.pid || star.star_id || star.id || '');
    this.selectedStar = star;
    try {
      sessionStorage.setItem('star_selected', JSON.stringify(star));
      sessionStorage.setItem('selectedStarId', this.selectedStarId);
    } catch (e) { /* ignore */ }
  },

  getSavedStarId() {
    if (this.selectedStarId) return this.selectedStarId;
    try {
      const saved = sessionStorage.getItem('selectedStarId');
      if (saved) return saved;
      const star = JSON.parse(sessionStorage.getItem('star_selected') || '{}');
      return String(star.pid || star.star_id || star.id || '') || null;
    } catch (e) { /* ignore */ }
    return null;
  },
};

// ==================== Work API (任务调度) ====================
const workApi = {
  listTasks: () => apiFetch('/api/work/tasks'),
  getTask: (taskId) => apiFetch('/api/work/tasks/' + taskId),
  getTaskScript: (taskId, scriptName) => apiFetch('/api/work/tasks/' + taskId + '/script/' + scriptName),
  listAIs: () => apiFetch('/api/work/ai'),
  getAIStatus: (aiId) => apiFetch('/api/work/ai/' + aiId + '/status'),
  askAI: (aiId, data) => apiFetch('/api/work/ai/' + aiId + '/ask', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
};

// ==================== Remote API (远程控制) ====================
const remoteApi = {
  getScreenshotUrl: (hwnd, force = false) =>
    '/api/remote/screenshot/' + hwnd + (force ? '?force=1' : ''),
  getScreenshotStatus: (hwnd) => apiFetch('/api/remote/screenshot/' + hwnd + '/status'),
  refreshScreenshot: (hwnd) =>
    apiFetch('/api/remote/screenshot/' + hwnd + '/refresh', { method: 'POST' }),
  getHotspots: (starType) => apiFetch('/api/remote/hotspots/' + starType),
  clickWindow: (hwnd, xRatio, yRatio) =>
    apiFetch('/api/remote/click/' + hwnd + '?x_ratio=' + xRatio + '&y_ratio=' + yRatio, { method: 'POST' }),
  sendText: (hwnd, text, hotspot = 'input_box', pressEnter = true) =>
    apiFetch('/api/remote/send/' + hwnd + '?text=' + encodeURIComponent(text) +
      '&hotspot=' + hotspot + '&press_enter=' + pressEnter, { method: 'POST' }),

  // 键盘操作
  hotkey: (hwnd, keys) =>
    apiFetch('/api/remote/keyboard/' + hwnd + '/hotkey?keys=' + encodeURIComponent(keys), { method: 'POST' }),
  pressKey: (hwnd, key) =>
    apiFetch('/api/remote/keyboard/' + hwnd + '/press?key=' + encodeURIComponent(key), { method: 'POST' }),
  sendKeys: (hwnd, text) =>
    apiFetch('/api/remote/keyboard/' + hwnd + '/send?text=' + encodeURIComponent(text), { method: 'POST' }),
  sequence: (hwnd, seq) =>
    apiFetch('/api/remote/keyboard/' + hwnd + '/sequence', {
      method: 'POST',
      body: JSON.stringify(seq),
    }),

  // 标签页切换
  switchTab: (hwnd, index) =>
    apiFetch('/api/remote/tab/' + hwnd + '/switch?index=' + index, { method: 'POST' }),
  nextTab: (hwnd) =>
    apiFetch('/api/remote/tab/' + hwnd + '/next', { method: 'POST' }),
  prevTab: (hwnd) =>
    apiFetch('/api/remote/tab/' + hwnd + '/prev', { method: 'POST' }),
  getTabRegion: (hwnd) => apiFetch('/api/remote/tab/' + hwnd + '/region'),

  // 热点校准
  calibrate: (hwnd, starType = 'trae') =>
    apiFetch('/api/remote/calibrate/' + hwnd + '?star_type=' + starType, { method: 'POST' }),
  calibrateAndApply: (hwnd, starType = 'trae') =>
    apiFetch('/api/remote/calibrate/' + hwnd + '/apply?star_type=' + starType, { method: 'POST' }),

  // 认证
  getAuthStatus: () => apiFetch('/api/remote/auth/status'),
  setApiKey: setApiKey,
  getApiKey: getApiKey,

  // 审计日志
  getAuditLogs: (operation, hwnd) => {
    let path = '/api/remote/audit/logs?limit=30';
    if (operation) path += '&operation=' + encodeURIComponent(operation);
    if (hwnd) path += '&hwnd=' + hwnd;
    return apiFetch(path);
  },
};