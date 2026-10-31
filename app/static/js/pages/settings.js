import { apiPost } from "../core/api.js";
import { t } from "../core/i18n.js";
import { initPasswordToggles } from "./auth.js";

initPasswordToggles();

const form = document.querySelector("[data-settings-password-form]");
if (form) {
  const errorEl = form.querySelector("[data-form-error]");
  const successEl = form.querySelector("[data-form-success]");
  const submit = form.querySelector('button[type="submit"]');

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (errorEl) {
      errorEl.textContent = "";
      errorEl.hidden = true;
    }
    if (successEl) {
      successEl.hidden = true;
    }
    if (submit) {
      submit.disabled = true;
      submit.classList.add("is-loading");
    }

    const formData = new FormData(form);
    try {
      await apiPost("/auth/change-password", {
        current_password: String(formData.get("current_password") || ""),
        new_password: String(formData.get("new_password") || ""),
      });
      form.reset();
      if (successEl) {
        successEl.hidden = false;
      }
    } catch (err) {
      if (errorEl) {
        errorEl.textContent = err.message || t("errors.unknown");
        errorEl.hidden = false;
      }
    } finally {
      if (submit) {
        submit.disabled = false;
        submit.classList.remove("is-loading");
      }
    }
  });
}
