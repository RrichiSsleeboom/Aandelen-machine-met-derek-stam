import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import ccxt
import pandas as pd
import pandas_ta as ta
import yfinance as yf

from src.analysis.news_checker import check_news
from src.data.universe import get_nasdaq100_tickers, get_sp500_tickers, get_top_crypto_pairs

# Limit concurrent Yahoo Finance calls to avoid rate limits
_YF_SEMAPHORE = threading.Semaphore(10)
# Limit concurrent Google News RSS calls
_NEWS_SEMAPHORE = threading.Semaphore(5)


@dataclass
class SentinelSignal:
    symbol: str
    asset_type: str          # "stock" or "crypto"
    price: float
    confidence_score: int    # 1-10
    reasons: list[str] = field(default_factory=list)
    golden_cross: bool = False
    rsi_bounce: bool = False
    momentum_pct: float = 0.0
    volume_ratio: float = 0.0
    news_match: bool = False
    news_title: str | None = None


class MarketScanner:
    def __init__(self, max_workers: int = 20):
        self._max_workers = max_workers
        self._exchange = ccxt.binance({"enableRateLimit": True})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_all(self) -> list[SentinelSignal]:
        stock_tickers = list(set(get_sp500_tickers() + get_nasdaq100_tickers()))
        crypto_pairs = get_top_crypto_pairs(limit=500)

        print(f"[SCANNER] {len(stock_tickers)} aandelen + {len(crypto_pairs)} crypto pairs")

        futures = {}
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            for sym in stock_tickers:
                f = executor.submit(self._scan_stock, sym)
                futures[f] = sym
            for sym in crypto_pairs:
                f = executor.submit(self._scan_crypto, sym)
                futures[f] = sym

        signals = []
        for f in as_completed(futures):
            result = f.result()
            if result is not None:
                signals.append(result)

        signals.sort(key=lambda s: s.confidence_score, reverse=True)
        print(f"[SCANNER] {len(signals)} signalen gevonden")
        return signals

    # ------------------------------------------------------------------
    # Per-ticker scan logic
    # ------------------------------------------------------------------

    def _scan_stock(self, symbol: str) -> SentinelSignal | None:
        try:
            with _YF_SEMAPHORE:
                df_daily = self._fetch_stock_daily(symbol)
            if df_daily is None or len(df_daily) < 210:
                return None

            with _YF_SEMAPHORE:
                df_hourly = self._fetch_stock_hourly(symbol)

            price = float(df_daily["close"].iloc[-1])

            golden = self._check_golden_cross(df_daily)
            rsi_ok = self._check_rsi_bounce(df_daily)
            momentum = self._calc_momentum(df_hourly) if df_hourly is not None else 0.0
            volume_ok, vol_ratio = self._check_volume_spike(df_daily)

            score = self._base_score(golden, rsi_ok, momentum, volume_ok)
            if score == 0:
                return None

            news_hit, news_title = False, None
            if score >= 5:
                with _NEWS_SEMAPHORE:
                    news_hit, news_title = check_news(symbol, "stock")

            score += (2 if news_hit else 0)
            reasons = self._build_reasons(golden, rsi_ok, momentum, vol_ratio, news_hit, news_title, df_daily)

            return SentinelSignal(
                symbol=symbol,
                asset_type="stock",
                price=price,
                confidence_score=min(score, 10),
                reasons=reasons,
                golden_cross=golden,
                rsi_bounce=rsi_ok,
                momentum_pct=round(momentum, 2),
                volume_ratio=round(vol_ratio, 2),
                news_match=news_hit,
                news_title=news_title,
            )
        except Exception:
            return None

    def _scan_crypto(self, symbol: str) -> SentinelSignal | None:
        try:
            df_daily = self._fetch_crypto_daily(symbol)
            if df_daily is None or len(df_daily) < 210:
                return None

            price = float(df_daily["close"].iloc[-1])

            golden = self._check_golden_cross(df_daily)
            rsi_ok = self._check_rsi_bounce(df_daily)
            momentum = self._fetch_crypto_momentum(symbol)
            volume_ok, vol_ratio = self._check_volume_spike(df_daily)

            score = self._base_score(golden, rsi_ok, momentum, volume_ok)
            if score == 0:
                return None

            news_hit, news_title = False, None
            if score >= 5:
                with _NEWS_SEMAPHORE:
                    news_hit, news_title = check_news(symbol, "crypto")

            score += (2 if news_hit else 0)
            reasons = self._build_reasons(golden, rsi_ok, momentum, vol_ratio, news_hit, news_title, df_daily)

            return SentinelSignal(
                symbol=symbol,
                asset_type="crypto",
                price=price,
                confidence_score=min(score, 10),
                reasons=reasons,
                golden_cross=golden,
                rsi_bounce=rsi_ok,
                momentum_pct=round(momentum, 2),
                volume_ratio=round(vol_ratio, 2),
                news_match=news_hit,
                news_title=news_title,
            )
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def _fetch_stock_daily(self, symbol: str) -> pd.DataFrame | None:
        try:
            df = yf.download(symbol, period="1y", interval="1d", progress=False, auto_adjust=True)
            if df.empty or len(df) < 50:
                return None
            df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]].dropna()
            return df
        except Exception:
            return None

    def _fetch_stock_hourly(self, symbol: str) -> pd.DataFrame | None:
        try:
            df = yf.download(symbol, period="1d", interval="1h", progress=False, auto_adjust=True)
            if df.empty or len(df) < 2:
                return None
            df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]].dropna()
            return df
        except Exception:
            return None

    def _fetch_crypto_daily(self, symbol: str) -> pd.DataFrame | None:
        try:
            ohlcv = self._exchange.fetch_ohlcv(symbol, "1d", limit=300)
            if not ohlcv or len(ohlcv) < 50:
                return None
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df.drop(columns=["timestamp"], inplace=True)
            return df
        except Exception:
            return None

    def _fetch_crypto_momentum(self, symbol: str) -> float:
        try:
            ohlcv = self._exchange.fetch_ohlcv(symbol, "1h", limit=2)
            if not ohlcv or len(ohlcv) < 2:
                return 0.0
            prev_close = ohlcv[-2][4]
            last_close = ohlcv[-1][4]
            if prev_close == 0:
                return 0.0
            return (last_close - prev_close) / prev_close * 100
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # Indicator checks
    # ------------------------------------------------------------------

    def _check_golden_cross(self, df: pd.DataFrame) -> bool:
        if len(df) < 210:
            return False
        close = df["close"]
        ema50 = ta.ema(close, length=50)
        ema200 = ta.ema(close, length=200)
        if ema50 is None or ema200 is None:
            return False
        ema50 = ema50.dropna()
        ema200 = ema200.dropna()
        if len(ema50) < 2 or len(ema200) < 2:
            return False
        # Align by index
        common = ema50.index.intersection(ema200.index)
        if len(common) < 2:
            return False
        e50 = ema50.loc[common]
        e200 = ema200.loc[common]
        # Golden Cross: EMA50 crossed above EMA200 in the last 3 bars
        for i in range(-3, 0):
            if e50.iloc[i - 1] < e200.iloc[i - 1] and e50.iloc[i] > e200.iloc[i]:
                return True
        return False

    def _check_rsi_bounce(self, df: pd.DataFrame) -> bool:
        rsi = ta.rsi(df["close"], length=14)
        if rsi is None:
            return False
        rsi = rsi.dropna()
        if len(rsi) < 5:
            return False
        recent = rsi.iloc[-5:]
        return float(recent.min()) < 30 and float(rsi.iloc[-1]) > float(rsi.iloc[-3])

    def _check_volume_spike(self, df: pd.DataFrame) -> tuple[bool, float]:
        if len(df) < 22:
            return False, 0.0
        avg_vol = float(df["volume"].iloc[-21:-1].mean())
        curr_vol = float(df["volume"].iloc[-1])
        if avg_vol == 0:
            return False, 0.0
        ratio = curr_vol / avg_vol
        return ratio >= 2.0, ratio

    def _calc_momentum(self, df_hourly: pd.DataFrame) -> float:
        if df_hourly is None or len(df_hourly) < 2:
            return 0.0
        prev = float(df_hourly["close"].iloc[-2])
        last = float(df_hourly["close"].iloc[-1])
        if prev == 0:
            return 0.0
        return (last - prev) / prev * 100

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _base_score(self, golden: bool, rsi_ok: bool, momentum: float, volume_ok: bool) -> int:
        score = 0
        if golden:
            score += 3
        if rsi_ok:
            score += 2
        if momentum >= 3.0:
            score += 2
        if volume_ok:
            score += 1
        return score

    def _build_reasons(
        self,
        golden: bool,
        rsi_ok: bool,
        momentum: float,
        vol_ratio: float,
        news_hit: bool,
        news_title: str | None,
        df: pd.DataFrame,
    ) -> list[str]:
        reasons = []
        if golden:
            reasons.append("Golden Cross (EMA50 kruiste boven EMA200)")
        if rsi_ok:
            rsi = ta.rsi(df["close"], length=14)
            low = float(rsi.dropna().iloc[-5:].min()) if rsi is not None else 0
            reasons.append(f"RSI hersteld van oversold ({low:.1f})")
        if momentum >= 3.0:
            reasons.append(f"Momentum +{momentum:.1f}% laatste uur")
        if vol_ratio >= 2.0:
            reasons.append(f"Volume spike {vol_ratio:.1f}× daggemiddelde")
        if news_hit and news_title:
            reasons.append(f"Bullish nieuws: \"{news_title[:80]}\"")
        elif news_hit:
            reasons.append("Bullish nieuws gedetecteerd")
        return reasons
