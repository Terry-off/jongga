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


class HistoricalProvider:
    """저장본이 없는 과거 날짜를 API로 '재구성'한다 — 사용자가 아무 날짜나 조회 가능하게

    그날 기준으로 다시 만들 수 있는 것: 유니버스(KRX 전종목 시세)·일봉·수급(KIS)·
    공시(DART)·테마(그날 수집분이 있으면). 분봉은 KIS 제공 범위(최근 영업일) 안에서만.
    복구 불가능한 것(거래소 경보 이력·지수 분봉·시간외)은 '확인 불가'로 정직하게 처리.
    """

    NEWS_RELIABLE_DAYS = 3  # 이보다 오래된 날짜는 뉴스 검색이 안 닿음 → 공시만 사용

    def __init__(self, trade_date: str):
        from jongga.kis.client import KisClient
        self.date = trade_date                       # YYYY-MM-DD
        self.ymd = trade_date.replace("-", "")
        self.client = KisClient()
        self._universe: list | None = None
        self._krx: dict = {}
        self._material_engine = None

    def _days_ago(self) -> int:
        from datetime import date as _date
        return (_date.today() - _date.fromisoformat(self.date)).days

    def universe(self):
        if self._universe is None:
            from jongga import krx
            from jongga.settings import cfg
            result = krx.fetch_day_detailed(self.ymd)
            if not result.rows:
                print(f"(진단) {self.date} KRX 조회 결과: status={result.status} / {result.detail}",
                      file=sys.stderr)
                if result.status == "empty":
                    raise RuntimeError(
                        f"{self.date}은 휴장일로 보여요 — 그날 거래된 종목이 없어요 "
                        "(주말·공휴일·임시휴장일). 거래가 있었던 평일을 선택해주세요.")
                raise RuntimeError(
                    f"{self.date}의 시장 데이터를 거래소(KRX)에서 받지 못했어요. "
                    f"원인: {result.detail or '알 수 없음'}. "
                    "잠시 후 다시 시도하거나 인터넷 연결을 확인해주세요.")
            self._krx = {r["code"]: r for r in result.rows}
            self._universe = krx.build_universe(result.rows, cfg)
        return self._universe

    def snapshot(self, code):
        # 경보·과열 플래그는 과거 이력 조회가 불가 → 비워서 '확인 불가' (재구성의 한계)
        r = self._krx.get(code, {})
        return {"code": code, "price": r.get("price", 0), "market": r.get("market", ""),
                "trading_value": r.get("trading_value", 0),
                "market_cap_eok": r.get("market_cap_eok", 0)}

    def daily(self, code):
        from datetime import date as _date
        from datetime import timedelta
        from jongga.kis.api import daily_candles
        end = _date.fromisoformat(self.date)
        start = end - timedelta(days=150)
        try:
            return daily_candles(self.client, code, start.strftime("%Y%m%d"), self.ymd)
        except Exception as exc:
            print(f"(안내) {code} 일봉 조회 실패: {exc}", file=sys.stderr)
            return []

    def minutes(self, code):
        from jongga.kis.api import minute_candles_on
        try:
            return minute_candles_on(self.client, code, self.ymd)
        except Exception:
            return []  # 제공 범위 밖 → '확인 불가'

    def investor(self, code):
        from jongga.kis.api import investor_trend
        try:
            rows = investor_trend(self.client, code)
            return [r for r in rows if r["date"] <= self.ymd]
        except Exception:
            return []

    def index(self):
        return {}  # 과거 지수 분봉은 복구 불가 → 시장 항목은 이벤트만 반영

    def theme_map(self):
        from jongga.db import load_theme_map
        return load_theme_map(self.date)

    def material_enabled(self):
        from jongga.material.engine import enabled
        return enabled()

    def materials(self, code, name):
        from datetime import datetime as _dt
        from jongga.material.engine import MaterialEngine
        old = self._days_ago() > self.NEWS_RELIABLE_DAYS
        if self._material_engine is None:
            self._material_engine = MaterialEngine(
                trade_date=_dt.fromisoformat(self.date + "T15:30"), use_news=not old)
        res = self._material_engine.evaluate(code, name)
        if old and res.get("checked") and res.get("grade") is None:
            # 공시만 확인한 상태에서 '없음' 판정은 과하다 → 확인 불가로 완화 (베토 1 방지)
            res["checked"] = False
        return res


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
