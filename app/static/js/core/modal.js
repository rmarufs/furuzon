import { t } from "./i18n.js";

export function confirmDialog({ title, text, confirmLabel, cancelLabel } = {}) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "modal";

    const body = document.createElement("div");
    body.className = "modal__body";

    const heading = document.createElement("h2");
    heading.id = "modal-title";
    heading.textContent = title ?? t("common.confirm_title");
    body.append(heading);

    if (text) {
      const paragraph = document.createElement("p");
      paragraph.id = "modal-text";
      paragraph.textContent = text;
      body.append(paragraph);
      dialog.setAttribute("aria-describedby", "modal-text");
    }
    dialog.setAttribute("aria-labelledby", "modal-title");

    const actions = document.createElement("div");
    actions.className = "modal__actions";

    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "btn btn--secondary";
    cancel.textContent = cancelLabel ?? t("common.cancel");
    cancel.autofocus = true;
    cancel.addEventListener("click", () => dialog.close("cancel"));

    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "btn btn--danger";
    confirm.textContent = confirmLabel ?? t("common.confirm_delete");
    confirm.addEventListener("click", () => dialog.close("confirm"));

    actions.append(cancel, confirm);
    dialog.append(body, actions);

    // Light dismiss counts as cancel.
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        dialog.close("cancel");
      }
    });

    dialog.addEventListener("close", () => {
      const confirmed = dialog.returnValue === "confirm";
      dialog.remove();
      resolve(confirmed);
    });

    document.body.append(dialog);
    dialog.showModal();
    cancel.focus();
  });
}
