import { getLang, setLang } from "./i18n.js";
import { initMenus } from "./menu.js";
import { initTheme } from "./theme.js";

initTheme();
initMenus();

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-lang-set]");
  if (button && button.dataset.langSet !== getLang()) {
    setLang(button.dataset.langSet);
  }
});
