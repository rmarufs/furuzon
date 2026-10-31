import { apiDelete, apiGet, apiPatch } from "../core/api.js";
import { t, tp } from "../core/i18n.js";
import { confirmDialog } from "../core/modal.js";
import { showToast } from "../core/toast.js";

const COURSES = [1, 2, 3, 4, 5, 6];
const SVG_NS = "http://www.w3.org/2000/svg";

const coursesSection = document.querySelector("[data-courses-section]");
const chipsContainer = document.querySelector("[data-course-chips]");
const gridContainer = document.querySelector("[data-groups-grid]");
const emptyCourseEl = document.querySelector("[data-empty-course]");
const emptyAllEl = document.querySelector("[data-empty-all]");

let allGroups = [];
let selectedCourse = null;

function buildIcon(name, extraClass = "") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", extraClass ? `icon ${extraClass}` : "icon");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `/static/img/icons.svg#i-${name}`);
  svg.append(use);
  return svg;
}

function formatDate(isoString) {
  if (!isoString) {
    return "";
  }
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const year = date.getFullYear();
  return `${day}.${month}.${year}`;
}

function readCourseFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const raw = Number(params.get("course"));
  if (Number.isInteger(raw) && raw >= 1 && raw <= 6) {
    return raw;
  }
  return null;
}

function writeCourseToUrl(course, { replace = false } = {}) {
  const url = new URL(window.location.href);
  url.searchParams.set("course", String(course));
  if (replace) {
    window.history.replaceState({}, "", url);
  } else {
    window.history.pushState({}, "", url);
  }
}

function resolveDefaultCourse(groups) {
  for (const course of COURSES) {
    if (groups.some((g) => g.course === course)) {
      return course;
    }
  }
  return 1;
}

function renderCourseChips() {
  if (!chipsContainer) {
    return;
  }
  chipsContainer.replaceChildren();

  const counts = new Map(COURSES.map((c) => [c, 0]));
  for (const g of allGroups) {
    counts.set(g.course, (counts.get(g.course) || 0) + 1);
  }

  for (const course of COURSES) {
    const label = document.createElement("label");
    label.className = "chip";

    const input = document.createElement("input");
    input.className = "chip__input";
    input.type = "radio";
    input.name = "course-filter";
    input.value = String(course);
    input.checked = course === selectedCourse;
    input.addEventListener("change", () => {
      if (input.checked) {
        selectedCourse = course;
        writeCourseToUrl(course);
        renderCards();
      }
    });

    const face = document.createElement("span");
    face.className = "chip__face";

    const titleSpan = document.createElement("span");
    titleSpan.textContent = t("groups.course_chip", { n: course });

    const countSpan = document.createElement("span");
    countSpan.className = "chip__count";
    countSpan.textContent = String(counts.get(course) || 0);

    face.append(titleSpan, countSpan);
    label.append(input, face);
    chipsContainer.append(label);
  }
}

function openRenameModal(group) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "modal";
    dialog.setAttribute("aria-labelledby", "rename-modal-title");

    const form = document.createElement("form");
    form.noValidate = true;

    const body = document.createElement("div");
    body.className = "modal__body";

    const heading = document.createElement("h2");
    heading.id = "rename-modal-title";
    heading.textContent = t("groups.rename.title");

    const field = document.createElement("div");
    field.className = "field";

    const label = document.createElement("label");
    label.className = "field__label";
    label.htmlFor = "rename-group-number";
    label.textContent = t("groups.rename.label");

    const input = document.createElement("input");
    input.className = "input";
    input.id = "rename-group-number";
    input.name = "number";
    input.type = "text";
    input.maxLength = 50;
    input.required = true;
    input.value = group.number;

    const errorEl = document.createElement("p");
    errorEl.className = "field__error";
    errorEl.setAttribute("role", "alert");
    errorEl.hidden = true;

    field.append(label, input, errorEl);
    body.append(heading, field);

    const actions = document.createElement("div");
    actions.className = "modal__actions";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn btn--secondary";
    cancelBtn.textContent = t("common.cancel");
    cancelBtn.addEventListener("click", () => dialog.close("cancel"));

    const saveBtn = document.createElement("button");
    saveBtn.type = "submit";
    saveBtn.className = "btn btn--primary";
    saveBtn.textContent = t("common.save");

    actions.append(cancelBtn, saveBtn);
    form.append(body, actions);
    dialog.append(form);

    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        dialog.close("cancel");
      }
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorEl.hidden = true;
      errorEl.textContent = "";

      const trimmed = input.value.trim();
      if (!trimmed || trimmed.length > 50) {
        errorEl.textContent = t("errors.validation_error");
        errorEl.hidden = false;
        return;
      }

      saveBtn.disabled = true;
      saveBtn.classList.add("is-loading");
      try {
        const updated = await apiPatch(`/groups/${group.id}`, { number: trimmed });
        dialog.close("saved");
        resolve(updated);
      } catch (err) {
        errorEl.textContent = err.message || t("errors.unknown");
        errorEl.hidden = false;
      } finally {
        saveBtn.disabled = false;
        saveBtn.classList.remove("is-loading");
      }
    });

    dialog.addEventListener("close", () => {
      const saved = dialog.returnValue === "saved";
      dialog.remove();
      if (!saved) {
        resolve(null);
      }
    });

    document.body.append(dialog);
    dialog.showModal();
    input.focus();
    input.select();
  });
}

function buildGroupCard(group) {
  const article = document.createElement("article");
  article.className = "card group-card";
  article.dataset.groupId = String(group.id);

  const header = document.createElement("div");
  header.className = "card__header group-card__header";

  const identity = document.createElement("div");
  identity.className = "group-card__identity";

  const iconBox = document.createElement("span");
  iconBox.className = "group-card__icon";
  iconBox.append(buildIcon("groups"));

  const titleWrap = document.createElement("div");
  titleWrap.className = "group-card__title-wrap";

  const title = document.createElement("h3");
  title.className = "card__title group-card__title";

  const link = document.createElement("a");
  link.className = "group-card__link";
  link.href = `/groups/${group.id}`;
  link.textContent = group.number;
  title.append(link);

  const courseBadge = document.createElement("span");
  courseBadge.className = "badge group-card__course-badge";
  courseBadge.textContent = t("groups.card.course", { n: group.course });

  titleWrap.append(title, courseBadge);
  identity.append(iconBox, titleWrap);

  const menuWrap = document.createElement("div");
  menuWrap.className = "menu-wrap";

  const menuId = `group-menu-${group.id}`;
  const toggleBtn = document.createElement("button");
  toggleBtn.type = "button";
  toggleBtn.className = "icon-btn";
  toggleBtn.dataset.menuToggle = "";
  toggleBtn.setAttribute("aria-controls", menuId);
  toggleBtn.setAttribute("aria-haspopup", "true");
  toggleBtn.setAttribute("aria-expanded", "false");
  toggleBtn.setAttribute("aria-label", t("common.more_actions"));
  toggleBtn.append(buildIcon("more"));

  const menu = document.createElement("div");
  menu.className = "menu";
  menu.id = menuId;
  menu.hidden = true;

  // Rename action
  const renameBtn = document.createElement("button");
  renameBtn.type = "button";
  renameBtn.className = "menu__item";
  renameBtn.dataset.menuClose = "";
  const renameText = document.createElement("span");
  renameText.textContent = t("groups.menu.rename");
  renameBtn.append(buildIcon("edit"), renameText);
  renameBtn.addEventListener("click", async () => {
    const updated = await openRenameModal(group);
    if (updated) {
      group.number = updated.number;
      group.updated_at = updated.updated_at;
      allGroups.sort((a, b) => a.number.localeCompare(b.number) || a.id - b.id);
      renderView();
      showToast(t("groups.rename.success"));
    }
  });

  // Edit action (link to /groups/{id})
  const editLink = document.createElement("a");
  editLink.className = "menu__item";
  editLink.href = `/groups/${group.id}`;
  editLink.dataset.menuClose = "";
  const editText = document.createElement("span");
  editText.textContent = t("groups.menu.edit");
  editLink.append(buildIcon("groups"), editText);

  const sep = document.createElement("hr");
  sep.className = "menu__separator";

  // Delete action
  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "menu__item menu__item--danger";
  deleteBtn.dataset.menuClose = "";
  const deleteText = document.createElement("span");
  deleteText.textContent = t("groups.menu.delete");
  deleteBtn.append(buildIcon("trash"), deleteText);
  deleteBtn.addEventListener("click", async () => {
    const confirmed = await confirmDialog({
      title: t("groups.delete.title"),
      text: t("groups.delete.text"),
    });
    if (!confirmed) {
      return;
    }
    try {
      await apiDelete(`/groups/${group.id}`);
      allGroups = allGroups.filter((g) => g.id !== group.id);
      renderView();
      showToast(t("groups.delete.success"));
    } catch (err) {
      showToast(err.message || t("errors.unknown"), "error");
    }
  });

  menu.append(renameBtn, editLink, sep, deleteBtn);
  menuWrap.append(toggleBtn, menu);
  header.append(identity, menuWrap);

  const body = document.createElement("div");
  body.className = "group-card__body";

  const studentsText = document.createElement("span");
  studentsText.textContent = tp("students_count", group.students_count);
  body.append(buildIcon("profile", "icon--sm"), studentsText);

  const footer = document.createElement("div");
  footer.className = "group-card__footer";

  const dateMeta = document.createElement("span");
  dateMeta.textContent = t("groups.card.modified", {
    date: formatDate(group.updated_at),
  });
  footer.append(dateMeta);

  article.append(header, body, footer);

  article.addEventListener("click", (event) => {
    if (
      event.target.closest(".menu-wrap") ||
      event.target.closest("a") ||
      event.target.closest("button")
    ) {
      return;
    }
    window.location.assign(`/groups/${group.id}`);
  });

  return article;
}

function renderCards() {
  if (!gridContainer || !emptyCourseEl) {
    return;
  }
  gridContainer.replaceChildren();
  const filtered = allGroups.filter((g) => g.course === selectedCourse);

  if (filtered.length === 0) {
    gridContainer.hidden = true;
    emptyCourseEl.hidden = false;
    return;
  }

  emptyCourseEl.hidden = true;
  gridContainer.hidden = false;
  for (const group of filtered) {
    gridContainer.append(buildGroupCard(group));
  }
}

function renderView() {
  if (!coursesSection || !emptyAllEl) {
    return;
  }
  if (allGroups.length === 0) {
    coursesSection.hidden = true;
    emptyAllEl.hidden = false;
    return;
  }

  emptyAllEl.hidden = true;
  coursesSection.hidden = false;
  renderCourseChips();
  renderCards();
}

async function init() {
  try {
    allGroups = await apiGet("/groups");
  } catch (err) {
    showToast(err.message || t("errors.unknown"), "error");
    return;
  }

  const urlCourse = readCourseFromUrl();
  if (urlCourse !== null) {
    selectedCourse = urlCourse;
  } else {
    selectedCourse = resolveDefaultCourse(allGroups);
    writeCourseToUrl(selectedCourse, { replace: true });
  }

  renderView();
}

window.addEventListener("popstate", () => {
  const urlCourse = readCourseFromUrl();
  if (urlCourse !== null) {
    selectedCourse = urlCourse;
    renderView();
  }
});

init();
