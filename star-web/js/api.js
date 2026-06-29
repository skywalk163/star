/**
 * 群星 Star — API Client
 * REST + WebSocket 对接 star_api 后端
 */

const API_BASE = '';  // 相对路径，自动使用当前服务地址
const WS_URL = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/starlight`;

// ==================== REST API ====================

async function request(url, options = {}) {
  try {
    const res = await fetch(API_BASE + url, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `请求失败: ${res.status}`);
    }
    return await res.json();
  } catch (e) {
    console.warn('[Star API]', e.message);
    throw e;
  }
}

// === 星体管理 ===
const starApi = {
  list: () => request('/api/stars/'),
  types: () => request('/api/stars/types'),
  get: (pid) => request(`/api/stars/${pid}`),
  refresh: (pid) => request(`/api/stars/${pid}/refresh`, { method: 'POST' }),
  idle: (type) => request('/api/stars/idle' + (type ? `?star_type=${type}` : '')),
};

// === 新星管理 ===
const novaApi = {
  create: (data) => request('/api/novas/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  list: (status, starType) => {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (starType) params.set('star_type', starType);
    return request('/api/novas/' + (params.toString() ? `?${params}` : ''));
  },
  get: (id) => request(`/api/novas/${id}`),
  launch: (id) => request(`/api/novas/${id}/launch`, { method: 'POST' }),
  adjust: (id, newStarlight) => request(`/api/novas/${id}/adjust`, {
    method: 'POST',
    body: JSON.stringify({ new_starlight: newStarlight }),
  }),
  echo: (id, echo) => request(`/api/novas/${id}/echo`, {
    method: 'POST',
    body: JSON.stringify({ echo }),
  }),
  fade: (id, reason) => request(`/api/novas/${id}/fade?reason=${encodeURIComponent(reason)}`, {
    method: 'POST',
  }),
  darken: (id) => request(`/api/novas/${id}/darken`, { method: 'POST' }),
  gaze: (id) => request(`/api/novas/${id}/gaze`),
};

// === 星座管理 ===
const constellationApi = {
  create: (data) => request('/api/constellations/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  list: () => request('/api/constellations/'),
  get: (id) => request(`/api/constellations/${id}`),
  launch: (id) => request(`/api/constellations/${id}/launch`, { method: 'POST' }),
};

// === 系统 ===
const sysApi = {
  health: () => request('/health'),
  stats: () => request('/api/stats'),
};

// ==================== WebSocket ====================

let ws = null;
let wsCallbacks = {};
let wsConnected = false;
let heartbeatTimer = null;

function connectWebSocket(handlers) {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  wsCallbacks = handlers || {};
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    wsConnected = true;
    console.log('[WS] 已连接');
    if (wsCallbacks.onOpen) wsCallbacks.onOpen();
    heartbeatTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
      }
    }, 30000);
  };

  ws.onmessage = (event) => {
    if (event.data === 'pong') return;
    try {
      const msg = JSON.parse(event.data);
      switch (msg.type) {
        case 'connected':
          if (wsCallbacks.onConnected) wsCallbacks.onConnected(msg.data);
          break;
        case 'stars_updated':
          if (wsCallbacks.onStarsUpdated) wsCallbacks.onStarsUpdated(msg.data);
          break;
        case 'nova_status_change':
          if (wsCallbacks.onNovaStatusChange) wsCallbacks.onNovaStatusChange(msg.data);
          break;
        case 'starlight_received':
          if (wsCallbacks.onStarlight) wsCallbacks.onStarlight(msg.data);
          break;
        default:
          console.log('[WS] 未知消息:', msg.type);
      }
    } catch (e) {
      // 非 JSON 消息，忽略
    }
  };

  ws.onclose = () => {
    wsConnected = false;
    console.log('[WS] 断开');
    if (wsCallbacks.onClose) wsCallbacks.onClose();
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    // 3 秒后自动重连
    setTimeout(() => connectWebSocket(handlers), 3000);
  };

  ws.onerror = (e) => {
    console.warn('[WS] 错误');
    wsConnected = false;
  };
}

function disconnectWebSocket() {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  if (ws) {
    ws.onclose = null; // 阻止重连
    ws.close();
    ws = null;
  }
  wsConnected = false;
}

// === 星使交互 (Emissary) ===
const emissaryApi = {
  status: (starId) => request(`/api/emissary/${starId}/status`),
  send: (starId, prompt, adapter) => request(`/api/emissary/${starId}/send`, {
    method: 'POST',
    body: JSON.stringify({ prompt, adapter_name: adapter || null }),
  }),
  ask: (starId, prompt, adapter, timeout) => request(`/api/emissary/${starId}/ask`, {
    method: 'POST',
    body: JSON.stringify({ prompt, adapter_name: adapter || null, timeout: timeout || null }),
  }),
  wait: (starId, timeout) => request(`/api/emissary/${starId}/wait`, {
    method: 'POST',
    body: JSON.stringify({ timeout: timeout || null }),
  }),
  response: (starId) => request(`/api/emissary/${starId}/response`),
  history: (starId, limit) => request(`/api/emissary/${starId}/history?limit=${limit || 20}`),
  tasks: (starId) => request(`/api/emissary/${starId}/tasks`),
  todos: (starId) => request(`/api/emissary/${starId}/todos`),
  ocrStatus: (starId) => request(`/api/emissary/${starId}/ocr-status`),
  screenshot: (starId) => request(`/api/emissary/${starId}/screenshot`),
  adapters: () => request('/api/emissary/adapters'),
  regions: () => request('/api/emissary/regions'),
};

// === OCR 实时流 WebSocket ===
let ocrWs = null;
let ocrWsCallbacks = {};
let ocrWsConnected = false;

function connectOcrStream(starId, handlers, interval = 3) {
  if (ocrWs && ocrWs.readyState === WebSocket.OPEN) {
    ocrWs.close();
  }

  ocrWsCallbacks = handlers || {};
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.host}/ws/ocr/${starId}?interval=${interval}`;

  ocrWs = new WebSocket(wsUrl);

  ocrWs.onopen = () => {
    ocrWsConnected = true;
    console.log('[OCR WS] 已连接:', starId);
    if (ocrWsCallbacks.onOpen) ocrWsCallbacks.onOpen();
  };

  ocrWs.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'ocr_update') {
        if (ocrWsCallbacks.onOcrUpdate) ocrWsCallbacks.onOcrUpdate(msg.data);
      } else if (msg.type === 'connected') {
        if (ocrWsCallbacks.onConnected) ocrWsCallbacks.onConnected(msg);
      }
    } catch (e) {
      // 忽略非 JSON 消息
    }
  };

  ocrWs.onclose = () => {
    ocrWsConnected = false;
    console.log('[OCR WS] 断开:', starId);
    if (ocrWsCallbacks.onClose) ocrWsCallbacks.onClose();
  };

  ocrWs.onerror = (e) => {
    console.warn('[OCR WS] 错误:', e);
    ocrWsConnected = false;
  };
}

function disconnectOcrStream() {
  if (ocrWs) {
    ocrWs.onclose = null;
    ocrWs.close();
    ocrWs = null;
  }
  ocrWsConnected = false;
}
