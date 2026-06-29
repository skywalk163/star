// ===== 新手引导 / Onboarding =====

window.Onboarding = (function() {
  const STORAGE_KEY = 'star_onboarding_completed';
  const VERSION = '1.0';

  const steps = [
    {
      icon: 'telescope',
      title: '欢迎来到群星 Star',
      subtitle: 'AI Agent 调度与观测平台 — 让每一个 AI 都成为你的星辰',
      content: [
        { num: 1, title: '发现星体', desc: '自动扫描系统中运行的 AI Agent（Trae、Cursor、Claude 等）' },
        { num: 2, title: '发送指令', desc: '通过星图页面选中星体，直接发送指令并获取响应' },
        { num: 3, title: '实时观测', desc: 'OCR 视觉识别 + 日志毫秒级读取，双引擎捕获输出' },
      ]
    },
    {
      icon: 'map',
      title: '星图 - 你的控制中心',
      subtitle: '在星图页面管理所有星体，查看详情、发送指令',
      content: [
        { num: 1, title: '选择星体', desc: '点击左侧星体卡片，右侧面板显示详细信息' },
        { num: 2, title: '发送指令', desc: '切换到"指令"Tab，输入问题并发送' },
        { num: 3, title: '查看日志', desc: '"日志"Tab 实时查看 AI 的原始日志' },
      ]
    },
    {
      icon: 'sparkles',
      title: '星辉 - 任务调度中心',
      subtitle: '创建新星任务，让 AI 自动为你完成工作',
      content: [
        { num: 1, title: '创建新星', desc: '描述你的任务需求，系统自动分配给合适的 AI' },
        { num: 2, title: '实时追踪', desc: '查看任务进度和 AI 输出，支持 OCR 实时流' },
        { num: 3, title: '批量处理', desc: '创建星座任务，多个 AI 并行协作完成复杂工作' },
      ]
    },
    {
      icon: 'settings',
      title: '开始你的星际之旅',
      subtitle: '配置好你的设置，开启 AI 协作新纪元',
      content: [
        { num: 1, title: '配置参数', desc: '前往设置页面调整 OCR、日志、超时等参数' },
        { num: 2, title: '安装插件', desc: '插件系统支持扩展更多 AI Agent 类型' },
        { num: 3, title: '随时帮助', desc: '点击右下角 "?" 按钮或按 F1 重新查看引导' },
      ]
    }
  ];

  let currentStep = 0;
  let overlayEl = null;

  function isCompleted() {
    try {
      const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      return data.version === VERSION && data.completed;
    } catch (e) {
      return false;
    }
  }

  function markCompleted() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        version: VERSION,
        completed: true,
        completed_at: new Date().toISOString()
      }));
    } catch (e) {}
  }

  function reset() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {}
  }

  function renderStep(stepIndex) {
    const step = steps[stepIndex];
    if (!step || !overlayEl) return;

    const modal = overlayEl.querySelector('.onboarding-modal');
    if (!modal) return;

    const iconSvg = {
      telescope: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m10.065 12.493-6.18 1.318a.934.934 0 0 1-1.108-1.099l.886-5.586a1 1 0 0 1 .592-.765l10.647-4.042a1 1 0 0 1 1.243.414l3.285 5.626a1 1 0 0 1-.192 1.25l-4.218 3.487"/><path d="M10.065 12.493a2 2 0 0 0-.726 2.117l.514 1.925a2 2 0 0 0 2.575 1.31l2.01-.754"/><path d="m13.946 17.103 3.233 3.232"/><path d="M17.5 6.5v.01"/><circle cx="17.5" cy="6.5" r="1"/></svg>',
      map: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.106 5.93a2.5 2.5 0 0 0-4.212 0l-6.37 10.616A2 2 0 0 0 5.264 19.5h13.472a2 2 0 0 0 1.74-2.954z"/><path d="M12 3v3"/><path d="M6 7l1.5 2.5"/><path d="M18 7l-1.5 2.5"/><path d="M12 12v3"/><path d="m9 15 3 4 3-4"/></svg>',
      sparkles: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/></svg>',
      settings: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>',
    };

    modal.innerHTML = `
      <button class="onboarding-close" onclick="Onboarding.skip()" aria-label="关闭">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
      </button>
      <div class="onboarding-icon">
        ${iconSvg[step.icon] || iconSvg.telescope}
      </div>
      <h2 class="onboarding-title">${step.title}</h2>
      <p class="onboarding-subtitle">${step.subtitle}</p>
      <div class="onboarding-steps">
        ${step.content.map(item => `
          <div class="onboarding-step">
            <div class="onboarding-step-num">${item.num}</div>
            <div class="onboarding-step-content">
              <h4>${item.title}</h4>
              <p>${item.desc}</p>
            </div>
          </div>
        `).join('')}
      </div>
      <div class="onboarding-dots">
        ${steps.map((_, i) => `<div class="onboarding-dot ${i === stepIndex ? 'active' : ''}"></div>`).join('')}
      </div>
      <div class="onboarding-footer">
        ${stepIndex > 0 ? '<button class="onboarding-btn" onclick="Onboarding.prev()">上一步</button>' : ''}
        ${stepIndex < steps.length - 1
          ? '<button class="onboarding-btn onboarding-btn-primary" onclick="Onboarding.next()">下一步</button>'
          : '<button class="onboarding-btn onboarding-btn-primary" onclick="Onboarding.complete()">开始使用</button>'
        }
      </div>
      ${stepIndex < steps.length - 1 ? '<div class="onboarding-skip"><a onclick="Onboarding.skip()">跳过引导</a></div>' : ''}
    `;
  }

  function show(stepIndex = 0) {
    currentStep = stepIndex;

    if (!overlayEl) {
      overlayEl = document.createElement('div');
      overlayEl.className = 'onboarding-overlay';
      overlayEl.innerHTML = '<div class="onboarding-modal"></div>';
      document.body.appendChild(overlayEl);
    }

    renderStep(currentStep);

    requestAnimationFrame(() => {
      overlayEl.classList.add('active');
    });
  }

  function hide() {
    if (overlayEl) {
      overlayEl.classList.remove('active');
    }
  }

  function next() {
    if (currentStep < steps.length - 1) {
      currentStep++;
      renderStep(currentStep);
    }
  }

  function prev() {
    if (currentStep > 0) {
      currentStep--;
      renderStep(currentStep);
    }
  }

  function skip() {
    hide();
    markCompleted();
  }

  function complete() {
    hide();
    markCompleted();
    if (typeof window.showNotification === 'function') {
      window.showNotification('欢迎来到群星 Star！探索你的 AI 星辰大海 ✨', 'success', 3000);
    }
  }

  function createHelpButton() {
    if (document.getElementById('onboarding-help-btn')) return;

    const btn = document.createElement('button');
    btn.id = 'onboarding-help-btn';
    btn.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--color-primary, #ffd700), #ffb700);
      color: #0a0a0f;
      border: none;
      cursor: pointer;
      font-size: 20px;
      font-weight: 700;
      box-shadow: 0 4px 20px rgba(255, 215, 0, 0.4);
      z-index: 9998;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: var(--font-display, serif);
    `;
    btn.innerHTML = '?';
    btn.title = '帮助 (F1)';
    btn.onclick = function() {
      showHelp();
    };
    btn.onmouseenter = function() {
      btn.style.transform = 'scale(1.1)';
      btn.style.boxShadow = '0 6px 24px rgba(255, 215, 0, 0.5)';
    };
    btn.onmouseleave = function() {
      btn.style.transform = 'scale(1)';
      btn.style.boxShadow = '0 4px 20px rgba(255, 215, 0, 0.4)';
    };
    document.body.appendChild(btn);
  }

  function init() {
    if (isCompleted()) {
      createHelpButton();
      return;
    }

    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/ui/css/onboarding.css';
    document.head.appendChild(link);

    setTimeout(() => {
      show(0);
      createHelpButton();
    }, 800);
  }

  function showHelp() {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/ui/css/onboarding.css';
    document.head.appendChild(link);

    show(0);
  }

  return {
    init,
    show,
    showHelp,
    next,
    prev,
    skip,
    complete,
    reset,
    isCompleted
  };
})();

document.addEventListener('DOMContentLoaded', function() {
  if (document.body.dataset.onboarding !== 'false') {
    window.Onboarding.init();
  }
});

document.addEventListener('keydown', function(e) {
  if (e.key === 'F1') {
    e.preventDefault();
    window.Onboarding.showHelp();
  }
  if (e.key === 'Escape') {
    const overlay = document.querySelector('.onboarding-overlay.active');
    if (overlay) {
      window.Onboarding.skip();
    }
  }
});
