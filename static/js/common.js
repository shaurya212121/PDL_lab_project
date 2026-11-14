/**
 * Used on every page.
 * Any form with data-confirm="question" asks the user before submitting.
 */
document.addEventListener('submit', event => {
  const question = event.target.dataset ? event.target.dataset.confirm : null;
  if (question && !window.confirm(question)) {
    event.preventDefault();
  }
});

/**
 * Theme toggle handler for Light / Dark Mode.
 * Persists user choice in localStorage across page transitions.
 */
document.addEventListener('DOMContentLoaded', () => {
  const toggleBtn = document.getElementById('themeToggleBtn');
  if (!toggleBtn) return;

  toggleBtn.addEventListener('click', () => {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (isDark) {
      document.documentElement.removeAttribute('data-theme');
      localStorage.setItem('clashaudit_theme', 'light');
    } else {
      document.documentElement.setAttribute('data-theme', 'dark');
      localStorage.setItem('clashaudit_theme', 'dark');
    }
  });
});
