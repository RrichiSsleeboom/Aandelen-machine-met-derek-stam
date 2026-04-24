import os

import requests
from dotenv import load_dotenv

load_dotenv()

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class NotificationManager:
    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ):
        self._token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        if not self._token or not self._chat_id:
            print("[TELEGRAM] WARNING: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")

    def send_signal(
        self,
        *,
        symbol: str,
        price: float,
        score: int,
        reasons: list[str],
        asset_type: str,
        news_title: str | None = None,
    ) -> bool:
        if score <= 7:
            return False
        if not self._token or not self._chat_id:
            print(f"[TELEGRAM] Skipped (no credentials): {symbol} score={score}")
            return False

        tv_url = self._tradingview_url(symbol, asset_type)
        reasons_text = "\n".join(f"  • {r}" for r in reasons)
        if news_title:
            reasons_text += f"\n  • Nieuws: \"{news_title}\""

        message = (
            f"🚨 <b>BUY SIGNAL: {symbol}</b>\n"
            f"💰 Prijs: <code>${price:,.4f}</code>\n"
            f"📊 Confidence: <b>{score}/10</b>\n"
            f"📋 Redenen:\n{reasons_text}\n"
            f"📈 <a href=\"{tv_url}\">Open op TradingView</a>"
        )

        try:
            resp = requests.post(
                _TELEGRAM_API.format(token=self._token),
                data={
                    "chat_id": self._chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"[TELEGRAM] Melding verzonden: {symbol} ({score}/10)")
                return True
            else:
                print(f"[TELEGRAM] Fout {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"[TELEGRAM] Verzenden mislukt: {e}")
            return False

    def _tradingview_url(self, symbol: str, asset_type: str) -> str:
        if asset_type == "crypto":
            clean = symbol.replace("/", "")
            return f"https://www.tradingview.com/chart/?symbol=BINANCE:{clean}"
        else:
            return f"https://www.tradingview.com/chart/?symbol=NASDAQ:{symbol}"
