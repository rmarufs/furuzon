function readMessages() {
  const element = document.getElementById("i18n-data");
  if (!element) {
    return {};
  }
  try {
    return JSON.parse(element.textContent);
  } catch {
    return {};
  }
}

const messages = readMessages();

export function hasKey(key) {
  return Object.hasOwn(messages, key);
}

export function t(key, params = {}) {
  const text = hasKey(key) ? messages[key] : key;
  return text.replace(/\{(\w+)\}/g, (match, name) =>
    Object.hasOwn(params, name) ? String(params[name]) : match,
  );
}

export function getLang() {
  return document.documentElement.lang;
}

export function setLang(lang) {
  document.cookie = `lang=${lang}; path=/; max-age=31536000; SameSite=Lax`;
  window.location.reload();
}
