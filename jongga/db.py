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

CREATE TABLE IF NOT EXISTS trade_journal (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date     TEXT NOT NULL,       -- 매수일 YYYY-MM-DD
    code           TEXT,
    name           TEXT,
    score_pct      REAL,                -- 매수 당시 점수
    material_grade TEXT,
    buy_price      REAL,
    quantity       INTEGER,
    amount         INTEGER,             -- 매수금액(원)
    one_r          INTEGER,             -- 기록 시점의 1R(원) — R 환산 기준 고정
    after_hours    TEXT,                -- 시간외 체결 메모
    exit_date      TEXT,
    exit_price     REAL,
    pnl_amount     INTEGER,
    pnl_r          REAL,
    rule_violation INTEGER DEFAULT 0,   -- 규칙 위반 여부 (수익이어도 위반은 위반)
    violation_note TEXT,
    lesson         TEXT,                -- 한 줄 교훈
    status         TEXT DEFAULT 'open', -- open(보유 중) / closed(청산)
    created_at     TEXT,
    updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS collect_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at  TEXT NOT NULL,
    kind    TEXT NOT NULL,                  -- universe / snapshot / ...
    status  TEXT NOT NULL,                  -- ok / error
    detail  TEXT
);

CREATE TABLE IF NOT EXISTS screening_day (
    trade_date     TEXT PRIMARY KEY,
    signal_color   TEXT,
    signal_reasons TEXT,
    analyzed       INTEGER,
    created_at     TEXT
);

CREATE TABLE IF NOT EXISTS settings_override (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS theme_snapshot (
    trade_date TEXT NOT NULL,
    theme      TEXT NOT NULL,
    codes      TEXT NOT NULL,           -- JSON 배열 [종목코드...]
    collected_at TEXT,
    PRIMARY KEY (trade_date, theme)
);

CREATE TABLE IF NOT EXISTS stock_collect (
    trade_date TEXT NOT NULL,
    code       TEXT NOT NULL,
    snapshot   TEXT,                    -- JSON: 현재가·시총·경보 플래그
    daily      TEXT,                    -- JSON: 일봉 배열
    minutes    TEXT,                    -- JSON: 당일 분봉 (지나가면 못 보는 데이터)
    investor   TEXT,                    -- JSON: 수급
    materials  TEXT,                    -- JSON: 재료 판정(등급·근거) 당시 스냅샷
    collected_at TEXT,
    PRIMARY KEY (trade_date, code)
);

CREATE TABLE IF NOT EXISTS index_collect (
    trade_date TEXT PRIMARY KEY,
    payload    TEXT,                    -- JSON: {KOSPI:{prev_close,minutes}, KOSDAQ:{...}}
    collected_at TEXT
);

CREATE TABLE IF NOT EXISTS screening_result (
    trade_date    TEXT NOT NULL,
    code          TEXT NOT NULL,
    name          TEXT,
    kind          TEXT NOT NULL,            -- candidate / rejected
    verdict       TEXT,                     -- full / half / watch (rejected는 빈값)
    pct           REAL,
    earned        REAL,
    available_max REAL,
    vetoes        TEXT,                     -- 탈락 사유 제목들
    summary       TEXT,                     -- 쉬운 말 요약
    created_at    TEXT,
    PRIMARY KEY (trade_date, code)
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


def load_universe(trade_date: str) -> list[dict]:
    """저장된 일자의 유니버스 row 목록 (거래대금 내림차순). 없으면 빈 리스트"""
    if not DB_PATH.exists():
        return []
    with connect() as conn:
        try:
            rows = conn.execute(
                "SELECT code, name, market, price, change_rate, volume, trading_value, sources "
                "FROM universe_snapshot WHERE trade_date = ? ORDER BY trading_value DESC",
                (trade_date,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(r) for r in rows]


def save_stock_collect(trade_date, code, snapshot, daily, minutes, investor, materials) -> None:
    import json
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    dump = lambda v: json.dumps(v, ensure_ascii=False) if v is not None else None
    with connect() as conn:
        conn.execute(
            """INSERT INTO stock_collect
               (trade_date, code, snapshot, daily, minutes, investor, materials, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(trade_date, code) DO UPDATE SET
                 snapshot=excluded.snapshot, daily=excluded.daily, minutes=excluded.minutes,
                 investor=excluded.investor, materials=excluded.materials,
                 collected_at=excluded.collected_at""",
            (trade_date, code, dump(snapshot), dump(daily), dump(minutes),
             dump(investor), dump(materials), now),
        )


def load_stock_collect(trade_date: str) -> dict:
    """{code: {snapshot, daily, minutes, investor, materials}}"""
    import json
    if not DB_PATH.exists():
        return {}
    load = lambda v: json.loads(v) if v else None
    with connect() as conn:
        try:
            rows = conn.execute(
                "SELECT code, snapshot, daily, minutes, investor, materials "
                "FROM stock_collect WHERE trade_date = ?", (trade_date,)
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
    return {r["code"]: {"snapshot": load(r["snapshot"]), "daily": load(r["daily"]),
                        "minutes": load(r["minutes"]), "investor": load(r["investor"]),
                        "materials": load(r["materials"])} for r in rows}


def save_index_collect(trade_date: str, index: dict) -> None:
    import json
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            "INSERT INTO index_collect (trade_date, payload, collected_at) VALUES (?, ?, ?) "
            "ON CONFLICT(trade_date) DO UPDATE SET payload=excluded.payload, collected_at=excluded.collected_at",
            (trade_date, json.dumps(index, ensure_ascii=False), now),
        )


def load_index_collect(trade_date: str) -> dict:
    import json
    if not DB_PATH.exists():
        return {}
    with connect() as conn:
        try:
            row = conn.execute(
                "SELECT payload FROM index_collect WHERE trade_date = ?", (trade_date,)
            ).fetchone()
        except sqlite3.OperationalError:
            return {}
    return json.loads(row["payload"]) if row and row["payload"] else {}


def collected_dates() -> list[str]:
    """수집된 거래일 목록 (최신순) — 과거 조회 달력·보충 판단용"""
    if not DB_PATH.exists():
        return []
    with connect() as conn:
        try:
            rows = conn.execute(
                "SELECT DISTINCT trade_date FROM universe_snapshot ORDER BY trade_date DESC"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [r["trade_date"] for r in rows]


def save_theme_map(trade_date: str, theme_map: dict) -> int:
    """테마 매핑을 일자별로 저장 (과거 조회 시 그날의 테마 재현용)"""
    import json
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute("DELETE FROM theme_snapshot WHERE trade_date = ?", (trade_date,))
        conn.executemany(
            "INSERT INTO theme_snapshot (trade_date, theme, codes, collected_at) VALUES (?, ?, ?, ?)",
            [(trade_date, theme, json.dumps(codes, ensure_ascii=False), now)
             for theme, codes in theme_map.items()],
        )
    return len(theme_map)


def load_theme_map(trade_date: str) -> dict:
    """해당 일자의 테마 매핑. 없으면 빈 dict"""
    import json
    if not DB_PATH.exists():
        return {}
    with connect() as conn:
        try:
            rows = conn.execute(
                "SELECT theme, codes FROM theme_snapshot WHERE trade_date = ?", (trade_date,)
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
    return {r["theme"]: json.loads(r["codes"]) for r in rows}


def latest_theme_date() -> str | None:
    """가장 최근 테마 수집 일자 (당일 수집 전 임시로 직전 데이터를 쓰기 위함)"""
    if not DB_PATH.exists():
        return None
    with connect() as conn:
        try:
            row = conn.execute("SELECT MAX(trade_date) AS d FROM theme_snapshot").fetchone()
        except sqlite3.OperationalError:
            return None
    return row["d"] if row else None


def save_screening(result) -> int:
    """채점 결과 저장 (복기용). result: engine.models.DayResult"""
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    rows = []
    for c in result.candidates:
        summary = " / ".join(n for it in c.items if it.available for n in it.notes[:1])
        rows.append((result.date, c.stock.code, c.stock.name, "candidate", c.verdict,
                     round(c.pct, 1), c.earned, c.available_max, "", summary, now))
    for stock, vetoes in result.rejected:
        rows.append((result.date, stock.code, stock.name, "rejected", "",
                     0.0, 0.0, 0.0, "; ".join(v.title for v in vetoes),
                     vetoes[0].easy if vetoes else "", now))
    with connect() as conn:
        conn.execute(
            """INSERT INTO screening_day (trade_date, signal_color, signal_reasons, analyzed, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(trade_date) DO UPDATE SET
                 signal_color=excluded.signal_color, signal_reasons=excluded.signal_reasons,
                 analyzed=excluded.analyzed, created_at=excluded.created_at""",
            (result.date, result.signal.color, " | ".join(result.signal.reasons), result.analyzed, now),
        )
        conn.executemany(
            """INSERT INTO screening_result
               (trade_date, code, name, kind, verdict, pct, earned, available_max, vetoes, summary, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(trade_date, code) DO UPDATE SET
                 kind=excluded.kind, verdict=excluded.verdict, pct=excluded.pct,
                 earned=excluded.earned, available_max=excluded.available_max,
                 vetoes=excluded.vetoes, summary=excluded.summary, created_at=excluded.created_at""",
            rows,
        )
    return len(rows)
