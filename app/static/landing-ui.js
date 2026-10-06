(() => {
  const root = document.documentElement;
  const nav = document.querySelector('nav');
  const theme = document.querySelector('.theme-toggle');
  const menu = document.querySelector('.menu-toggle');
  const syncTheme = () => { theme.textContent = root.dataset.theme === 'light' ? 'Dark theme' : 'Light theme'; theme.setAttribute('aria-label', 'Switch to ' + (root.dataset.theme === 'light' ? 'dark' : 'light') + ' theme'); };
  syncTheme();
  theme.addEventListener('click', () => { root.dataset.theme = root.dataset.theme === 'light' ? 'dark' : 'light'; try { localStorage.setItem('gate-theme', root.dataset.theme); } catch (_) {} syncTheme(); });
  const close = () => { delete nav.dataset.menu; menu.setAttribute('aria-expanded', 'false'); };
  menu.addEventListener('click', () => { const open = menu.getAttribute('aria-expanded') !== 'true'; nav.dataset.menu = open ? 'open' : ''; menu.setAttribute('aria-expanded', String(open)); });
  nav.querySelectorAll('a').forEach(a => a.addEventListener('click', close));
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && nav.dataset.menu === 'open') { close(); menu.focus(); } });
})();
