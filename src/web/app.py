"""
Web dashboard voor de AI Koop-Signaal Machine.
Start met: python main.py --dashboard
Open in je browser: http://localhost:5000
"""

import threading
import time
from dataclasses import asdict
from datetime import datetime

import yaml
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Gedeelde staat tussen de achtergrond-scan en de webserver
_state = {
    "last_scan": None,
    "signals": [],
    "scanning": False,
    "error": None,
}
_state_lock = threading.Lock()


def _load_config():
    with open("config/settings.yaml", "r") as f:
        return yaml.safe_load(f)


def _run_scan_loop():
    """Draait in een achtergrondthread: scant elke N seconden."""
    from main import scan_all  # importeer hier om circulaire imports te vermijden

    config = _load_config()
    interval = config.get("service", {}).get("scan_interval_seconds", 60)

    while True:
        with _state_lock:
            _state["scanning"] = True
            _state["error"] = None

        try:
            results = scan_all(config, verbose=False)
            signals_data = []
            for sig in results:
                signals_data.append({
                    "asset": sig.asset,
                    "asset_type": sig.asset_type,
                    "price": sig.current_price,
                    "confidence": sig.confidence,
                    "is_buy": sig.is_buy,
                    "active_indicators": sig.active_indicators,
                    "all_indicators": [
                        "RSI Oversold",
                        "MACD Crossover",
                        "EMA Crossover",
                        "Bollinger Bands",
                        "Volume Spike",
                    ],
                })

            with _state_lock:
                _state["signals"] = signals_data
                _state["last_scan"] = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                _state["scanning"] = False

        except Exception as e:
            with _state_lock:
                _state["error"] = str(e)
                _state["scanning"] = False

        time.sleep(interval)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze")
def analyze_page():
    return render_template("analyze.html")


@app.route("/api/status")
def api_status():
    with _state_lock:
        return jsonify({
            "last_scan": _state["last_scan"],
            "signals": _state["signals"],
            "scanning": _state["scanning"],
            "error": _state["error"],
        })


@app.route("/api/analyze")
def api_analyze():
    """Genereer een uitgebreid 5-delig analyserapport voor één aandeel."""
    symbol = (request.args.get("symbol") or "").strip().upper()
    term = (request.args.get("term") or "medium").strip().lower()
    if not symbol:
        return jsonify({"error": "Geen 'symbol' parameter opgegeven."}), 400
    if term not in ("short", "medium", "long"):
        term = "medium"

    try:
        from src.data import stock_fetcher
        from src.analysis import stock_analyzer

        df = stock_fetcher.get_ohlcv(symbol, period="2y")
        price = stock_fetcher.get_current_price(symbol)
        analysis = stock_analyzer.analyze_stock(symbol, df, price, term=term)
        return jsonify(analysis.to_dict())
    except Exception as e:
        return jsonify({"error": f"Analyse mislukt voor {symbol}: {e}"}), 500


def start_dashboard(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """Start de achtergrond-scan thread en daarna de Flask webserver."""
    scan_thread = threading.Thread(target=_run_scan_loop, daemon=True)
    scan_thread.start()

    print(f"\n{'=' * 50}")
    print("AI Koop-Signaal Machine — WEB DASHBOARD")
    print(f"Open in je browser: http://localhost:{port}")
    print("Druk op Ctrl+C om te stoppen.")
    print("=" * 50 + "\n")

    app.run(host=host, port=port, debug=debug, use_reloader=False)
