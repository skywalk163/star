/**
 * 群星 Star — 星轨控制台
 * 任务创建、队列管理、发射/调整/回响、星使交互
 */

async function renderOrbit(container) {
  let novas = [];
  let adapters = [];
  let stars = [];
  try {
    const res = await novaApi.list();
    novas = res.novas || [];
    AppState.novas = novas;
  } catch (e) {}

  try {
    const res = await emissaryApi.adapters();
    adapters = res.adapters || [];
  } catch (e) {}

  try {
    const res = await starApi.list();
    stars = res.stars || [];
  } catch (e) {}

  const tab = AppState.orbitTab || 'create';

  container.innerHTML = `
    <div class="orbit-layout">
      <!-- 左栏：任务队列 -->
      <div class="orbit-left">
        <div class="orbit-filters">
          <div class="filter-pills" id="nova-status-pills">
            <button class="pill active" data-status="">全部</button>
            <button class="pill" data-status="nascent">初生</button>
            <button class="pill" data-status="orbiting">入轨</button>
            <button class="pill" data-status="shining">闪耀中</button>
            <button class="pill" data-status="awaiting">待回响</button>
            <button class="pill" data-status="constellated">成星</button>
          </div>
        </div>
        <div class="nova-list" id="nova-list">
          ${novas.length === 0 ? '<div class="empty-state"><div class="empty-icon">&#9734;</div><div>暂无新星</div><div class="empty-hint">在右侧表单中创建第一个任务</div></div>' :
            novas.map(n => renderNovaRow(n)).join('')}
        </div>
      </div>

      <!-- 右栏：标签切换 -->
      <div class="orbit-right">
        <div style="display:flex;gap:4px;margin-bottom:12px;">
          <button class="btn-sm ${tab === 'create' ? 'btn-primary' : 'btn-ghost'}" onclick="switchOrbitTab('create')">诞生新星</button>
          <button class="btn-sm ${tab === 'emissary' ? 'btn-primary' : 'btn-ghost'}" onclick="switchOrbitTab('emissary')">星使交互</button>
        </div>
        ${tab === 'create' ? renderCreateForm(novas, stars) : renderEmissaryPanel(adapters, stars)}
      </div>
    </div>
  `;

  // 绑定状态筛选
  document.querySelectorAll('#nova-status-pills .pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#nova-status-pills .pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      AppState.filters.novaStatus = btn.dataset.status;
      filterNovaList();
    });
  });
}

function renderNovaRow(nova) {
  const borderColor = priorityBorder(nova.priority);
  return `
    <div class="nova-row" data-status="${nova.status}" data-id="${nova.id}" style="border-left:3px solid ${borderColor};">
      <div class="nova-row-main">
        <div class="nova-row-header">
          <span class="nova-id font-mono">${escapeHtml(nova.id)}</span>
          ${statusBadge(nova.status)}
          ${priorityBadge(nova.priority)}
        </div>
        <div class="nova-title">${escapeHtml(nova.title)}</div>
        <div class="nova-meta">
          <span class="nova-star-tag">${nova.assigned_star ? escapeHtml(nova.assigned_star) : '自动'}</span>
          <span class="nova-time">${timeAgo(nova.created_at)}</span>
        </div>
      </div>
      <div class="nova-row-actions">
        ${nova.status === 'nascent' ? `<button class="btn-sm btn-accent" onclick="launchNova('${nova.id}')">发射</button>` : ''}
        ${nova.status === 'shining' ? `<button class="btn-sm btn-info" onclick="adjustNova('${nova.id}')">调整</button>` : ''}
        ${nova.status === 'awaiting' ? `<button class="btn-sm btn-warning" onclick="echoNova('${nova.id}')">回响</button>` : ''}
        ${nova.status !== 'darkened' && nova.status !== 'faded' && nova.status !== 'constellated' ? `<button class="btn-sm btn-ghost" onclick="darkenNova('${nova.id}')">熄灭</button>` : ''}
        <button class="btn-sm btn-ghost" onclick="viewNovaDetail('${nova.id}')">详情</button>
      </div>
    </div>
  `;
}

function renderCreateForm(novas, stars) {
  return `
    <div class="form-panel">
      <h2 class="form-title">诞生新星</h2>
      <form id="nova-form" onsubmit="handleCreateNova(event)">
        <div class="form-group">
          <label class="form-label">任务标题</label>
          <input type="text" name="title" class="form-input" placeholder="输入任务标题..." required>
        </div>
        <div class="form-group">
          <label class="form-label">任务描述</label>
          <textarea name="description" class="form-textarea" rows="2" placeholder="详细描述任务需求..."></textarea>
        </div>
        <div class="form-group">
          <label class="form-label">星光指令</label>
          <textarea name="starlight" class="form-textarea font-mono" rows="4" placeholder="发送给 AI Agent 的具体指令..." required></textarea>
        </div>
        <div class="form-group">
          <label class="form-label">目标星体</label>
          <select name="assigned_star" class="form-select">
            <option value="">自动路由</option>
            ${stars.length > 0 ? stars.map(s => `<option value="${s.pid}">${escapeHtml(s.title)} (${s.pid})</option>`).join('') : ''}
            <option value="trae">Trae</option>
            <option value="cursor">Cursor</option>
            <option value="claude">Claude</option>
            <option value="windsurf">Windsurf</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">优先级</label>
          <div class="priority-selector">
            ${[
              { value: '0', label: '暗星', color: 'var(--color-star-dim)' },
              { value: '1', label: '常星', color: 'var(--color-star-normal)' },
              { value: '2', label: '亮星', color: 'var(--color-star-bright)' },
              { value: '3', label: '超新星', color: 'var(--color-star-supernova)' },
            ].map((p, i) => `
              <label class="priority-option">
                <input type="radio" name="priority" value="${p.value}" ${i === 1 ? 'checked' : ''}>
                <span class="priority-tag" style="color:${p.color};">${p.label}</span>
              </label>
            `).join('')}
          </div>
        </div>
        <button type="submit" class="btn-primary btn-block">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新星诞生
        </button>
      </form>
    </div>
  `;
}

function renderEmissaryPanel(adapters, stars) {
  const selectedStar = AppState.selectedEmissaryStar || (stars.length > 0 ? stars[0].pid : '');
  return `
    <div class="form-panel">
      <h2 class="form-title">星使交互</h2>
      <div class="form-group">
        <label class="form-label">目标星体</label>
        <select id="emissary-star-select" class="form-select" onchange="selectEmissaryStar(this.value)">
          <option value="">选择星体...</option>
          ${stars.map(s => `<option value="${s.pid}" ${s.pid === selectedStar ? 'selected' : ''}>${escapeHtml(s.title)} (${s.pid})</option>`).join('')}
        </select>
      </div>

      <div id="emissary-info" style="display:${selectedStar ? 'block' : 'none'};">
        <div style="display:flex;gap:4px;margin-bottom:8px;flex-wrap:wrap;">
          <button class="btn-sm btn-info" onclick="emissaryGetStatus()" style="font-size:11px;">状态</button>
          <button class="btn-sm btn-info" onclick="emissaryGetTasks()" style="font-size:11px;">任务列</button>
          <button class="btn-sm btn-info" onclick="emissaryGetTodos()" style="font-size:11px;">待办列</button>
          <button class="btn-sm btn-info" onclick="emissaryGetResponse()" style="font-size:11px;">响应</button>
          <button class="btn-sm btn-ghost" onclick="emissaryClearLog()" style="font-size:11px;">清空</button>
        </div>

        <div class="form-group">
          <label class="form-label">适配器</label>
          <select id="emissary-adapter-select" class="form-select">
            <option value="">自动检测</option>
            ${adapters.map(a => `<option value="${a.name}">${escapeHtml(a.name)}</option>`).join('')}
          </select>
        </div>

        <div class="form-group">
          <label class="form-label">文本指令</label>
          <textarea id="emissary-prompt-input" class="form-textarea font-mono" rows="4" placeholder="输入要发送给星体的文本指令..."></textarea>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn-sm btn-accent" onclick="emissarySendPrompt()" style="flex:1;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            发送指令
          </button>
          <button class="btn-sm btn-primary" onclick="emissaryAskAndWait()" style="flex:1;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            发送 + 等待
          </button>
        </div>

        <div class="emissary-log" id="emissary-log" style="margin-top:12px;background:var(--color-bg-deep);border:1px solid var(--color-border);border-radius:var(--radius-md);padding:10px;max-height:250px;overflow-y:auto;font-family:var(--font-mono);font-size:11px;line-height:1.6;color:var(--color-text-secondary);">
          <div style="color:var(--color-text-muted);text-align:center;padding:20px 0;">选择星体并发送指令...</div>
        </div>
      </div>
    </div>
  `;
}

// ==================== 任务操作 ====================

async function handleCreateNova(e) {
  e.preventDefault();
  const form = e.target;
  const data = {
    title: form.title.value.trim(),
    description: form.description.value.trim(),
    starlight: form.starlight.value.trim(),
    assigned_star: form.assigned_star.value || null,
    priority: parseInt(form.priority.value),
  };

  try {
    const res = await novaApi.create(data);
    showToast(`新星已诞生: ${res.id}`, 'success');
    form.reset();
    form.priority.value = '1';
    renderPage();
  } catch (err) {
    showToast('新星诞生失败: ' + err.message, 'error');
  }
}

async function launchNova(id) {
  try {
    await novaApi.launch(id);
    showToast(`新星 ${id} 已发射`, 'success');
    renderPage();
  } catch (e) {
    showToast('发射失败: ' + e.message, 'error');
  }
}

async function adjustNova(id) {
  const newStarlight = prompt('输入新的星光指令:');
  if (!newStarlight) return;
  try {
    await novaApi.adjust(id, newStarlight);
    showToast(`新星 ${id} 星轨已调整`, 'success');
    renderPage();
  } catch (e) {
    showToast('调整失败: ' + e.message, 'error');
  }
}

async function echoNova(id) {
  const echo = prompt('输入回响内容:');
  if (!echo) return;
  try {
    await novaApi.echo(id, echo);
    showToast(`回响已发送`, 'success');
    renderPage();
  } catch (e) {
    showToast('回响失败: ' + e.message, 'error');
  }
}

async function darkenNova(id) {
  if (!confirm('确认熄灭此新星？')) return;
  try {
    await novaApi.darken(id);
    showToast(`新星 ${id} 已熄灭`, 'info');
    renderPage();
  } catch (e) {
    showToast('操作失败: ' + e.message, 'error');
  }
}

async function viewNovaDetail(id) {
  navigate('starlight');
  setTimeout(() => {
    AppState.selectedNova = id;
    renderPage();
  }, 100);
}

function filterNovaList() {
  const rows = document.querySelectorAll('.nova-row');
  const status = AppState.filters.novaStatus;
  rows.forEach(row => {
    row.style.display = (!status || row.dataset.status === status) ? '' : 'none';
  });
}

// ==================== 标签切换 ====================

function switchOrbitTab(tab) {
  AppState.orbitTab = tab;
  renderPage();
}

function selectEmissaryStar(value) {
  AppState.selectedEmissaryStar = value;
  const info = document.getElementById('emissary-info');
  if (info) info.style.display = value ? 'block' : 'none';
  if (value) {
    const log = document.getElementById('emissary-log');
    if (log) log.innerHTML = `<div style="color:var(--color-status-orbiting);">已选择星体: ${value}</div>`;
  }
}

// ==================== 星使交互 ====================

function logEmissaryMsg(type, msg) {
  const log = document.getElementById('emissary-log');
  if (!log) return;
  const time = new Date().toLocaleTimeString();
  const colors = {
    send: 'var(--color-status-shining)',
    recv: 'var(--color-status-awaiting)',
    error: 'var(--color-status-faded)',
    info: 'var(--color-text-muted)',
  };
  const entry = document.createElement('div');
  entry.style.cssText = `padding:4px 0;border-bottom:1px solid var(--color-border);`;
  entry.innerHTML = `<span style="color:var(--color-text-muted);font-size:10px;">${time}</span> <span style="color:${colors[type] || colors.info};">${escapeHtml(msg)}</span>`;
  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
}

function getEmissaryStarId() {
  const sel = document.getElementById('emissary-star-select');
  return sel ? sel.value : AppState.selectedEmissaryStar;
}

function getEmissaryAdapter() {
  const sel = document.getElementById('emissary-adapter-select');
  return sel ? sel.value || null : null;
}

async function emissaryGetStatus() {
  const starId = getEmissaryStarId();
  if (!starId) { showToast('请先选择星体', 'warning'); return; }
  try {
    const res = await emissaryApi.status(starId);
    logEmissaryMsg('recv', `状态: ${JSON.stringify(res)}`);
  } catch (e) {
    logEmissaryMsg('error', `状态查询失败: ${e.message}`);
  }
}

async function emissaryGetTasks() {
  const starId = getEmissaryStarId();
  if (!starId) { showToast('请先选择星体', 'warning'); return; }
  try {
    const res = await emissaryApi.tasks(starId);
    const tasks = res.tasks || [];
    if (tasks.length === 0) {
      logEmissaryMsg('info', '暂无任务');
    } else {
      tasks.forEach(t => logEmissaryMsg('recv', `[${t.status || '?'}] ${t.title || t.text}`));
      logEmissaryMsg('info', `共 ${tasks.length} 个任务`);
    }
  } catch (e) {
    logEmissaryMsg('error', `任务查询失败: ${e.message}`);
  }
}

async function emissaryGetTodos() {
  const starId = getEmissaryStarId();
  if (!starId) { showToast('请先选择星体', 'warning'); return; }
  try {
    const res = await emissaryApi.todos(starId);
    const todos = res.todos || [];
    if (todos.length === 0) {
      logEmissaryMsg('info', '暂无待办');
    } else {
      todos.forEach(t => logEmissaryMsg('recv', `[${t.done ? '✓' : '○'}] ${t.text || t.title}`));
      logEmissaryMsg('info', `共 ${todos.length} 个待办`);
    }
  } catch (e) {
    logEmissaryMsg('error', `待办查询失败: ${e.message}`);
  }
}

async function emissaryGetResponse() {
  const starId = getEmissaryStarId();
  if (!starId) { showToast('请先选择星体', 'warning'); return; }
  try {
    const res = await emissaryApi.response(starId);
    const text = res.text || res.response || res.content || JSON.stringify(res);
    logEmissaryMsg('recv', `响应: ${text.substring(0, 500)}`);
  } catch (e) {
    logEmissaryMsg('error', `响应查询失败: ${e.message}`);
  }
}

async function emissarySendPrompt() {
  const starId = getEmissaryStarId();
  const input = document.getElementById('emissary-prompt-input');
  if (!starId || !input || !input.value.trim()) {
    showToast('请选择星体并输入指令', 'warning');
    return;
  }
  const prompt = input.value.trim();
  const adapter = getEmissaryAdapter();
  logEmissaryMsg('send', prompt.substring(0, 100));
  try {
    const res = await emissaryApi.send(starId, prompt, adapter);
    logEmissaryMsg('recv', `已发送, 响应ID: ${res.id || 'ok'}`);
    showToast('指令已发送', 'success');
  } catch (e) {
    logEmissaryMsg('error', `发送失败: ${e.message}`);
  }
}

async function emissaryAskAndWait() {
  const starId = getEmissaryStarId();
  const input = document.getElementById('emissary-prompt-input');
  if (!starId || !input || !input.value.trim()) {
    showToast('请选择星体并输入指令', 'warning');
    return;
  }
  const prompt = input.value.trim();
  const adapter = getEmissaryAdapter();
  logEmissaryMsg('send', `[等待响应] ${prompt.substring(0, 100)}`);
  try {
    const res = await emissaryApi.ask(starId, prompt, adapter, 60);
    const text = res.text || res.response || res.content || JSON.stringify(res);
    logEmissaryMsg('recv', `响应: ${text.substring(0, 500)}`);
    showToast('响应已接收', 'success');
  } catch (e) {
    logEmissaryMsg('error', `请求失败: ${e.message}`);
  }
}

function emissaryClearLog() {
  const log = document.getElementById('emissary-log');
  if (log) log.innerHTML = '<div style="color:var(--color-text-muted);text-align:center;padding:20px 0;">日志已清空</div>';
}