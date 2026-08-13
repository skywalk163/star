/**
 * calibrator.js — 定位器校准器前端逻辑
 *
 * 原生 JS + fetch，不引第三方库。
 * 提供 window.__MOCK__ 开关：为 true 时用内置 mock 数据渲染。
 */

(function() {
  'use strict';

  // ==================== 状态 ====================
  var state = {
    candidates: [],
    selectedStarId: null,
    selectedCandidate: null,
    screenshot: null,       // base64 string
    uiaTree: [],
    truncated: false,
    imgNaturalW: 0,
    imgNaturalH: 0,
    imgDisplayW: 0,
    imgDisplayH: 0,
    highlightBox: null,     // {left, top, w, h} in display coords
    pendingPreview: null,   // YAML text from preview API
    loading: false,
  };

  var MOCK = typeof window.__MOCK__ !== 'undefined' ? window.__MOCK__ : false;

  // ==================== Mock 数据 ====================
  var MOCK_CANDIDATES = [
    {
      star_id: '12345', star_type: 'wechat', title: 'WeChat (微信)',
      pid: 12345,
      capabilities: { uia: true, visual: false, cdp: false }
    },
    {
      star_id: '67890', star_type: 'browser', title: 'Chrome — ChatGPT',
      pid: 67890,
      capabilities: { uia: true, visual: true, cdp: true }
    },
    {
      star_id: '11111', star_type: 'feishu', title: 'Feishu (飞书)',
      pid: 11111,
      capabilities: { uia: true, visual: false, cdp: false }
    },
  ];

  var MOCK_UIA_TREE = [
    { name: '微信', control_type: 'Window', automation_id: '', rect: [0,0,800,600], depth: 0 },
    { name: '', control_type: 'Pane', automation_id: '', rect: [0,0,800,600], depth: 1 },
    { name: '聊天区域', control_type: 'Pane', automation_id: 'chat_area', rect: [200,60,600,500], depth: 2 },
    { name: '输入框', control_type: 'Edit', automation_id: 'msg_input', rect: [200,480,600,560], depth: 3 },
    { name: '发送', control_type: 'Button', automation_id: 'send_btn', rect: [610,490,680,550], depth: 3 },
    { name: '停止', control_type: 'Button', automation_id: 'stop_btn', rect: [690,490,760,550], depth: 3 },
  ];

  var MOCK_SCREENSHOT =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';

  // ==================== DOM 引用 ====================
  function $(id) { return document.getElementById(id); }

  // ==================== API 调用 ====================
  function apiCall(path, options) {
    if (typeof apiFetch === 'function') {
      return apiFetch(path, options);
    }
    // 兜底：直接 fetch
    var url = path.startsWith('http') ? path : '/api' + path;
    return fetch(url, options).then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function notify(msg, type, duration) {
    if (typeof showNotification === 'function') {
      showNotification(msg, type, duration);
    } else {
      console.log('[' + (type || 'info') + '] ' + msg);
    }
  }

  // ==================== 状态横幅 ====================
  function setOnline(online) {
    var banner = $('statusBanner');
    var text = $('statusText');
    if (online) {
      banner.className = 'status-banner online';
      text.textContent = 'API 服务在线 — ' + new Date().toLocaleTimeString();
    } else {
      banner.className = 'status-banner offline';
      text.textContent = '后端未就绪 — 请检查 star_api 服务是否启动';
    }
  }

  // ==================== 渲染：候选列表 ====================
  function renderCandidates() {
    var container = $('candidateList');
    if (state.candidates.length === 0) {
      container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--color-text-muted);">未发现任何 agent</div>';
      return;
    }

    var html = '';
    state.candidates.forEach(function(c) {
      var active = c.star_id === state.selectedStarId ? ' active' : '';
      var capsHtml = '';
      ['uia', 'visual', 'cdp'].forEach(function(cap) {
        var on = c.capabilities && c.capabilities[cap];
        capsHtml += '<span class="cap-badge ' + (on ? 'on' : 'off') + '">' + cap + '</span>';
      });

      html += '<div class="candidate-item' + active + '" data-star-id="' + c.star_id + '">'
            + '<div class="candidate-name">' + escapeHtml(c.title || c.star_type) + '</div>'
            + '<div class="candidate-pid">PID: ' + c.pid + ' / type: ' + escapeHtml(c.star_type) + '</div>'
            + '<div class="candidate-caps">' + capsHtml + '</div>'
            + '</div>';
    });
    container.innerHTML = html;

    // 绑定点击
    container.querySelectorAll('.candidate-item').forEach(function(el) {
      el.addEventListener('click', function() {
        var starId = el.dataset.starId;
        selectCandidate(starId);
      });
    });
  }

  // ==================== 选中候选 -> 加载 inspect ====================
  function selectCandidate(starId) {
    state.selectedStarId = starId;
    state.selectedCandidate = state.candidates.find(function(c) {
      return c.star_id === starId;
    });
    renderCandidates();
    enableButtons(false);

    if (MOCK) {
      loadInspectMock();
    } else {
      loadInspect(starId);
    }
  }

  function loadInspectMock() {
    state.screenshot = MOCK_SCREENSHOT;
    state.uiaTree = MOCK_UIA_TREE;
    state.truncated = false;
    renderScreenshot();
    renderUiaTree();
    notify('Mock: inspect loaded', 'info', 2000);
  }

  function loadInspect(starId) {
    state.loading = true;
    notify('正在检视窗口...', 'info', 2000);

    apiCall('/locators/' + starId + '/inspect')
      .then(function(data) {
        state.loading = false;
        if (data.ok === false) {
          notify('检视失败: ' + (data.error || '未知错误'), 'error', 4000);
          return;
        }
        state.screenshot = data.screenshot_b64;
        state.uiaTree = data.uia_tree || [];
        state.truncated = data.truncated || false;
        renderScreenshot();
        renderUiaTree();
        notify('窗口检视完成: ' + state.uiaTree.length + ' 个控件节点', 'success', 2500);
      })
      .catch(function(err) {
        state.loading = false;
        notify('检视请求失败: ' + err.message, 'error', 4000);
      });
  }

  // ==================== 渲染：截图 ====================
  function renderScreenshot() {
    var area = $('screenshotArea');
    if (!state.screenshot) {
      area.innerHTML = '<div class="screenshot-placeholder"><p>截图获取失败</p></div>';
      return;
    }

    var imgSrc = 'data:image/png;base64,' + state.screenshot;
    area.innerHTML =
      '<div class="screenshot-container" id="ssContainer">' +
        '<img class="screenshot-img" id="ssImg" src="' + imgSrc + '">' +
        '<div class="screenshot-overlay" id="ssOverlay"></div>' +
      '</div>';

    var img = $('ssImg');
    img.addEventListener('load', function() {
      state.imgNaturalW = img.naturalWidth;
      state.imgNaturalH = img.naturalHeight;
      state.imgDisplayW = img.clientWidth;
      state.imgDisplayH = img.clientHeight;
      renderHighlights();
    });

    // 点击截图取坐标
    img.addEventListener('click', function(e) {
      var rect = img.getBoundingClientRect();
      var clickX = e.clientX - rect.left;
      var clickY = e.clientY - rect.top;
      // 换算为比例
      var xRatio = state.imgDisplayW > 0 ? clickX / state.imgDisplayW : 0.5;
      var yRatio = state.imgDisplayH > 0 ? clickY / state.imgDisplayH : 0.5;
      $('ratioX').value = xRatio.toFixed(2);
      $('ratioY').value = yRatio.toFixed(2);

      // 画一个临时高亮框
      drawClickHighlight(clickX, clickY);

      // 尝试匹配最近的 UIA 节点
      matchUiaNode(clickX, clickY);
    });
  }

  function renderHighlights() {
    // 清除旧高亮
    var overlay = $('ssOverlay');
    if (!overlay) return;
    overlay.innerHTML = '';
    state.highlightBox = null;
  }

  function drawClickHighlight(x, y) {
    var overlay = $('ssOverlay');
    if (!overlay) return;

    // 画一个 40x30 的临时红框
    var w = 40, h = 24;
    var left = x - w / 2;
    var top = y - h / 2;
    overlay.innerHTML =
      '<div class="highlight-box" style="left:' + left + 'px;top:' + top + 'px;width:' + w + 'px;height:' + h + 'px;">' +
      '</div>';
    state.highlightBox = { left: left, top: top, w: w, h: h };
  }

  function drawUiaHighlight(uiaNode) {
    var overlay = $('ssOverlay');
    if (!overlay || !state.imgDisplayW) return;

    var rect = uiaNode.rect;
    if (!rect || rect.length < 4) return;
    var l = rect[0], t = rect[1], r = rect[2], b = rect[3];
    var scaleX = state.imgDisplayW / state.imgNaturalW;
    var scaleY = state.imgDisplayH / state.imgNaturalH;
    var left = l * scaleX;
    var top = t * scaleY;
    var w = (r - l) * scaleX;
    var h = (b - t) * scaleY;

    overlay.innerHTML =
      '<div class="highlight-box" style="left:' + left + 'px;top:' + top + 'px;width:' + w + 'px;height:' + h + 'px;">' +
        '<div style="position:absolute;top:-18px;left:0;font-size:10px;color:#ef4444;background:rgba(0,0,0,0.7);padding:1px 4px;border-radius:3px;white-space:nowrap;">' +
          escapeHtml(uiaNode.control_type || 'node') +
        '</div>' +
      '</div>';
    state.highlightBox = { left: left, top: top, w: w, h: h };
  }

  function matchUiaNode(clickX, clickY) {
    if (!state.uiaTree || !state.imgDisplayW) return;
    var scaleX = state.imgDisplayW / state.imgNaturalW;
    var scaleY = state.imgDisplayH / state.imgNaturalH;
    var bestNode = null;
    var bestArea = Infinity;

    state.uiaTree.forEach(function(node) {
      var rect = node.rect;
      if (!rect || rect.length < 4) return;
      var l = rect[0] * scaleX, t = rect[1] * scaleY;
      var r = rect[2] * scaleX, b = rect[3] * scaleY;
      if (clickX >= l && clickX <= r && clickY >= t && clickY <= b) {
        var area = (r - l) * (b - t);
        // 取最小的包含点击点的节点（最精确的匹配）
        if (area < bestArea) {
          bestArea = area;
          bestNode = node;
        }
      }
    });

    if (bestNode) {
      drawUiaHighlight(bestNode);
      // 同步高亮 UIA 树列表中的对应项
      highlightUiaTreeNode(bestNode);
      // 自动填充参数表单
      autoFillParams(bestNode);
    }
  }

  function autoFillParams(node) {
    if (node.control_type) {
      $('uiaControlType').value = node.control_type;
    }
    if (node.automation_id) {
      $('uiaAutomationId').value = node.automation_id;
    }
    if (node.name) {
      $('uiaNameRegex').value = node.name;
      $('visualHintText').value = node.name;
    }
  }

  // ==================== 渲染：UIA 树 ====================
  function renderUiaTree() {
    var container = $('uiaTree');
    if (!state.uiaTree || state.uiaTree.length === 0) {
      container.innerHTML = '<div style="color:var(--color-text-muted);font-size:12px;">未获取到控件树</div>';
      return;
    }

    var html = '';
    state.uiaTree.forEach(function(node, i) {
      var indent = (node.depth || 0) * 12;
      var name = node.name ? ' "' + escapeHtml(node.name).substring(0, 30) + '"' : '';
      html += '<div class="uia-node" data-idx="' + i + '" style="padding-left:' + (8 + indent) + 'px;">'
            + '<span class="uia-type">' + escapeHtml(node.control_type || '?') + '</span>'
            + name
            + (node.automation_id ? ' <span style="color:var(--color-text-muted);">#' + escapeHtml(node.automation_id) + '</span>' : '')
            + '</div>';
    });

    if (state.truncated) {
      html += '<div style="padding:8px;font-size:11px;color:var(--color-status-awaiting);">'
            + '... 控件树已截断（仅显示前 80 个节点）</div>';
    }

    container.innerHTML = html;

    // 绑定点击
    container.querySelectorAll('.uia-node').forEach(function(el) {
      el.addEventListener('click', function() {
        var idx = parseInt(el.dataset.idx, 10);
        var node = state.uiaTree[idx];
        if (node) {
          drawUiaHighlight(node);
          highlightUiaTreeNode(node);
          autoFillParams(node);
        }
      });
    });
  }

  function highlightUiaTreeNode(node) {
    document.querySelectorAll('.uia-node').forEach(function(el) {
      el.classList.remove('active');
    });
    var idx = state.uiaTree.indexOf(node);
    if (idx >= 0) {
      var el = document.querySelector('.uia-node[data-idx="' + idx + '"]');
      if (el) {
        el.classList.add('active');
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }

  // ==================== 参数组装 ====================
  function buildParams() {
    var params = {};

    var controlType = $('uiaControlType').value.trim();
    var automationId = $('uiaAutomationId').value.trim();
    var nameRegex = $('uiaNameRegex').value.trim();
    if (controlType || automationId || nameRegex) {
      params.uia = {};
      if (controlType) params.uia.control_type = controlType;
      if (automationId) params.uia.automation_id = automationId;
      if (nameRegex) params.uia.name_regex = nameRegex;
    }

    var hintText = $('visualHintText').value.trim();
    if (hintText) {
      params.visual = { hint_text: hintText };
    }

    var xRatio = parseFloat($('ratioX').value) || 0.5;
    var yRatio = parseFloat($('ratioY').value) || 0.92;
    params.ratio = { x_ratio: xRatio, y_ratio: yRatio };

    return params;
  }

  function buildInteraction() {
    var order = $('locOrder').value.trim().split(',').map(function(s) { return s.trim(); }).filter(Boolean);
    var params = buildParams();

    var locators = [];
    order.forEach(function(name) {
      if (params[name]) {
        locators.push({ source: name, query: params[name] });
      }
    });
    // 至少包含 ratio 作为兜底
    if (!locators.some(function(l) { return l.source === 'ratio'; }) && params.ratio) {
      locators.push({ source: 'ratio', query: params.ratio });
    }

    return {
      input: {
        locators: locators,
        send_on: { type: 'enter' },
      },
      output: {
        strategy: 'regex',
        pattern: '',
      },
    };
  }

  // ==================== 动作按钮 ====================
  function enableButtons(enabled) {
    $('probeBtn').disabled = !enabled;
    $('previewBtn').disabled = !enabled;
    // apply 按钮在生成配置后才可用
    $('applyBtn').disabled = true;
  }

  window.doProbe = function() {
    if (!state.selectedStarId) {
      notify('请先选择一个 agent', 'warning', 2000);
      return;
    }

    var prompt = $('probePrompt').value || 'calibrator test';
    var params = buildParams();

    if (MOCK) {
      notify('Mock: 试发测试命中 (source=ratio)', 'success', 3000);
      return;
    }

    $('probeBtn').disabled = true;
    $('probeBtn').innerHTML = '<span class="loading"></span> 测试中...';

    apiCall('/locators/' + state.selectedStarId + '/probe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt, params: params }),
    })
      .then(function(data) {
        $('probeBtn').disabled = false;
        $('probeBtn').innerHTML = '&#9654; 试发测试';

        if (data.hit) {
          notify('试发命中! source=' + data.source + ' confidence=' +
                 (data.box.confidence || 'N/A'), 'success', 4000);
        } else {
          notify('试发未命中: ' + (data.error || 'no hit'), 'error', 4000);
        }
      })
      .catch(function(err) {
        $('probeBtn').disabled = false;
        $('probeBtn').innerHTML = '&#9654; 试发测试';
        notify('试发请求失败: ' + err.message, 'error', 4000);
      });
  };

  window.doPreview = function() {
    if (!state.selectedCandidate) {
      notify('请先选择一个 agent', 'warning', 2000);
      return;
    }

    var interaction = buildInteraction();

    if (MOCK) {
      var mockYaml = '# Mock YAML preview\n' +
        state.selectedCandidate.star_type + ':\n' +
        '  interaction:\n' +
        '    input:\n' +
        '      locators:\n' +
        '        - source: ratio\n' +
        '          query:\n' +
        '            x_ratio: ' + ($('ratioX').value || 0.5) + '\n' +
        '            y_ratio: ' + ($('ratioY').value || 0.92) + '\n';
      $('previewArea').textContent = mockYaml;
      $('previewSection').style.display = '';
      $('applyBtn').disabled = false;
      state.pendingPreview = mockYaml;
      notify('Mock: 配置已生成', 'success', 2000);
      return;
    }

    apiCall('/locators/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_id: state.selectedCandidate.star_type,
        interaction: interaction,
      }),
    })
      .then(function(data) {
        if (data.ok) {
          $('previewArea').textContent = data.yaml;
          $('previewSection').style.display = '';
          $('applyBtn').disabled = false;
          state.pendingPreview = data.yaml;
          notify('配置预览已生成 (路径: ' + data.path + ')', 'success', 3000);
        } else {
          notify('生成失败: ' + (data.error || ''), 'error', 3000);
        }
      })
      .catch(function(err) {
        notify('生成请求失败: ' + err.message, 'error', 3000);
      });
  };

  window.doApply = function() {
    if (!state.pendingPreview) {
      notify('请先生成配置', 'warning', 2000);
      return;
    }

    if (!confirm('确认将配置写入 config/ai-agents.yaml？\n\n原文件将备份为 .bak')) {
      return;
    }

    if (MOCK) {
      notify('Mock: 配置已应用 (模拟)', 'success', 3000);
      return;
    }

    var interaction = buildInteraction();
    $('applyBtn').disabled = true;
    $('applyBtn').innerHTML = '<span class="loading"></span> 应用中...';

    apiCall('/locators/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_id: state.selectedCandidate.star_type,
        interaction: interaction,
      }),
    })
      .then(function(data) {
        $('applyBtn').disabled = false;
        $('applyBtn').innerHTML = '&#9989; 应用生效';

        if (data.ok) {
          var msg = '配置已应用! 备份: ' + (data.backup || 'ai-agents.yaml.bak');
          if (data.note) msg += '\n' + data.note;
          notify(msg, 'success', 5000);
        } else {
          notify('应用失败: ' + (data.error || ''), 'error', 4000);
        }
      })
      .catch(function(err) {
        $('applyBtn').disabled = false;
        $('applyBtn').innerHTML = '&#9989; 应用生效';
        notify('应用请求失败: ' + err.message, 'error', 4000);
      });
  };

  window.doClear = function() {
    state.selectedStarId = null;
    state.selectedCandidate = null;
    state.screenshot = null;
    state.uiaTree = [];
    state.pendingPreview = null;

    renderCandidates();
    $('screenshotArea').innerHTML =
      '<div class="screenshot-placeholder"><p>&#128269; 从左侧选择一个 agent 开始检视</p></div>';
    $('uiaTree').innerHTML =
      '<div style="color:var(--color-text-muted);font-size:12px;">选择 agent 后显示控件树</div>';
    $('previewSection').style.display = 'none';

    $('uiaControlType').value = '';
    $('uiaAutomationId').value = '';
    $('uiaNameRegex').value = '';
    $('visualHintText').value = '';
    $('ratioX').value = '0.5';
    $('ratioY').value = '0.92';

    enableButtons(false);
    notify('已清空', 'info', 1500);
  };

  // ==================== 初始化 ====================
  function init() {
    if (MOCK) {
      state.candidates = MOCK_CANDIDATES;
      renderCandidates();
      setOnline(true);
      notify('Mock 模式已启用', 'info', 2000);
      return;
    }

    // 检测 API 是否在线
    apiCall('/locators/candidates')
      .then(function(data) {
        setOnline(true);
        state.candidates = (data && data.candidates) || [];
        renderCandidates();
        if (state.candidates.length === 0) {
          notify('未发现任何 agent，请先在星图页面发现 agent', 'info', 3000);
        }
      })
      .catch(function(err) {
        setOnline(false);
        state.candidates = [];
        renderCandidates();
      });

    // 如果 nav.js 提供了注入函数，确保被调用
    if (typeof initNav === 'function') {
      initNav();
    }
  }

  // ==================== 工具 ====================
  function escapeHtml(str) {
    if (typeof str !== 'string') return '';
    return str.replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#039;');
  }

  // 暴露给全局（与 star-ui 风格一致）
  window.__calibrator = {
    state: state,
    init: init,
  };

  // DOM 就绪后初始化
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
