import { apiGet } from "../core/api.js";
import { t } from "../core/i18n.js";

const labelEl = document.querySelector("[data-home-create-group-label]");

async function init() {
  if (!labelEl) {
    return;
  }
  try {
    const groups = await apiGet("/groups");
    const hasGroups = Array.isArray(groups) && groups.length > 0;
    labelEl.textContent = t(
      hasGroups ? "home.create_group" : "home.create_first_group",
    );
  } catch {
    // Keep default label if request fails.
  }
}

init();
