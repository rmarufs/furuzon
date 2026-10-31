import { hasKey, t } from "./i18n.js";

const API_PREFIX = "/api";
const LOGIN_PATH = "/login";

export class ApiError extends Error {
  constructor(status, code, details = {}) {
    super(hasKey(`errors.${code}`) ? t(`errors.${code}`) : t("errors.unknown"));
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function readError(response) {
  try {
    const data = await response.json();
    return new ApiError(response.status, data.error.code, data.error.details);
  } catch {
    return new ApiError(response.status, "unknown");
  }
}

export async function api(path, { method = "GET", body, headers = {} } = {}) {
  const options = { method, headers: { ...headers }, credentials: "same-origin" };
  if (body instanceof FormData) {
    options.body = body;
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, options);
  } catch {
    throw new ApiError(0, "network_error");
  }

  if (response.status === 401) {
    window.location.assign(LOGIN_PATH);
    throw new ApiError(401, "unauthorized");
  }
  if (!response.ok) {
    throw await readError(response);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

export const apiGet = (path) => api(path);
export const apiPost = (path, body) => api(path, { method: "POST", body });
export const apiPut = (path, body) => api(path, { method: "PUT", body });
export const apiPatch = (path, body) => api(path, { method: "PATCH", body });
export const apiDelete = (path) => api(path, { method: "DELETE" });
