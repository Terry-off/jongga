"""SQLite 저장 계층 — 스키마 전체 개요는 DESIGN.md 7장"""
import sqlite3
from datetime import datetime

from jongga.settings import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS universe_snapshot (
    trade_date    TEXT NOT NULL,            -- YYYY-MM-DD
    code          TEXT NOT NULL,            -- 종목코드 6자리
    name          TEXT,
    market        TEXT,                     -- KOSPI / KOSDAQ
    price         INTEGER,                  -- 수집 시점 가격(원)
    change_rate   REAL,                     -- 등락률(%)
    volume        INTEGER,                  -- 누적 거래량(주)
    trading_value INTEGER,                  -- 누적 거래대금(원)
    sources       TEXT,                     -- 편입 경로: 거래대금상위,상승률상위
    collected_at  TEXT NOT NULL,
    PRIMARY KEY (trade_date, code)
);

CREATE TABLE IF NOT EXISTS collect_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at  TEXT NOT NULL,
    kind    TEXT NOT NULL,                  -- universe / snapshot / ...
    status  TEXT NOT NULL,                  -- ok / error
    detail  TEXT
);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def save_universe(trade_date: str, rows: list[dict]) -> int:
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        conn.executemany(
            """INSERT INTO universe_snapshot
               (trade_date, code, name, market, price, change_rate, volume, trading_value, sources, collected_at)
               VALUES (:trade_date, :code, :name, :market, :price, :change_rate, :volume, :trading_value, :sources, :collected_at)
               ON CONFLICT(trade_date, code) DO UPDATE SET
                 price=excluded.price, change_rate=excluded.change_rate,
                 volume=excluded.volume, trading_value=excluded.trading_value,
                 sources=excluded.sources, collected_at=excluded.collected_at""",
            [dict(r, trade_date=trade_date, collected_at=now) for r in rows],
        )
        conn.execute(
            "INSERT INTO collect_log (run_at, kind, status, detail) VALUES (?, 'universe', 'ok', ?)",
            (now, f"{trade_date} {len(rows)}종목"),
        )
    return len(rows)
