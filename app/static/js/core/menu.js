const VIEWPORT_MARGIN = 8;
const MENU_GAP = 8;

const originalLocations = new WeakMap();
let activeState = null;

function getViewportBounds() {
  let bottom = window.innerHeight;
  const bottomNav = document.querySelector(".bottom-nav");
  if (bottomNav && window.getComputedStyle(bottomNav).display !== "none") {
    const navRect = bottomNav.getBoundingClientRect();
    if (navRect.height > 0 && navRect.top > 0) {
      bottom = Math.min(bottom, navRect.top);
    }
  }
  return {
    top: VIEWPORT_MARGIN,
    bottom: bottom - VIEWPORT_MARGIN,
    left: VIEWPORT_MARGIN,
    right: window.innerWidth - VIEWPORT_MARGIN,
  };
}

function positionMenu(toggle, menu) {
  const toggleRect = toggle.getBoundingClientRect();
  const menuRect = menu.getBoundingClientRect();
  const bounds = getViewportBounds();

  let left = toggleRect.right - menuRect.width;
  if (left + menuRect.width > bounds.right) {
    left = bounds.right - menuRect.width;
  }
  if (left < bounds.left) {
    left = bounds.left;
  }

  const downTop = toggleRect.bottom + MENU_GAP;
  const upTop = toggleRect.top - MENU_GAP - menuRect.height;
  const spaceBelow = bounds.bottom - toggleRect.bottom;
  const spaceAbove = toggleRect.top - bounds.top;

  let top = downTop;
  if (downTop + menuRect.height > bounds.bottom && spaceAbove > spaceBelow) {
    top = Math.max(bounds.top, upTop);
  } else if (top + menuRect.height > bounds.bottom) {
    top = Math.max(bounds.top, bounds.bottom - menuRect.height);
  }

  menu.style.left = `${Math.round(left)}px`;
  menu.style.top = `${Math.round(top)}px`;
}

function restoreMenuDom(menu) {
  const loc = originalLocations.get(menu);
  if (!loc) {
    return;
  }
  const { parent, nextSibling } = loc;
  if (parent && parent.isConnected) {
    if (nextSibling && nextSibling.parentNode === parent) {
      parent.insertBefore(menu, nextSibling);
    } else {
      parent.append(menu);
    }
  } else {
    menu.remove();
  }
  originalLocations.delete(menu);
}

function closeMenu(toggle, { restoreFocus = false } = {}) {
  const menuId = toggle.getAttribute("aria-controls");
  const menu =
    activeState && activeState.toggle === toggle
      ? activeState.menu
      : document.getElementById(menuId);

  if (!menu || menu.hidden) {
    return;
  }

  menu.hidden = true;
  menu.style.left = "";
  menu.style.top = "";
  toggle.setAttribute("aria-expanded", "false");
  restoreMenuDom(menu);

  if (activeState && activeState.toggle === toggle) {
    activeState = null;
  }

  if (restoreFocus && toggle.isConnected) {
    toggle.focus();
  }
}

function openMenu(toggle) {
  const menu = document.getElementById(toggle.getAttribute("aria-controls"));
  if (!menu) {
    return;
  }

  originalLocations.set(menu, {
    parent: menu.parentNode,
    nextSibling: menu.nextSibling,
  });

  document.body.append(menu);
  menu.hidden = false;
  toggle.setAttribute("aria-expanded", "true");
  activeState = { toggle, menu };
  positionMenu(toggle, menu);
}

function closeAll(except = null, { restoreFocus = false } = {}) {
  if (activeState && activeState.toggle !== except) {
    closeMenu(activeState.toggle, { restoreFocus });
  }
  for (const toggle of document.querySelectorAll("[data-menu-toggle]")) {
    if (toggle !== except && toggle.getAttribute("aria-expanded") === "true") {
      closeMenu(toggle, { restoreFocus });
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
        closeMenu(toggle, { restoreFocus: true });
      } else {
        openMenu(toggle);
      }
      return;
    }
    if (!event.target.closest(".menu")) {
      closeAll();
    } else if (event.target.closest("[data-menu-close]")) {
      const toggleToFocus = activeState ? activeState.toggle : null;
      closeAll(null, { restoreFocus: Boolean(toggleToFocus) });
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    if (activeState) {
      closeMenu(activeState.toggle, { restoreFocus: true });
      return;
    }
    for (const toggle of document.querySelectorAll("[data-menu-toggle]")) {
      if (toggle.getAttribute("aria-expanded") === "true") {
        closeMenu(toggle, { restoreFocus: true });
      }
    }
  });

  window.addEventListener(
    "resize",
    () => {
      if (!activeState) {
        return;
      }
      if (!activeState.toggle.isConnected) {
        closeAll();
        return;
      }
      positionMenu(activeState.toggle, activeState.menu);
    },
    { passive: true },
  );

  window.addEventListener(
    "scroll",
    () => {
      if (!activeState) {
        return;
      }
      if (!activeState.toggle.isConnected) {
        closeAll();
        return;
      }
      positionMenu(activeState.toggle, activeState.menu);
    },
    { capture: true, passive: true },
  );
}
