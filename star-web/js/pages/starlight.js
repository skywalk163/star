/**
 * 群星 Star — 星辉审查面板
 * 结果查看、回响反馈、观星历史、OCR 实时识别
 */

let _ocrStreamActive = false;
let _ocrStreamStarId = null;

async function renderStarlight(container) {
  let novas = [];
  try {
    const res = await novaApi.list();
    novas = res.novas || [];
    AppState.novas = novas;
  } catch (e) {
    // API 不可用
  }

  // 优先显示已选中的 nova，否则选第一个活跃的
  const activeNovas = novas.filter(n => n.status === 'shining' || n.status === 'awaiting');
  const selectedId = AppState.selectedNova || (activeNovas.length > 0 ? activeNovas[0].id : (novas.length > 0 ? novas[0].id : null));
  const selectedNova = novas.find(n => n.id === selectedId);

  container.innerHTML = `
    <!-- 实时星辉流 -->
    <div class="stream-section">
      <div class="section-label">实时星辉流</div>
      <div class="stream-cards" id="stream-cards">
        ${novas.length === 0 ? '<div class="empty-state" style="grid-column:1/-1;"><div class="empty-icon">&#9734;</div><div>暂无新星</div></div>' :
          activeNovas.length > 0 ?
            activeNovas.map(n => renderStreamCard(n, n.id === selectedId)).join('') :
            '<div class="empty-state" style="grid-column:1/-1;"><div class="empty-icon">&#9733;</div><div>暂无活跃新星</div></div>'
        }
      </div>
    </div>

    <!-- OCR 实时识别 -->
    <div class="ocr-section" style="margin-top:16px;">
      <div class="section-label" style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
        <span>📷 OCR 实时识别</span>
        <span style="font-size:11px;color:var(--color-text-muted);font-weight:400;" id="ocr-fps-info">--</span>
        <span style="flex:1;"></span>
        <button class="btn-sm ${_ocrStreamActive ? 'btn-danger' : 'btn-accent'}" id="ocr-toggle-btn" onclick="toggleOcrStream()" style="font-size:11px;">
          ${_ocrStreamActive ? '关闭' : '开启'}
        </button>
      </div>
      <div id="ocr-panel" style="display:${_ocrStreamActive ? 'block' : 'none'};">
        <div style="display:flex;gap:12px;font-size:11px;color:var(--color-text-muted);padding:8px 12px;background:var(--color-bg-card);border-radius:var(--radius-md) var(--radius-md) 0 0;border:1px solid var(--color-border);border-bottom:none;">
          <span>识别区域: <span id="ocr-region">--</span></span>
          <span>行数: <span id="ocr-lines">0</span></span>
          <span>截图: <span id="ocr-cap-time">--</span></span>
          <span>识别: <span id="ocr-recog-time">--</span></span>
        </div>
        <div id="ocr-display" style="background:var(--color-bg-deep);border:1px solid var(--color-border);border-radius:0 0 var(--radius-md) var(--radius-md);padding:12px;min-height:120px;max-height:300px;overflow-y:auto;font-family:var(--font-mono);font-size:12px;line-height:1.8;color:var(--color-text-secondary);">
          <div style="color:var(--color-text-muted);text-align:center;padding:40px 0;">等待 OCR 数据...</div>
        </div>
        ${_ocrStreamActive ? `
        <div style="display:flex;gap:8px;margin-top:8px;">
          <input type="text" id="ocr-star-input" class="form-input" style="flex:1;" placeholder="目标星体 PID" value="${_ocrStreamStarId || ''}">
          <button class="btn-sm btn-primary" onclick="sendOcrPrompt()">发送文本指令</button>
        </div>` : ''}
      </div>
    </div>

    <!-- 星辉详情 -->
    ${selectedNova ? `
    <div class="detail-section" style="margin-top:16px;">
      <div class="detail-split">
        <!-- 左：输出 -->
        <div class="output-panel">
          <div class="panel-header">
            <span class="section-label">星辉输出 / Starlight Output</span>
            <button class="btn-sm btn-ghost" onclick="copyOutput()">复制</button>
          </div>
          <div class="output-tabs">
            <button class="output-tab active" onclick="switchOutputTab(this, 'full')">完整输出</button>
            <button class="output-tab" onclick="switchOutputTab(this, 'log')">对话历史</button>
            <button class="output-tab" onclick="switchOutputTab(this, 'gaze')">观星日志</button>
          </div>
          <div class="output-content" id="output-content">
            <pre class="code-output" id="code-output">${escapeHtml(selectedNova.result_starlight || selectedNova.starlight || '等待星辉输出...')}</pre>
          </div>
        </div>

        <!-- 右：回响 -->
        <div class="echo-panel">
          <div class="section-label">回响 / Echo</div>
          <div class="echo-status">${selectedNova.status === 'shining' ? '任务执行中，星辉持续收集中...' : selectedNova.status === 'awaiting' ? '任务完成，等待你的回响' : '任务已结束'}</div>
          <div class="echo-quick-actions">
            <button class="btn-sm btn-accent" onclick="quickEcho('${selectedNova.id}', '继续')">继续</button>
            <button class="btn-sm btn-info" onclick="quickEcho('${selectedNova.id}', '请修改方向')">修改方向</button>
            <button class="btn-sm btn-success" onclick="quickEcho('${selectedNova.id}', '满意')">满意</button>
            <button class="btn-sm btn-danger" onclick="quickEcho('${selectedNova.id}', '不满意')">不满意</button>
          </div>
          <textarea id="echo-input" class="form-textarea font-mono" rows="4" placeholder="输入你的回响指令..."></textarea>
          <button class="btn-primary btn-block" style="margin-top:8px;" onclick="sendEcho('${selectedNova.id}')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            发送回响
          </button>
        </div>
      </div>
    </div>

    <!-- 观星历史 -->
    <div class="timeline-section" style="margin-top:16px;">
      <div class="section-label">观星历史</div>
      <div class="timeline" id="timeline">
        ${renderTimeline(selectedNova)}
      </div>
    </div>
    ` : '<div class="empty-state" style="margin-top:16px;"><div class="empty-icon">&#9734;</div><div>选择一颗新星查看星辉</div></div>'}
  `;
}

function renderStreamCard(nova, isSelected) {
  const statusColor = STATUS_MAP[nova.status] || STATUS_MAP.nascent;
  return `
    <div class="stream-card ${isSelected ? 'stream-card-selected' : ''}" onclick="selectNova('${nova.id}')">
      <div class="stream-card-header">
        <span class="font-mono" style="color:var(--color-text-muted);">${escapeHtml(nova.id)}</span>
        <span class="status-badge" style="background:${statusColor.color}20;color:${statusColor.color};border:1px solid ${statusColor.color}40;">${statusColor.label}</span>
      </div>
      <div class="stream-card-title">${escapeHtml(nova.title)}</div>
      <div class="stream-card-meta">
        <span>${nova.assigned_star || '自动'}</span>
        <span>${timeAgo(nova.updated_at)}</span>
      </div>
      <div class="stream-card-preview">${escapeHtml((nova.result_starlight || '等待输出...').substring(0, 80))}${(nova.result_starlight || '').length > 80 ? '...' : ''}</div>
    </div>
  `;
}

function renderTimeline(nova) {
  if (!nova || !nova.starlight_log || nova.starlight_log.length === 0) {
    return '<div class="empty-state"><div>暂无观星记录</div></div>';
  }

  const statusColors = {
    nascent: 'var(--color-status-nascent)',
    orbiting: 'var(--color-status-orbiting)',
    shining: 'var(--color-status-shining)',
    awaiting: 'var(--color-status-awaiting)',
    constellated: 'var(--color-status-constellated)',
    faded: 'var(--color-status-faded)',
    darkened: 'var(--color-status-darkened)',
  };

  return nova.starlight_log.map((entry, i) => {
    const isLast = i === nova.starlight_log.length - 1;
    const dotColor = entry.status ? (statusColors[entry.status] || 'var(--color-text-muted)') : 'var(--color-primary)';
    const label = entry.status ? STATUS_MAP[entry.status]?.label : (entry.role || '');
    const detail = entry.action === 'status_change' ? STATUS_MAP[entry.status]?.label + ' — ' + (entry.content || '') : (entry.content || entry.action || '');
    const timestamp = entry.timestamp ? entry.timestamp.split('T')[1]?.substring(0, 8) || entry.timestamp : '';

    return `
      <div class="timeline-item">
        <div class="timeline-dot" style="background:${dotColor};${isLast && nova.status === 'shining' ? 'animation:pulse 2s infinite;' : ''}"></div>
        <div class="timeline-line" style="background:${isLast ? 'transparent' : 'var(--color-border)'}"></div>
        <div class="timeline-content">
          <div class="timeline-time font-mono">${timestamp}</div>
          <div class="timeline-label" style="color:${dotColor};">${escapeHtml(label)}</div>
          <div class="timeline-detail">${escapeHtml(detail)}</div>
        </div>
      </div>
    `;
  }).join('');
}

function selectNova(id) {
  AppState.selectedNova = id;
  renderPage();
}

async function quickEcho(id, message) {
  try {
    await novaApi.echo(id, message);
    showToast('回响已发送', 'success');
    renderPage();
  } catch (e) {
    showToast('回响失败: ' + e.message, 'error');
  }
}

async function sendEcho(id) {
  const input = document.getElementById('echo-input');
  if (!input || !input.value.trim()) return;
  try {
    await novaApi.echo(id, input.value.trim());
    showToast('回响已发送', 'success');
    renderPage();
  } catch (e) {
    showToast('回响失败: ' + e.message, 'error');
  }
}

function copyOutput() {
  const code = document.getElementById('code-output');
  if (code) {
    navigator.clipboard.writeText(code.textContent).then(() => {
      showToast('已复制到剪贴板', 'success');
    });
  }
}

function switchOutputTab(btn, tab) {
  document.querySelectorAll('.output-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
}

// ==================== OCR 实时流控制 ====================

function toggleOcrStream() {
  if (_ocrStreamActive) {
    disconnectOcrStream();
    _ocrStreamActive = false;
    _ocrStreamStarId = null;
    document.getElementById('ocr-panel').style.display = 'none';
    document.getElementById('ocr-toggle-btn').textContent = '开启';
    document.getElementById('ocr-toggle-btn').className = 'btn-sm btn-accent';
  } else {
    const starInput = document.getElementById('ocr-star-input');
    const starId = starInput ? starInput.value.trim() : '';
    if (!starId) {
      // 尝试从当前选中的 nova 获取 assigned_star
      const selectedNova = AppState.novas.find(n => n.id === AppState.selectedNova);
      if (selectedNova && selectedNova.assigned_star) {
        _ocrStreamStarId = selectedNova.assigned_star;
      } else {
        showToast('请输入目标星体 PID', 'warning');
        return;
      }
    } else {
      _ocrStreamStarId = starId;
    }
    startOcrStream();
  }
}

function startOcrStream() {
  connectOcrStream(_ocrStreamStarId, {
    onOpen: () => {
      _ocrStreamActive = true;
      document.getElementById('ocr-panel').style.display = 'block';
      document.getElementById('ocr-toggle-btn').textContent = '关闭';
      document.getElementById('ocr-toggle-btn').className = 'btn-sm btn-danger';
      updateWsDot(true);
    },
    onClose: () => {
      _ocrStreamActive = false;
      document.getElementById('ocr-toggle-btn').textContent = '开启';
      document.getElementById('ocr-toggle-btn').className = 'btn-sm btn-accent';
      updateWsDot(false);
    },
    onOcrUpdate: (data) => renderOcrData(data),
  });
}

function renderOcrData(data) {
  document.getElementById('ocr-region').textContent = data.region || '--';
  document.getElementById('ocr-lines').textContent = data.line_count || 0;
  document.getElementById('ocr-cap-time').textContent = data.capture_time ? data.capture_time.toFixed(3) + 's' : '--';
  document.getElementById('ocr-recog-time').textContent = data.recognize_time ? data.recognize_time.toFixed(3) + 's' : '--';

  const display = document.getElementById('ocr-display');
  if (data.lines && data.lines.length > 0) {
    display.innerHTML = data.lines.map(line => `
      <div style="padding:1px 0;transition:background 0.3s;">
        <span style="font-size:10px;color:var(--color-text-muted);margin-right:6px;">[${(line.confidence * 100).toFixed(0)}%]</span>
        ${escapeHtml(line.text)}
      </div>
    `).join('');
    display.scrollTop = display.scrollHeight;
  } else if (data.text) {
    display.innerHTML = `<pre style="margin:0;">${escapeHtml(data.text)}</pre>`;
  } else {
    display.innerHTML = '<div style="color:var(--color-text-muted);">未识别到文字</div>';
  }

  // FPS
  const fpsEl = document.getElementById('ocr-fps-info');
  if (data.recognize_time) {
    fpsEl.textContent = `${(1 / (data.capture_time + data.recognize_time + 3)).toFixed(1)} FPS (间隔3s)`;
  }
}

async function sendOcrPrompt() {
  const input = document.getElementById('ocr-star-input');
  const starId = input ? input.value.trim() : _ocrStreamStarId;
  if (!starId) {
    showToast('请先输入目标星体 PID', 'warning');
    return;
  }
  const promptText = prompt('输入要发送的文本指令:');
  if (!promptText) return;

  try {
    const res = await emissaryApi.send(starId, promptText);
    showToast('指令已发送', 'success');
  } catch (e) {
    showToast('发送失败: ' + e.message, 'error');
  }
}

function updateWsDot(connected) {
  const dot = document.getElementById('ws-dot');
  const text = document.getElementById('ws-text');
  if (dot) {
    dot.style.background = connected ? 'var(--color-status-shining)' : 'var(--color-star-dim)';
    dot.style.boxShadow = connected ? '0 0 6px var(--color-status-shining)' : 'none';
  }
  if (text) text.textContent = connected ? 'OCR 已连接' : '连接中...';
}