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

document.addEventListener('DOMContentLoaded', initNav);
