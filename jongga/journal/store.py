"""매매일지 저장 — 설계서 제9부 표준 양식

복기의 단 하나의 질문: "오늘 나는 규칙을 지켰는가?"
규칙을 지킨 손실은 비용이고, 규칙을 어긴 수익은 부채다 — 그래서 위반 여부를 손익과 따로 기록한다.
"""
from datetime import datetime

from jongga.db import connect, init_db
from jongga.settings import cfg


def current_one_r() -> int:
    """지금 설정 기준 1R(원). 기록 시점에 고정 저장해 나중에 설정을 바꿔도 과거 R이 안 변한다."""
    return int(cfg("account.total_asset", 10_000_000) * cfg("account.risk_per_trade_pct", 0.4) / 100)


def add_entry(trade_date: str, code: str, name: str, buy_price: float, quantity: int,
              score_pct: float | None = None, material_grade: str = "",
              after_hours: str = "", one_r: int | None = None) -> int:
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    one_r = one_r or current_one_r()
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO trade_journal
               (trade_date, code, name, score_pct, material_grade, buy_price, quantity,
                amount, one_r, after_hours, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
            (trade_date, code, name, score_pct, material_grade, buy_price, quantity,
             int(buy_price * quantity), one_r, after_hours, now, now),
        )
        return cur.lastrowid


def close_entry(entry_id: int, exit_date: str, exit_price: float,
                rule_violation: bool = False, violation_note: str = "", lesson: str = "") -> dict | None:
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        row = conn.execute("SELECT * FROM trade_journal WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return None
        pnl_amount = int((exit_price - row["buy_price"]) * row["quantity"])
        pnl_r = pnl_amount / row["one_r"] if row["one_r"] else 0.0
        conn.execute(
            """UPDATE trade_journal SET exit_date=?, exit_price=?, pnl_amount=?, pnl_r=?,
               rule_violation=?, violation_note=?, lesson=?, status='closed', updated_at=?
               WHERE id=?""",
            (exit_date, exit_price, pnl_amount, round(pnl_r, 2),
             1 if rule_violation else 0, violation_note, lesson, now, entry_id),
        )
        return dict(conn.execute("SELECT * FROM trade_journal WHERE id = ?", (entry_id,)).fetchone())


def delete_entry(entry_id: int) -> None:
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM trade_journal WHERE id = ?", (entry_id,))


def list_entries(status: str | None = None, limit: int = 300) -> list[dict]:
    """최신순. status: open / closed / None(전체)"""
    init_db()
    query = "SELECT * FROM trade_journal "
    params: tuple = ()
    if status:
        query += "WHERE status = ? "
        params = (status,)
    query += "ORDER BY trade_date DESC, id DESC LIMIT ?"
    with connect() as conn:
        return [dict(r) for r in conn.execute(query, params + (limit,)).fetchall()]


def recent_screening_candidates(limit: int = 20) -> list[dict]:
    """일지 입력 폼의 자동 채움용 — 최근 추천 후보 (날짜·종목·점수)"""
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """SELECT trade_date, code, name, verdict, pct FROM screening_result
               WHERE kind = 'candidate' AND verdict IN ('full', 'half')
               ORDER BY trade_date DESC, pct DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
