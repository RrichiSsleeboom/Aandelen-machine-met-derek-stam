"""The Global Market Sentinel — 24/7 marktscanner met multi-factor scoring en Telegram alerts."""

import os
import signal
import sys
import time
from datetime import datetime, timedelta

import yaml
from dotenv import load_dotenv

load_dotenv()


def _load_config(path: str = "config/settings.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _single_symbol(symbol: str, asset_type: str, cfg: dict) -> None:
    """Debug mode: scan één ticker en print het resultaat."""
    from src.scanner.market_scanner import MarketScanner

    scanner = MarketScanner(max_workers=2)
    if asset_type == "stock":
        result = scanner._scan_stock(symbol)
    else:
        result = scanner._scan_crypto(symbol)

    if result is None:
        print(f"[SENTINEL] Geen signaal voor {symbol} (score=0 of data ontbreekt)")
        return

    print(f"\n{'='*50}")
    print(f"  {symbol} ({asset_type.upper()})")
    print(f"  Prijs:      ${result.price:,.4f}")
    print(f"  Score:      {result.confidence_score}/10")
    print(f"  Golden Cross: {'✅' if result.golden_cross else '❌'}")
    print(f"  RSI bounce:   {'✅' if result.rsi_bounce else '❌'}")
    print(f"  Momentum:     {result.momentum_pct:+.2f}%/uur")
    print(f"  Volume ratio: {result.volume_ratio:.2f}×")
    print(f"  Nieuws match: {'✅' if result.news_match else '❌'}")
    if result.news_title:
        print(f"  Nieuws titel: {result.news_title[:80]}")
    print(f"  Redenen:")
    for r in result.reasons:
        print(f"    • {r}")
    print(f"{'='*50}\n")


def main() -> None:
    cfg = _load_config()
    sentinel_cfg = cfg.get("sentinel", {})

    scan_interval = sentinel_cfg.get("scan_interval_seconds", 1800)
    threshold = sentinel_cfg.get("confidence_threshold", 7)
    max_workers = sentinel_cfg.get("max_workers", 20)
    cooldown_hours = sentinel_cfg.get("cooldown_hours", 4)
    db_path = sentinel_cfg.get("db_path", "data/sentinel.db")

    # ------------------------------------------------------------------
    # Debug mode: python sentinel.py --symbol AAPL [--crypto]
    # ------------------------------------------------------------------
    if "--symbol" in sys.argv:
        idx = sys.argv.index("--symbol")
        sym = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        if not sym:
            print("Gebruik: python sentinel.py --symbol AAPL [--crypto]")
            sys.exit(1)
        asset_type = "crypto" if "--crypto" in sys.argv else "stock"
        _single_symbol(sym, asset_type, cfg)
        return

    # ------------------------------------------------------------------
    # Normal service mode
    # ------------------------------------------------------------------
    from src.database.db_manager import SignalDB
    from src.notifications.telegram_notifier import NotificationManager
    from src.scanner.market_scanner import MarketScanner

    db = SignalDB(db_path)
    notifier = NotificationManager()
    scanner = MarketScanner(max_workers=max_workers)

    last_notified: dict[str, datetime] = {}
    running = {"active": True}

    def _shutdown(signum, frame):
        print("\n[SENTINEL] Shutdown ontvangen, stoppen...")
        running["active"] = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    scan_count = 0
    print("[SENTINEL] The Global Market Sentinel gestart")
    print(f"[SENTINEL] Scan interval: {scan_interval}s | Threshold: >{threshold} | Workers: {max_workers}")

    while running["active"]:
        scan_count += 1
        start = time.time()
        print(f"\n[SENTINEL] Scan #{scan_count} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            signals = scanner.scan_all()
        except Exception as e:
            print(f"[SENTINEL] Scan mislukt: {e}")
            signals = []

        notified_count = 0
        for sig in signals:
            # Save everything with score >= 1
            notified = False
            if sig.confidence_score > threshold:
                now = datetime.now()
                last = last_notified.get(sig.symbol)
                in_cooldown = last and (now - last) < timedelta(hours=cooldown_hours)
                if not in_cooldown:
                    sent = notifier.send_signal(
                        symbol=sig.symbol,
                        price=sig.price,
                        score=sig.confidence_score,
                        reasons=sig.reasons,
                        asset_type=sig.asset_type,
                        news_title=sig.news_title,
                    )
                    if sent:
                        last_notified[sig.symbol] = now
                        notified = True
                        notified_count += 1

            db.save(
                symbol=sig.symbol,
                asset_type=sig.asset_type,
                price=sig.price,
                confidence=sig.confidence_score,
                reasons=sig.reasons,
                golden_cross=sig.golden_cross,
                rsi_bounce=sig.rsi_bounce,
                momentum_pct=sig.momentum_pct,
                volume_ratio=sig.volume_ratio,
                news_match=sig.news_match,
                news_title=sig.news_title,
                notified=notified,
            )

        elapsed = time.time() - start
        print(f"[SENTINEL] Scan #{scan_count} klaar in {elapsed:.0f}s | "
              f"{len(signals)} signalen | {notified_count} Telegram alerts")

        if running["active"]:
            sleep_time = max(0, scan_interval - elapsed)
            print(f"[SENTINEL] Volgende scan over {sleep_time/60:.1f} minuten...")
            time.sleep(sleep_time)

    print("[SENTINEL] Gestopt.")


if __name__ == "__main__":
    main()
