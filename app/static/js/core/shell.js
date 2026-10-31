import { apiPost } from "./api.js";
import { getLang, setLang } from "./i18n.js";
import { initMenus } from "./menu.js";
import { initTheme } from "./theme.js";

initTheme();
initMenus();

document.addEventListener("click", async (event) => {
  const langButton = event.target.closest("[data-lang-set]");
  if (langButton && langButton.dataset.langSet !== getLang()) {
    await setLang(langButton.dataset.langSet);
    return;
  }

  const logoutButton = event.target.closest('[data-action="logout"]');
  if (logoutButton) {
    logoutButton.disabled = true;
    try {
      await apiPost("/auth/logout");
    } catch {
      // Redirect to login even if session already expired.
    }
    window.location.assign("/login");
  }
});
