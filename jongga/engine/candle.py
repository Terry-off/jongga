"""캔들·분봉 순수 계산 함수 — 외부 의존 없음, 단위 테스트 대상"""


def upper_shadow_ratio(high: float, low: float, close: float) -> float:
    """윗꼬리 ÷ 당일 전체 변동폭 (0~1)"""
    rng = high - low
    return (high - close) / rng if rng > 0 else 0.0


def close_position(high: float, low: float, close: float) -> float:
    """(종가-저가) ÷ (고가-저가). 1.0 = 최고가 마감"""
    rng = high - low
    return (close - low) / rng if rng > 0 else 1.0


def sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def late_gain_share(minutes: list[dict], prev_close: float, cutoff: str = "1400") -> float | None:
    """14시 이후 상승분 ÷ 당일 전체 상승분 (베토 4)"""
    before = [m for m in minutes if m["time"] <= cutoff]
    if not before or not minutes or prev_close <= 0:
        return None
    total = minutes[-1]["close"] - prev_close
    if total <= 0:
        return 0.0
    return max(0.0, (minutes[-1]["close"] - before[-1]["close"]) / total)


def afternoon_low_steps(minutes: list[dict], start: str = "1300", end: str = "1515", parts: int = 3) -> int | None:
    """오후 구간을 N등분해 저점이 단계적으로 높아진 횟수 (0~parts-1)"""
    seg = [m for m in minutes if start <= m["time"] < end]
    if len(seg) < parts * 3:
        return None
    n = len(seg)
    lows = [min(m["low"] for m in seg[i * n // parts:(i + 1) * n // parts]) for i in range(parts)]
    return sum(1 for i in range(1, parts) if lows[i] > lows[i - 1])


def volume_reinflow_ratio(minutes: list[dict], base: tuple = ("1300", "1500"), late: tuple = ("1510", "1520")) -> float | None:
    """15:10 이후 분당 거래량 ÷ 오후 평소 분당 거래량"""
    b = [m["volume"] for m in minutes if base[0] <= m["time"] < base[1]]
    l = [m["volume"] for m in minutes if late[0] <= m["time"] < late[1]]
    if not b or not l:
        return None
    avg_b = sum(b) / len(b)
    return (sum(l) / len(l)) / avg_b if avg_b > 0 else None


def vwap(minutes: list[dict]) -> float | None:
    """거래량 가중 평균가 — 오늘 산 사람들의 평균 단가"""
    total_vol = sum(m["volume"] for m in minutes)
    if total_vol <= 0:
        return None
    return sum(m["close"] * m["volume"] for m in minutes) / total_vol


def afternoon_new_low(minutes: list[dict], cutoff: str = "1400") -> bool | None:
    """오후에 당일 최저가를 갱신하고 저가권에서 마감했는가 (지수 약세 판정)"""
    after = [m for m in minutes if m["time"] >= cutoff]
    if not after or not minutes:
        return None
    day_low = min(m["low"] for m in minutes)
    day_high = max(m["high"] for m in minutes)
    rng = day_high - day_low
    if rng <= 0:
        return False
    weak_close = (minutes[-1]["close"] - day_low) / rng < 0.25
    return min(m["low"] for m in after) <= day_low and weak_close
