"""시연용 '가상의 하루' — 설계서의 좋은/나쁜 유형을 하나씩 보여주는 결정적(랜덤 없음) 데이터

종목 구성:
  알파전자   — 모범 사례: A급 재료(수주 공시) + 고가권 마감 + 외인·기관 양매수 → 정상 비중 후보
  감마바이오 — 베토 4: 오후 2시 이후 수직 급등 (재료가 C급 '단독' 기사뿐인 전형적 함정)
  베타테크   — 베토 3: 장대 윗꼬리 + 힘없는 종가
  엡실론건설 — 베토 6: 투자경고 지정 (A급 재료가 있어도 위험종목은 무조건 제외)
  제타식품   — B급 재료, 차트 무난 → 점수 70점대 '관찰만'
  델타소재   — 베토 1: 차트는 괜찮은데 재료(이유) 없는 급등 → 제외
"""

from datetime import date, timedelta

DEMO_DATE = "2026-06-10"  # 수요일, 익일 이벤트 없음


def _weekdays_back(n: int, end: str = "2026-06-09") -> list[str]:
    d = date.fromisoformat(end)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out[::-1]


def _t2i(t: str) -> int:
    return int(t[:2]) * 60 + int(t[2:])


def _i2t(i: int) -> str:
    return f"{i // 60:02d}{i % 60:02d}"


def _interp(points: list[tuple[int, float]], x: int) -> float:
    if x <= points[0][0]:
        return points[0][1]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x <= x2:
            return y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    return points[-1][1]


def gen_minutes(waypoints: list[tuple[str, float]], vol_segments: list[tuple[str, str, int]],
                final_close: float, final_volume: int) -> list[dict]:
    pts = [(_t2i(t), p) for t, p in waypoints]
    out = []
    prev = pts[0][1]
    for i in range(_t2i("0900"), _t2i("1519") + 1):
        price = _interp(pts, i)
        vol = 100
        for t1, t2, v in vol_segments:
            if _t2i(t1) <= i < _t2i(t2):
                vol = v
                break
        out.append({"time": _i2t(i), "open": prev, "high": max(prev, price),
                    "low": min(prev, price), "close": price, "volume": vol})
        prev = price
    out.append({"time": "1530", "open": prev, "high": max(prev, final_close),
                "low": min(prev, final_close), "close": final_close, "volume": final_volume})
    return out


def gen_daily(days: int, start: float, end: float, volume: int, value: int,
              spike_high: float | None = None, spike_at: int = 30) -> list[dict]:
    dates = _weekdays_back(days)
    out = []
    for i in range(days):
        c = start + (end - start) * i / max(days - 1, 1)
        high = c * 1.005
        if spike_high and i == spike_at:
            high = spike_high
        out.append({"date": dates[i], "open": c * 0.995, "high": high,
                    "low": c * 0.99, "close": c, "volume": volume, "trading_value": value})
    return out


def _stock(code, name, market, prev_close, minutes, cap_eok, prev_value, today_value,
           daily_base, investor_rows, warn="00"):
    today_close = minutes[-1]["close"]
    today = {
        "date": DEMO_DATE.replace("-", ""),
        "open": minutes[0]["open"],
        "high": max(m["high"] for m in minutes),
        "low": min(m["low"] for m in minutes),
        "close": today_close,
        "volume": sum(m["volume"] for m in minutes),
        "trading_value": today_value,
    }
    daily_base[-1]["close"] = prev_close
    daily_base[-1]["trading_value"] = prev_value
    daily = daily_base + [today]
    change = (today_close - prev_close) / prev_close * 100
    row = {"code": code, "name": name, "market": market, "price": int(today_close),
           "change_rate": round(change, 1), "volume": today["volume"],
           "trading_value": today_value, "sources": "거래대금상위"}
    snapshot = {"code": code, "market_cap_eok": cap_eok, "market_warn_code": warn,
                "status_code": "55", "short_overheat_yn": "N", "halt_yn": "N",
                "delisting_yn": "N", "caution_yn": "N",
                "price": int(today_close), "trading_value": today_value}
    return row, snapshot, daily, minutes, investor_rows


def build_demo_day() -> dict:
    stocks = []

    # 알파전자 — 모범 사례 (+15%, 1300억, 오후 저점 상승, 막판 거래 재유입, 외인·기관 양매수)
    alpha_min = gen_minutes(
        waypoints=[("0900", 10300), ("0905", 10250), ("1100", 11200), ("1300", 11000),
                   ("1345", 11090), ("1400", 11080), ("1430", 11200), ("1445", 11160),
                   ("1510", 11350), ("1518", 11550), ("1519", 11520)],
        vol_segments=[("0900", "1100", 3000), ("1100", "1300", 1200),
                      ("1300", "1510", 800), ("1510", "1520", 4000)],
        final_close=11500, final_volume=50000,
    )
    stocks.append(_stock("201010", "알파전자", "KOSDAQ", 10000, alpha_min,
                         cap_eok=8000, prev_value=int(500e8), today_value=int(1300e8),
                         daily_base=gen_daily(59, 8000, 10000, 400000, int(500e8), spike_high=11000),
                         investor_rows=[{"date": "20260610", "foreign_net": 120000, "inst_net": 40000, "person_net": -150000}]))

    # 감마바이오 — 베토 4: 14시 이후 수직 급등 (+9.3%인데 상승분의 89%가 오후 2시 이후)
    gamma_min = gen_minutes(
        waypoints=[("0900", 30100), ("1400", 30300), ("1500", 32800), ("1519", 32800)],
        vol_segments=[("0900", "1400", 500), ("1400", "1520", 5000)],
        final_close=32800, final_volume=30000,
    )
    stocks.append(_stock("203030", "감마바이오", "KOSDAQ", 30000, gamma_min,
                         cap_eok=4000, prev_value=int(300e8), today_value=int(900e8),
                         daily_base=gen_daily(59, 27000, 30000, 200000, int(300e8)),
                         investor_rows=[{"date": "20260610", "foreign_net": 10000, "inst_net": -5000, "person_net": -4000}]))

    # 베타테크 — 베토 3: 장대 윗꼬리 (고가 12000 → 종가 10900)
    beta_min = gen_minutes(
        waypoints=[("0900", 10800), ("1030", 12000), ("1300", 11200), ("1519", 10920)],
        vol_segments=[("0900", "1100", 4000), ("1100", "1520", 1000)],
        final_close=10900, final_volume=20000,
    )
    stocks.append(_stock("202020", "베타테크", "KOSPI", 10000, beta_min,
                         cap_eok=5000, prev_value=int(250e8), today_value=int(800e8),
                         daily_base=gen_daily(59, 9000, 10000, 300000, int(250e8)),
                         investor_rows=[{"date": "20260610", "foreign_net": -20000, "inst_net": -10000, "person_net": 31000}]))

    # 엡실론건설 — 베토 6: 투자경고 지정
    eps_min = gen_minutes(
        waypoints=[("0900", 5100), ("1200", 5250), ("1519", 5290)],
        vol_segments=[("0900", "1520", 2000)],
        final_close=5300, final_volume=15000,
    )
    stocks.append(_stock("205050", "엡실론건설", "KOSPI", 5000, eps_min,
                         cap_eok=2500, prev_value=int(200e8), today_value=int(600e8),
                         daily_base=gen_daily(59, 4500, 5000, 500000, int(200e8)),
                         investor_rows=[{"date": "20260610", "foreign_net": 5000, "inst_net": 2000, "person_net": -7000}],
                         warn="02"))

    # 델타소재 — 베토 통과, 점수 70점대 '관찰만' (+4.2%, 고점과 멀고 소형주라 수급 제외)
    delta_min = gen_minutes(
        waypoints=[("0900", 20300), ("1000", 20100), ("1300", 20400), ("1345", 20520),
                   ("1400", 20500), ("1430", 20650), ("1445", 20620), ("1510", 20800),
                   ("1515", 21100), ("1519", 20900)],
        vol_segments=[("0900", "1300", 900), ("1300", "1520", 600)],
        final_close=20840, final_volume=8000,
    )
    stocks.append(_stock("204040", "델타소재", "KOSPI", 20000, delta_min,
                         cap_eok=1500, prev_value=int(250e8), today_value=int(350e8),
                         daily_base=gen_daily(59, 19000, 20000, 250000, int(250e8), spike_high=23000),
                         investor_rows=[{"date": "20260610", "foreign_net": -3000, "inst_net": -1000, "person_net": 4200}]))

    # 제타식품 — B급 재료(목표가 상향), 차트 무난 → '관찰만' (+7.3%)
    zeta_min = gen_minutes(
        waypoints=[("0900", 15450), ("1000", 15400), ("1300", 15800), ("1345", 15860),
                   ("1400", 15840), ("1430", 15950), ("1445", 15930), ("1510", 16050),
                   ("1515", 16200), ("1519", 16120)],
        vol_segments=[("0900", "1300", 1000), ("1300", "1510", 700), ("1510", "1520", 1400)],
        final_close=16100, final_volume=12000,
    )
    stocks.append(_stock("206060", "제타식품", "KOSPI", 15000, zeta_min,
                         cap_eok=5000, prev_value=int(300e8), today_value=int(420e8),
                         daily_base=gen_daily(59, 14000, 15000, 300000, int(300e8), spike_high=16800),
                         investor_rows=[{"date": "20260610", "foreign_net": -2000, "inst_net": 9000, "person_net": -7000}]))

    materials = {
        "201010": {"checked": True, "grade": "A", "risks": [], "evidence": [
            "공시(A급): 단일판매ㆍ공급계약체결 — 해외 2차전지 장비 320억 원",
            "기사(A급 신호): 알파전자, 유럽 배터리사와 320억 규모 공급계약 수주",
        ]},
        "203030": {"checked": True, "grade": "C", "risks": [], "evidence": [
            "기사(C급 신호): [단독] 감마바이오, 신약 기술수출 추진 중",
        ]},
        "202020": {"checked": True, "grade": "B", "risks": [], "evidence": [
            "기사(B급 신호): 증권가, 베타테크 목표가 상향 행렬",
        ]},
        "205050": {"checked": True, "grade": "A", "risks": [], "evidence": [
            "기사(A급 신호): 엡실론건설, 해외 플랜트 수주 임박",
        ]},
        "206060": {"checked": True, "grade": "B", "risks": [], "evidence": [
            "기사(B급 신호): 제타식품 목표가 상향 — K푸드 수출 성장 지속",
        ]},
        "204040": {"checked": True, "grade": None, "risks": [], "evidence": []},
    }

    # 지수 — 코스피·코스닥 모두 오후 회복형 (양호한 환경)
    kospi_min = gen_minutes(
        waypoints=[("0900", 2595), ("1000", 2580), ("1200", 2598), ("1300", 2600),
                   ("1345", 2604), ("1430", 2610), ("1510", 2615), ("1519", 2617)],
        vol_segments=[("0900", "1520", 1)], final_close=2618, final_volume=1,
    )
    kosdaq_min = gen_minutes(
        waypoints=[("0900", 848), ("1000", 845), ("1300", 851), ("1400", 853), ("1519", 855)],
        vol_segments=[("0900", "1520", 1)], final_close=856, final_volume=1,
    )

    return {
        "universe": [s[0] for s in stocks],
        "snapshots": {s[0]["code"]: s[1] for s in stocks},
        "daily": {s[0]["code"]: s[2] for s in stocks},
        "minutes": {s[0]["code"]: s[3] for s in stocks},
        "investor": {s[0]["code"]: s[4] for s in stocks},
        "materials": materials,
        "index": {
            "KOSPI": {"prev_close": 2600.0, "minutes": kospi_min},
            "KOSDAQ": {"prev_close": 850.0, "minutes": kosdaq_min},
        },
    }
