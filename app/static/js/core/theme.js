const THEMES = ["light", "dark"];

export function getTheme() {
  return document.documentElement.dataset.theme;
}

export function setTheme(theme) {
  if (!THEMES.includes(theme)) {
    return;
  }
  document.documentElement.dataset.theme = theme;
  document.cookie = `theme=${theme}; path=/; max-age=31536000; SameSite=Lax`;
  syncThemeButtons();
}

export function syncThemeButtons() {
  const current = getTheme();
  for (const button of document.querySelectorAll("[data-theme-set]")) {
    button.setAttribute("aria-pressed", String(button.dataset.themeSet === current));
  }
}

export function initTheme() {
  syncThemeButtons();
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-theme-set]");
    if (button) {
      setTheme(button.dataset.themeSet);
    }
  });
}
