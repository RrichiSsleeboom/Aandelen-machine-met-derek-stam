"""
Backtest engine: test de koop-signaal strategie op historische data.

Methode:
- Simuleer de signaallogica op elk punt in de historische data
- Controleer of de prijs >= min_gain_percent steeg binnen forward_days na het signaal
- Bereken de win-rate per asset en overall

Een win-rate > 50% valideert dat de strategie beter presteert dan willekeurig raden.
"""

from dataclasses import dataclass
from typing import List
import pandas as pd

from src.analysis import indicators as ind


@dataclass
class BacktestResult:
    asset: str
    total_signals: int
    wins: int
    losses: int
    win_rate: float
    avg_gain_pct: float

    def __str__(self) -> str:
        return (
            f"{self.asset:10s} | Signalen: {self.total_signals:3d} | "
            f"Wins: {self.wins:3d} | Losses: {self.losses:3d} | "
            f"Win-rate: {self.win_rate:5.1f}% | Gem. winst: {self.avg_gain_pct:+.2f}%"
        )


def run_backtest(
    df: pd.DataFrame,
    asset: str,
    min_indicators_required: int = 3,
    rsi_oversold: float = 35,
    volume_multiplier: float = 1.5,
    volume_avg_period: int = 20,
    min_gain_percent: float = 2.0,
    forward_days: int = 5,
    min_history: int = 50,
) -> BacktestResult:
    """
    Voer een backtest uit op historische OHLCV data.

    Args:
        df: DataFrame met kolommen open, high, low, close, volume (gesorteerd op datum)
        asset: Naam van het asset
        min_indicators_required: Minimaal aantal positieve indicatoren
        rsi_oversold: RSI drempel
        volume_multiplier: Volume spike multiplier
        volume_avg_period: Periode voor volume gemiddelde
        min_gain_percent: Minimale stijging (%) om als win te tellen
        forward_days: Aantal dagen vooruit om te controleren
        min_history: Minimum aantal rijen nodig voordat we gaan scannen
    """
    wins = 0
    losses = 0
    gains: List[float] = []

    n = len(df)
    # Scan elk punt in de data (met genoeg history, en genoeg toekomst om te evalueren)
    for i in range(min_history, n - forward_days):
        window = df.iloc[:i + 1].copy()

        checks = [
            ind.check_rsi(window, oversold_threshold=rsi_oversold),
            ind.check_macd_crossover(window),
            ind.check_ema_crossover(window),
            ind.check_bollinger_bands(window),
            ind.check_volume_spike(window, multiplier=volume_multiplier, avg_period=volume_avg_period),
        ]

        num_positive = sum(checks)
        if num_positive < min_indicators_required:
            continue

        # Evalueer het resultaat: max prijs in de volgende forward_days
        entry_price = float(df["close"].iloc[i])
        future_prices = df["close"].iloc[i + 1: i + 1 + forward_days]
        max_future_price = float(future_prices.max())

        gain_pct = ((max_future_price - entry_price) / entry_price) * 100
        gains.append(gain_pct)

        if gain_pct >= min_gain_percent:
            wins += 1
        else:
            losses += 1

    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0
    avg_gain = (sum(gains) / len(gains)) if gains else 0.0

    return BacktestResult(
        asset=asset,
        total_signals=total,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        avg_gain_pct=avg_gain,
    )


def print_backtest_summary(results: List[BacktestResult]) -> None:
    """Print een overzichtstabel van alle backtest resultaten."""
    print("\n" + "=" * 75)
    print("BACKTEST RESULTATEN")
    print("=" * 75)
    print(f"{'Asset':10s} | {'Signalen':8s} | {'Wins':5s} | {'Losses':6s} | {'Win-rate':8s} | {'Gem. winst'}")
    print("-" * 75)

    total_signals = 0
    total_wins = 0

    for r in results:
        print(str(r))
        total_signals += r.total_signals
        total_wins += r.wins

    overall_rate = (total_wins / total_signals * 100) if total_signals > 0 else 0.0
    print("=" * 75)
    print(f"{'TOTAAL':10s} | Signalen: {total_signals:3d} | Wins: {total_wins:3d} | "
          f"Overall win-rate: {overall_rate:.1f}%")
    print("=" * 75)

    if overall_rate > 50:
        print(f"✅ Strategie haalt {overall_rate:.1f}% win-rate (doel: >50%)")
    else:
        print(f"⚠️  Win-rate is {overall_rate:.1f}% - overweeg drempelwaarden aan te passen in settings.yaml")
    print()
