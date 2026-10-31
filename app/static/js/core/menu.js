function closeMenu(toggle, { restoreFocus = false } = {}) {
  const menu = document.getElementById(toggle.getAttribute("aria-controls"));
  if (!menu || menu.hidden) {
    return;
  }
  menu.hidden = true;
  toggle.setAttribute("aria-expanded", "false");
  if (restoreFocus) {
    toggle.focus();
  }
}

function openMenu(toggle) {
  const menu = document.getElementById(toggle.getAttribute("aria-controls"));
  if (!menu) {
    return;
  }
  menu.hidden = false;
  toggle.setAttribute("aria-expanded", "true");
}

function closeAll(except = null) {
  for (const toggle of document.querySelectorAll("[data-menu-toggle]")) {
    if (toggle !== except) {
      closeMenu(toggle);
    }
  }
}

export function initMenus() {
  document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-menu-toggle]");
    if (toggle) {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      closeAll(toggle);
      if (expanded) {
        closeMenu(toggle);
      } else {
        openMenu(toggle);
      }
      return;
    }
    if (!event.target.closest(".menu")) {
      closeAll();
    } else if (event.target.closest("[data-menu-close]")) {
      closeAll();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    for (const toggle of document.querySelectorAll("[data-menu-toggle]")) {
      if (toggle.getAttribute("aria-expanded") === "true") {
        closeMenu(toggle, { restoreFocus: true });
      }
    }
  });
}
