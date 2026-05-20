"""
Technische indicatoren voor koop-signaal analyse.

Elke indicator-functie neemt een pandas DataFrame (met kolommen: close, volume, ...)
en geeft True/False terug: True = bullish/koop-signaal aanwezig.

Geïmplementeerd in pure pandas — geen externe TA-bibliotheek nodig (pandas-ta
ondersteunt geen Python 3.11+ meer).
"""

import pandas as pd


def rsi_series(close: pd.Series, length: int = 14) -> pd.Series:
    """RSI (Wilder's smoothing) — standaard implementatie."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing == EMA met alpha = 1/length
    avg_gain = gain.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def macd_series(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Geeft (macd_line, signal_line, histogram)."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger_bands(close: pd.Series, length: int = 20, std_mult: float = 2.0):
    """Geeft (lower_band, middle_band, upper_band)."""
    middle = close.rolling(length).mean()
    std = close.rolling(length).std()
    lower = middle - std_mult * std
    upper = middle + std_mult * std
    return lower, middle, upper


def check_rsi(df: pd.DataFrame, oversold_threshold: float = 35) -> bool:
    """
    RSI Oversold conditie. True als de meest recente RSI(14) onder de drempel valt.
    RSI < 35 = oversold, terugvering waarschijnlijk.
    """
    if len(df) < 15:
        return False
    rsi = rsi_series(df["close"], length=14).dropna()
    if rsi.empty:
        return False
    return float(rsi.iloc[-1]) < oversold_threshold


def check_macd_crossover(df: pd.DataFrame) -> bool:
    """
    MACD Bullish Crossover op de laatste twee candles.
    Kentering bearish → bullish momentum.
    """
    if len(df) < 35:
        return False
    macd_line, signal_line, _ = macd_series(df["close"])
    macd_line = macd_line.dropna()
    signal_line = signal_line.dropna()
    if len(macd_line) < 2 or len(signal_line) < 2:
        return False
    return (float(macd_line.iloc[-2]) < float(signal_line.iloc[-2])
            and float(macd_line.iloc[-1]) > float(signal_line.iloc[-1]))


def check_ema_crossover(df: pd.DataFrame) -> bool:
    """
    EMA9 / EMA21 Bullish Crossover (korte-termijn Golden Cross).
    """
    if len(df) < 22:
        return False
    ema9 = df["close"].ewm(span=9, adjust=False).mean()
    ema21 = df["close"].ewm(span=21, adjust=False).mean()
    if len(ema9) < 2 or len(ema21) < 2:
        return False
    prev_diff = float(ema9.iloc[-2]) - float(ema21.iloc[-2])
    curr_diff = float(ema9.iloc[-1]) - float(ema21.iloc[-1])
    return (prev_diff < 0) and (curr_diff > 0)


def check_bollinger_bands(df: pd.DataFrame) -> bool:
    """
    Bollinger Bands Oversold: slotkoers op of onder de onderste band.
    """
    if len(df) < 21:
        return False
    lower, _, _ = bollinger_bands(df["close"], length=20, std_mult=2.0)
    lower = lower.dropna()
    if lower.empty:
        return False
    latest_close = float(df["close"].dropna().iloc[-1])
    latest_lower = float(lower.iloc[-1])
    return latest_close <= latest_lower


def check_volume_spike(df: pd.DataFrame, multiplier: float = 1.5, avg_period: int = 20) -> bool:
    """
    Volume Spike bevestiging — huidig volume > multiplier × gemiddeld volume.
    """
    if "volume" not in df.columns or len(df) < avg_period + 1:
        return False
    volume = df["volume"].dropna()
    if len(volume) < avg_period + 1:
        return False
    avg_vol = float(volume.iloc[-(avg_period + 1):-1].mean())
    curr_vol = float(volume.iloc[-1])
    if avg_vol <= 0:
        return False
    return curr_vol >= (avg_vol * multiplier)
