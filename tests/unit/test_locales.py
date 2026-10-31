import json
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[2] / "app" / "locales"


def _load(lang: str) -> dict[str, str]:
    return json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def test_locales_have_same_keys() -> None:
    ru = set(_load("ru"))
    tg = set(_load("tg"))
    assert ru - tg == set(), "keys missing in tg.json"
    assert tg - ru == set(), "keys missing in ru.json"
