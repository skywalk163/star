function initNav() {
  const path = window.location.pathname;
  const pageMatch = path.match(/\/pages\/(\w+)\.html/);
  const currentPage = pageMatch ? pageMatch[1] : 'starmap';

  document.querySelectorAll('[data-dom-id^="nav-"]').forEach(el => {
    const page = el.dataset.domId.replace('nav-', '');
    const isActive = page === currentPage;

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

    el.addEventListener('click', (e) => {
      e.preventDefault();
      window.location.href = `/ui/pages/${page}.html`;
    });
  });
}

/**
 * 动态注入"定位器校准器"导航项到侧边栏。
 * 查找包含 data-dom-id="nav-*" 元素的 <nav> 容器，
 * 在 Remote Control 项之前插入校准器入口。
 */
function injectCalibratorNav() {
  // 已存在则跳过
  if (document.querySelector('[data-dom-id="nav-calibrator"]')) return;

  // 找到侧边栏 nav 容器（包含 nav- 前缀元素的 <nav> 或 <aside>）
  const navContainer =
    document.querySelector('nav.flex.flex-col') ||
    document.querySelector('aside nav') ||
    document.querySelector('nav');
  if (!navContainer) return;

  const link = document.createElement('a');
  link.href = '/ui/pages/calibrator.html';
  link.title = 'Locator Calibrator';
  link.dataset.domId = 'nav-calibrator';
  link.className = 'relative flex items-center justify-center w-10 h-10 transition-all duration-200';
  link.style.cssText =
    'color:var(--color-text-muted);border-left:3px solid transparent;border-radius:8px;';
  link.innerHTML = '<i data-lucide="crosshair" class="w-5 h-5"></i>';

  // 插入到 Remote Control 之前；找不到则追加到末尾
  const remoteEntry = navContainer.querySelector('[data-dom-id="nav-remote"]');
  if (remoteEntry) {
    navContainer.insertBefore(link, remoteEntry);
  } else {
    navContainer.appendChild(link);
  }

  // 如果 lucide 已加载，重新创建图标
  if (typeof lucide !== 'undefined' && lucide.createIcons) {
    lucide.createIcons();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  injectCalibratorNav();
  initNav();
});
