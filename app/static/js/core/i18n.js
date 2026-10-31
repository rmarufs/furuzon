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

export function tp(key, n, params = {}) {
  const lang = getLang();
  const merged = { ...params, n };
  if (lang === "tg") {
    const otherKey = `${key}.other`;
    return t(hasKey(otherKey) ? otherKey : key, merged);
  }

  let rule = "other";
  try {
    rule = new Intl.PluralRules(lang).select(n);
  } catch {
    rule = "other";
  }

  const ruleKey = `${key}.${rule}`;
  if (hasKey(ruleKey)) {
    return t(ruleKey, merged);
  }
  const otherKey = `${key}.other`;
  if (hasKey(otherKey)) {
    return t(otherKey, merged);
  }
  return t(key, merged);
}

export async function setLang(lang) {
  document.cookie = `lang=${lang}; path=/; max-age=31536000; SameSite=Lax`;
  if (document.documentElement.dataset.authenticated === "true") {
    try {
      await fetch("/api/me/preferences", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ language: lang }),
      });
    } catch {
      // Cookie is already set; reload anyway.
    }
  }
  window.location.reload();
}
