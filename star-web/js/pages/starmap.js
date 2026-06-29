/**
 * 群星 Star — 星图面板
 * Agent 发现与实时状态管理
 */

async function renderStarMap(container) {
  let stars = [];
  try {
    const res = await starApi.list();
    stars = res.stars || [];
    AppState.stars = stars;
  } catch (e) {
    // API 不可用时显示空状态
  }

  const shining = stars.filter(s => s.is_shining);
  const idle = stars.filter(s => !s.is_shining);
  const types = [...new Set(stars.map(s => s.star_type))];

  container.innerHTML = `
    <!-- Stats -->
    <div class="stats-strip">
      <div class="stat-card">
        <div class="stat-icon" style="color:var(--color-primary);">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
        </div>
        <div class="stat-info">
          <div class="stat-value">${stars.length}</div>
          <div class="stat-label">已发现星体</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color:var(--color-status-shining);">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        </div>
        <div class="stat-info">
          <div class="stat-value">${shining.length}</div>
          <div class="stat-label">闪耀中</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color:var(--color-star-dim);">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
        </div>
        <div class="stat-info">
          <div class="stat-value">${idle.length}</div>
          <div class="stat-label">空闲</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="color:var(--color-status-orbiting);">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
        </div>
        <div class="stat-info">
          <div class="stat-value">${types.length}</div>
          <div class="stat-label">星体类型</div>
        </div>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <select id="filter-star-type" class="filter-select">
        <option value="">全部类型</option>
        ${types.map(t => `<option value="${t}">${t}</option>`).join('')}
      </select>
      <div class="filter-pills">
        <button class="pill active" data-filter="all">全部</button>
        <button class="pill" data-filter="shining">闪耀中</button>
        <button class="pill" data-filter="idle">空闲</button>
      </div>
      <input type="text" id="search-star" class="filter-input" placeholder="搜索星体...">
      <button class="btn-primary" onclick="navigate('orbit')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        创建新星
      </button>
    </div>

    <!-- Star Grid -->
    <div class="star-grid" id="star-grid">
      ${stars.length === 0 ? '<div class="empty-state"><div class="empty-icon">&#9734;</div><div>暂未发现星体</div><div class="empty-hint">请确认 AI Agent 进程正在运行</div></div>' :
        stars.map(s => renderStarCard(s)).join('')}
    </div>

    <!-- Detail Panel -->
    <div class="detail-panel" id="detail-panel" style="display:none;">
      <div class="detail-header">
        <span>星体详情</span>
        <button class="btn-ghost" onclick="document.getElementById('detail-panel').style.display='none'">&times;</button>
      </div>
      <div id="detail-content"></div>
    </div>
  `;

  // 事件绑定
  bindStarMapEvents();
}

function renderStarCard(star) {
  const color = starTypeColor(star.star_type);
  const icon = starTypeIcon(star.star_type);
  const statusColor = star.is_shining ? 'var(--color-status-shining)' : 'var(--color-star-dim)';
  const statusText = star.is_shining ? '闪耀中' : '空闲';
  const glowClass = star.is_shining ? 'star-card-shining' : '';

  return `
    <div class="star-card ${glowClass}" data-pid="${star.pid}" onclick="showStarDetail(${star.pid})">
      <div class="star-card-header">
        <div class="star-avatar" style="background:${color}20;color:${color};border:1px solid ${color}40;">
          ${icon}
        </div>
        <div class="star-meta">
          <div class="star-name">${escapeHtml(star.star_type)}</div>
          <div class="star-pid">PID: ${star.pid}</div>
        </div>
      </div>
      <div class="star-title">${escapeHtml(star.title || star.star_type)}</div>
      <div class="star-card-footer">
        <div class="star-status">
          <span class="status-dot" style="background:${statusColor};${star.is_shining ? 'box-shadow:0 0 6px ' + statusColor : ''}"></span>
          <span style="color:${statusColor}">${statusText}</span>
        </div>
        <div class="star-actions">
          <button class="btn-sm btn-ghost" onclick="event.stopPropagation();refreshStar(${star.pid})">刷新</button>
        </div>
      </div>
    </div>
  `;
}

async function showStarDetail(pid) {
  try {
    const star = await starApi.get(pid);
    const panel = document.getElementById('detail-panel');
    const content = document.getElementById('detail-content');
    panel.style.display = 'flex';

    const color = starTypeColor(star.star_type);
    const statusColor = star.is_shining ? 'var(--color-status-shining)' : 'var(--color-star-dim)';

    content.innerHTML = `
      <div class="detail-avatar" style="background:${color}20;color:${color};">${starTypeIcon(star.star_type)}</div>
      <div class="detail-name">${escapeHtml(star.star_type)}</div>
      <div class="detail-rows">
        <div class="detail-row"><span class="detail-label">PID</span><span class="detail-value font-mono">${star.pid}</span></div>
        <div class="detail-row"><span class="detail-label">窗口句柄</span><span class="detail-value font-mono">${star.hwnd || '—'}</span></div>
        <div class="detail-row"><span class="detail-label">标题</span><span class="detail-value">${escapeHtml(star.title || '—')}</span></div>
        <div class="detail-row"><span class="detail-label">状态</span><span class="detail-value">${star.is_shining ? '<span style="color:var(--color-status-shining)">闪耀中</span>' : '<span style="color:var(--color-star-dim)">空闲</span>'}</span></div>
        <div class="detail-row"><span class="detail-label">最后活动</span><span class="detail-value">${star.last_activity || '—'}</span></div>
      </div>
    `;
  } catch (e) {
    showToast('获取星体详情失败: ' + e.message, 'error');
  }
}

async function refreshStar(pid) {
  try {
    const star = await starApi.refresh(pid);
    showToast(`星体 ${pid} 已刷新`, 'success');
    // 重新加载列表
    renderPage();
  } catch (e) {
    showToast('刷新失败: ' + e.message, 'error');
  }
}

function bindStarMapEvents() {
  // 类型筛选
  const typeSelect = document.getElementById('filter-star-type');
  if (typeSelect) {
    typeSelect.addEventListener('change', () => {
      AppState.filters.starType = typeSelect.value;
      filterStarGrid();
    });
  }

  // 状态筛选 pills
  document.querySelectorAll('.filter-pills .pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-pills .pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      AppState.filters.starStatus = btn.dataset.filter;
      filterStarGrid();
    });
  });

  // 搜索
  const searchInput = document.getElementById('search-star');
  if (searchInput) {
    let timer;
    searchInput.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        AppState.searchQuery = searchInput.value.toLowerCase();
        filterStarGrid();
      }, 200);
    });
  }
}

function filterStarGrid() {
  const cards = document.querySelectorAll('.star-card');
  const { starType, starStatus, searchQuery } = { ...AppState.filters, searchQuery: AppState.searchQuery };

  cards.forEach(card => {
    const pid = parseInt(card.dataset.pid);
    const star = AppState.stars.find(s => s.pid === pid);
    if (!star) return;

    let visible = true;
    if (starType && star.star_type !== starType) visible = false;
    if (starStatus === 'shining' && !star.is_shining) visible = false;
    if (starStatus === 'idle' && star.is_shining) visible = false;
    if (searchQuery && !star.star_type.toLowerCase().includes(searchQuery) && !(star.title || '').toLowerCase().includes(searchQuery)) visible = false;

    card.style.display = visible ? '' : 'none';
  });
}
