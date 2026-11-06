import { apiDelete, apiGet, apiPatch, apiPost } from "../core/api.js";
import { t, tp } from "../core/i18n.js";
import { confirmDialog } from "../core/modal.js";
import { showToast } from "../core/toast.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const SEARCH_DEBOUNCE_MS = 250;

const pageEl = document.querySelector("[data-group-detail-page]");
const groupId = pageEl ? Number(pageEl.dataset.groupId) : null;

const titleEl = document.querySelector("[data-group-title]");
const metaCourseEl = document.querySelector("[data-meta-course]");
const metaStudentsEl = document.querySelector("[data-meta-students]");
const metaModifiedEl = document.querySelector("[data-meta-modified]");
const backLinkEl = document.querySelector("[data-back-link]");

const studentsSection = document.querySelector("[data-students-section]");
const emptyStudentsEl = document.querySelector("[data-empty-students]");
const tableWrapEl = document.querySelector("[data-table-wrap]");
const theadRowEl = document.querySelector("[data-students-thead-row]");
const tbodyEl = document.querySelector("[data-students-tbody]");
const searchEmptyEl = document.querySelector("[data-search-empty]");

const searchInput = document.querySelector("[data-search-input]");
const searchClearBtn = document.querySelector("[data-search-clear]");
const addStudentBtns = document.querySelectorAll("[data-action-add-student]");
const columnsBtn = document.querySelector("[data-action-columns]");

let groupData = null; // { id, number, course, columns, students, updated_at }
let displayedStudents = [];
let searchQuery = "";
let searchTimer = null;
let searchRequestSeq = 0;

function buildIcon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "icon");
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

function touchModifiedNow() {
  if (groupData) {
    groupData.updated_at = new Date().toISOString();
  }
}

function renderHeaderMeta() {
  if (!groupData) {
    return;
  }
  if (titleEl) {
    titleEl.textContent = groupData.number;
  }
  if (backLinkEl) {
    backLinkEl.href = `/groups?course=${groupData.course}`;
  }
  if (metaCourseEl) {
    metaCourseEl.textContent = t("groups.card.course", { n: groupData.course });
  }
  if (metaStudentsEl) {
    metaStudentsEl.textContent = tp(
      "students_count",
      groupData.students.length,
    );
  }
  if (metaModifiedEl) {
    metaModifiedEl.textContent = t("groups.card.modified", {
      date: formatDate(groupData.updated_at),
    });
  }
}

function renderCellDisplay(td, value) {
  td.replaceChildren();
  const span = document.createElement("span");
  span.className = "student-cell__value";
  if (value === "") {
    span.classList.add("student-cell__value--empty");
    span.textContent = t("groups.detail.empty_cell");
  } else {
    span.textContent = value;
  }
  td.append(span);
}

function startCellEdit(td, student, colKey) {
  if (td.dataset.editing === "true") {
    return;
  }
  td.dataset.editing = "true";

  const oldValue = String(
    student.data && student.data[colKey] !== undefined
      ? student.data[colKey]
      : "",
  );

  const input = document.createElement("input");
  input.type = "text";
  input.className = "input student-cell__input";
  input.maxLength = 500;
  input.value = oldValue;

  td.replaceChildren(input);
  input.focus();
  input.select();

  let finished = false;

  async function commit() {
    if (finished) {
      return;
    }
    finished = true;
    delete td.dataset.editing;

    const newValue = input.value.trim();
    if (newValue === oldValue) {
      renderCellDisplay(td, oldValue);
      return;
    }

    renderCellDisplay(td, newValue);
    try {
      const updated = await apiPatch(
        `/groups/${groupId}/students/${student.id}`,
        { key: colKey, value: newValue },
      );
      student.data = updated.data;
      const inFull = groupData.students.find((s) => s.id === student.id);
      if (inFull) {
        inFull.data = updated.data;
      }
      touchModifiedNow();
      renderHeaderMeta();
      renderCellDisplay(td, String(updated.data[colKey] || ""));
    } catch (err) {
      showToast(err.message || t("errors.unknown"), "error");
      renderCellDisplay(td, oldValue);
    }
  }

  function cancel() {
    if (finished) {
      return;
    }
    finished = true;
    delete td.dataset.editing;
    renderCellDisplay(td, oldValue);
  }

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      commit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancel();
    }
  });

  input.addEventListener("blur", () => {
    commit();
  });
}

const NUMBER_COLUMN_TITLES = new Set(["номер", "№", "№ п/п", "п/п", "рақам"]);

function findNumberColumnKey(columns) {
  if (!Array.isArray(columns) || columns.length <= 1) {
    return null;
  }
  for (const col of columns) {
    const norm = String((col && col.title) || "")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, " ")
      .replace(/[.:]+$/, "");
    if (NUMBER_COLUMN_TITLES.has(norm)) {
      return col.key;
    }
  }
  return null;
}

function buildStudentRow(student) {
  const tr = document.createElement("tr");
  tr.dataset.studentId = String(student.id);

  const numberColKey = findNumberColumnKey(groupData.columns);
  if (numberColKey !== null) {
    tr.classList.add("student-row--numbered");
  }
  let titleAssigned = false;

  for (const col of groupData.columns) {
    const td = document.createElement("td");
    td.className = "student-cell";
    if (col.key === numberColKey) {
      td.classList.add("student-cell--number");
    } else if (!titleAssigned) {
      td.classList.add("student-cell--title");
      titleAssigned = true;
    }
    td.dataset.label = col.title;
    td.dataset.colKey = col.key;
    td.tabIndex = 0;

    const val = String(
      student.data && student.data[col.key] !== undefined
        ? student.data[col.key]
        : "",
    );
    renderCellDisplay(td, val);

    td.addEventListener("click", () => {
      startCellEdit(td, student, col.key);
    });
    td.addEventListener("keydown", (event) => {
      if (
        td.dataset.editing !== "true" &&
        (event.key === "Enter" || event.key === " ")
      ) {
        event.preventDefault();
        startCellEdit(td, student, col.key);
      }
    });

    tr.append(td);
  }

  // Actions cell with 3-dots menu
  const actionsTd = document.createElement("td");
  actionsTd.className = "student-actions-cell";

  const menuWrap = document.createElement("div");
  menuWrap.className = "menu-wrap";

  const menuId = `student-menu-${student.id}`;
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

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "menu__item menu__item--danger";
  deleteBtn.dataset.menuClose = "";
  const deleteText = document.createElement("span");
  deleteText.textContent = t("common.delete");
  deleteBtn.append(buildIcon("trash"), deleteText);

  deleteBtn.addEventListener("click", async () => {
    const confirmed = await confirmDialog({
      title: t("groups.student_delete.title"),
      text: t("groups.student_delete.text"),
    });
    if (!confirmed) {
      return;
    }
    try {
      await apiDelete(`/groups/${groupId}/students/${student.id}`);
      groupData.students = groupData.students.filter(
        (s) => s.id !== student.id,
      );
      displayedStudents = displayedStudents.filter((s) => s.id !== student.id);
      touchModifiedNow();
      renderAll();
      showToast(t("groups.student_delete.success"));
    } catch (err) {
      showToast(err.message || t("errors.unknown"), "error");
    }
  });

  menu.append(deleteBtn);
  menuWrap.append(toggleBtn, menu);
  actionsTd.append(menuWrap);
  tr.append(actionsTd);

  return tr;
}

function renderTable() {
  if (!theadRowEl || !tbodyEl || !tableWrapEl || !searchEmptyEl) {
    return;
  }

  theadRowEl.replaceChildren();
  for (const col of groupData.columns) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = col.title;
    theadRowEl.append(th);
  }
  const actionsTh = document.createElement("th");
  actionsTh.scope = "col";
  const srActions = document.createElement("span");
  srActions.className = "visually-hidden";
  srActions.textContent = t("common.more_actions");
  actionsTh.append(srActions);
  theadRowEl.append(actionsTh);

  tbodyEl.replaceChildren();

  if (displayedStudents.length === 0 && searchQuery.trim() !== "") {
    tableWrapEl.hidden = true;
    searchEmptyEl.hidden = false;
    return;
  }

  searchEmptyEl.hidden = true;
  tableWrapEl.hidden = false;
  for (const student of displayedStudents) {
    tbodyEl.append(buildStudentRow(student));
  }
}

function renderAll() {
  if (!groupData || !studentsSection || !emptyStudentsEl) {
    return;
  }
  renderHeaderMeta();

  if (groupData.students.length === 0) {
    studentsSection.hidden = true;
    emptyStudentsEl.hidden = false;
    return;
  }

  emptyStudentsEl.hidden = true;
  studentsSection.hidden = false;
  renderTable();
}

async function runSearch(query) {
  const seq = ++searchRequestSeq;
  const trimmed = query.trim();

  if (!trimmed) {
    displayedStudents = [...groupData.students];
    renderAll();
    return;
  }

  try {
    const params = new URLSearchParams({ q: query });
    const results = await apiGet(
      `/groups/${groupId}/students?${params.toString()}`,
    );
    if (seq !== searchRequestSeq) {
      return;
    }
    displayedStudents = results;
    renderAll();
  } catch (err) {
    if (seq !== searchRequestSeq) {
      return;
    }
    showToast(err.message || t("errors.unknown"), "error");
  }
}

function openAddStudentModal() {
  if (!groupData) {
    return;
  }
  const dialog = document.createElement("dialog");
  dialog.className = "modal";
  dialog.setAttribute("aria-labelledby", "add-student-modal-title");

  const form = document.createElement("form");
  form.noValidate = true;

  const body = document.createElement("div");
  body.className = "modal__body";

  const heading = document.createElement("h2");
  heading.id = "add-student-modal-title";
  heading.textContent = t("groups.student_add.title");
  body.append(heading);

  const inputsByKey = new Map();
  groupData.columns.forEach((col, idx) => {
    const field = document.createElement("div");
    field.className = "field";

    const inputId = `add-student-col-${col.key}`;
    const label = document.createElement("label");
    label.className = "field__label";
    label.htmlFor = inputId;
    label.textContent = col.title;

    const input = document.createElement("input");
    input.className = "input";
    input.id = inputId;
    input.name = col.key;
    input.type = "text";
    input.maxLength = 500;
    if (idx === 0) {
      input.autofocus = true;
    }

    inputsByKey.set(col.key, input);
    field.append(label, input);
    body.append(field);
  });

  const errorEl = document.createElement("p");
  errorEl.className = "field__error";
  errorEl.setAttribute("role", "alert");
  errorEl.hidden = true;
  body.append(errorEl);

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
  saveBtn.textContent = t("common.add");

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

    const dataPayload = {};
    let hasNonEmpty = false;
    for (const [key, input] of inputsByKey.entries()) {
      const val = input.value.trim();
      dataPayload[key] = val;
      if (val !== "") {
        hasNonEmpty = true;
      }
    }

    if (!hasNonEmpty) {
      errorEl.textContent = t("errors.student_empty");
      errorEl.hidden = false;
      return;
    }

    saveBtn.disabled = true;
    saveBtn.classList.add("is-loading");
    try {
      const created = await apiPost(`/groups/${groupId}/students`, {
        data: dataPayload,
      });
      groupData.students.push(created);
      touchModifiedNow();

      // Reset search so the new student is visible
      searchQuery = "";
      if (searchInput) {
        searchInput.value = "";
      }
      if (searchClearBtn) {
        searchClearBtn.hidden = true;
      }
      displayedStudents = [...groupData.students];

      dialog.close("saved");
      renderAll();
      showToast(t("groups.student_add.success"));

      const newRow = tbodyEl
        ? tbodyEl.querySelector(`tr[data-student-id="${created.id}"]`)
        : null;
      if (newRow) {
        newRow.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    } catch (err) {
      errorEl.textContent = err.message || t("errors.unknown");
      errorEl.hidden = false;
    } finally {
      saveBtn.disabled = false;
      saveBtn.classList.remove("is-loading");
    }
  });

  dialog.addEventListener("close", () => {
    dialog.remove();
  });

  document.body.append(dialog);
  dialog.showModal();
  const firstInput = inputsByKey.values().next().value;
  if (firstInput) {
    firstInput.focus();
  }
}

function openColumnsModal() {
  if (!groupData) {
    return;
  }
  const dialog = document.createElement("dialog");
  dialog.className = "modal";
  dialog.setAttribute("aria-labelledby", "columns-modal-title");

  const body = document.createElement("div");
  body.className = "modal__body";

  const heading = document.createElement("h2");
  heading.id = "columns-modal-title";
  heading.textContent = t("groups.columns_modal.title");

  const listEl = document.createElement("ul");
  listEl.className = "column-list";

  const hintEl = document.createElement("p");
  hintEl.className = "text-small text-muted";
  hintEl.textContent = t("groups.columns_modal.last_col_hint");

  const errorEl = document.createElement("p");
  errorEl.className = "field__error";
  errorEl.setAttribute("role", "alert");
  errorEl.hidden = true;

  body.append(heading, listEl, hintEl, errorEl);

  const actions = document.createElement("div");
  actions.className = "modal__actions";

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "btn btn--secondary";
  closeBtn.textContent = t("common.close");
  closeBtn.addEventListener("click", () => dialog.close());
  actions.append(closeBtn);

  dialog.append(body, actions);

  let busy = false;

  async function reorderColumns(newOrderKeys) {
    if (busy) {
      return;
    }
    busy = true;
    errorEl.hidden = true;
    renderModalColumns();
    try {
      const updated = await apiPatch(`/groups/${groupId}`, {
        columns_order: newOrderKeys,
      });
      groupData.columns = updated.columns;
      groupData.updated_at = updated.updated_at;
      renderAll();
    } catch (err) {
      errorEl.textContent = err.message || t("errors.unknown");
      errorEl.hidden = false;
    } finally {
      busy = false;
      renderModalColumns();
    }
  }

  async function removeColumn(colKey) {
    if (busy || groupData.columns.length <= 1) {
      return;
    }
    const confirmed = await confirmDialog({
      title: t("groups.upload.col_remove_title"),
      text: t("groups.upload.col_remove_text"),
      confirmLabel: t("groups.upload.col_remove_confirm"),
    });
    if (!confirmed) {
      return;
    }
    busy = true;
    errorEl.hidden = true;
    renderModalColumns();
    try {
      const updated = await apiDelete(`/groups/${groupId}/columns/${colKey}`);
      groupData = updated;
      if (!searchQuery.trim()) {
        displayedStudents = [...groupData.students];
      } else {
        await runSearch(searchQuery);
      }
      renderAll();
      showToast(t("groups.columns_modal.removed_toast"));
    } catch (err) {
      errorEl.textContent = err.message || t("errors.unknown");
      errorEl.hidden = false;
    } finally {
      busy = false;
      renderModalColumns();
    }
  }

  function renderModalColumns() {
    listEl.replaceChildren();
    const isLast = groupData.columns.length <= 1;
    hintEl.hidden = !isLast;

    groupData.columns.forEach((col, idx) => {
      const li = document.createElement("li");
      li.className = "column-item";

      const titleSpan = document.createElement("span");
      titleSpan.className = "column-item__title";
      titleSpan.textContent = col.title;

      const btnGroup = document.createElement("div");
      btnGroup.className = "column-item__actions";

      const upBtn = document.createElement("button");
      upBtn.type = "button";
      upBtn.className = "btn btn--secondary btn--compact";
      upBtn.textContent = t("groups.upload.col_up");
      upBtn.disabled = busy || idx === 0;
      upBtn.addEventListener("click", () => {
        const keys = groupData.columns.map((c) => c.key);
        const tmp = keys[idx - 1];
        keys[idx - 1] = keys[idx];
        keys[idx] = tmp;
        reorderColumns(keys);
      });

      const downBtn = document.createElement("button");
      downBtn.type = "button";
      downBtn.className = "btn btn--secondary btn--compact";
      downBtn.textContent = t("groups.upload.col_down");
      downBtn.disabled = busy || idx === groupData.columns.length - 1;
      downBtn.addEventListener("click", () => {
        const keys = groupData.columns.map((c) => c.key);
        const tmp = keys[idx + 1];
        keys[idx + 1] = keys[idx];
        keys[idx] = tmp;
        reorderColumns(keys);
      });

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "btn btn--danger btn--compact";
      removeBtn.textContent = t("groups.upload.col_remove");
      removeBtn.disabled = busy || isLast;
      if (isLast) {
        removeBtn.title = t("groups.columns_modal.last_col_hint");
      }
      removeBtn.addEventListener("click", () => {
        removeColumn(col.key);
      });

      btnGroup.append(upBtn, downBtn, removeBtn);
      li.append(titleSpan, btnGroup);
      listEl.append(li);
    });
  }

  renderModalColumns();

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      dialog.close();
    }
  });

  dialog.addEventListener("close", () => {
    dialog.remove();
  });

  document.body.append(dialog);
  dialog.showModal();
  closeBtn.focus();
}

for (const btn of addStudentBtns) {
  btn.addEventListener("click", () => {
    openAddStudentModal();
  });
}

if (columnsBtn) {
  columnsBtn.addEventListener("click", () => {
    openColumnsModal();
  });
}

if (searchInput) {
  searchInput.addEventListener("input", () => {
    searchQuery = searchInput.value;
    if (searchClearBtn) {
      searchClearBtn.hidden = searchQuery.length === 0;
    }
    if (searchTimer) {
      window.clearTimeout(searchTimer);
    }
    searchTimer = window.setTimeout(() => {
      runSearch(searchQuery);
    }, SEARCH_DEBOUNCE_MS);
  });
}

if (searchClearBtn && searchInput) {
  searchClearBtn.addEventListener("click", () => {
    if (searchTimer) {
      window.clearTimeout(searchTimer);
    }
    searchQuery = "";
    searchInput.value = "";
    searchClearBtn.hidden = true;
    displayedStudents = groupData ? [...groupData.students] : [];
    renderAll();
    searchInput.focus();
  });
}

async function init() {
  if (!groupId) {
    return;
  }
  try {
    groupData = await apiGet(`/groups/${groupId}`);
    displayedStudents = [...groupData.students];
    renderAll();
  } catch (err) {
    showToast(err.message || t("errors.unknown"), "error");
  }
}

init();
