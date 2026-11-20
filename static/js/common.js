
document.addEventListener('submit', event => {
  const question = event.target.dataset ? event.target.dataset.confirm : null;
  if (question && !window.confirm(question)) {
    event.preventDefault();
  }
});

document.addEventListener('DOMContentLoaded', () => {
  const toggleBtn = document.getElementById('themeToggleBtn');
  if (!toggleBtn) return;

  toggleBtn.addEventListener('click', () => {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (isDark) {
      document.documentElement.removeAttribute('data-theme');
      localStorage.setItem('chronos_theme', 'light');
    } else {
      document.documentElement.setAttribute('data-theme', 'dark');
      localStorage.setItem('chronos_theme', 'dark');
    }
  });
});

document.addEventListener('DOMContentLoaded', () => {
  const bar = document.getElementById('scrollProgress');
  if (bar) {
    const update = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.width = max > 0 ? (window.scrollY / max * 100) + '%' : '0';
    };
    window.addEventListener('scroll', update, { passive: true });
    update();
  }

  document.querySelectorAll('.main-content > .flash').forEach(msg => {
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'flash-close';
    close.setAttribute('aria-label', 'Close message');
    close.innerHTML = '&times;';
    close.addEventListener('click', () => hideFlash(msg));
    msg.appendChild(close);
    if (msg.classList.contains('success')) {
      setTimeout(() => hideFlash(msg), 6000);
    }
  });
});

function hideFlash(msg) {
  msg.classList.add('hiding');
  setTimeout(() => msg.remove(), 300);
}
