import httpx

from kibo.clients import google_news

_RealAsyncClient = httpx.AsyncClient

_FEED_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>First headline</title><link>https://example.com/1</link></item>
<item><title>Second headline</title><link>https://example.com/2</link></item>
<item><title>Third headline</title><link>https://example.com/3</link></item>
</channel></rss>"""


def _patch_client(monkeypatch, handler) -> None:
    monkeypatch.setattr(
        google_news.httpx,
        "AsyncClient",
        lambda **kwargs: _RealAsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_top_headlines_parses_items_and_respects_limit(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "news.google.com/rss/headlines/section/topic/TECHNOLOGY" in str(request.url)
        assert request.url.params["hl"] == "en-US"
        return httpx.Response(200, text=_FEED_XML)

    _patch_client(monkeypatch, handler)
    headlines = await google_news.top_headlines("tech", "en", limit=2)
    assert [h.title for h in headlines] == ["First headline", "Second headline"]
    assert headlines[0].link == "https://example.com/1"


async def test_top_headlines_general_topic_has_no_section_path(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://news.google.com/rss?")
        return httpx.Response(200, text=_FEED_XML)

    _patch_client(monkeypatch, handler)
    await google_news.top_headlines("general", "ca", limit=1)
