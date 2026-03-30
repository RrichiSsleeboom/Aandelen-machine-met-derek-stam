#!/usr/bin/env python3
"""
AI Koop-Signaal Machine - Aandelen & Crypto Monitor
====================================================

Gebruik:
  python main.py --scan       Eenmalige scan van alle assets, toont signalen
  python main.py --service    Realtime monitoring (elke minuut), stuurt email bij signaal
  python main.py --backtest   Test de strategie op historische data (win-rate validatie)

Setup:
  1. pip install -r requirements.txt
  2. cp .env.example .env   en vul je Gmail gegevens in
  3. python main.py --service
"""

import argparse
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict

import yaml
from dotenv import load_dotenv

load_dotenv()

from src.data import crypto_fetcher, stock_fetcher
from src.analysis import signals
from src.notifications import email_notifier
from src.backtest import engine as backtest_engine


def load_config(path: str = "config/settings.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def scan_all(config: dict, verbose: bool = True) -> list:
    """
    Scan alle geconfigureerde assets en geef een lijst van Signal objecten terug.
    """
    cfg_signals = config.get("signals", {})
    min_indicators = cfg_signals.get("min_indicators_required", 3)
    rsi_oversold = cfg_signals.get("rsi_oversold", 35)
    volume_mult = cfg_signals.get("volume_multiplier", 1.5)
    volume_period = cfg_signals.get("volume_avg_period", 20)

    results = []

    # --- Crypto ---
    for coin in config.get("crypto", []):
        coin_id = coin["id"]
        symbol = coin["symbol"]
        try:
            if verbose:
                print(f"  Scannen: {symbol} (crypto)...", end=" ", flush=True)
            df = crypto_fetcher.get_ohlcv(coin_id, days=365)
            price = crypto_fetcher.get_current_price(coin_id)
            sig = signals.analyse(
                df=df,
                current_price=price,
                asset=symbol,
                asset_type="crypto",
                min_indicators_required=min_indicators,
                rsi_oversold=rsi_oversold,
                volume_multiplier=volume_mult,
                volume_avg_period=volume_period,
            )
            results.append(sig)
            if verbose:
                status = "🟢 KOOP" if sig.is_buy else "⚪ geen"
                print(f"{status} | Confidence: {sig.confidence:.0f}%")
        except Exception as e:
            if verbose:
                print(f"FOUT: {e}")

    # --- Aandelen ---
    for stock in config.get("stocks", []):
        symbol = stock["symbol"]
        try:
            if verbose:
                print(f"  Scannen: {symbol} (aandeel)...", end=" ", flush=True)
            df = stock_fetcher.get_ohlcv(symbol, period="1y")
            price = stock_fetcher.get_current_price(symbol)
            sig = signals.analyse(
                df=df,
                current_price=price,
                asset=symbol,
                asset_type="stock",
                min_indicators_required=min_indicators,
                rsi_oversold=rsi_oversold,
                volume_multiplier=volume_mult,
                volume_avg_period=volume_period,
            )
            results.append(sig)
            if verbose:
                status = "🟢 KOOP" if sig.is_buy else "⚪ geen"
                print(f"{status} | Confidence: {sig.confidence:.0f}%")
        except Exception as e:
            if verbose:
                print(f"FOUT: {e}")

    return results


def run_scan(config: dict) -> None:
    """Eenmalige scan met output."""
    print("\n" + "=" * 60)
    print(f"AI Koop-Signaal Machine — Scan op {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
    print("=" * 60)

    results = scan_all(config)

    buy_signals = [s for s in results if s.is_buy]

    print(f"\n{'=' * 60}")
    if buy_signals:
        print(f"🚨 {len(buy_signals)} KOOP SIGNAAL(EN) GEVONDEN:")
        print("-" * 60)
        for sig in buy_signals:
            print(str(sig))
    else:
        print("Geen koop-signalen op dit moment.")
    print("=" * 60 + "\n")


def run_service(config: dict) -> None:
    """
    Realtime service: scant elke N seconden en stuurt email bij nieuw signaal.
    Deduplicatie: geen tweede email voor hetzelfde asset binnen cooldown_hours.
    """
    interval = config.get("service", {}).get("scan_interval_seconds", 60)
    cooldown_hours = config.get("service", {}).get("signal_cooldown_hours", 4)

    # Dict: asset -> tijdstip laatste email signaal
    last_notified: Dict[str, datetime] = {}

    # Graceful shutdown
    running = {"active": True}

    def _shutdown(signum, frame):
        print("\n\nAfsluiten... (Ctrl+C ontvangen)")
        running["active"] = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    print(f"\n{'=' * 60}")
    print("AI Koop-Signaal Machine — SERVICE MODUS")
    print(f"Scan interval: {interval} seconden")
    print(f"Cooldown: {cooldown_hours} uur per asset")
    print("Druk op Ctrl+C om te stoppen.")
    print("=" * 60)

    scan_count = 0
    while running["active"]:
        scan_count += 1
        now = datetime.now()
        print(f"\n[{now.strftime('%H:%M:%S')}] Scan #{scan_count} gestart...")

        try:
            results = scan_all(config, verbose=False)
        except Exception as e:
            print(f"  Scan fout: {e}")
            results = []

        buy_signals = [s for s in results if s.is_buy]

        if buy_signals:
            for sig in buy_signals:
                last = last_notified.get(sig.asset)
                cooldown_expired = (last is None) or (now - last > timedelta(hours=cooldown_hours))

                if cooldown_expired:
                    print(f"  🚨 KOOP SIGNAAL: {sig.asset} | Confidence: {sig.confidence:.0f}% | Prijs: ${sig.current_price:,.4f}")
                    sent = email_notifier.send_buy_signal(sig)
                    if sent:
                        last_notified[sig.asset] = now
                else:
                    remaining = cooldown_hours - (now - last).total_seconds() / 3600
                    print(f"  ℹ️  {sig.asset}: signaal actief maar cooldown ({remaining:.1f}u resterend)")
        else:
            total = len(results)
            print(f"  Geen koop-signalen ({total} assets gescand)")

        if running["active"]:
            print(f"  Volgende scan over {interval} seconden...")
            time.sleep(interval)

    print("Service gestopt.")


def run_backtest(config: dict) -> None:
    """Backtest de strategie op historische data en toon win-rates."""
    cfg_signals = config.get("signals", {})
    cfg_bt = config.get("backtest", {})

    min_indicators = cfg_signals.get("min_indicators_required", 3)
    rsi_oversold = cfg_signals.get("rsi_oversold", 35)
    volume_mult = cfg_signals.get("volume_multiplier", 1.5)
    volume_period = cfg_signals.get("volume_avg_period", 20)
    min_gain = cfg_bt.get("min_gain_percent", 2.0)
    forward_days = cfg_bt.get("forward_days", 5)
    lookback_years = cfg_bt.get("lookback_years", 1)

    days = int(lookback_years * 365)
    period = f"{lookback_years}y"

    print(f"\n{'=' * 60}")
    print("BACKTEST — Historische win-rate validatie")
    print(f"Lookback: {lookback_years} jaar | Min stijging: {min_gain}% | Forward: {forward_days} dagen")
    print("=" * 60)

    results = []

    for coin in config.get("crypto", []):
        symbol = coin["symbol"]
        coin_id = coin["id"]
        print(f"  Backtesting {symbol}...", end=" ", flush=True)
        try:
            df = crypto_fetcher.get_ohlcv(coin_id, days=days)
            result = backtest_engine.run_backtest(
                df=df,
                asset=symbol,
                min_indicators_required=min_indicators,
                rsi_oversold=rsi_oversold,
                volume_multiplier=volume_mult,
                volume_avg_period=volume_period,
                min_gain_percent=min_gain,
                forward_days=forward_days,
            )
            results.append(result)
            print(f"klaar ({result.total_signals} signalen)")
        except Exception as e:
            print(f"FOUT: {e}")

    for stock in config.get("stocks", []):
        symbol = stock["symbol"]
        print(f"  Backtesting {symbol}...", end=" ", flush=True)
        try:
            df = stock_fetcher.get_ohlcv(symbol, period=period)
            result = backtest_engine.run_backtest(
                df=df,
                asset=symbol,
                min_indicators_required=min_indicators,
                rsi_oversold=rsi_oversold,
                volume_multiplier=volume_mult,
                volume_avg_period=volume_period,
                min_gain_percent=min_gain,
                forward_days=forward_days,
            )
            results.append(result)
            print(f"klaar ({result.total_signals} signalen)")
        except Exception as e:
            print(f"FOUT: {e}")

    backtest_engine.print_backtest_summary(results)


def main():
    parser = argparse.ArgumentParser(
        description="AI Koop-Signaal Machine — Crypto & Aandelen Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Voorbeelden:
  python main.py --scan       Eenmalige scan
  python main.py --service    Start realtime monitoring
  python main.py --backtest   Valideer win-rate op historische data
        """,
    )
    parser.add_argument("--scan", action="store_true", help="Eenmalige scan van alle assets")
    parser.add_argument("--service", action="store_true", help="Start realtime monitoring service")
    parser.add_argument("--backtest", action="store_true", help="Backtest strategie op historische data")
    parser.add_argument("--config", default="config/settings.yaml", help="Pad naar configuratiebestand")

    args = parser.parse_args()

    if not (args.scan or args.service or args.backtest):
        parser.print_help()
        print("\nGebruik --scan, --service, of --backtest")
        sys.exit(1)

    config = load_config(args.config)

    if args.scan:
        run_scan(config)
    elif args.service:
        run_service(config)
    elif args.backtest:
        run_backtest(config)


if __name__ == "__main__":
    main()
