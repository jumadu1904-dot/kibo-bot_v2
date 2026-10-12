"""News block for the daily briefing (see docs/ARCHITECTURE.md F4): turns
the user's chosen topics into a short list of headlines, tolerating a
single topic's feed being unreachable (that topic is skipped, not fatal
to the rest of the briefing)."""

import logging

import httpx

from kibo.clients import google_news

logger = logging.getLogger(__name__)

HEADLINES_PER_TOPIC = 2


async def headlines_for_topics(topics: list[str], lang: str) -> list[str]:
    """Up to HEADLINES_PER_TOPIC headline titles per topic, flattened into
    one list, in the order the topics were given."""
    titles: list[str] = []
    for topic in topics:
        try:
            items = await google_news.top_headlines(topic, lang, limit=HEADLINES_PER_TOPIC)
        except httpx.HTTPError:
            logger.warning("Failed to fetch news for topic %s", topic, exc_info=True)
            continue
        titles.extend(item.title for item in items)
    return titles
