import json
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[2] / "app" / "locales"
PLURAL_SUFFIXES = (".one", ".few", ".many", ".other")


def _load(lang: str) -> dict[str, str]:
    return json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def _normalize_plural_keys(keys: set[str]) -> set[str]:
    normalized: set[str] = set()
    for key in keys:
        matched = False
        for suffix in PLURAL_SUFFIXES:
            if key.endswith(suffix):
                normalized.add(f"{key[: -len(suffix)]}.*")
                matched = True
                break
        if not matched:
            normalized.add(key)
    return normalized


def test_locales_have_same_keys() -> None:
    ru_raw = set(_load("ru"))
    tg_raw = set(_load("tg"))
    ru = _normalize_plural_keys(ru_raw)
    tg = _normalize_plural_keys(tg_raw)
    assert ru - tg == set(), f"keys missing in tg.json: {ru - tg}"
    assert tg - ru == set(), f"keys missing in ru.json: {tg - ru}"
