"""시장 신호등 — 매매 금지일 판정 (DESIGN.md 4.1)"""
from jongga.engine import candle
from jongga.engine.models import MarketSignal


def judge(index_data: dict, events_tomorrow: list[str], pre_holiday: bool,
          theme_available: bool = False, sector_sync_exists: bool | None = None) -> MarketSignal:
    """index_data: {"KOSPI": {"prev_close": float, "minutes": [...]}, "KOSDAQ": {...}}"""
    red, yellow = [], []
    day_pct = closed_strong = higher_lows = None
    index_available = False

    for name, label in (("KOSPI", "코스피"), ("KOSDAQ", "코스닥")):
        data = index_data.get(name) or {}
        minutes = data.get("minutes") or []
        # 분봉이 오전부터 충분히 있어야 '오후 약세' 판정 가능
        if not minutes or minutes[0]["time"] > "1000":
            continue
        index_available = True
        weak = candle.afternoon_new_low(minutes)
        if weak:
            red.append(f"{label}가 오후에도 계속 바닥을 낮추며 마감했어요 — 시장 전체가 위험 회피 중")
        if name == "KOSPI":
            prev = data.get("prev_close") or 0
            last = minutes[-1]["close"]
            if prev > 0:
                day_pct = (last - prev) / prev * 100
            day_high = max(m["high"] for m in minutes)
            day_low = min(m["low"] for m in minutes)
            closed_strong = candle.close_position(day_high, day_low, last) >= 0.5
            steps = candle.afternoon_low_steps(minutes)
            higher_lows = steps is not None and steps >= 2

    if events_tomorrow:
        red.append(f"내일 {', '.join(events_tomorrow)} — 밤사이 결과가 모든 종목의 갭을 결정해요. 쉬는 날이에요")
    if theme_available and sector_sync_exists is False:
        red.append("오늘은 함께 오르는 주도 테마가 없어요 — 내일까지 이어질 힘이 없는 날이에요")
    if pre_holiday:
        yellow.append("내일은 휴장일이에요 — 들고 가는 시간이 길어져서 더 보수적으로 봐야 해요")
    if not index_available:
        yellow.append("지수 분봉을 확인할 수 없어 시장 환경 판단이 제한돼요")

    if red:
        color, reasons = "red", red + yellow
    elif yellow:
        color, reasons = "yellow", yellow
    else:
        color, reasons = "green", ["시장이 안정적이고 내일 예정된 큰 발표가 없어요"]

    return MarketSignal(color=color, reasons=reasons, day_pct=day_pct,
                        closed_strong=closed_strong, afternoon_higher_lows=higher_lows,
                        index_available=index_available)
