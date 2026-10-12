import httpx

from kibo.clients.google_news import Headline
from kibo.services import news


async def test_headlines_for_topics_flattens_in_order(monkeypatch):
    async def fake_top_headlines(topic, lang, *, limit):
        return [Headline(title=f"{topic}-1", link=""), Headline(title=f"{topic}-2", link="")]

    monkeypatch.setattr(news.google_news, "top_headlines", fake_top_headlines)
    titles = await news.headlines_for_topics(["tech", "sports"], "en")
    assert titles == ["tech-1", "tech-2", "sports-1", "sports-2"]


async def test_headlines_for_topics_skips_topic_that_fails(monkeypatch):
    async def fake_top_headlines(topic, lang, *, limit):
        if topic == "tech":
            raise httpx.ConnectError("boom")
        return [Headline(title=f"{topic}-1", link="")]

    monkeypatch.setattr(news.google_news, "top_headlines", fake_top_headlines)
    titles = await news.headlines_for_topics(["tech", "sports"], "en")
    assert titles == ["sports-1"]
