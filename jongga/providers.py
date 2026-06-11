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
        return self.day.get("themes", {})

    def material_enabled(self):
        return True

    def materials(self, code, name):
        return self.day["materials"].get(code)


class DBProvider:
    """저장된 일자를 그대로 재현 — 과거 날짜 조회 (collector가 적재한 데이터)

    수집되지 않은 항목은 빈 값을 돌려 '확인 불가'로 정직하게 처리한다.
    """

    def __init__(self, trade_date: str):
        from jongga.db import (load_index_collect, load_stock_collect,
                               load_theme_map, load_universe)
        self.date = trade_date
        self._universe = load_universe(trade_date)
        self._stocks = load_stock_collect(trade_date)
        self._index = load_index_collect(trade_date)
        self._themes = load_theme_map(trade_date)
        self._has_materials = any(v.get("materials") for v in self._stocks.values())

    def has_data(self) -> bool:
        return bool(self._universe)

    def universe(self):
        return self._universe

    def snapshot(self, code):
        return (self._stocks.get(code) or {}).get("snapshot") or {}

    def daily(self, code):
        return (self._stocks.get(code) or {}).get("daily") or []

    def minutes(self, code):
        return (self._stocks.get(code) or {}).get("minutes") or []

    def investor(self, code):
        return (self._stocks.get(code) or {}).get("investor") or []

    def index(self):
        return self._index

    def theme_map(self):
        return self._themes

    def material_enabled(self):
        return self._has_materials

    def materials(self, code, name):
        return (self._stocks.get(code) or {}).get("materials")


class LiveProvider:
    """한국투자증권 API 실시간 — 당일 기준"""

    def __init__(self):
        from jongga.kis.client import KisClient
        self.client = KisClient()
        self._material_engine = None

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
        """오늘 수집된 테마맵을 DB에서 읽는다. 없으면 가장 최근 수집분으로 대체.
        둘 다 없으면 빈 dict → '테마 확인 불가'로 우아하게 후퇴 (collect-themes 안내)."""
        from datetime import date as _date
        from jongga.db import latest_theme_date, load_theme_map
        today = _date.today().isoformat()
        themes = load_theme_map(today)
        if themes:
            return themes
        recent = latest_theme_date()
        if recent:
            print(f"(안내) 오늘 테마 수집분이 없어 {recent} 수집분으로 대체합니다 "
                  f"(최신화: python -m jongga collect-themes)", file=sys.stderr)
            return load_theme_map(recent)
        print("(안내) 테마 데이터가 없습니다 — 테마 항목은 '확인 불가'로 처리됩니다 "
              "(수집: python -m jongga collect-themes)", file=sys.stderr)
        return {}

    def material_enabled(self):
        from jongga.material.engine import enabled
        return enabled()

    def materials(self, code, name):
        from jongga.material.engine import MaterialEngine
        if not self.material_enabled():
            return None
        if self._material_engine is None:
            self._material_engine = MaterialEngine()
        return self._material_engine.evaluate(code, name)
