"""
Technische indicatoren voor koop-signaal analyse.

Elke indicator-functie neemt een pandas DataFrame (met kolommen: close, volume, ...)
en geeft True/False terug: True = bullish/koop-signaal aanwezig.
"""

import pandas as pd
import pandas_ta as ta


def check_rsi(df: pd.DataFrame, oversold_threshold: float = 35) -> bool:
    """
    RSI (Relative Strength Index) - Oversold conditie.
    True als de meest recente RSI(14) onder de drempel valt.
    Logica: RSI < 35 betekent dat het asset oversold is en een terugvering waarschijnlijk is.
    """
    if len(df) < 15:
        return False

    rsi = ta.rsi(df["close"], length=14)
    if rsi is None or rsi.empty:
        return False

    latest = rsi.dropna().iloc[-1]
    return float(latest) < oversold_threshold


def check_macd_crossover(df: pd.DataFrame) -> bool:
    """
    MACD Bullish Crossover.
    True als de MACD lijn de signaallijn van onder naar boven kruist (op de laatste twee candles).
    Logica: Een MACD crossover signaleert een kentering van bearish naar bullish momentum.
    """
    if len(df) < 35:
        return False

    macd_data = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd_data is None or macd_data.empty:
        return False

    macd_col = [c for c in macd_data.columns if "MACD_" in c and "s" not in c.lower() and "h" not in c.lower()]
    signal_col = [c for c in macd_data.columns if "MACDs_" in c]

    if not macd_col or not signal_col:
        return False

    macd_line = macd_data[macd_col[0]].dropna()
    signal_line = macd_data[signal_col[0]].dropna()

    if len(macd_line) < 2 or len(signal_line) < 2:
        return False

    # Crossover: vorige candle MACD < signaal, huidige candle MACD > signaal
    prev_macd = float(macd_line.iloc[-2])
    curr_macd = float(macd_line.iloc[-1])
    prev_signal = float(signal_line.iloc[-2])
    curr_signal = float(signal_line.iloc[-1])

    return (prev_macd < prev_signal) and (curr_macd > curr_signal)


def check_ema_crossover(df: pd.DataFrame) -> bool:
    """
    EMA9 / EMA21 Bullish Crossover (korte-termijn Golden Cross).
    True als EMA9 de EMA21 van onder naar boven kruist op de laatste twee candles.
    Logica: Snelle EMA kruist trage EMA omhoog = momentum verschuift naar bullish.
    """
    if len(df) < 22:
        return False

    ema9 = ta.ema(df["close"], length=9)
    ema21 = ta.ema(df["close"], length=21)

    if ema9 is None or ema21 is None or len(ema9.dropna()) < 2 or len(ema21.dropna()) < 2:
        return False

    ema9 = ema9.dropna()
    ema21 = ema21.dropna()

    prev_diff = float(ema9.iloc[-2]) - float(ema21.iloc[-2])
    curr_diff = float(ema9.iloc[-1]) - float(ema21.iloc[-1])

    return (prev_diff < 0) and (curr_diff > 0)


def check_bollinger_bands(df: pd.DataFrame) -> bool:
    """
    Bollinger Bands Oversold.
    True als de slotkoers de onderste Bollinger Band raakt of eronder ligt.
    Logica: Prijs op/onder de onderste BB = statistisch oversold, kans op terugvering.
    """
    if len(df) < 21:
        return False

    bb = ta.bbands(df["close"], length=20, std=2.0)
    if bb is None or bb.empty:
        return False

    lower_col = [c for c in bb.columns if "BBL_" in c]
    if not lower_col:
        return False

    lower_band = bb[lower_col[0]].dropna()
    if lower_band.empty:
        return False

    close_series = df["close"].dropna()
    latest_close = float(close_series.iloc[-1])
    latest_lower = float(lower_band.iloc[-1])

    return latest_close <= latest_lower


def check_volume_spike(df: pd.DataFrame, multiplier: float = 1.5, avg_period: int = 20) -> bool:
    """
    Volume Spike bevestiging.
    True als het huidige volume meer dan `multiplier` keer het gemiddelde volume is.
    Logica: Hoog volume bij een potentieel koop-signaal = meer marktdeelnemers stappen in = hogere betrouwbaarheid.
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
