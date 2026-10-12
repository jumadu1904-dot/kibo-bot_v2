"""Google News RSS, by topic and language — no API key needed (see
docs/ARCHITECTURE.md). Parsed by hand with stdlib `xml.etree` rather than
pulling in a feed-parsing library just for <title>/<link>, to stay
consistent with the rest of the clients (thin httpx wrappers, no SDKs —
see clients/gemini.py)."""

from dataclasses import dataclass
from xml.etree import ElementTree

import httpx

BASE_URL = "https://news.google.com/rss"

# Google News' own topic feeds; "general" has no topic segment — it's the
# front-page feed at BASE_URL itself.
_TOPIC_PATHS = {
    "general": "",
    "tech": "/headlines/section/topic/TECHNOLOGY",
    "business": "/headlines/section/topic/BUSINESS",
    "science": "/headlines/section/topic/SCIENCE",
    "health": "/headlines/section/topic/HEALTH",
    "sports": "/headlines/section/topic/SPORTS",
}

# hl/gl/ceid per bot language — Google News needs a country edition, not
# just a language, to decide which feed to serve.
_EDITIONS = {
    "en": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "es": {"hl": "es-ES", "gl": "ES", "ceid": "ES:es"},
    "ca": {"hl": "ca", "gl": "ES", "ceid": "ES:ca"},
}


@dataclass
class Headline:
    title: str
    link: str


async def top_headlines(topic: str, lang: str, *, limit: int = 3) -> list[Headline]:
    """The `limit` most recent headlines for `topic` in `lang`'s edition."""
    path = _TOPIC_PATHS.get(topic, "")
    params = _EDITIONS.get(lang, _EDITIONS["en"])
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{BASE_URL}{path}", params=params)
        response.raise_for_status()
    root = ElementTree.fromstring(response.text)
    items = root.findall("./channel/item")[:limit]
    return [
        Headline(title=item.findtext("title") or "", link=item.findtext("link") or "")
        for item in items
    ]
