/**
 * 群星 Star — API Key 网关（AuthGate）
 * 全站唯一的「未授权」出口：无 Key 顶部提示条 + 填 Key 浮层 + 填完自动重试。
 * 一处实现，全站引用（各页面在 api-bridge.js 之后引入本文件即可）。
 *
 * 依赖 api-bridge.js 的 setApiKey/getApiKey；两者缺失时退化为直接读写 localStorage。
 */
(function () {
  'use strict';

  // GET /api/stars/types 是安全方法，只需 read 权限，admin key 可通过，作为最轻量校验端点。
  var VALIDATE_PATH = '/api/stars/types';
  var STORAGE_KEY = 'star_api_key';
  var BANNER_ID = 'star-auth-banner';
  var MODAL_ID = 'star-auth-modal';

  var authorizedCb = null; // 页面注册的重试回调；未注册则默认 location.reload()
  var modalOpen = false;   // 去重：多个并发 401 只弹一个浮层
  var lastFocused = null;  // 打开浮层前的焦点元素，关闭后归还

  // ==================== Key 读写（隐私模式容错） ====================
  function currentKey() {
    try {
      if (typeof getApiKey === 'function') {
        var k = getApiKey();
        if (k) return k;
      }
    } catch (e) { /* ignore */ }
    try {
      return localStorage.getItem(STORAGE_KEY) || '';
    } catch (e) {
      return '';
    }
  }

  function persistKey(key) {
    // 优先复用 api-bridge 的 setApiKey（会同步内存态 _apiKey）
    try {
      if (typeof setApiKey === 'function') { setApiKey(key); return; }
    } catch (e) { /* ignore */ }
    try { localStorage.setItem(STORAGE_KEY, key); } catch (e) { /* 内存态，本次会话可用 */ }
  }

  // ==================== 校验（裸 fetch，绝不走 apiFetch，避免事件回环） ====================
  function validate(key) {
    return fetch(VALIDATE_PATH, { headers: { 'X-API-Key': key } })
      .then(function (res) {
        if (res.status === 401 || res.status === 403) {
          return { ok: false, reason: '服务端拒绝了这个 Key（无效或权限不足）' };
        }
        if (!res.ok) return { ok: false, reason: '服务端返回 ' + res.status };
        return { ok: true };
      })
      .catch(function () {
        return { ok: false, reason: '无法连接后端，请确认 star_api 服务在运行' };
      });
  }

  // ==================== 顶部提示条 ====================
  function showBanner(text) {
    var bar = document.getElementById(BANNER_ID);
    if (!bar) {
      bar = document.createElement('div');
      bar.id = BANNER_ID;
      bar.setAttribute('role', 'status');
      Object.assign(bar.style, {
        position: 'fixed', top: '0', left: '0', right: '0',
        zIndex: '9000', // 低于 showNotification 的 9999，避免遮挡通知
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        gap: '12px', flexWrap: 'wrap',
        padding: '10px 16px', boxSizing: 'border-box',
        background: '#d97706', color: '#fff',
        fontSize: '14px', lineHeight: '1.4',
        boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
      });
      var label = document.createElement('span');
      label.className = 'star-auth-banner-text';
      bar.appendChild(label);

      var btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = '填入 API Key';
      Object.assign(btn.style, {
        minHeight: '32px', padding: '4px 14px',
        border: '1px solid rgba(255,255,255,0.7)', borderRadius: '6px',
        background: 'rgba(255,255,255,0.15)', color: '#fff',
        fontSize: '13px', cursor: 'pointer',
      });
      btn.addEventListener('click', function () {
        open(currentKey() ? 'invalid' : 'missing');
      });
      bar.appendChild(btn);

      document.body.appendChild(bar);
    }
    var textEl = bar.querySelector('.star-auth-banner-text');
    if (textEl) textEl.textContent = text || '';
    bar.style.display = 'flex';
  }

  function hideBanner() {
    var bar = document.getElementById(BANNER_ID);
    if (bar) bar.remove();
  }

  // ==================== 填 Key 浮层 ====================
  function open(reason) {
    if (modalOpen) return;
    modalOpen = true;
    lastFocused = document.activeElement;

    var overlay = document.createElement('div');
    overlay.id = MODAL_ID;
    Object.assign(overlay.style, {
      position: 'fixed', inset: '0', zIndex: '9500',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: '16px', boxSizing: 'border-box',
      background: 'rgba(0,0,0,0.6)',
    });

    var titleId = 'star-auth-title';
    var descId = 'star-auth-desc';
    var errId = 'star-auth-err';

    var box = document.createElement('div');
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-labelledby', titleId);
    box.setAttribute('aria-describedby', descId);
    Object.assign(box.style, {
      width: '100%', maxWidth: 'min(420px, calc(100vw - 32px))',
      boxSizing: 'border-box',
      background: '#141821', color: '#e5e7eb',
      border: '1px solid #2a2f3a', borderRadius: '12px',
      padding: '24px', boxShadow: '0 12px 40px rgba(0,0,0,0.5)',
      fontSize: '14px', lineHeight: '1.5',
    });

    var invalid = reason === 'invalid';
    box.innerHTML =
      '<h2 id="' + titleId + '" style="margin:0 0 8px;font-size:18px;color:#ffd700;">' +
        (invalid ? 'API Key 已失效' : '需要 API Key') + '</h2>' +
      '<p id="' + descId + '" style="margin:0 0 16px;color:#9ca3af;">' +
        (invalid
          ? '当前 Key 被服务端拒绝，请重新填入有效的 API Key。'
          : '群星 Star 的所有数据接口都需要 API Key。请填入服务端 config.yaml 里 auth.api_keys 中 role=admin 的 Key。') +
      '</p>' +
      '<label for="star-auth-input" style="display:block;margin-bottom:6px;color:#9ca3af;font-size:13px;">API Key</label>' +
      '<input id="star-auth-input" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" ' +
        'inputmode="text" placeholder="粘贴你的 API Key" ' +
        'style="width:100%;box-sizing:border-box;min-height:44px;padding:10px 12px;' +
        'background:#0d1017;border:1px solid #2a2f3a;border-radius:8px;color:#e5e7eb;font-size:14px;" />' +
      '<p id="' + errId + '" role="alert" style="display:none;margin:8px 0 0;color:#f87171;font-size:13px;"></p>' +
      '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:20px;">' +
        '<button type="button" data-act="cancel" ' +
          'style="min-height:44px;padding:0 16px;border:1px solid #2a2f3a;border-radius:8px;' +
          'background:transparent;color:#9ca3af;font-size:14px;cursor:pointer;">稍后</button>' +
        '<button type="button" data-act="submit" ' +
          'style="min-height:44px;padding:0 20px;border:none;border-radius:8px;' +
          'background:#ffd700;color:#0a0a0f;font-size:14px;font-weight:600;cursor:pointer;">保存并验证</button>' +
      '</div>';

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    var input = box.querySelector('#star-auth-input');
    var errEl = box.querySelector('#' + errId);
    var submitBtn = box.querySelector('[data-act="submit"]');
    var cancelBtn = box.querySelector('[data-act="cancel"]');

    try { input.value = currentKey(); } catch (e) { /* ignore */ }

    function showErr(msg) {
      errEl.textContent = msg;
      errEl.style.display = 'block';
    }

    function doSubmit() {
      var key = (input.value || '').trim();
      if (!key) { showErr('请先填入 API Key'); return; }
      submitBtn.disabled = true;
      submitBtn.textContent = '验证中…';
      validate(key).then(function (r) {
        submitBtn.disabled = false;
        submitBtn.textContent = '保存并验证';
        if (!r.ok) { showErr(r.reason); return; } // 校验不过：不写入，不关闭
        persistKey(key);
        close();
        hideBanner();
        if (typeof authorizedCb === 'function') {
          try { authorizedCb(); } catch (e) { location.reload(); }
        } else {
          location.reload();
        }
      });
    }

    submitBtn.addEventListener('click', doSubmit);
    cancelBtn.addEventListener('click', function () { close(); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); doSubmit(); }
    });
    overlay.addEventListener('mousedown', function (e) {
      if (e.target === overlay) close(); // 点遮罩关闭
    });
    overlay._escHandler = function (e) {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('keydown', overlay._escHandler);

    // 打开时聚焦输入框
    setTimeout(function () { try { input.focus(); } catch (e) {} }, 0);
  }

  function close() {
    var overlay = document.getElementById(MODAL_ID);
    if (overlay) {
      if (overlay._escHandler) document.removeEventListener('keydown', overlay._escHandler);
      overlay.remove();
    }
    modalOpen = false;
    // 焦点归还
    try { if (lastFocused && lastFocused.focus) lastFocused.focus(); } catch (e) {}
    lastFocused = null;
  }

  // ==================== 事件接线 ====================
  window.addEventListener('star:unauthorized', function () {
    var has = !!currentKey();
    showBanner(has ? 'API Key 已失效或权限不足，请重新填入' : '尚未设置 API Key，页面数据无法加载');
    open(has ? 'invalid' : 'missing');
  });

  document.addEventListener('DOMContentLoaded', function () {
    if (currentKey()) return;
    // 服务端可能把鉴权整体关掉（auth.enabled=false），此时不该无故骚扰用户：
    // 先不带 Key 探一次，只有真的被拒才提示。
    fetch(VALIDATE_PATH).then(function (res) {
      if (res.status !== 401 && res.status !== 403) return;
      showBanner('尚未设置 API Key，页面数据无法加载');
      open('missing');
    }).catch(function () { /* 后端不可达属于另一类问题，交由页面自身报错 */ });
  });

  // ==================== 导出 ====================
  window.AuthGate = {
    open: open,
    close: close,
    hasKey: function () { return !!currentKey(); },
    onAuthorized: function (fn) { authorizedCb = fn; },
    isAuthError: function (e) { return !!e && (e.status === 401 || e.status === 403); },
  };
})();
