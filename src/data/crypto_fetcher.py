"""
Haalt historische en actuele koersdata op voor cryptocurrencies via de CoinGecko API.
Geen API key vereist voor de gratis tier.
"""

import time
import requests
import pandas as pd


COINGECKO_BASE = "https://api.coingecko.com/api/v3"
_cache: dict = {}
_cache_ts: dict = {}
CACHE_TTL_SECONDS = 60


def _is_cache_valid(key: str) -> bool:
    if key not in _cache_ts:
        return False
    return (time.time() - _cache_ts[key]) < CACHE_TTL_SECONDS


def get_ohlcv(coin_id: str, days: int = 365) -> pd.DataFrame:
    """
    Haal OHLCV data op voor een coin.
    Geeft een DataFrame terug met kolommen: timestamp, open, high, low, close, volume.
    CoinGecko gratis tier geeft dagelijkse data terug voor days > 90.
    """
    cache_key = f"{coin_id}_{days}"
    if _is_cache_valid(cache_key):
        return _cache[cache_key]

    url = f"{COINGECKO_BASE}/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": str(days)}

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"CoinGecko OHLC ophalen mislukt voor {coin_id}: {e}")

    if not raw:
        raise ValueError(f"Geen OHLC data ontvangen voor {coin_id}")

    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Voeg volume toe via market_chart endpoint
    df["volume"] = _get_volume(coin_id, days)

    _cache[cache_key] = df
    _cache_ts[cache_key] = time.time()
    return df


def _get_volume(coin_id: str, days: int) -> pd.Series:
    """Haal volume data op via market_chart en align met OHLC tijdstempels."""
    url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": str(days), "interval": "daily"}

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return pd.Series(dtype=float)

    volumes = data.get("total_volumes", [])
    if not volumes:
        return pd.Series(dtype=float)

    vol_df = pd.DataFrame(volumes, columns=["timestamp", "volume"])
    vol_df["timestamp"] = pd.to_datetime(vol_df["timestamp"], unit="ms").dt.normalize()
    vol_df = vol_df.drop_duplicates("timestamp").set_index("timestamp")

    return vol_df["volume"]


def get_current_price(coin_id: str) -> float:
    """Haal de actuele prijs op voor een coin (in USD)."""
    cache_key = f"price_{coin_id}"
    if _is_cache_valid(cache_key):
        return _cache[cache_key]

    url = f"{COINGECKO_BASE}/simple/price"
    params = {"ids": coin_id, "vs_currencies": "usd"}

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Prijs ophalen mislukt voor {coin_id}: {e}")

    price = data.get(coin_id, {}).get("usd")
    if price is None:
        raise ValueError(f"Geen prijs gevonden voor {coin_id}")

    _cache[cache_key] = price
    _cache_ts[cache_key] = time.time()
    return price
