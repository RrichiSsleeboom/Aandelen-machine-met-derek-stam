import time

import ccxt
import pandas as pd

_cache: dict = {}
_cache_ts: dict = {}
_CACHE_TTL = 86400  # 24 hours — ticker lists don't change intra-day


def _cached(key: str, fn):
    now = time.time()
    if key in _cache and (now - _cache_ts.get(key, 0)) < _CACHE_TTL:
        return _cache[key]
    result = fn()
    _cache[key] = result
    _cache_ts[key] = now
    return result


def get_sp500_tickers() -> list[str]:
    def _fetch():
        try:
            tables = pd.read_html(
                "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                attrs={"id": "constituents"},
            )
            symbols = tables[0]["Symbol"].tolist()
            # yfinance uses "-" not "." (e.g. BRK-B not BRK.B)
            return [s.replace(".", "-") for s in symbols]
        except Exception as e:
            print(f"[UNIVERSE] S&P 500 fetch failed: {e}")
            return []

    return _cached("sp500", _fetch)


def get_nasdaq100_tickers() -> list[str]:
    def _fetch():
        try:
            tables = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")
            for table in tables:
                for c in table.columns:
                    if str(c).lower() == "ticker":
                        return table[c].dropna().tolist()
            print("[UNIVERSE] Nasdaq-100: 'Ticker' column not found in any table")
            return []
        except Exception as e:
            print(f"[UNIVERSE] Nasdaq-100 fetch failed: {e}")
            return []

    return _cached("nasdaq100", _fetch)


def get_top_crypto_pairs(limit: int = 500) -> list[str]:
    def _fetch():
        try:
            exchange = ccxt.binance({"enableRateLimit": True})
            tickers = exchange.fetch_tickers()
            usdt_pairs = [
                (sym, t.get("quoteVolume") or 0)
                for sym, t in tickers.items()
                if sym.endswith("/USDT") and (t.get("quoteVolume") or 0) > 0
            ]
            usdt_pairs.sort(key=lambda x: x[1], reverse=True)
            return [sym for sym, _ in usdt_pairs[:limit]]
        except Exception as e:
            print(f"[UNIVERSE] Binance crypto fetch failed: {e}")
            return []

    return _cached(f"crypto_{limit}", _fetch)
