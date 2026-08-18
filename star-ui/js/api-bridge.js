/**
 * 群星 Star — API 桥接层
 * 连接静态设计页面与后端 API
 */

const API_BASE = '';
const WS_URL = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/starlight`;

// ==================== REST API ====================
let _apiKey = '';
try {
  _apiKey = localStorage.getItem('star_api_key') || '';
} catch (e) {
  // 隐私模式下 localStorage 不可用：Key 退化为内存态，本次会话仍可用
}

function setApiKey(key) {
  _apiKey = key || '';
  try {
    if (key) {
      localStorage.setItem('star_api_key', key);
    } else {
      localStorage.removeItem('star_api_key');
    }
  } catch (e) { /* 同上：仅内存态 */ }
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
  if (!res.ok) {
    const err = new Error(`${res.status} ${res.statusText}`);
    err.status = res.status;   // 便于调用方区分 401（缺 Key）和其它失败
    // 鉴权失败统一广播，由 auth-gate.js 兜底做引导；页面只负责画自己的失败态。
    if (res.status === 401 || res.status === 403) {
      window.dispatchEvent(new CustomEvent('star:unauthorized', {
        detail: { path, status: res.status },
      }));
    }
    throw err;
  }
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

// ==================== 流式连接票据（SSE / WebSocket） ====================
//
// 浏览器原生 EventSource / WebSocket 都设不了 X-API-Key 请求头，所以先用带 header 的
// apiFetch 换一张短时一次性票据，票据再随 query 参数进连接 URL。
// 详见后端 star_api/auth.py 的「流式连接票据」一节。

// 取一张一次性流式票据。
// 鉴权未启用时后端返回空票据（ticket:''），调用方拿到 '' 原样使用即可，不必特判。
// 401/403 由 apiFetch 广播 star:unauthorized，同时向上抛给调用方决定是否重连。
async function getStreamTicket() {
  const data = await apiFetch('/api/auth/stream-ticket', { method: 'POST' });
  return (data && data.ticket) || '';
}

// 给流式 URL 附加票据。票据为空（鉴权未开）时原样返回。
function appendStreamTicket(url, ticket) {
  if (!ticket) return url;
  return url + (url.includes('?') ? '&' : '?') + 'ticket=' + encodeURIComponent(ticket);
}

// ==================== WebSocket 星光流 ====================
let ws = null;
let wsConnected = false;
let heartbeatTimer = null;
let wsCallbacks = {};

function connectWebSocket(handlers) {
  wsCallbacks = handlers || {};
  if (ws) ws.close();
  // 票据用后即焚，所以每次连接（含每次重连）都必须重新取，不能缓存复用
  getStreamTicket().then(ticket => {
    ws = new WebSocket(appendStreamTicket(WS_URL, ticket));
    bindWsHandlers();
  }).catch(err => {
    // 401/403：apiFetch 已广播 star:unauthorized，交给 AuthGate 引导补 Key。
    // 此时重连只是空转，等 AuthGate 拿到 Key 后由页面重新调用。
    if (err && (err.status === 401 || err.status === 403)) return;
    // 其它失败（服务刚起、网络抖动）沿用既有重连节奏
    setTimeout(() => connectWebSocket(wsCallbacks), 5000);
  });
}

function bindWsHandlers() {
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
  const baseUrl = `${protocol}//${location.host}/ws/ocr/${starId}?interval=${interval}`;
  // 每次连接重新取票据（一次性，重连不可复用）
  getStreamTicket().then(ticket => {
    ocrWs = new WebSocket(appendStreamTicket(baseUrl, ticket));
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
  }).catch(err => {
    // 401/403 已由 apiFetch 广播；OCR 流不自动重连，交给调用方在补 Key 后重新发起
    if (err && (err.status === 401 || err.status === 403)) return;
    if (ocrWsCallbacks.onClose) ocrWsCallbacks.onClose();
  });
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
  // @deprecated 后端 /api/work/ai 依赖从未赋值的 state.emissaries，恒返回空列表。
  // 请改用 adapterApi.list()（/api/dumate/adapters，AIAdapterRegistry 的唯一投影）。
  listAIs: () => apiFetch('/api/work/ai'),
  getAIStatus: (aiId) => apiFetch('/api/work/ai/' + aiId + '/status'),
  // @deprecated 后端 POST /api/work/ai/{id}/ask 签名不匹配（await 同步方法 + 多传 adapter_name），必然 TypeError。
  // 请改用 adapterApi.createTask() + adapterApi.getOutput() 轮询。
  askAI: (aiId, data) => apiFetch('/api/work/ai/' + aiId + '/ask', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
};

// ==================== DuMate API (搭子桥) ====================
const dumateApi = {
  discover: () => apiFetch('/api/dumate/discover'),
  status: () => apiFetch('/api/dumate/status'),
  bridgeStatus: () => apiFetch('/api/dumate/bridge/status'),
  listTasks: () => apiFetch('/api/dumate/tasks'),
  activeTasks: () => apiFetch('/api/dumate/tasks/active'),
  getTask: (taskId) => apiFetch('/api/dumate/tasks/' + taskId),
  getTaskContent: (taskId) => apiFetch('/api/dumate/tasks/' + taskId + '/content'),
  getTaskLog: (taskId) => apiFetch('/api/dumate/tasks/' + taskId + '/log'),
  listTaskTypes: () => apiFetch('/api/dumate/task-types'),
  listConversations: () => apiFetch('/api/dumate/conversations'),
  listWorkspaces: () => apiFetch('/api/dumate/workspaces'),
  createTask: (prompt, opts) => {
    const { agentName, workspaceId, taskType } = opts || {};
    return apiFetch('/api/dumate/tasks/create', {
      method: 'POST',
      body: JSON.stringify({
        prompt,
        agent_name: agentName || 'Comate',
        workspace_id: workspaceId || '',
        task_type: taskType || 'work',
      }),
    });
  },
  stopTask: (taskId) => apiFetch('/api/dumate/tasks/' + taskId + '/stop', {
    method: 'POST',
  }),
  // 会话输出内容（实时轮询）
  getConversationOutput: (convId, maxLines) =>
    apiFetch(`/api/dumate/conversations/${convId}/output?max_lines=${maxLines || 200}`),
  // SSE 事件流。EventSource 设不了请求头，URL 里必须带一次性票据；
  // 票据用后即焚，所以这两个函数是 async 的，每次（重）连都会重新取一张。
  streamUrl: async () => appendStreamTicket('/api/dumate/stream', await getStreamTicket()),
  streamSessionUrl: async (convId) =>
    appendStreamTicket('/api/dumate/stream/session/' + convId, await getStreamTicket()),
};

// ==================== Adapter API (统一 AI 适配器) ====================
// 通用适配器接口：DuMate / Trae Work 等任意已注册适配器共用同一套路由，
// 前端据此提供统一的连接入口与任务派发，而不必为每个适配器单独写 UI。
const adapterApi = {
  list: () => apiFetch('/api/dumate/adapters'),
  connect: (aiId) => apiFetch(`/api/dumate/adapters/${aiId}/connect`, { method: 'POST' }),
  disconnect: (aiId) => apiFetch(`/api/dumate/adapters/${aiId}/disconnect`, { method: 'POST' }),
  restart: (aiId) => apiFetch(`/api/dumate/adapters/${aiId}/restart`, { method: 'POST' }),
  setDefault: (aiId) => apiFetch(`/api/dumate/adapters/${aiId}/default`, { method: 'POST' }),
  status: (aiId) => apiFetch(`/api/dumate/adapters/${aiId}/status`),
  // 连接成功后能力自检（仅 Trae Work 等实现了 self_check 的适配器返回有效数据）
  selfCheck: (aiId) => apiFetch(`/api/dumate/adapters/${aiId}/selfcheck`),
  createTask: (aiId, prompt, opts) => {
    const { workspaceId, taskType } = opts || {};
    return apiFetch(`/api/dumate/adapters/${aiId}/tasks`, {
      method: 'POST',
      body: JSON.stringify({
        prompt,
        workspace_id: workspaceId || '',
        task_type: taskType || 'work',
      }),
    });
  },
  stopTask: (aiId, taskId) =>
    apiFetch(`/api/dumate/adapters/${aiId}/tasks/${taskId}/stop`, { method: 'POST' }),
  // 适配器无关的会话输出轮询（DuMate 走 .output 映射；Trae 读最新响应）
  getOutput: (aiId, convId, maxLines) =>
    apiFetch(`/api/dumate/adapters/${aiId}/tasks/${convId}/output?max_lines=${maxLines || 200}`),
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

  // 星群状态（/api/remote/* 需要 X-API-Key，必须走 apiFetch 而非裸 fetch）
  getStarsStatus: () => apiFetch('/api/remote/stars/status'),
  getStarsBrief: () => apiFetch('/api/remote/stars/brief'),

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