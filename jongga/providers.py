"""데이터 공급자 — 엔진은 공급자 인터페이스만 알고, 출처(실시간 API/시연 데이터/DB)는 모른다

공급자 규약 (모든 메서드는 실패 시 빈 값을 반환해 '확인 불가' 처리로 이어진다):
  universe() -> list[dict]            오늘 돈이 몰린 종목
  snapshot(code) -> dict              현재가·시총·경보 플래그 (kis.api.current_price 형태)
  daily(code) -> list[dict]           과거→오늘 일봉
  minutes(code) -> list[dict]         당일 분봉
  investor(code) -> list[dict]        일별 수급
  index() -> dict                     {"KOSPI": {prev_close, minutes}, "KOSDAQ": ...}
  theme_map() -> dict                 테마명 -> 종목코드 목록 (M3 합류 전엔 빈 dict)
"""
import sys
from datetime import date, timedelta


class DemoProvider:
    """내장 시연 데이터 — 네트워크·API 키 없이 엔진 전체를 돌려본다"""

    def __init__(self):
        from jongga.demo import build_demo_day
        self.day = build_demo_day()

    def universe(self):
        return self.day["universe"]

    def snapshot(self, code):
        return self.day["snapshots"].get(code, {})

    def daily(self, code):
        return self.day["daily"].get(code, [])

    def minutes(self, code):
        return self.day["minutes"].get(code, [])

    def investor(self, code):
        return self.day["investor"].get(code, [])

    def index(self):
        return self.day["index"]

    def theme_map(self):
        return {}


class LiveProvider:
    """한국투자증권 API 실시간 — 당일 기준"""

    def __init__(self):
        from jongga.kis.client import KisClient
        self.client = KisClient()

    def universe(self):
        from jongga.universe import collect_universe
        return collect_universe(self.client)

    def snapshot(self, code):
        from jongga.kis.api import current_price
        return current_price(self.client, code)

    def daily(self, code):
        from jongga.kis.api import daily_candles
        end = date.today()
        start = end - timedelta(days=150)
        return daily_candles(self.client, code, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))

    def minutes(self, code):
        from jongga.kis.api import minute_candles
        try:
            return minute_candles(self.client, code)
        except Exception as exc:  # 분봉 실패는 '확인 불가'로 처리하고 계속
            print(f"(안내) {code} 분봉 조회 실패 — 해당 항목은 확인 불가 처리: {exc}", file=sys.stderr)
            return []

    def investor(self, code):
        from jongga.kis.api import investor_trend
        try:
            return investor_trend(self.client, code)
        except Exception as exc:
            print(f"(안내) {code} 수급 조회 실패 — 해당 항목은 확인 불가 처리: {exc}", file=sys.stderr)
            return []

    def index(self):
        from jongga.kis.api import index_minutes, index_price
        out = {}
        for code, name in (("0001", "KOSPI"), ("1001", "KOSDAQ")):
            try:
                price = index_price(self.client, code)
                minutes = index_minutes(self.client, code)
                out[name] = {"prev_close": price["prev_close"], "minutes": minutes}
            except Exception as exc:
                print(f"(안내) {name} 지수 조회 실패 — 시장 판단 일부 제한: {exc}", file=sys.stderr)
        return out

    def theme_map(self):
        return {}  # M3에서 네이버 테마 수집으로 채움
