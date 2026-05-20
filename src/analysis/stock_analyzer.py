"""
Uitgebreide aandelen-analyse machine.

Produceert een 5-delig gestructureerd rapport per aandeel:
  1. Huidige status   - winst, omzet, sterke punten vs. concurrenten
  2. Kansrijke signalen - trends, technische signalen
  3. Risico's          - macro-economisch, concurrentie, schuld
  4. De voorspelling   - 3 scenario's (bull/base/bear) met koersdoelen
  5. Conclusie         - Koop/Hold/Verkoop + slim instapmoment

De prijsdoelen worden afgeleid uit historische volatiliteit, technische niveaus
(steun/weerstand, Bollinger Bands) en fundamentele waardering (P/E, EPS-groei).
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import math
import pandas as pd
import yfinance as yf

from src.analysis import indicators as ind


# Termijn -> (label, kalenderdagen, handelsdagen, volatiliteit-multiplier)
# Multiplier ≈ √(handelsdagen/252) — schaalt 1-sigma beweging naar de termijn.
TERM_PROFILES: Dict[str, Tuple[str, int, int, float]] = {
    "short": ("Korte termijn (1-3 maanden)", 90, 63, 0.50),
    "medium": ("Middellange termijn (6-12 maanden)", 365, 252, 1.00),
    "long": ("Lange termijn (2-3 jaar)", 1000, 700, 1.60),
}

# Sector -> indicatieve concurrenten voor relatieve vergelijking
SECTOR_PEERS: Dict[str, List[str]] = {
    "Technology": ["AAPL", "MSFT", "GOOGL", "META", "NVDA"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "NKE", "MCD"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "TMUS"],
    "Financial Services": ["JPM", "BAC", "V", "MA", "BLK"],
    "Healthcare": ["JNJ", "UNH", "LLY", "PFE", "MRK"],
    "Industrials": ["CAT", "BA", "GE", "HON", "UPS"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
    "Consumer Defensive": ["WMT", "PG", "KO", "PEP", "COST"],
    "Basic Materials": ["LIN", "SHW", "FCX", "NEM", "DOW"],
    "Real Estate": ["PLD", "AMT", "EQIX", "CCI", "SPG"],
    "Utilities": ["NEE", "DUK", "SO", "AEP", "EXC"],
}


@dataclass
class Fundamentals:
    company_name: str
    sector: str
    industry: str
    market_cap: Optional[float]
    pe_ratio: Optional[float]
    forward_pe: Optional[float]
    peg_ratio: Optional[float]
    revenue_ttm: Optional[float]
    revenue_growth: Optional[float]
    earnings_growth: Optional[float]
    profit_margin: Optional[float]
    operating_margin: Optional[float]
    debt_to_equity: Optional[float]
    free_cashflow: Optional[float]
    dividend_yield: Optional[float]
    beta: Optional[float]
    analyst_target_mean: Optional[float]
    analyst_recommendation: Optional[str]
    fifty_two_week_high: Optional[float]
    fifty_two_week_low: Optional[float]


@dataclass
class TechnicalSnapshot:
    current_price: float
    rsi: Optional[float]
    macd_bullish: bool
    ema_bullish: bool
    bb_oversold: bool
    volume_spike: bool
    sma50: Optional[float]
    sma200: Optional[float]
    above_sma200: bool
    realized_vol_annual: float
    support: float
    resistance: float
    momentum_30d: float


@dataclass
class Scenario:
    label: str            # "Bullish" / "Base-case" / "Bearish"
    probability: float    # 0-1
    target_price: float
    return_pct: float
    rationale: str


@dataclass
class StockAnalysis:
    symbol: str
    timestamp: str
    term_label: str
    term_key: str
    fundamentals: Fundamentals
    technicals: TechnicalSnapshot
    peers: List[Dict]
    huidige_status: List[str]
    kansrijke_signalen: List[str]
    risicos: List[str]
    scenarios: List[Scenario]
    conclusie: str
    actie: str            # "Koop" / "Hold" / "Verkoop"
    instapmoment: str
    score: float          # -100..+100, basis voor advies

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _safe(info: dict, key: str) -> Optional[float]:
    v = info.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "n.v.t."
    abs_v = abs(v)
    if abs_v >= 1e12:
        return f"${v / 1e12:.2f}B (biljoen)"
    if abs_v >= 1e9:
        return f"${v / 1e9:.2f}B (miljard)"
    if abs_v >= 1e6:
        return f"${v / 1e6:.1f}M"
    if abs_v >= 1e3:
        return f"${v / 1e3:.1f}K"
    return f"${v:,.2f}"


def _fmt_pct(v: Optional[float], decimals: int = 1) -> str:
    if v is None:
        return "n.v.t."
    return f"{v * 100:.{decimals}f}%"


# ----------------------------------------------------------------------------
# Fundamentals via yfinance
# ----------------------------------------------------------------------------

def fetch_fundamentals(symbol: str) -> Fundamentals:
    ticker = yf.Ticker(symbol)
    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    return Fundamentals(
        company_name=info.get("longName") or info.get("shortName") or symbol,
        sector=info.get("sector") or "Onbekend",
        industry=info.get("industry") or "Onbekend",
        market_cap=_safe(info, "marketCap"),
        pe_ratio=_safe(info, "trailingPE"),
        forward_pe=_safe(info, "forwardPE"),
        peg_ratio=_safe(info, "pegRatio"),
        revenue_ttm=_safe(info, "totalRevenue"),
        revenue_growth=_safe(info, "revenueGrowth"),
        earnings_growth=_safe(info, "earningsGrowth"),
        profit_margin=_safe(info, "profitMargins"),
        operating_margin=_safe(info, "operatingMargins"),
        debt_to_equity=_safe(info, "debtToEquity"),
        free_cashflow=_safe(info, "freeCashflow"),
        dividend_yield=_safe(info, "dividendYield"),
        beta=_safe(info, "beta"),
        analyst_target_mean=_safe(info, "targetMeanPrice"),
        analyst_recommendation=info.get("recommendationKey"),
        fifty_two_week_high=_safe(info, "fiftyTwoWeekHigh"),
        fifty_two_week_low=_safe(info, "fiftyTwoWeekLow"),
    )


def fetch_peers(symbol: str, sector: str, max_peers: int = 4) -> List[Dict]:
    """Haal kerncijfers van sectorgenoten op voor relatieve vergelijking."""
    peers_symbols = SECTOR_PEERS.get(sector, [])
    peers_symbols = [p for p in peers_symbols if p.upper() != symbol.upper()][:max_peers]

    out: List[Dict] = []
    for peer in peers_symbols:
        try:
            info = yf.Ticker(peer).info or {}
        except Exception:
            continue
        out.append({
            "symbol": peer,
            "name": info.get("shortName") or peer,
            "pe_ratio": _safe(info, "trailingPE"),
            "revenue_growth": _safe(info, "revenueGrowth"),
            "profit_margin": _safe(info, "profitMargins"),
            "market_cap": _safe(info, "marketCap"),
        })
    return out


# ----------------------------------------------------------------------------
# Technical snapshot
# ----------------------------------------------------------------------------

def build_technical_snapshot(df: pd.DataFrame, current_price: float) -> TechnicalSnapshot:
    close = df["close"]

    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    try:
        rsi = ind.rsi_series(close, length=14).dropna()
        rsi_val = float(rsi.iloc[-1]) if not rsi.empty else None
    except Exception:
        rsi_val = None

    returns = close.pct_change().dropna()
    if len(returns) >= 30:
        realized_vol = float(returns.std() * math.sqrt(252))
    else:
        realized_vol = 0.30

    lookback = min(60, len(df))
    recent = df.tail(lookback)
    support = float(recent["low"].min())
    resistance = float(recent["high"].max())

    if len(close) >= 30:
        momentum_30d = float((close.iloc[-1] / close.iloc[-30] - 1.0))
    else:
        momentum_30d = 0.0

    return TechnicalSnapshot(
        current_price=current_price,
        rsi=rsi_val,
        macd_bullish=ind.check_macd_crossover(df),
        ema_bullish=ind.check_ema_crossover(df),
        bb_oversold=ind.check_bollinger_bands(df),
        volume_spike=ind.check_volume_spike(df),
        sma50=sma50,
        sma200=sma200,
        above_sma200=(sma200 is not None and current_price > sma200),
        realized_vol_annual=realized_vol,
        support=support,
        resistance=resistance,
        momentum_30d=momentum_30d,
    )


# ----------------------------------------------------------------------------
# Narratieve secties
# ----------------------------------------------------------------------------

def build_huidige_status(f: Fundamentals, peers: List[Dict]) -> List[str]:
    lines: List[str] = []
    lines.append(
        f"{f.company_name} ({f.sector} / {f.industry}) heeft een marktkapitalisatie van "
        f"{_fmt_money(f.market_cap)}."
    )

    if f.revenue_ttm is not None:
        rev_line = f"Omzet (TTM) bedraagt {_fmt_money(f.revenue_ttm)}"
        if f.revenue_growth is not None:
            rev_line += f", met een omzetgroei jaar-op-jaar van {_fmt_pct(f.revenue_growth)}"
        lines.append(rev_line + ".")

    if f.profit_margin is not None or f.operating_margin is not None:
        margin_line = "Winstgevendheid: "
        parts = []
        if f.profit_margin is not None:
            parts.append(f"nettomarge {_fmt_pct(f.profit_margin)}")
        if f.operating_margin is not None:
            parts.append(f"operationele marge {_fmt_pct(f.operating_margin)}")
        margin_line += ", ".join(parts) + "."
        lines.append(margin_line)

    if f.earnings_growth is not None:
        lines.append(f"Winstgroei (EPS) jaar-op-jaar: {_fmt_pct(f.earnings_growth)}.")

    if f.pe_ratio is not None or f.forward_pe is not None:
        pe_parts = []
        if f.pe_ratio is not None:
            pe_parts.append(f"trailing P/E {f.pe_ratio:.1f}")
        if f.forward_pe is not None:
            pe_parts.append(f"forward P/E {f.forward_pe:.1f}")
        lines.append("Waardering: " + ", ".join(pe_parts) + ".")

    # Peer comparison
    if peers:
        pe_peers = [p["pe_ratio"] for p in peers if p.get("pe_ratio")]
        margin_peers = [p["profit_margin"] for p in peers if p.get("profit_margin")]
        growth_peers = [p["revenue_growth"] for p in peers if p.get("revenue_growth")]

        if pe_peers and f.pe_ratio is not None:
            avg_pe = sum(pe_peers) / len(pe_peers)
            verdict = "goedkoper" if f.pe_ratio < avg_pe else "duurder"
            lines.append(
                f"Tegenover sectorgenoten ({', '.join(p['symbol'] for p in peers)}) is het aandeel "
                f"{verdict} gewaardeerd: P/E {f.pe_ratio:.1f} vs. sectorgemiddelde {avg_pe:.1f}."
            )
        if margin_peers and f.profit_margin is not None:
            avg_margin = sum(margin_peers) / len(margin_peers)
            sterk = "boven" if f.profit_margin > avg_margin else "onder"
            lines.append(
                f"Nettomarge ligt {sterk} het sectorgemiddelde "
                f"({_fmt_pct(f.profit_margin)} vs. {_fmt_pct(avg_margin)})."
            )
        if growth_peers and f.revenue_growth is not None:
            avg_growth = sum(growth_peers) / len(growth_peers)
            sterk = "hoger" if f.revenue_growth > avg_growth else "lager"
            lines.append(
                f"Omzetgroei is {sterk} dan bij concurrenten "
                f"({_fmt_pct(f.revenue_growth)} vs. {_fmt_pct(avg_growth)})."
            )

    # Sterke punten
    sterke_punten: List[str] = []
    if f.profit_margin is not None and f.profit_margin > 0.15:
        sterke_punten.append(f"hoge nettomarge ({_fmt_pct(f.profit_margin)})")
    if f.revenue_growth is not None and f.revenue_growth > 0.10:
        sterke_punten.append(f"sterke omzetgroei ({_fmt_pct(f.revenue_growth)})")
    if f.free_cashflow is not None and f.free_cashflow > 0:
        sterke_punten.append(f"positieve vrije kasstroom ({_fmt_money(f.free_cashflow)})")
    if f.dividend_yield is not None and f.dividend_yield > 0.02:
        sterke_punten.append(f"dividendrendement van {_fmt_pct(f.dividend_yield)}")
    if f.debt_to_equity is not None and f.debt_to_equity < 50:
        sterke_punten.append(f"gezonde balans (Debt/Equity {f.debt_to_equity:.0f})")
    if sterke_punten:
        lines.append("Sterke punten: " + ", ".join(sterke_punten) + ".")

    return lines


def build_kansrijke_signalen(t: TechnicalSnapshot, f: Fundamentals) -> List[str]:
    out: List[str] = []

    if t.rsi is not None and t.rsi < 35:
        out.append(f"RSI({t.rsi:.0f}) signaleert oversold — historisch volgt vaak een terugvering.")
    if t.macd_bullish:
        out.append("MACD heeft een bullish crossover gemaakt: momentum draait positief.")
    if t.ema_bullish:
        out.append("EMA9 kruist EMA21 omhoog (korte-termijn golden cross).")
    if t.bb_oversold:
        out.append("Koers raakt de onderste Bollinger Band: statistisch oversold.")
    if t.volume_spike:
        out.append("Volume-piek wijst op verhoogde marktbelangstelling.")
    if t.above_sma200 and t.sma50 and t.sma200 and t.sma50 > t.sma200:
        out.append("Koers boven SMA200 en SMA50 > SMA200: structureel uptrend intact.")
    if t.momentum_30d > 0.05:
        out.append(f"Sterk 30-daags momentum ({t.momentum_30d * 100:+.1f}%).")

    if f.revenue_growth is not None and f.revenue_growth > 0.15:
        out.append(f"Bovengemiddelde omzetgroei ({_fmt_pct(f.revenue_growth)}) ondersteunt een herwaardering.")
    if f.earnings_growth is not None and f.earnings_growth > 0.20:
        out.append(f"Krachtige winstgroei ({_fmt_pct(f.earnings_growth)}) creëert ruimte voor multiple-expansion.")
    if f.peg_ratio is not None and 0 < f.peg_ratio < 1.0:
        out.append(f"PEG-ratio {f.peg_ratio:.2f} (< 1) wijst op groei tegen aantrekkelijke prijs.")
    if f.analyst_target_mean is not None and f.analyst_target_mean > t.current_price * 1.10:
        upside = (f.analyst_target_mean / t.current_price - 1.0) * 100
        out.append(
            f"Analistenconsensus mikt op ${f.analyst_target_mean:.2f} ({upside:+.1f}% upside) "
            f"— '{f.analyst_recommendation or 'n.v.t.'}'."
        )

    if not out:
        out.append("Geen scherp uitspringende koop-signalen op dit moment; markt is neutraal voor dit aandeel.")
    return out


def build_risicos(t: TechnicalSnapshot, f: Fundamentals) -> List[str]:
    out: List[str] = []

    if t.rsi is not None and t.rsi > 70:
        out.append(f"RSI({t.rsi:.0f}) is overbought — kans op een correctie op korte termijn.")
    if t.sma200 and t.current_price < t.sma200 * 0.95:
        out.append("Koers ligt duidelijk onder de SMA200: lange-termijn trend is bearish.")
    if t.realized_vol_annual > 0.45:
        out.append(
            f"Hoge volatiliteit ({_fmt_pct(t.realized_vol_annual)} geannualiseerd) "
            f"betekent grote uitslagen in beide richtingen."
        )
    if t.momentum_30d < -0.08:
        out.append(f"Negatief 30-daags momentum ({t.momentum_30d * 100:+.1f}%).")

    if f.beta is not None and f.beta > 1.5:
        out.append(f"Hoge bèta ({f.beta:.2f}): aandeel beweegt sterker mee met de markt — gevoelig voor macroschokken (rente, recessie).")
    if f.debt_to_equity is not None and f.debt_to_equity > 150:
        out.append(f"Hoge schuldratio (Debt/Equity {f.debt_to_equity:.0f}): kwetsbaar bij stijgende rentes.")
    if f.pe_ratio is not None and f.pe_ratio > 40:
        out.append(f"Premium waardering (P/E {f.pe_ratio:.1f}): hoge verwachtingen ingeprijsd; teleurstelling kan flink afstraffen.")
    if f.profit_margin is not None and f.profit_margin < 0.05:
        out.append(f"Dunne nettomarge ({_fmt_pct(f.profit_margin)}) maakt het bedrijf kwetsbaar voor kostenstijgingen of prijsconcurrentie.")
    if f.revenue_growth is not None and f.revenue_growth < 0:
        out.append(f"Krimpende omzet ({_fmt_pct(f.revenue_growth)}): fundamenteel zwak signaal.")

    out.append(
        f"Concurrentiedruk binnen {f.sector} blijft een doorlopend risico — verlies van marktaandeel "
        f"of margedruk kan de koers raken."
    )
    out.append(
        "Macro: rentebeleid van centrale banken, inflatie en geopolitiek (handelsoorlogen, sancties) "
        "kunnen de waardering van het hele segment drukken."
    )

    return out


def build_scenarios(t: TechnicalSnapshot, f: Fundamentals, term_key: str) -> List[Scenario]:
    label, _days, _trading_days, vol_mult = TERM_PROFILES[term_key]

    base_price = t.current_price
    # Verwachte beweging gebaseerd op gerealiseerde volatiliteit en termijn
    expected_move = t.realized_vol_annual * vol_mult

    # Trendaanpassing — koers in uptrend tilt base-case op
    trend_bias = 0.0
    if t.above_sma200:
        trend_bias += 0.03
    if t.sma50 and t.sma200 and t.sma50 > t.sma200:
        trend_bias += 0.02
    if t.momentum_30d > 0:
        trend_bias += min(t.momentum_30d, 0.05)
    else:
        trend_bias += max(t.momentum_30d, -0.05)

    # Fundamenteel anker — earnings growth tilt mee
    if f.earnings_growth is not None:
        trend_bias += max(-0.10, min(0.10, f.earnings_growth * 0.3))

    bull = base_price * (1 + expected_move + max(trend_bias, 0))
    base = base_price * (1 + trend_bias)
    bear = base_price * max(0.40, (1 - expected_move + min(trend_bias, 0)))

    # Cap base-case op analist target indien beschikbaar voor middellange termijn
    if term_key == "medium" and f.analyst_target_mean:
        base = (base + f.analyst_target_mean) / 2.0

    # Waarschijnlijkheden — verschuiven op basis van technisch beeld
    p_bull, p_base, p_bear = 0.25, 0.50, 0.25
    if t.above_sma200 and t.macd_bullish:
        p_bull, p_base, p_bear = 0.35, 0.50, 0.15
    elif not t.above_sma200 and t.rsi and t.rsi > 60:
        p_bull, p_base, p_bear = 0.20, 0.45, 0.35

    def pct(target: float) -> float:
        return (target / base_price - 1.0) * 100

    scenarios = [
        Scenario(
            label="Bullish",
            probability=p_bull,
            target_price=round(bull, 2),
            return_pct=round(pct(bull), 1),
            rationale=(
                "Trend houdt aan, sentiment verbetert verder en/of bedrijf overtreft consensus. "
                "Multiple-expansion gecombineerd met operationele groei tilt de koers door weerstandszones."
            ),
        ),
        Scenario(
            label="Base-case",
            probability=p_base,
            target_price=round(base, 2),
            return_pct=round(pct(base), 1),
            rationale=(
                "Bedrijf groeit in lijn met de huidige verwachtingen, geen grote macro-schokken. "
                "Waardering blijft rond historische gemiddelden."
            ),
        ),
        Scenario(
            label="Bearish",
            probability=p_bear,
            target_price=round(bear, 2),
            return_pct=round(pct(bear), 1),
            rationale=(
                "Cyclische tegenwind, margedruk of een macro-correctie (rente/recessie). "
                "Koers test eerdere steunzones, multiples krimpen."
            ),
        ),
    ]
    return scenarios


# ----------------------------------------------------------------------------
# Score & advies
# ----------------------------------------------------------------------------

def calculate_score(t: TechnicalSnapshot, f: Fundamentals) -> float:
    """
    Heuristische score van -100 (sterk verkoop) tot +100 (sterk koop).
    Combineert technische en fundamentele factoren.
    """
    s = 0.0

    # Technisch
    if t.rsi is not None:
        if t.rsi < 30:
            s += 12
        elif t.rsi < 40:
            s += 6
        elif t.rsi > 70:
            s -= 10
    if t.macd_bullish: s += 8
    if t.ema_bullish: s += 6
    if t.bb_oversold: s += 6
    if t.volume_spike: s += 4
    if t.above_sma200: s += 8
    if t.sma50 and t.sma200 and t.sma50 > t.sma200: s += 5
    if t.momentum_30d > 0.05: s += 6
    elif t.momentum_30d < -0.05: s -= 6

    # Fundamenteel
    if f.revenue_growth is not None:
        if f.revenue_growth > 0.15: s += 10
        elif f.revenue_growth > 0.05: s += 5
        elif f.revenue_growth < 0: s -= 10
    if f.earnings_growth is not None:
        if f.earnings_growth > 0.20: s += 10
        elif f.earnings_growth > 0.05: s += 4
        elif f.earnings_growth < 0: s -= 8
    if f.profit_margin is not None:
        if f.profit_margin > 0.20: s += 6
        elif f.profit_margin < 0.05: s -= 4
    if f.peg_ratio is not None and 0 < f.peg_ratio < 1.0: s += 6
    if f.pe_ratio is not None and f.pe_ratio > 50: s -= 5
    if f.debt_to_equity is not None and f.debt_to_equity > 200: s -= 6
    if f.analyst_target_mean is not None:
        upside = (f.analyst_target_mean / t.current_price - 1.0)
        s += max(-10, min(15, upside * 50))

    return max(-100.0, min(100.0, s))


def derive_action(score: float) -> str:
    if score >= 20: return "Koop"
    if score <= -15: return "Verkoop"
    return "Hold"


def build_instapmoment(t: TechnicalSnapshot, action: str) -> str:
    if action == "Verkoop":
        return (
            f"Niet instappen op dit moment. Indien je positie wilt afbouwen, doe dat richting "
            f"weerstandsniveau ${t.resistance:.2f} of bij elke rally."
        )

    # Bereken instap-zone iets boven steun
    steun = t.support
    instap_laag = steun * 1.005
    instap_hoog = steun * 1.025
    huidig = t.current_price

    if action == "Koop":
        if huidig <= instap_hoog:
            return (
                f"Huidige prijs (${huidig:.2f}) ligt al binnen een aantrekkelijke instapzone "
                f"(${instap_laag:.2f}–${instap_hoog:.2f}). Gespreid kopen (DCA over 2-4 weken) "
                f"verlaagt timingrisico. Stop-loss: ${steun * 0.95:.2f}."
            )
        return (
            f"Wacht op een terugval naar ${instap_laag:.2f}–${instap_hoog:.2f} (rond steun ${steun:.2f}). "
            f"Alternatief: gespreid kopen (DCA) in 3-4 tranches om timingrisico te verkleinen. "
            f"Stop-loss-niveau: ${steun * 0.95:.2f}."
        )

    # Hold
    return (
        f"Niet actief instappen. Pas een tranche kopen bij een correctie richting steun ${steun:.2f}, "
        f"of na bevestiging van een doorbraak boven weerstand ${t.resistance:.2f}."
    )


def build_conclusie(action: str, score: float, scenarios: List[Scenario], term_label: str) -> str:
    base = next((s for s in scenarios if s.label == "Base-case"), scenarios[0])
    risk_reward_parts = []
    bull = next((s for s in scenarios if s.label == "Bullish"), None)
    bear = next((s for s in scenarios if s.label == "Bearish"), None)
    if bull and bear:
        upside = bull.return_pct
        downside = abs(bear.return_pct)
        rr = upside / downside if downside > 1 else 0
        risk_reward_parts.append(f"Risk/reward ≈ {rr:.1f}:1 ({upside:+.1f}% bull vs. {-downside:+.1f}% bear)")

    rr_txt = " | " + " | ".join(risk_reward_parts) if risk_reward_parts else ""
    return (
        f"Advies: **{action}** (score {score:+.0f}/100). "
        f"Voor de {term_label.lower()} mikt het base-case scenario op ${base.target_price:.2f} "
        f"({base.return_pct:+.1f}%).{rr_txt}"
    )


# ----------------------------------------------------------------------------
# Hoofdfunctie
# ----------------------------------------------------------------------------

def analyze_stock(
    symbol: str,
    df: pd.DataFrame,
    current_price: float,
    term: str = "medium",
) -> StockAnalysis:
    """
    Voer een volledige 5-delige analyse uit op een aandeel.

    Args:
        symbol: ticker, bijv. "AAPL"
        df: OHLCV DataFrame (timestamp, open, high, low, close, volume)
        current_price: huidige marktprijs
        term: "short" | "medium" | "long"
    """
    if term not in TERM_PROFILES:
        term = "medium"
    term_label = TERM_PROFILES[term][0]

    fundamentals = fetch_fundamentals(symbol)
    peers = fetch_peers(symbol, fundamentals.sector)
    technicals = build_technical_snapshot(df, current_price)

    huidige_status = build_huidige_status(fundamentals, peers)
    kansrijke_signalen = build_kansrijke_signalen(technicals, fundamentals)
    risicos = build_risicos(technicals, fundamentals)
    scenarios = build_scenarios(technicals, fundamentals, term)

    score = calculate_score(technicals, fundamentals)
    action = derive_action(score)
    instapmoment = build_instapmoment(technicals, action)
    conclusie = build_conclusie(action, score, scenarios, term_label)

    return StockAnalysis(
        symbol=symbol.upper(),
        timestamp=datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        term_label=term_label,
        term_key=term,
        fundamentals=fundamentals,
        technicals=technicals,
        peers=peers,
        huidige_status=huidige_status,
        kansrijke_signalen=kansrijke_signalen,
        risicos=risicos,
        scenarios=scenarios,
        conclusie=conclusie,
        actie=action,
        instapmoment=instapmoment,
        score=score,
    )


# ----------------------------------------------------------------------------
# Console rendering
# ----------------------------------------------------------------------------

def render_text(a: StockAnalysis) -> str:
    lines: List[str] = []
    sep = "=" * 72
    sub = "-" * 72

    lines.append(sep)
    lines.append(f"AANDELEN-ANALYSE  —  {a.symbol}  ({a.fundamentals.company_name})")
    lines.append(f"Termijn: {a.term_label}   |   Gegenereerd: {a.timestamp}")
    lines.append(f"Huidige prijs: ${a.technicals.current_price:,.2f}")
    lines.append(sep)

    lines.append("\n1. HUIDIGE STATUS — winstcijfers, omzet en sterke punten t.o.v. concurrenten")
    lines.append(sub)
    for s in a.huidige_status:
        lines.append(f" • {s}")

    if a.peers:
        lines.append("\n   Sectorgenoten:")
        for p in a.peers:
            pe = f"P/E {p['pe_ratio']:.1f}" if p.get('pe_ratio') else "P/E n.v.t."
            mg = _fmt_pct(p.get('profit_margin')) if p.get('profit_margin') is not None else "n.v.t."
            gr = _fmt_pct(p.get('revenue_growth')) if p.get('revenue_growth') is not None else "n.v.t."
            lines.append(f"     - {p['symbol']:6s} | {pe:12s} | marge {mg:7s} | omzetgroei {gr}")

    lines.append("\n2. KANSRIJKE SIGNALEN — trends en technische signalen voor een stijging")
    lines.append(sub)
    for s in a.kansrijke_signalen:
        lines.append(f" • {s}")

    lines.append("\n3. RISICO'S — macro, concurrentie en bedrijfsspecifiek")
    lines.append(sub)
    for s in a.risicos:
        lines.append(f" • {s}")

    lines.append(f"\n4. VOORSPELLING — drie scenario's voor {a.term_label.lower()}")
    lines.append(sub)
    for sc in a.scenarios:
        lines.append(
            f" • {sc.label:10s} | kans {sc.probability * 100:4.0f}% | "
            f"doel ${sc.target_price:,.2f} ({sc.return_pct:+.1f}%)"
        )
        lines.append(f"     {sc.rationale}")

    lines.append("\n5. CONCLUSIE")
    lines.append(sub)
    lines.append(f" • {a.conclusie}")
    lines.append(f" • Instapmoment: {a.instapmoment}")

    lines.append("\n" + sep)
    lines.append("Deze analyse is automatisch gegenereerd op basis van publieke data en algoritmische")
    lines.append("heuristieken. Geen financieel advies — doe altijd je eigen onderzoek.")
    lines.append(sep)

    return "\n".join(lines)
