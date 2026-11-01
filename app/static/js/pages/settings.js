import { apiPatch, apiPost } from "../core/api.js";
import { t } from "../core/i18n.js";
import { showToast } from "../core/toast.js";
import { initPasswordToggles } from "./auth.js";

initPasswordToggles();

const profileForm = document.querySelector("[data-settings-profile-form]");
if (profileForm) {
  const errorEl = profileForm.querySelector("[data-form-error]");
  const submit = profileForm.querySelector('button[type="submit"]');

  profileForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (errorEl) {
      errorEl.textContent = "";
      errorEl.hidden = true;
    }

    const formData = new FormData(profileForm);
    const firstName = String(formData.get("first_name") || "").trim();
    const lastName = String(formData.get("last_name") || "").trim();

    if (!firstName || !lastName) {
      if (errorEl) {
        errorEl.textContent = t("auth.name_required");
        errorEl.hidden = false;
      }
      return;
    }

    if (submit) {
      submit.disabled = true;
      submit.classList.add("is-loading");
    }

    try {
      const updated = await apiPatch("/me/profile", {
        first_name: firstName,
        last_name: lastName,
      });
      const fullName = `${updated.first_name} ${updated.last_name}`.trim();
      const initials =
        (updated.first_name ? updated.first_name[0].toUpperCase() : "") +
        (updated.last_name ? updated.last_name[0].toUpperCase() : "");
      const btn = document.querySelector(".profile-btn");
      if (btn && fullName) {
        btn.setAttribute("aria-label", fullName);
      }
      const btnName = document.querySelector(".profile-btn__name");
      if (btnName && fullName) {
        btnName.textContent = fullName;
      }
      const btnAvatar = document.querySelector(".profile-btn__avatar");
      if (btnAvatar && initials) {
        btnAvatar.textContent = initials;
      }
      const menuName = document.querySelector(".menu__user-name");
      if (menuName && fullName) {
        menuName.textContent = fullName;
      }
      showToast(t("settings.profile_saved"));
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
