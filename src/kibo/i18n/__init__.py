import json
from functools import lru_cache
from pathlib import Path

DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "es", "ca")
_DIR = Path(__file__).parent


@lru_cache
def _load(lang: str) -> dict[str, str]:
    return json.loads((_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def t(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    """Translate `key`, falling back to English and then to the key itself."""
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    text = _load(lang).get(key) or _load(DEFAULT_LANG).get(key) or key
    return text.format(**kwargs) if kwargs else text
