/**
 * 群星 Star — 统一导航
 *
 * 全站导航只有这一份配置（NAV_ITEMS）。改这里，11 个页面同时生效。
 *
 * 两种接管方式：
 *   1. 页面已有 [data-dom-id^="nav-"] 容器 → 补齐缺失项 + 统一高亮，沿用页面原有视觉类名
 *   2. 页面完全没有导航（starfleet/remote/programming/broadcast/calibrator）→ 注入 sticky 顶部导航条
 */

// 顺序即展示顺序；新增页面只需在这里加一行
const NAV_ITEMS = [
  { id: 'starmap',     label: '星图',       icon: 'map',                 href: '/ui/pages/starmap.html' },
  { id: 'dumate',      label: 'Agents',     icon: 'bot',                 href: '/ui/pages/dumate.html' },
  { id: 'dispatch',    label: '任务派发',   icon: 'send',                href: '/ui/pages/dispatch.html' },
  { id: 'starlight',   label: '星辉',       icon: 'sparkles',            href: '/ui/pages/starlight.html' },
  { id: 'orbit',       label: '轨道台',     icon: 'orbit',               href: '/ui/pages/orbit.html' },
  { id: 'starfleet',   label: '星群状态',   icon: 'radar',               href: '/ui/pages/starfleet.html' },
  { id: 'broadcast',   label: '批量发送',   icon: 'megaphone',           href: '/ui/pages/broadcast.html' },
  { id: 'programming', label: '编程工作台', icon: 'code',                href: '/ui/pages/programming.html' },
  { id: 'remote',      label: '遥控台',     icon: 'monitor-smartphone',  href: '/ui/pages/remote.html' },
  { id: 'calibrator',  label: '定位校准',   icon: 'crosshair',           href: '/ui/pages/calibrator.html' },
  { id: 'settings',    label: '设置',       icon: 'settings',            href: '/ui/pages/settings.html' },
];

const FLOATING_NAV_ID = 'star-floating-nav';

// ===== 移动端底部 tab bar =====
// 375px 屏上底部最多放 5 格，再多每格就低于 44px 触控目标了。
// 所以只放 4 个最常用的，其余 7 项收进"更多"抽屉，一个入口都不丢。
const MOBILE_TAB_IDS = ['dumate', 'dispatch', 'starmap', 'starfleet'];
const TAB_BAR_ID = 'star-mobile-tabbar';
const DRAWER_ID = 'star-mobile-drawer';
const DRAWER_MASK_ID = 'star-mobile-drawer-mask';
const MOBILE_STYLE_ID = 'star-mobile-style';
const TAB_BAR_HEIGHT = 56;

function currentPageId() {
  const path = window.location.pathname;
  const m = path.match(/\/pages\/(\w+)\.html/);
  if (m) return m[1];
  // /remote 是后端另挂的路由，不在 /ui/pages/ 下
  if (path.indexOf('/remote') === 0) return 'remote';
  return 'starmap';
}

function findNavContainer() {
  const anyItem = document.querySelector('[data-dom-id^="nav-"]');
  return anyItem ? anyItem.parentElement : null;
}

/**
 * 补齐缺失的导航项。
 * 只在末尾追加，不重排既有项——各页布局是手写的，重排容易把视觉搞坏。
 */
function ensureNavItems(container) {
  const sample = container.querySelector('[data-dom-id^="nav-"]');
  NAV_ITEMS.forEach(item => {
    if (container.querySelector('[data-dom-id="nav-' + item.id + '"]')) return;
    const a = document.createElement('a');
    a.href = item.href;
    a.title = item.label;
    a.dataset.domId = 'nav-' + item.id;
    if (sample) a.className = sample.className;   // 抄同容器既有项的样式
    a.innerHTML = hasLucide()
      ? '<i data-lucide="' + item.icon + '" class="w-5 h-5"></i>'
      : '<span style="font-size:12px;">' + item.label + '</span>';
    container.appendChild(a);
  });
}

function hasLucide() {
  return typeof lucide !== 'undefined' && typeof lucide.createIcons === 'function';
}

/**
 * 给没有任何导航的页面注入一条 sticky 顶部导航。
 * sticky 而非 fixed：随文档流，不会盖住页面自身的固定头部。
 */
function injectFloatingNav() {
  if (document.getElementById(FLOATING_NAV_ID)) return;
  const current = currentPageId();

  const bar = document.createElement('nav');
  bar.id = FLOATING_NAV_ID;
  bar.className = 'star-nav-floating';   // 窄屏由 @media 隐藏，改用底部 tab bar
  bar.setAttribute('aria-label', '主导航');
  Object.assign(bar.style, {
    position: 'sticky', top: '0',
    zIndex: '8000',              // 低于 AuthGate 提示条(9000)与通知(9999)
    display: 'flex', alignItems: 'center', gap: '4px',
    padding: '6px 8px', boxSizing: 'border-box',
    overflowX: 'auto', whiteSpace: 'nowrap',
    background: 'var(--color-bg-panel, #141821)',
    borderBottom: '1px solid var(--color-border, #2a2f3a)',
  });

  NAV_ITEMS.forEach(item => {
    const a = document.createElement('a');
    a.href = item.href;
    a.title = item.label;
    a.textContent = item.label;
    a.dataset.domId = 'nav-' + item.id;
    const active = item.id === current;
    Object.assign(a.style, {
      display: 'inline-flex', alignItems: 'center',
      minHeight: '44px', padding: '0 12px',
      borderRadius: '8px', textDecoration: 'none',
      fontSize: '13px', flex: '0 0 auto',
      color: active ? '#ffd700' : 'var(--color-text-muted, #9ca3af)',
      background: active ? 'var(--color-primary-dim, rgba(255,215,0,0.12))' : 'transparent',
    });
    if (active) a.setAttribute('aria-current', 'page');
    bar.appendChild(a);
  });

  document.body.insertBefore(bar, document.body.firstChild);
}

/** tab 内部：图标在上、文字在下；没有 lucide 就只留文字 */
function tabInner(icon, label) {
  const iconHtml = hasLucide()
    ? '<i data-lucide="' + icon + '"></i>'
    : '';
  return iconHtml + '<span>' + label + '</span>';
}

function buildTab(item, isActive) {
  const a = document.createElement('a');
  a.href = item.href;
  a.className = 'star-tab';
  a.title = item.label;
  a.dataset.domId = 'tab-' + item.id;
  a.innerHTML = tabInner(item.icon, item.label);
  if (isActive) a.setAttribute('aria-current', 'page');
  return a;
}

/**
 * 注入底部 tab bar。
 * 无条件注入到所有页面——显隐完全交给 CSS @media，不用 JS 判 innerWidth：
 * JS 判断要监听 resize、处理横竖屏、还会有首屏闪烁，媒体查询没有这些问题。
 */
function injectMobileTabBar() {
  if (document.getElementById(TAB_BAR_ID)) return;
  const current = currentPageId();

  const bar = document.createElement('nav');
  bar.id = TAB_BAR_ID;
  bar.setAttribute('aria-label', '移动端主导航');

  MOBILE_TAB_IDS.forEach(id => {
    const item = NAV_ITEMS.find(i => i.id === id);
    if (!item) return;                 // NAV_ITEMS 改名/删项时少一格，但不崩
    bar.appendChild(buildTab(item, item.id === current));
  });

  const more = document.createElement('button');
  more.type = 'button';
  more.id = 'star-tab-more';
  more.className = 'star-tab';
  more.setAttribute('aria-haspopup', 'true');
  more.setAttribute('aria-expanded', 'false');
  more.innerHTML = tabInner('menu', '更多');
  more.addEventListener('click', openMoreDrawer);
  bar.appendChild(more);

  document.body.appendChild(bar);
}

/**
 * 注入移动端样式。
 * append 到 <head> 末尾，晚于各页内联 <style>，同特异性下后者生效，
 * 因此这里的 @media 规则能盖住页内的桌面态布局。
 */
function injectMobileStyle() {
  if (document.getElementById(MOBILE_STYLE_ID)) return;
  const safeBottom = 'env(safe-area-inset-bottom, 0px)';
  const style = document.createElement('style');
  style.id = MOBILE_STYLE_ID;
  style.textContent = `
/* 桌面态：tab bar 与抽屉完全不存在，页面渲染与改造前逐像素一致 */
#${TAB_BAR_ID} { display: none; }

#${TAB_BAR_ID} .star-tab {
  flex: 1 1 0;
  min-width: 0;
  min-height: ${TAB_BAR_HEIGHT}px;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 2px;
  padding: 6px 2px;
  border: none; background: transparent;
  font-family: inherit; font-size: 11px; line-height: 1.2;
  color: var(--color-text-muted, #9ca3af);
  text-decoration: none; cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
#${TAB_BAR_ID} .star-tab[aria-current="page"] { color: #ffd700; }
#${TAB_BAR_ID} .star-tab svg { width: 20px; height: 20px; }
#${TAB_BAR_ID} .star-tab span {
  max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

#${DRAWER_MASK_ID} {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  z-index: 8600; background: rgba(0, 0, 0, 0.6);
}
#${DRAWER_ID} {
  position: fixed; left: 0; right: 0; bottom: 0;
  z-index: 8601;
  max-height: 70vh; overflow-y: auto;
  padding: 8px 8px calc(8px + ${safeBottom});
  box-sizing: border-box;
  background: var(--color-bg-panel, #141821);
  border-top: 1px solid var(--color-border, #2a2f3a);
  border-radius: 12px 12px 0 0;
}
#${DRAWER_ID} .star-drawer-item {
  display: flex; align-items: center; gap: 12px;
  min-height: 44px; padding: 0 12px;
  border-radius: 8px; text-decoration: none;
  font-size: 14px;
  color: var(--color-text-secondary, #cbd5e1);
}
#${DRAWER_ID} .star-drawer-item[aria-current="page"] {
  color: #ffd700; background: var(--color-primary-dim, rgba(255, 215, 0, 0.12));
}
#${DRAWER_ID} .star-drawer-item svg { width: 18px; height: 18px; flex-shrink: 0; }

@media (max-width: 768px) {
  #${TAB_BAR_ID} {
    display: flex;
    position: fixed; left: 0; right: 0; bottom: 0;
    /* AuthGate 提示条 9000 > 抽屉 8600 > tab bar 8500 > 注入顶栏 8000 */
    z-index: 8500;
    box-sizing: border-box;
    background: var(--color-bg-panel, #141821);
    border-top: 1px solid var(--color-border, #2a2f3a);
    padding-bottom: ${safeBottom};
  }
  /* 顶栏和底部 tab bar 是同一份 NAV_ITEMS 的两种形态，窄屏只留一个 */
  .star-nav-floating { display: none !important; }
  /* 给 fixed 的 tab bar 让位，否则页面底部内容被永久遮住 */
  body { padding-bottom: calc(${TAB_BAR_HEIGHT}px + ${safeBottom}); }
}
`;
  document.head.appendChild(style);
}

/** "更多"抽屉：把全部 11 项列出来，一个入口都不丢 */
let _lastDrawerTrigger = null;

function openMoreDrawer() {
  if (document.getElementById(DRAWER_ID)) return;
  _lastDrawerTrigger = document.getElementById('star-tab-more');
  if (_lastDrawerTrigger) _lastDrawerTrigger.setAttribute('aria-expanded', 'true');
  const current = currentPageId();

  const mask = document.createElement('div');
  mask.id = DRAWER_MASK_ID;
  mask.addEventListener('click', closeMoreDrawer);

  const panel = document.createElement('nav');
  panel.id = DRAWER_ID;
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-modal', 'true');
  panel.setAttribute('aria-label', '全部页面');

  NAV_ITEMS.forEach(item => {
    const a = document.createElement('a');
    a.href = item.href;
    a.className = 'star-drawer-item';
    a.innerHTML = (hasLucide() ? '<i data-lucide="' + item.icon + '"></i>' : '')
      + '<span>' + item.label + '</span>';
    if (item.id === current) a.setAttribute('aria-current', 'page');
    panel.appendChild(a);
  });

  document.body.appendChild(mask);
  document.body.appendChild(panel);
  document.addEventListener('keydown', onDrawerKeydown);
  if (hasLucide()) lucide.createIcons();
  // 焦点移进抽屉，方便键盘/读屏用户
  const first = panel.querySelector('.star-drawer-item');
  if (first) first.focus();
}

function closeMoreDrawer() {
  const mask = document.getElementById(DRAWER_MASK_ID);
  const panel = document.getElementById(DRAWER_ID);
  if (mask) mask.remove();
  if (panel) panel.remove();
  document.removeEventListener('keydown', onDrawerKeydown);
  if (_lastDrawerTrigger) {
    _lastDrawerTrigger.setAttribute('aria-expanded', 'false');
    _lastDrawerTrigger.focus();               // 焦点归还触发按钮
    _lastDrawerTrigger = null;
  }
}

function onDrawerKeydown(e) {
  if (e.key === 'Escape') closeMoreDrawer();
}

/** 统一高亮 + 点击行为 */
function initNav() {
  const current = currentPageId();

  document.querySelectorAll('[data-dom-id^="nav-"]').forEach(el => {
    const page = el.dataset.domId.replace('nav-', '');
    const isActive = page === current;
    const item = NAV_ITEMS.find(i => i.id === page);

    // 补上真实 href：早期页面写的是 href="#"，中键/新标签打不开
    if (item && (!el.getAttribute('href') || el.getAttribute('href') === '#')) {
      el.setAttribute('href', item.href);
    }

    if (isActive) {
      el.setAttribute('aria-current', 'page');
      el.classList.add('active');            // starlight 等靠 class 表达选中
    } else {
      el.removeAttribute('aria-current');
      el.classList.remove('active');
    }

    // 浮动导航条自己管样式，别被下面的内联高亮覆盖
    if (el.closest('#' + FLOATING_NAV_ID)) return;

    if (isActive) {
      el.style.background = 'var(--color-primary-dim)';
      el.style.color = '#ffd700';
      el.style.borderLeft = '3px solid #ffd700';
      el.style.borderRadius = '0 8px 8px 0';
    } else {
      el.style.background = 'transparent';
      el.style.color = 'var(--color-text-muted)';
      el.style.borderLeft = '3px solid transparent';
      el.style.borderRadius = '8px';
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const container = findNavContainer();
  if (container) {
    ensureNavItems(container);
  } else {
    injectFloatingNav();
  }
  // 移动端形态：样式先进 <head>，再放 DOM，显隐交给 @media
  injectMobileStyle();
  injectMobileTabBar();
  initNav();
  if (hasLucide()) lucide.createIcons();
});
