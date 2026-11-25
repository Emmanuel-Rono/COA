// Apply the saved appearance before the page paints. No model or network calls.
(() => {
  let preference = 'system';
  try { preference = localStorage.getItem('commerce-appearance') || 'system'; } catch (_) {}
  const dark = preference === 'dark' || (preference === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
})();
