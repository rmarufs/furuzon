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
  if (document.documentElement.dataset.authenticated === "true") {
    fetch("/api/me/preferences", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ theme }),
    }).catch(() => {});
  }
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
