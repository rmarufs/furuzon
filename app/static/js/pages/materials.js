import { api, apiDelete, apiGet } from "../core/api.js";
import { t, tp } from "../core/i18n.js";
import { confirmDialog } from "../core/modal.js";
import { showToast } from "../core/toast.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXTENSIONS = [".pdf", ".doc", ".docx"];

const form = document.querySelector("[data-upload-form]");
const fileInput = document.querySelector("[data-file-input]");
const fileNameEl = document.querySelector("[data-file-name]");
const courseRadios = document.querySelectorAll("[data-course-radio]");
const groupChecksEl = document.querySelector("[data-group-checks]");
const groupsPlaceholderEl = document.querySelector("[data-groups-placeholder]");
const uploadErrorEl = document.querySelector("[data-upload-error]");
const submitBtn = document.querySelector("[data-upload-submit]");
const treeEl = document.querySelector("[data-tree]");

let tree = { courses: [] };
let selectedCourse = null;
const selectedGroupIds = new Set();
const openKeys = new Set();

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
  return `${day}.${month}.${date.getFullYear()}`;
}

function formatSize(bytes) {
  if (bytes < 1024) {
    return t("materials.size.b", { n: bytes });
  }
  if (bytes < 1024 * 1024) {
    return t("materials.size.kb", { n: Math.round(bytes / 1024) });
  }
  const mb = Math.round((bytes / (1024 * 1024)) * 10) / 10;
  return t("materials.size.mb", { n: mb });
}

function validateFile(file) {
  if (!file) {
    return t("materials.error.no_file");
  }
  const lowerName = file.name.toLowerCase();
  if (!ALLOWED_EXTENSIONS.some((ext) => lowerName.endsWith(ext))) {
    return t("errors.invalid_material_type");
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return t("errors.file_too_large");
  }
  return null;
}

function showUploadError(message) {
  uploadErrorEl.textContent = message;
  uploadErrorEl.hidden = false;
}

function clearUploadError() {
  uploadErrorEl.textContent = "";
  uploadErrorEl.hidden = true;
}

function groupsOfCourse(course) {
  const node = tree.courses.find((c) => c.course === course);
  return node ? node.groups : [];
}

/* ---------- Upload form ---------- */

function renderGroupChecks() {
  groupChecksEl.replaceChildren();

  if (selectedCourse === null) {
    groupsPlaceholderEl.textContent = t("materials.upload.pick_course");
    groupsPlaceholderEl.hidden = false;
    return;
  }

  const groups = groupsOfCourse(selectedCourse);
  if (groups.length === 0) {
    groupsPlaceholderEl.textContent = t("materials.upload.no_groups_course");
    groupsPlaceholderEl.hidden = false;
    return;
  }
  groupsPlaceholderEl.hidden = true;

  for (const group of groups) {
    const label = document.createElement("label");
    label.className = "check";

    const box = document.createElement("span");
    box.className = "check__box";

    const input = document.createElement("input");
    input.className = "check__input";
    input.type = "checkbox";
    input.value = String(group.id);
    input.checked = selectedGroupIds.has(group.id);
    input.addEventListener("change", () => {
      if (input.checked) {
        selectedGroupIds.add(group.id);
      } else {
        selectedGroupIds.delete(group.id);
      }
      clearUploadError();
    });

    box.append(input, buildIcon("check", "icon--sm check__mark"));

    const text = document.createElement("span");
    text.className = "check__text";
    text.textContent = group.number;

    label.append(box, text);
    groupChecksEl.append(label);
  }
}

function resetForm() {
  fileInput.value = "";
  fileNameEl.textContent = t("materials.upload.no_file");
  selectedCourse = null;
  selectedGroupIds.clear();
  for (const radio of courseRadios) {
    radio.checked = false;
  }
  renderGroupChecks();
  clearUploadError();
}

function setSubmitting(isSubmitting) {
  submitBtn.disabled = isSubmitting;
  submitBtn.classList.toggle("is-loading", isSubmitting);
}

async function handleUpload(event) {
  event.preventDefault();
  clearUploadError();

  const file = fileInput.files[0];
  const fileError = validateFile(file);
  if (fileError) {
    showUploadError(fileError);
    return;
  }
  if (selectedCourse === null) {
    showUploadError(t("materials.error.no_course"));
    return;
  }
  if (selectedGroupIds.size === 0) {
    showUploadError(t("materials.error.no_groups"));
    return;
  }

  const body = new FormData();
  body.append("file", file);
  body.append("course", String(selectedCourse));
  for (const groupId of selectedGroupIds) {
    body.append("group_ids", String(groupId));
  }

  const uploadedCourse = selectedCourse;
  const uploadedGroupIds = [...selectedGroupIds];

  setSubmitting(true);
  try {
    await api("/materials", { method: "POST", body });
  } catch (err) {
    showUploadError(err.message || t("errors.unknown"));
    setSubmitting(false);
    return;
  }

  openKeys.add(`course-${uploadedCourse}`);
  for (const groupId of uploadedGroupIds) {
    openKeys.add(`group-${groupId}`);
  }
  resetForm();
  setSubmitting(false);
  showToast(t("materials.upload.success"));
  await reloadTree();
}

/* ---------- Dialogs ---------- */

function buildDialog(titleId) {
  const dialog = document.createElement("dialog");
  dialog.className = "modal";
  dialog.setAttribute("aria-labelledby", titleId);
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      dialog.close("cancel");
    }
  });
  return dialog;
}

function openQrModal(file, { title } = {}) {
  return new Promise((resolve) => {
    const dialog = buildDialog("qr-modal-title");

    const body = document.createElement("div");
    body.className = "modal__body";

    const heading = document.createElement("h2");
    heading.id = "qr-modal-title";
    heading.textContent = title ?? t("materials.qr.title");

    const fileName = document.createElement("p");
    fileName.className = "text-muted file-name";
    fileName.textContent = file.original_name;

    const qrBox = document.createElement("div");
    qrBox.className = "qr-box";
    const img = document.createElement("img");
    img.className = "qr-box__img";
    img.src = `/api/materials/${file.id}/qr.svg?v=${encodeURIComponent(file.public_token)}`;
    img.alt = t("materials.qr.alt", { name: file.original_name });
    qrBox.append(img);

    const field = document.createElement("div");
    field.className = "field";
    const label = document.createElement("label");
    label.className = "field__label";
    label.htmlFor = "qr-public-link";
    label.textContent = t("materials.qr.link_label");
    const linkInput = document.createElement("input");
    linkInput.className = "input";
    linkInput.id = "qr-public-link";
    linkInput.type = "text";
    linkInput.readOnly = true;
    linkInput.value = file.public_url;
    linkInput.addEventListener("focus", () => linkInput.select());
    field.append(label, linkInput);

    body.append(heading, fileName, qrBox, field);

    const actions = document.createElement("div");
    actions.className = "modal__actions";

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "btn btn--secondary";
    closeBtn.textContent = t("common.close");
    closeBtn.addEventListener("click", () => dialog.close("cancel"));

    const downloadLink = document.createElement("a");
    downloadLink.className = "btn btn--secondary";
    downloadLink.href = `/api/materials/${file.id}/qr.svg?v=${encodeURIComponent(file.public_token)}`;
    downloadLink.download = `qr-${file.id}.svg`;
    downloadLink.append(buildIcon("qr"));
    const downloadText = document.createElement("span");
    downloadText.textContent = t("materials.qr.download");
    downloadLink.append(downloadText);

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "btn btn--primary";
    copyBtn.textContent = t("materials.qr.copy");
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(file.public_url);
        showToast(t("materials.qr.copied"));
      } catch {
        linkInput.focus();
        linkInput.select();
        showToast(t("materials.qr.copy_failed"), "error");
      }
    });

    // Phones show actions in reverse order, so the main action goes last in the DOM.
    actions.append(closeBtn, downloadLink, copyBtn);
    dialog.append(body, actions);

    dialog.addEventListener("close", () => {
      dialog.remove();
      resolve();
    });

    document.body.append(dialog);
    dialog.showModal();
    copyBtn.focus();
  });
}

function openReplaceModal(file) {
  return new Promise((resolve) => {
    const dialog = buildDialog("replace-modal-title");

    const formEl = document.createElement("form");
    formEl.noValidate = true;

    const body = document.createElement("div");
    body.className = "modal__body";

    const heading = document.createElement("h2");
    heading.id = "replace-modal-title";
    heading.textContent = t("materials.replace.title");

    const fileName = document.createElement("p");
    fileName.className = "text-muted file-name";
    fileName.textContent = file.original_name;

    const warning = document.createElement("p");
    warning.className = "notice notice--warning";
    warning.append(buildIcon("alert"));
    const warningText = document.createElement("span");
    warningText.textContent = t("materials.replace.warning");
    warning.append(warningText);

    const picker = document.createElement("div");
    picker.className = "file-picker";
    const input = document.createElement("input");
    input.className = "visually-hidden";
    input.id = "replace-file-input";
    input.type = "file";
    input.accept = ".pdf,.doc,.docx";
    const chooseLabel = document.createElement("label");
    chooseLabel.className = "btn btn--secondary";
    chooseLabel.htmlFor = "replace-file-input";
    const chooseText = document.createElement("span");
    chooseText.textContent = t("materials.replace.choose_file");
    chooseLabel.append(buildIcon("plus"), chooseText);
    const pickedName = document.createElement("span");
    pickedName.className = "file-picker__name text-muted";
    pickedName.textContent = t("materials.upload.no_file");
    picker.append(input, chooseLabel, pickedName);

    const errorEl = document.createElement("p");
    errorEl.className = "field__error";
    errorEl.setAttribute("role", "alert");
    errorEl.hidden = true;

    body.append(heading, fileName, warning, picker, errorEl);

    const actions = document.createElement("div");
    actions.className = "modal__actions";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn btn--secondary";
    cancelBtn.textContent = t("common.cancel");
    cancelBtn.addEventListener("click", () => dialog.close("cancel"));

    const confirmBtn = document.createElement("button");
    confirmBtn.type = "submit";
    confirmBtn.className = "btn btn--primary";
    confirmBtn.textContent = t("materials.replace.confirm");

    actions.append(cancelBtn, confirmBtn);
    formEl.append(body, actions);
    dialog.append(formEl);

    input.addEventListener("change", () => {
      errorEl.hidden = true;
      const picked = input.files[0];
      pickedName.textContent = picked ? picked.name : t("materials.upload.no_file");
    });

    formEl.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorEl.hidden = true;

      const picked = input.files[0];
      const fileError = validateFile(picked);
      if (fileError) {
        errorEl.textContent = fileError;
        errorEl.hidden = false;
        return;
      }

      const payload = new FormData();
      payload.append("file", picked);

      confirmBtn.disabled = true;
      confirmBtn.classList.add("is-loading");
      try {
        const updated = await api(`/materials/${file.id}/file`, {
          method: "PUT",
          body: payload,
        });
        dialog.close("saved");
        resolve(updated);
      } catch (err) {
        errorEl.textContent = err.message || t("errors.unknown");
        errorEl.hidden = false;
      } finally {
        confirmBtn.disabled = false;
        confirmBtn.classList.remove("is-loading");
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
    cancelBtn.focus();
  });
}

/* ---------- File actions ---------- */

async function handleReplace(file) {
  const updated = await openReplaceModal(file);
  if (!updated) {
    return;
  }
  showToast(t("materials.replace.success"));
  await reloadTree();
  await openQrModal(updated, { title: t("materials.replace.new_qr_title") });
}

async function handleRemoveFromGroup(file, group) {
  const isLast = file.group_ids.length <= 1;
  const confirmed = await confirmDialog({
    title: t("materials.remove.title"),
    text: isLast
      ? t("materials.remove.text_last", { name: file.original_name })
      : t("materials.remove.text", { name: file.original_name, group: group.number }),
    confirmLabel: isLast ? t("common.confirm_delete") : t("materials.remove.confirm"),
  });
  if (!confirmed) {
    return;
  }
  try {
    await apiDelete(`/materials/${file.id}/groups/${group.id}`);
  } catch (err) {
    showToast(err.message || t("errors.unknown"), "error");
    return;
  }
  showToast(t(isLast ? "materials.delete.success" : "materials.remove.success"));
  await reloadTree();
}

async function handleDelete(file) {
  const confirmed = await confirmDialog({
    title: t("materials.delete.title"),
    text: t("materials.delete.text", { name: file.original_name }),
  });
  if (!confirmed) {
    return;
  }
  try {
    await apiDelete(`/materials/${file.id}`);
  } catch (err) {
    showToast(err.message || t("errors.unknown"), "error");
    return;
  }
  showToast(t("materials.delete.success"));
  await reloadTree();
}

/* ---------- Tree ---------- */

function buildMenuItem({ iconName, label, danger = false, onClick }) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = danger ? "menu__item menu__item--danger" : "menu__item";
  btn.dataset.menuClose = "";
  const text = document.createElement("span");
  text.textContent = label;
  btn.append(buildIcon(iconName), text);
  btn.addEventListener("click", onClick);
  return btn;
}

function buildFileRow(file, group) {
  const row = document.createElement("li");
  row.className = "file-row";

  const iconBox = document.createElement("span");
  iconBox.className = "file-row__icon";
  const isPdf = file.original_name.toLowerCase().endsWith(".pdf");
  iconBox.append(buildIcon(isPdf ? "file-pdf" : "file-doc"));

  const info = document.createElement("div");
  info.className = "file-row__info";
  const name = document.createElement("span");
  name.className = "file-row__name";
  name.textContent = file.original_name;
  const meta = document.createElement("span");
  meta.className = "file-row__meta";
  meta.textContent = `${formatSize(file.size_bytes)} · ${t("materials.file.uploaded", {
    date: formatDate(file.updated_at),
  })}`;
  info.append(name, meta);

  const actions = document.createElement("div");
  actions.className = "file-row__actions";

  const qrBtn = document.createElement("button");
  qrBtn.type = "button";
  qrBtn.className = "btn btn--secondary btn--compact";
  qrBtn.setAttribute("aria-label", t("materials.file.qr_aria", { name: file.original_name }));
  const qrText = document.createElement("span");
  qrText.textContent = t("common.qr");
  qrBtn.append(buildIcon("qr"), qrText);
  qrBtn.addEventListener("click", () => openQrModal(file));

  const menuWrap = document.createElement("div");
  menuWrap.className = "menu-wrap";

  const menuId = `file-menu-${group.id}-${file.id}`;
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

  const separator = document.createElement("hr");
  separator.className = "menu__separator";

  menu.append(
    buildMenuItem({
      iconName: "edit",
      label: t("materials.menu.replace"),
      onClick: () => handleReplace(file),
    }),
    buildMenuItem({
      iconName: "close",
      label: t("materials.menu.remove_from_group"),
      onClick: () => handleRemoveFromGroup(file, group),
    }),
    separator,
    buildMenuItem({
      iconName: "trash",
      label: t("materials.menu.delete"),
      danger: true,
      onClick: () => handleDelete(file),
    }),
  );

  menuWrap.append(toggleBtn, menu);
  actions.append(qrBtn, menuWrap);
  row.append(iconBox, info, actions);
  return row;
}

function buildSummary(titleText, countText) {
  const summary = document.createElement("summary");
  summary.className = "tree-summary";
  const chevron = buildIcon("chevron-down", "tree-summary__chevron");
  const title = document.createElement("span");
  title.className = "tree-summary__title";
  title.textContent = titleText;
  const count = document.createElement("span");
  count.className = "badge tree-summary__count";
  count.textContent = countText;
  summary.append(chevron, title, count);
  return summary;
}

function buildNode(key, className, summary) {
  const details = document.createElement("details");
  details.className = className;
  details.open = openKeys.has(key);
  details.addEventListener("toggle", () => {
    if (details.open) {
      openKeys.add(key);
    } else {
      openKeys.delete(key);
    }
  });
  details.append(summary);
  return details;
}

function buildEmpty(text) {
  const p = document.createElement("p");
  p.className = "text-muted tree-empty";
  p.textContent = text;
  return p;
}

function buildGroupNode(group) {
  const node = buildNode(
    `group-${group.id}`,
    "tree-node tree-group",
    buildSummary(group.number, tp("materials.files_count", group.files.length)),
  );

  if (group.files.length === 0) {
    node.append(buildEmpty(t("materials.tree.empty_group")));
    return node;
  }

  const list = document.createElement("ul");
  list.className = "file-list";
  for (const file of group.files) {
    list.append(buildFileRow(file, group));
  }
  node.append(list);
  return node;
}

function renderTree() {
  treeEl.replaceChildren();
  for (const courseNode of tree.courses) {
    const node = buildNode(
      `course-${courseNode.course}`,
      "tree-node card tree-course",
      buildSummary(
        t("materials.tree.course", { n: courseNode.course }),
        tp("materials.groups_count", courseNode.groups.length),
      ),
    );

    if (courseNode.groups.length === 0) {
      node.append(buildEmpty(t("materials.tree.empty_course")));
    } else {
      const inner = document.createElement("div");
      inner.className = "tree-course__groups";
      for (const group of courseNode.groups) {
        inner.append(buildGroupNode(group));
      }
      node.append(inner);
    }
    treeEl.append(node);
  }
}

async function reloadTree() {
  try {
    tree = await apiGet("/materials/tree");
  } catch (err) {
    showToast(err.message || t("errors.unknown"), "error");
    return;
  }
  renderTree();
  renderGroupChecks();
}

/* ---------- Init ---------- */

function bindForm() {
  fileInput.addEventListener("change", () => {
    clearUploadError();
    const file = fileInput.files[0];
    if (!file) {
      fileNameEl.textContent = t("materials.upload.no_file");
      return;
    }
    fileNameEl.textContent = file.name;
    const error = validateFile(file);
    if (error) {
      showUploadError(error);
    }
  });

  for (const radio of courseRadios) {
    radio.addEventListener("change", () => {
      if (!radio.checked) {
        return;
      }
      selectedCourse = Number(radio.value);
      selectedGroupIds.clear();
      clearUploadError();
      renderGroupChecks();
    });
  }

  form.addEventListener("submit", handleUpload);
}

async function init() {
  bindForm();
  try {
    tree = await apiGet("/materials/tree");
  } catch (err) {
    showToast(err.message || t("errors.unknown"), "error");
    return;
  }
  for (const courseNode of tree.courses) {
    for (const group of courseNode.groups) {
      if (group.files.length > 0) {
        openKeys.add(`course-${courseNode.course}`);
        openKeys.add(`group-${group.id}`);
      }
    }
  }
  renderTree();
  renderGroupChecks();
}

init();
