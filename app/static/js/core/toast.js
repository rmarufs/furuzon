import { t } from "./i18n.js";

const TOAST_LIFETIME_MS = 4000;
const SVG_NS = "http://www.w3.org/2000/svg";

function buildIcon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "icon toast__icon");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `/static/img/icons.svg#i-${name}`);
  svg.append(use);
  return svg;
}

export function showToast(text, type = "success") {
  const region = document.getElementById("toast-region");
  if (!region) {
    return;
  }

  const toast = document.createElement("div");
  toast.className = `toast toast--${type}`;

  const label = document.createElement("span");
  label.className = "visually-hidden";
  label.textContent = t(type === "error" ? "toast.error_label" : "toast.success_label");

  const message = document.createElement("span");
  message.textContent = text;

  toast.append(buildIcon(type === "error" ? "alert" : "check"), label, message);
  region.append(toast);

  window.setTimeout(() => toast.remove(), TOAST_LIFETIME_MS);
}
