"""
Email notificaties via Gmail SMTP.
Stuur een nette HTML email wanneer een koop-signaal wordt gedetecteerd.

Vereisten:
- GMAIL_USER en GMAIL_APP_PASSWORD in .env bestand
- Gmail 2-staps verificatie aan + App-wachtwoord aangemaakt
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", GMAIL_USER)


def _build_html(signal) -> str:
    indicator_rows = ""
    all_indicators = ["RSI Oversold", "MACD Crossover", "EMA Crossover", "Bollinger Bands", "Volume Spike"]
    for name in all_indicators:
        active = name in signal.active_indicators
        icon = "✅" if active else "❌"
        color = "#2ecc71" if active else "#e74c3c"
        indicator_rows += f"""
        <tr>
            <td style="padding:6px 12px; border-bottom:1px solid #eee;">{icon} {name}</td>
            <td style="padding:6px 12px; border-bottom:1px solid #eee; color:{color}; font-weight:bold;">
                {"Positief" if active else "Negatief"}
            </td>
        </tr>"""

    bar_width = int(signal.confidence)
    bar_color = "#2ecc71" if signal.confidence >= 80 else "#f39c12" if signal.confidence >= 60 else "#e74c3c"
    timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; background:#f4f6f8; margin:0; padding:20px;">
        <div style="max-width:520px; margin:0 auto; background:#fff; border-radius:10px;
                    box-shadow:0 2px 8px rgba(0,0,0,0.1); overflow:hidden;">

            <!-- Header -->
            <div style="background:#1a237e; color:white; padding:20px 24px;">
                <h2 style="margin:0; font-size:20px;">📈 Koop Signaal Gedetecteerd!</h2>
                <p style="margin:4px 0 0; opacity:0.8; font-size:13px;">{timestamp}</p>
            </div>

            <!-- Asset info -->
            <div style="padding:20px 24px; border-bottom:1px solid #eee;">
                <table style="width:100%; border-collapse:collapse;">
                    <tr>
                        <td style="color:#666; padding:4px 0;">Asset</td>
                        <td style="font-weight:bold; font-size:18px; text-align:right;">
                            {signal.asset} ({signal.asset_type.upper()})
                        </td>
                    </tr>
                    <tr>
                        <td style="color:#666; padding:4px 0;">Huidige Prijs</td>
                        <td style="font-weight:bold; font-size:18px; text-align:right; color:#1a237e;">
                            ${signal.current_price:,.4f}
                        </td>
                    </tr>
                </table>
            </div>

            <!-- Confidence -->
            <div style="padding:20px 24px; border-bottom:1px solid #eee;">
                <p style="margin:0 0 8px; color:#666; font-size:13px;">Betrouwbaarheid (Confidence)</p>
                <div style="background:#eee; border-radius:20px; height:20px; overflow:hidden;">
                    <div style="width:{bar_width}%; background:{bar_color}; height:100%; border-radius:20px;
                                display:flex; align-items:center; justify-content:center;
                                color:white; font-size:12px; font-weight:bold;">
                        {signal.confidence:.0f}%
                    </div>
                </div>
                <p style="margin:6px 0 0; font-size:12px; color:#999;">
                    {len(signal.active_indicators)} van 5 indicatoren positief
                </p>
            </div>

            <!-- Indicatoren -->
            <div style="padding:20px 24px;">
                <p style="margin:0 0 12px; font-weight:bold; color:#333;">Indicator Resultaten</p>
                <table style="width:100%; border-collapse:collapse; font-size:14px;">
                    {indicator_rows}
                </table>
            </div>

            <!-- Footer -->
            <div style="background:#f9f9f9; padding:14px 24px; text-align:center; font-size:11px; color:#999;">
                Dit is geen financieel advies. Doe altijd je eigen onderzoek (DYOR).
                <br>AI Koop-Signaal Machine
            </div>
        </div>
    </body>
    </html>
    """


def send_buy_signal(signal) -> bool:
    """
    Stuur een email met het koop-signaal.
    Geeft True terug bij succes, False bij fout.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[EMAIL] Waarschuwing: GMAIL_USER of GMAIL_APP_PASSWORD niet ingesteld in .env")
        return False

    subject = f"📈 KOOP SIGNAAL: {signal.asset} | Confidence {signal.confidence:.0f}%"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL

    plain_text = (
        f"Koop Signaal: {signal.asset} ({signal.asset_type.upper()})\n"
        f"Prijs: ${signal.current_price:,.4f}\n"
        f"Confidence: {signal.confidence:.0f}%\n"
        f"Positieve indicatoren: {', '.join(signal.active_indicators)}\n\n"
        f"Dit is geen financieel advies."
    )
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(_build_html(signal), "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
        print(f"[EMAIL] Signaal verstuurd naar {NOTIFY_EMAIL} voor {signal.asset}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("[EMAIL] Fout: Authenticatie mislukt. Controleer GMAIL_USER en GMAIL_APP_PASSWORD in .env")
        return False
    except Exception as e:
        print(f"[EMAIL] Fout bij versturen: {e}")
        return False
