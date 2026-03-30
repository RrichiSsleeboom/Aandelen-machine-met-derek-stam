"""
Haalt historische en actuele koersdata op voor aandelen via Yahoo Finance (yfinance).
"""

import time
import yfinance as yf
import pandas as pd


_cache: dict = {}
_cache_ts: dict = {}
CACHE_TTL_SECONDS = 60


def _is_cache_valid(key: str) -> bool:
    if key not in _cache_ts:
        return False
    return (time.time() - _cache_ts[key]) < CACHE_TTL_SECONDS


def get_ohlcv(symbol: str, period: str = "1y") -> pd.DataFrame:
    """
    Haal dagelijkse OHLCV data op voor een aandeelssymbool.
    Geeft een DataFrame terug met kolommen: timestamp, open, high, low, close, volume.

    Args:
        symbol: Ticker symbool, bijv. "AAPL", "NVDA", "ASML.AS"
        period: Periode, bijv. "1y", "2y", "6mo"
    """
    cache_key = f"{symbol}_{period}"
    if _is_cache_valid(cache_key):
        return _cache[cache_key]

    try:
        ticker = yf.Ticker(symbol)
        raw = ticker.history(period=period, interval="1d", auto_adjust=True)
    except Exception as e:
        raise RuntimeError(f"Yahoo Finance ophalen mislukt voor {symbol}: {e}")

    if raw.empty:
        raise ValueError(f"Geen data ontvangen voor {symbol}. Controleer het symbool.")

    df = raw.reset_index()[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
    df = df.sort_values("timestamp").reset_index(drop=True)

    _cache[cache_key] = df
    _cache_ts[cache_key] = time.time()
    return df


def get_current_price(symbol: str) -> float:
    """Haal de actuele prijs op voor een aandeel."""
    cache_key = f"price_{symbol}"
    if _is_cache_valid(cache_key):
        return _cache[cache_key]

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        price = info.last_price
    except Exception as e:
        raise RuntimeError(f"Prijs ophalen mislukt voor {symbol}: {e}")

    if price is None or price != price:  # NaN check
        raise ValueError(f"Geen geldige prijs gevonden voor {symbol}")

    _cache[cache_key] = float(price)
    _cache_ts[cache_key] = time.time()
    return float(price)
