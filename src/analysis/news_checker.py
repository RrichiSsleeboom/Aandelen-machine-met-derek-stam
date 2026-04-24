from datetime import datetime, timedelta, timezone

import feedparser
import requests

KEYWORDS = [
    "merger",
    "earnings beat",
    "partnership",
    "acquisition",
    "revenue beat",
    "buyout",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def check_news(symbol: str, asset_type: str = "stock") -> tuple[bool, str | None]:
    """Return (matched, first_matching_title) for bullish news in the last 24h."""
    if asset_type == "crypto":
        query = symbol.replace("/USDT", "").replace("/", "")
        query = f"{query} crypto"
    else:
        query = f"{symbol} stock"

    url = (
        f"https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}&hl=en&gl=US&ceid=US:en"
    )

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=8)
        if resp.status_code != 200:
            return False, None
        feed = feedparser.parse(resp.text)
    except Exception:
        return False, None

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)

    for entry in feed.entries:
        published = entry.get("published_parsed")
        if published:
            pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue

        title = entry.get("title", "").lower()
        summary = entry.get("summary", "").lower()
        text = title + " " + summary

        for kw in KEYWORDS:
            if kw in text:
                return True, entry.get("title", "")

    return False, None
