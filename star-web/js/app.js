/**
 * 群星 Star — App Core
 * SPA 路由、全局状态、页面渲染调度
 */

// ==================== 全局状态 ====================
const AppState = {
  currentPage: 'starmap',
  stars: [],
  novas: [],
  selectedNova: null,
  selectedStar: null,
  stats: null,
  wsConnected: false,
  // 星轨控制台
  orbitTab: 'create',
  selectedEmissaryStar: null,
  filters: {
    starType: '',
    starStatus: '',
    novaStatus: '',
    novaPriority: '',
  },
};

// ==================== 路由 ====================
const routes = {
  starmap: { title: '星图面板', subtitle: 'Star Map', breadcrumb: '星图' },
  orbit: { title: '星轨控制台', subtitle: 'Orbit Console', breadcrumb: '星轨' },
  starlight: { title: '星辉审查', subtitle: 'Starlight Review', breadcrumb: '星辉' },
};

function navigate(page) {
  if (!routes[page]) return;
  AppState.currentPage = page;
  window.location.hash = page;
  renderPage();
}

function renderPage() {
  const page = AppState.currentPage;
  const route = routes[page];

  // 更新 header
  document.getElementById('page-title').textContent = route.title + ' / ' + route.subtitle;
  document.getElementById('page-breadcrumb').textContent = '群星 Star > ' + route.breadcrumb;

  // 更新导航激活状态
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
  });

  // 渲染页面内容
  const container = document.getElementById('main-content');
  container.innerHTML = '<div class="loading-spinner"></div>';

  switch (page) {
    case 'starmap':
      if (typeof renderStarMap === 'function') renderStarMap(container);
      break;
    case 'orbit':
      if (typeof renderOrbit === 'function') renderOrbit(container);
      break;
    case 'starlight':
      if (typeof renderStarlight === 'function') renderStarlight(container);
      break;
  }
}

// ==================== 工具函数 ====================

// 状态标签映射
const STATUS_MAP = {
  nascent: { label: '初生', color: 'var(--color-status-nascent)' },
  orbiting: { label: '入轨', color: 'var(--color-status-orbiting)' },
  shining: { label: '闪耀中', color: 'var(--color-status-shining)' },
  awaiting: { label: '待回响', color: 'var(--color-status-awaiting)' },
  constellated: { label: '成星', color: 'var(--color-status-constellated)' },
  faded: { label: '暗淡', color: 'var(--color-status-faded)' },
  darkened: { label: '熄灭', color: 'var(--color-status-darkened)' },
};

const PRIORITY_MAP = {
  3: { label: '超新星', color: 'var(--color-star-supernova)' },
  2: { label: '亮星', color: 'var(--color-star-bright)' },
  1: { label: '常星', color: 'var(--color-star-normal)' },
  0: { label: '暗星', color: 'var(--color-star-dim)' },
};

function statusBadge(status) {
  const s = STATUS_MAP[status] || { label: status, color: '#666' };
  return `<span class="status-badge" style="background:${s.color}20;color:${s.color};border:1px solid ${s.color}40;">${s.label}</span>`;
}

function priorityBadge(priority) {
  const p = PRIORITY_MAP[priority] || PRIORITY_MAP[1];
  return `<span class="priority-badge" style="background:${p.color}15;color:${p.color};">${p.label}</span>`;
}

function priorityBorder(priority) {
  const p = PRIORITY_MAP[priority] || PRIORITY_MAP[1];
  return p.color;
}

function timeAgo(dateStr) {
  if (!dateStr) return '—';
  const now = new Date();
  const date = new Date(dateStr);
  const diff = Math.floor((now - date) / 1000);
  if (diff < 60) return '刚刚';
  if (diff < 3600) return Math.floor(diff / 60) + '分钟前';
  if (diff < 86400) return Math.floor(diff / 3600) + '小时前';
  return Math.floor(diff / 86400) + '天前';
}

function starTypeIcon(type) {
  const icons = {
    trae: 'T', cursor: 'C', claude: 'Cl',
    codearts_atomcode: 'CA', windsurf: 'W', copilot: 'G',
  };
  return icons[type] || type.charAt(0).toUpperCase();
}

function starTypeColor(type) {
  const colors = {
    trae: '#42a5f5', cursor: '#66bb6a', claude: '#ab47bc',
    codearts_atomcode: '#ef5350', windsurf: '#ffa726', copilot: '#4fc3f7',
  };
  return colors[type] || '#9fa8da';
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ==================== Toast 通知 ====================
function showToast(message, type = 'info') {
  const colors = {
    info: 'var(--color-status-orbiting)',
    success: 'var(--color-status-shining)',
    warning: 'var(--color-status-awaiting)',
    error: 'var(--color-status-faded)',
  };
  const toast = document.createElement('div');
  toast.className = 'toast-notification';
  toast.style.borderLeftColor = colors[type] || colors.info;
  toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
  document.getElementById('toast-container').appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ==================== 初始化 ====================
async function initApp() {
  // 监听 hash 变化
  window.addEventListener('hashchange', () => {
    const page = window.location.hash.slice(1) || 'starmap';
    if (page !== AppState.currentPage) {
      AppState.currentPage = page;
      renderPage();
    }
  });

  // 导航事件委托
  document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', () => navigate(el.dataset.page));
  });

  // 连接 WebSocket
  connectWebSocket({
    onConnected: (data) => {
      AppState.wsConnected = true;
      AppState.stats = data.stats;
      updateConnectionStatus(true);
      if (AppState.currentPage === 'starmap') renderPage();
    },
    onStarsUpdated: (data) => {
      AppState.stars = data;
      if (AppState.currentPage === 'starmap') renderPage();
    },
    onNovaStatusChange: (data) => {
      // 刷新 nova 列表
      novaApi.list().then(res => {
        AppState.novas = res.novas || [];
        if (AppState.currentPage === 'orbit') renderPage();
        if (AppState.currentPage === 'starlight') renderPage();
      });
    },
    onStarlight: (data) => {
      if (AppState.currentPage === 'starlight') renderPage();
    },
    onClose: () => {
      AppState.wsConnected = false;
      updateConnectionStatus(false);
    },
  });

  // 初始导航
  AppState.currentPage = window.location.hash.slice(1) || 'starmap';
  renderPage();
}

function updateConnectionStatus(connected) {
  const dot = document.getElementById('ws-dot');
  const text = document.getElementById('ws-text');
  if (dot) {
    dot.style.background = connected ? 'var(--color-status-shining)' : 'var(--color-status-faded)';
    dot.style.boxShadow = connected ? '0 0 6px var(--color-status-shining)' : 'none';
  }
  if (text) text.textContent = connected ? '已连接' : '未连接';
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', initApp);
