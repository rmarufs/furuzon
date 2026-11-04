import { confirmDialog } from "../core/modal.js";
import { t } from "../core/i18n.js";
import { showToast } from "../core/toast.js";

document.addEventListener("click", async (event) => {
  const trigger = event.target.closest("[data-demo]");
  if (!trigger) {
    return;
  }
  switch (trigger.dataset.demo) {
    case "confirm":
      await confirmDialog({ title: t("ui.dialog.title"), text: t("ui.dialog.text") });
      break;
    case "toast-success":
      showToast(t("ui.toast.success_text"), "success");
      break;
    case "toast-error":
      showToast(t("ui.toast.error_text"), "error");
      break;
  }
});
