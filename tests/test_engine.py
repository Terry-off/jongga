"""M2 판단 엔진 테스트 — 네트워크·API 키 없이 실행 가능

실행: python -m unittest discover tests -v
"""
import unittest
from datetime import date

from jongga import calendar_events
from jongga.demo import DEMO_DATE
from jongga.engine import candle, pipeline
from jongga.engine.position import position_amount
from jongga.engine.score import verdict
from jongga.providers import DemoProvider
from jongga.settings import cfg


class TestCandleMath(unittest.TestCase):
    def test_upper_shadow(self):
        # 고가 12000, 저가 10800, 종가 10900 → 윗꼬리가 변동폭의 92%
        self.assertAlmostEqual(candle.upper_shadow_ratio(12000, 10800, 10900), 1100 / 1200)

    def test_close_position(self):
        self.assertAlmostEqual(candle.close_position(11550, 10250, 11500), 1250 / 1300)
        self.assertEqual(candle.close_position(100, 100, 100), 1.0)  # 변동 없음 = 고가권 취급

    def test_late_gain_share(self):
        minutes = [
            {"time": "0900", "close": 10100},
            {"time": "1400", "close": 10100},
            {"time": "1500", "close": 11000},
        ]
        # 전일 종가 10000 → 총 상승 1000 중 900이 14시 이후
        self.assertAlmostEqual(candle.late_gain_share(minutes, 10000), 0.9)

    def test_vwap(self):
        minutes = [{"time": "0900", "close": 100, "volume": 10}, {"time": "0901", "close": 200, "volume": 10}]
        self.assertAlmostEqual(candle.vwap(minutes), 150)


class TestVerdictAndPosition(unittest.TestCase):
    def test_verdict_tiers(self):
        self.assertEqual(verdict(92.0, cfg)[0], "full")
        self.assertEqual(verdict(80.0, cfg)[0], "half")
        self.assertEqual(verdict(70.0, cfg)[0], "watch")
        self.assertEqual(verdict(50.0, cfg)[0], "exclude")

    def test_position_amount(self):
        # 계좌 1,000만 × 1R 0.4% = 4만 → 테마주(-10% 가정) 최대 40만
        self.assertEqual(position_amount(cfg, "midsmall", "full"), 400_000)
        self.assertEqual(position_amount(cfg, "midsmall", "half"), 200_000)
        # 대형주(-5% 가정) 최대 80만
        self.assertEqual(position_amount(cfg, "large", "full"), 800_000)
        self.assertEqual(position_amount(cfg, "large", "watch"), 0)


class TestCalendar(unittest.TestCase):
    def test_fomc_blocks_previous_day(self):
        # 2026-06-18 새벽 FOMC → 6/17 매매분에 베토 7
        self.assertTrue(calendar_events.events_for_next_session(date(2026, 6, 17)))
        self.assertFalse(calendar_events.events_for_next_session(date(2026, 6, 10)))

    def test_pre_holiday(self):
        self.assertTrue(calendar_events.is_pre_holiday(date(2026, 5, 4)))   # 어린이날 전날
        self.assertFalse(calendar_events.is_pre_holiday(date(2026, 6, 10)))

    def test_next_trading_day_skips_weekend(self):
        self.assertEqual(calendar_events.next_trading_day(date(2026, 6, 12)), date(2026, 6, 15))


class TestDemoPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = pipeline.run(DemoProvider(), trade_date=DEMO_DATE)

    def test_signal_green(self):
        self.assertEqual(self.result.signal.color, "green")
        self.assertTrue(self.result.signal.index_available)

    def test_alpha_is_full_weight_candidate(self):
        alpha = next(c for c in self.result.candidates if c.stock.code == "201010")
        self.assertEqual(alpha.verdict, "full")
        self.assertGreaterEqual(alpha.pct, 85)
        self.assertEqual(alpha.position_amount, 400_000)
        # 재료·테마는 M2에서 확인 불가 → 만점 65점 기준
        self.assertEqual(alpha.available_max, 65)

    def test_delta_is_watch_only(self):
        delta = next(c for c in self.result.candidates if c.stock.code == "204040")
        self.assertEqual(delta.verdict, "watch")
        self.assertEqual(delta.position_amount, 0)
        # 소형주라 수급 항목도 제외 → 55점 만점
        self.assertEqual(delta.available_max, 55)

    def test_veto_reasons(self):
        rejected = {s.code: [v.code for v in vetoes] for s, vetoes in self.result.rejected}
        self.assertIn("V4", rejected["203030"])  # 감마바이오: 막판 수직 급등
        self.assertIn("V3", rejected["202020"])  # 베타테크: 장대 윗꼬리
        self.assertIn("V6", rejected["205050"])  # 엡실론건설: 투자경고

    def test_no_stock_slips_through(self):
        total = len(self.result.candidates) + len(self.result.rejected)
        self.assertEqual(total, self.result.analyzed)


class TestFridayRule(unittest.TestCase):
    def test_friday_blocks_everything_without_a_grade(self):
        # 2026-06-12은 금요일 — 재료 등급을 모르는 M2에서는 전 종목이 베토 8
        result = pipeline.run(DemoProvider(), trade_date="2026-06-12")
        self.assertEqual(len(result.candidates), 0)
        for _, vetoes in result.rejected:
            self.assertIn("V8", [v.code for v in vetoes])


if __name__ == "__main__":
    unittest.main()
