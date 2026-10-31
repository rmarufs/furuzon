import { apiPost } from "../core/api.js";
import { t } from "../core/i18n.js";

export function initPasswordToggles(root = document) {
  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-password-toggle]");
    if (!button) {
      return;
    }
    const input = document.getElementById(button.dataset.passwordToggle);
    if (!input) {
      return;
    }
    const isPassword = input.type === "password";
    input.type = isPassword ? "text" : "password";
    button.textContent = t(isPassword ? "auth.hide_password" : "auth.show_password");
  });
}

function showError(form, message) {
  const errorEl = form.querySelector("[data-form-error]");
  if (!errorEl) {
    return;
  }
  errorEl.textContent = message;
  errorEl.hidden = false;
}

function clearError(form) {
  const errorEl = form.querySelector("[data-form-error]");
  if (!errorEl) {
    return;
  }
  errorEl.textContent = "";
  errorEl.hidden = true;
}

function setSubmitting(form, busy) {
  const submit = form.querySelector('button[type="submit"]');
  if (!submit) {
    return;
  }
  submit.disabled = busy;
  submit.classList.toggle("is-loading", busy);
}

initPasswordToggles();

for (const form of document.querySelectorAll("[data-auth-form]")) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError(form);
    setSubmitting(form, true);

    const kind = form.dataset.authForm;
    const formData = new FormData(form);

    try {
      if (kind === "login") {
        await apiPost("/auth/login", {
          email: String(formData.get("email") || "").trim(),
          password: String(formData.get("password") || ""),
        });
        window.location.assign("/");
        return;
      }

      if (kind === "register") {
        await apiPost("/auth/register", {
          email: String(formData.get("email") || "").trim(),
          password: String(formData.get("password") || ""),
        });
        window.location.assign("/");
        return;
      }

      if (kind === "forgot") {
        await apiPost("/auth/forgot-password", {
          email: String(formData.get("email") || "").trim(),
        });
        form.hidden = true;
        const success = form.parentElement?.querySelector("[data-form-success]");
        if (success) {
          success.hidden = false;
        }
        return;
      }

      if (kind === "reset") {
        const params = new URLSearchParams(window.location.search);
        const token = String(formData.get("token") || params.get("token") || "");
        await apiPost("/auth/reset-password", {
          token,
          new_password: String(formData.get("new_password") || ""),
        });
        form.hidden = true;
        const footer = form.parentElement?.querySelector("[data-reset-footer]");
        if (footer) {
          footer.hidden = true;
        }
        const success = form.parentElement?.querySelector("[data-form-success]");
        if (success) {
          success.hidden = false;
        }
      }
    } catch (err) {
      showError(form, err.message || t("errors.unknown"));
    } finally {
      setSubmitting(form, false);
    }
  });
}
