import { apiPost } from "../core/api.js";
import { t } from "../core/i18n.js";
import { confirmDialog } from "../core/modal.js";
import { showToast } from "../core/toast.js";

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXTENSIONS = [".xlsx", ".xls"];

const dropzone = document.querySelector("[data-dropzone]");
const fileInput = document.querySelector("[data-file-input]");
const selectedFileEl = document.querySelector("[data-selected-file]");
const parseErrorEl = document.querySelector("[data-parse-error]");

const previewSection = document.querySelector("[data-preview-section]");
const previewTbody = document.querySelector("[data-preview-tbody]");
const rowsCountBadge = document.querySelector("[data-rows-count]");

const columnsSection = document.querySelector("[data-columns-section]");
const columnsList = document.querySelector("[data-columns-list]");

const detailsSection = document.querySelector("[data-details-section]");
const saveForm = document.querySelector("[data-save-group-form]");
const numberInput = document.querySelector("[data-number-input]");
const courseRadios = document.querySelectorAll("[data-course-radio]");
const saveErrorEl = document.querySelector("[data-save-error]");
const saveSubmitBtn = document.querySelector("[data-save-submit]");

let currentFile = null;
let currentHeaderRow = 0;
let previewRows = [];
let activeColumns = []; // Array of { index: number, title: string }
let isParsing = false;
let isSaving = false;

function showParseError(message) {
  if (!parseErrorEl) {
    return;
  }
  parseErrorEl.textContent = message;
  parseErrorEl.hidden = false;
}

function clearParseError() {
  if (!parseErrorEl) {
    return;
  }
  parseErrorEl.textContent = "";
  parseErrorEl.hidden = true;
}

function showSaveError(message) {
  if (!saveErrorEl) {
    return;
  }
  saveErrorEl.textContent = message;
  saveErrorEl.hidden = false;
}

function clearSaveError() {
  if (!saveErrorEl) {
    return;
  }
  saveErrorEl.textContent = "";
  saveErrorEl.hidden = true;
}

function getSelectedCourse() {
  for (const radio of courseRadios) {
    if (radio.checked) {
      return Number(radio.value);
    }
  }
  return null;
}

function syncSubmitState() {
  if (!saveSubmitBtn) {
    return;
  }
  const hasFile = Boolean(currentFile);
  const hasColumns = activeColumns.length >= 1;
  const hasNumber = Boolean(numberInput && numberInput.value.trim().length >= 1);
  const hasCourse = getSelectedCourse() !== null;
  saveSubmitBtn.disabled =
    isParsing || isSaving || !(hasFile && hasColumns && hasNumber && hasCourse);
}

function validateFileClientSide(file) {
  const name = (file.name || "").toLowerCase();
  const hasValidExt = ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext));
  if (!hasValidExt) {
    showParseError(t("errors.invalid_file_type"));
    return false;
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    showParseError(t("errors.file_too_large"));
    return false;
  }
  return true;
}

function renderPreviewTable() {
  if (!previewTbody) {
    return;
  }
  previewTbody.replaceChildren();

  previewRows.forEach((rowCells, rowIdx) => {
    const tr = document.createElement("tr");
    tr.className = "preview-row";
    if (rowIdx < currentHeaderRow) {
      tr.classList.add("preview-row--above");
    } else if (rowIdx === currentHeaderRow) {
      tr.classList.add("preview-row--header");
    }

    const numTd = document.createElement("td");
    numTd.className = "preview-row__num";
    numTd.textContent = String(rowIdx + 1);
    if (rowIdx === currentHeaderRow) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = t("groups.upload.header_badge");
      numTd.append(" ", badge);
    }
    tr.append(numTd);

    for (const cellVal of rowCells) {
      const td = document.createElement("td");
      td.textContent = cellVal;
      tr.append(td);
    }

    tr.addEventListener("click", () => {
      if (!isParsing && rowIdx !== currentHeaderRow) {
        parseFile(currentFile, rowIdx);
      }
    });

    previewTbody.append(tr);
  });
}

function renderColumnsList() {
  if (!columnsList) {
    return;
  }
  columnsList.replaceChildren();

  activeColumns.forEach((col, pos) => {
    const li = document.createElement("li");
    li.className = "column-item";

    const titleSpan = document.createElement("span");
    titleSpan.className = "column-item__title";
    titleSpan.textContent = col.title;

    const actions = document.createElement("div");
    actions.className = "column-item__actions";

    const upBtn = document.createElement("button");
    upBtn.type = "button";
    upBtn.className = "btn btn--secondary btn--compact";
    upBtn.textContent = t("groups.upload.col_up");
    upBtn.disabled = pos === 0;
    upBtn.addEventListener("click", () => {
      if (pos > 0) {
        const temp = activeColumns[pos - 1];
        activeColumns[pos - 1] = activeColumns[pos];
        activeColumns[pos] = temp;
        renderColumnsList();
      }
    });

    const downBtn = document.createElement("button");
    downBtn.type = "button";
    downBtn.className = "btn btn--secondary btn--compact";
    downBtn.textContent = t("groups.upload.col_down");
    downBtn.disabled = pos === activeColumns.length - 1;
    downBtn.addEventListener("click", () => {
      if (pos < activeColumns.length - 1) {
        const temp = activeColumns[pos + 1];
        activeColumns[pos + 1] = activeColumns[pos];
        activeColumns[pos] = temp;
        renderColumnsList();
      }
    });

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn--danger btn--compact";
    removeBtn.textContent = t("groups.upload.col_remove");
    removeBtn.disabled = activeColumns.length <= 1;
    removeBtn.addEventListener("click", async () => {
      if (activeColumns.length <= 1) {
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
      activeColumns.splice(pos, 1);
      renderColumnsList();
      syncSubmitState();
    });

    actions.append(upBtn, downBtn, removeBtn);
    li.append(titleSpan, actions);
    columnsList.append(li);
  });
}

async function parseFile(file, headerRowOverride = null) {
  clearParseError();
  clearSaveError();
  isParsing = true;
  syncSubmitState();

  const formData = new FormData();
  formData.append("file", file);
  if (headerRowOverride !== null) {
    formData.append("header_row", String(headerRowOverride));
  }

  try {
    const data = await apiPost("/groups/parse", formData);
    currentFile = file;
    currentHeaderRow = data.header_row;
    previewRows = data.rows || [];
    activeColumns = (data.columns || []).map((c) => ({
      index: c.index,
      title: c.title,
    }));

    if (selectedFileEl) {
      selectedFileEl.textContent = t("groups.upload.selected_file", {
        name: file.name,
      });
      selectedFileEl.hidden = false;
    }

    if (rowsCountBadge) {
      rowsCountBadge.textContent = t("groups.upload.data_rows", {
        n: data.data_rows_count,
      });
    }

    renderPreviewTable();
    renderColumnsList();

    if (previewSection) {
      previewSection.hidden = false;
    }
    if (columnsSection) {
      columnsSection.hidden = false;
    }
    if (detailsSection) {
      detailsSection.hidden = false;
    }
  } catch (err) {
    showParseError(err.message || t("errors.unknown"));
    if (headerRowOverride === null) {
      currentFile = null;
      if (previewSection) {
        previewSection.hidden = true;
      }
      if (columnsSection) {
        columnsSection.hidden = true;
      }
      if (detailsSection) {
        detailsSection.hidden = true;
      }
    }
  } finally {
    isParsing = false;
    syncSubmitState();
  }
}

function handleSelectedFile(file) {
  if (!file) {
    return;
  }
  clearParseError();
  if (!validateFileClientSide(file)) {
    return;
  }
  parseFile(file, null);
}

if (fileInput) {
  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    if (file) {
      handleSelectedFile(file);
    }
  });
}

if (dropzone) {
  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("is-dragover");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("is-dragover");
  });

  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-dragover");
    const file =
      event.dataTransfer &&
      event.dataTransfer.files &&
      event.dataTransfer.files[0];
    if (file) {
      handleSelectedFile(file);
    }
  });
}

if (numberInput) {
  numberInput.addEventListener("input", () => {
    clearSaveError();
    syncSubmitState();
  });
}

for (const radio of courseRadios) {
  radio.addEventListener("change", () => {
    clearSaveError();
    syncSubmitState();
  });
}

if (saveForm) {
  saveForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearSaveError();

    const course = getSelectedCourse();
    const number = numberInput ? numberInput.value.trim() : "";
    if (!currentFile || !number || course === null || activeColumns.length === 0) {
      return;
    }

    isSaving = true;
    if (saveSubmitBtn) {
      saveSubmitBtn.disabled = true;
      saveSubmitBtn.classList.add("is-loading");
    }

    const formData = new FormData();
    formData.append("file", currentFile);
    formData.append("header_row", String(currentHeaderRow));
    formData.append(
      "columns",
      JSON.stringify(activeColumns.map((c) => c.index)),
    );
    formData.append("number", number);
    formData.append("course", String(course));

    try {
      await apiPost("/groups", formData);
      showToast(t("groups.upload.created_toast"));
      window.location.assign(`/groups?course=${course}`);
    } catch (err) {
      showSaveError(err.message || t("errors.unknown"));
    } finally {
      isSaving = false;
      if (saveSubmitBtn) {
        saveSubmitBtn.classList.remove("is-loading");
      }
      syncSubmitState();
    }
  });
}
