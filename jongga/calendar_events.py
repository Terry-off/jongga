"""이벤트 캘린더 — 매크로 이벤트·휴장일 (config/calendar.yaml + 추후 DB 사용자 추가분)"""
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from jongga.settings import BASE_DIR

CALENDAR_PATH = BASE_DIR / "config" / "calendar.yaml"


@lru_cache(maxsize=1)
def _load() -> dict:
    if not Path(CALENDAR_PATH).exists():
        return {"macro_events": [], "holidays": set()}
    with open(CALENDAR_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return {
        "macro_events": [{"date": str(e["date"]), "name": str(e["name"])} for e in raw.get("macro_events", [])],
        "holidays": {str(h) for h in raw.get("holidays", [])},
    }


def is_holiday(d: date) -> bool:
    return d.weekday() >= 5 or d.isoformat() in _load()["holidays"]


def next_trading_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    while is_holiday(nxt):
        nxt += timedelta(days=1)
    return nxt


def prev_trading_day(d: date) -> date:
    prev = d - timedelta(days=1)
    while is_holiday(prev):
        prev -= timedelta(days=1)
    return prev


def events_for_next_session(d: date) -> list[str]:
    """오늘(d) 이후 다음 거래일까지 사이에 걸린 이벤트 — 베토 7 판정용"""
    end = next_trading_day(d)
    found = []
    for e in _load()["macro_events"]:
        if d.isoformat() < e["date"] <= end.isoformat():
            found.append(e["name"])
    return found


def is_pre_holiday(d: date) -> bool:
    """내일(달력 기준)이 한국 휴장일인가 — '연휴 전일' 판정 (금요일은 별도 처리)"""
    nxt = d + timedelta(days=1)
    return nxt.isoformat() in _load()["holidays"]
