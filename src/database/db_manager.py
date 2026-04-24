import json
import os
import sqlite3
import threading
from datetime import datetime


_DDL = """
CREATE TABLE IF NOT EXISTS signals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               TEXT    NOT NULL,
    symbol           TEXT    NOT NULL,
    asset_type       TEXT    NOT NULL,
    price            REAL    NOT NULL,
    confidence       INTEGER NOT NULL,
    reasons          TEXT    NOT NULL,
    golden_cross     INTEGER NOT NULL DEFAULT 0,
    rsi_bounce       INTEGER NOT NULL DEFAULT 0,
    momentum_pct     REAL    NOT NULL DEFAULT 0.0,
    volume_ratio     REAL    NOT NULL DEFAULT 0.0,
    news_match       INTEGER NOT NULL DEFAULT 0,
    news_title       TEXT    DEFAULT NULL,
    notified         INTEGER NOT NULL DEFAULT 0,
    outcome_pct      REAL    DEFAULT NULL,
    outcome_at       TEXT    DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_ts ON signals(symbol, ts);
"""


class SignalDB:
    def __init__(self, db_path: str = "data/sentinel.db"):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._db_path = db_path
        self._lock = threading.Lock()
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.executescript(_DDL)
        conn.commit()
        conn.close()

    def save(
        self,
        *,
        symbol: str,
        asset_type: str,
        price: float,
        confidence: int,
        reasons: list,
        golden_cross: bool,
        rsi_bounce: bool,
        momentum_pct: float,
        volume_ratio: float,
        news_match: bool,
        news_title: str | None = None,
        notified: bool = False,
    ) -> int:
        ts = datetime.utcnow().isoformat()
        row = (
            ts, symbol, asset_type, price, confidence,
            json.dumps(reasons),
            int(golden_cross), int(rsi_bounce),
            round(momentum_pct, 4), round(volume_ratio, 4),
            int(news_match), news_title, int(notified),
        )
        sql = """
            INSERT INTO signals
            (ts, symbol, asset_type, price, confidence, reasons,
             golden_cross, rsi_bounce, momentum_pct, volume_ratio,
             news_match, news_title, notified)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        with self._lock:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            cur = conn.execute(sql, row)
            conn.commit()
            row_id = cur.lastrowid
            conn.close()
        return row_id

    def get_all(self, limit: int = 500) -> list[dict]:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM signals ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            d["reasons"] = json.loads(d["reasons"])
            result.append(d)
        return result

    def update_outcome(self, signal_id: int, outcome_pct: float) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.execute(
                "UPDATE signals SET outcome_pct=?, outcome_at=? WHERE id=?",
                (outcome_pct, datetime.utcnow().isoformat(), signal_id),
            )
            conn.commit()
            conn.close()

    def win_rate(self) -> dict:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome_pct > 0 THEN 1 ELSE 0 END) as wins,
                AVG(outcome_pct) as avg_outcome
            FROM signals WHERE outcome_pct IS NOT NULL
        """).fetchone()
        conn.close()
        total, wins, avg = row
        return {
            "total": total or 0,
            "wins": wins or 0,
            "win_rate": round((wins / total * 100) if total else 0, 1),
            "avg_outcome_pct": round(avg or 0, 2),
        }
