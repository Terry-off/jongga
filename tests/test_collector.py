"""M5 일일 수집기 + 과거 재현(DBProvider) 통합 테스트 (네트워크 불필요)

시연 데이터를 가짜 공급자로 감싸 수집 → DB 저장 → DBProvider로 되읽어
파이프라인 결과가 원본(DemoProvider)과 동일하게 재현되는지 검증한다.
"""
import unittest

from jongga import settings
from jongga.demo import DEMO_DATE, build_demo_day
from jongga.engine import pipeline


class _FakeLive:
    """DemoProvider처럼 동작하되 collector가 부르는 인터페이스를 그대로 노출"""

    def __init__(self):
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

    def material_enabled(self):
        return True

    def materials(self, code, name):
        return self.day["materials"].get(code)


class TestCollectAndReplay(unittest.TestCase):
    def setUp(self):
        if settings.DB_PATH.exists():
            settings.DB_PATH.unlink()

    def tearDown(self):
        if settings.DB_PATH.exists():
            settings.DB_PATH.unlink()

    def _collect(self):
        from jongga.collector import collect_day
        from jongga.db import save_theme_map
        collect_day(provider=_FakeLive(), trade_date=DEMO_DATE,
                    with_themes=False, log=lambda *_: None)
        # 테마는 별도 경로이므로 시연 테마를 직접 저장
        save_theme_map(DEMO_DATE, build_demo_day()["themes"])

    def test_dbprovider_reproduces_demo_result(self):
        self._collect()
        from jongga.providers import DBProvider
        db_result = pipeline.run(DBProvider(DEMO_DATE), trade_date=DEMO_DATE)

        from jongga.providers import DemoProvider
        demo_result = pipeline.run(DemoProvider(), trade_date=DEMO_DATE)

        # 같은 후보가 같은 점수로 재현되어야 한다
        db_cands = {c.stock.code: round(c.pct, 1) for c in db_result.candidates}
        demo_cands = {c.stock.code: round(c.pct, 1) for c in demo_result.candidates}
        self.assertEqual(db_cands, demo_cands)
        # 알파전자가 대장주로 재현 (테마·재료까지 저장·복원됨)
        alpha = next(c for c in db_result.candidates if c.stock.code == "201010")
        self.assertEqual(alpha.verdict, "full")
        self.assertTrue(alpha.stock.is_theme_leader)
        self.assertEqual(alpha.available_max, 100)

    def test_collected_dates_and_missing(self):
        self._collect()
        from jongga.db import collected_dates
        self.assertIn(DEMO_DATE, collected_dates())

        from jongga.providers import DBProvider
        self.assertFalse(DBProvider("1999-01-01").has_data())

    def test_minutes_and_materials_persisted(self):
        self._collect()
        from jongga.db import load_stock_collect
        stocks = load_stock_collect(DEMO_DATE)
        self.assertGreater(len(stocks["201010"]["minutes"]), 300)   # 분봉 보존
        self.assertEqual(stocks["201010"]["materials"]["grade"], "A")  # 재료 보존


if __name__ == "__main__":
    unittest.main()
