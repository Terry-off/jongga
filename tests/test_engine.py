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
        self.assertEqual(alpha.stock.material_grade, "A")
        # 테마 동조만 확인 불가 → 만점 85점 기준
        self.assertEqual(alpha.available_max, 85)

    def test_zeta_is_watch_only(self):
        zeta = next(c for c in self.result.candidates if c.stock.code == "206060")
        self.assertEqual(zeta.verdict, "watch")
        self.assertEqual(zeta.position_amount, 0)
        self.assertEqual(zeta.available_max, 85)

    def test_veto_reasons(self):
        rejected = {s.code: [v.code for v in vetoes] for s, vetoes in self.result.rejected}
        self.assertIn("V4", rejected["203030"])  # 감마바이오: 막판 수직 급등
        self.assertIn("V3", rejected["202020"])  # 베타테크: 장대 윗꼬리
        self.assertIn("V6", rejected["205050"])  # 엡실론건설: 투자경고 (A급 재료여도 제외)
        self.assertIn("V1", rejected["204040"])  # 델타소재: 재료 없는 급등

    def test_no_stock_slips_through(self):
        total = len(self.result.candidates) + len(self.result.rejected)
        self.assertEqual(total, self.result.analyzed)


class TestFridayRule(unittest.TestCase):
    def test_friday_caps_a_grade_to_half(self):
        # 2026-06-12은 금요일 — A급+85점(알파전자)만 살아남되 절반 비중으로 제한
        result = pipeline.run(DemoProvider(), trade_date="2026-06-12")
        survivors = [c for c in result.candidates if c.verdict in ("full", "half")]
        self.assertEqual([c.stock.code for c in survivors], ["201010"])
        self.assertEqual(survivors[0].verdict, "half")
        rejected = {s.code: [v.code for v in vetoes] for s, vetoes in result.rejected}
        self.assertIn("V8", rejected["206060"])  # B급 제타식품은 금요일 탈락


class TestMaterialRules(unittest.TestCase):
    def test_news_grading_priority(self):
        from jongga.material import rules
        grade, hits = rules.grade_news_titles([
            "[단독] OO전자, 신사업 추진 검토",          # C
            "OO전자, 320억 규모 공급계약 수주",          # A
            "증권가 OO전자 목표가 상향",                 # B
        ])
        self.assertEqual(grade, "A")
        self.assertEqual(len(hits), 3)

    def test_no_keyword_no_grade(self):
        from jongga.material import rules
        grade, hits = rules.grade_news_titles(["OO전자 주가 5% 상승 마감"])
        self.assertIsNone(grade)
        self.assertEqual(hits, [])

    def test_dart_risk_detection(self):
        from jongga.material import rules
        risks = rules.dart_risk_titles(["주요사항보고서(유상증자결정)", "단일판매ㆍ공급계약체결"])
        self.assertEqual(len(risks), 1)
        self.assertIn("유상증자", risks[0])

    def test_c_grade_needs_companions(self):
        # C급인데 종가가 고가권이 아니면 재료 인정 취소 → 베토 1 대상
        from jongga.engine.models import DayContext, MarketSignal, StockView
        stock = StockView(code="000001", name="테스트", market="KOSPI", price=10000,
                          change_rate=5.0, trading_value=int(400e8), market_cap_eok=1000,
                          value_rank=10, minutes=[], investor=[], flags={},
                          daily=[{"date": "d", "open": 9800, "high": 10500, "low": 9700,
                                  "close": 10000, "volume": 1, "trading_value": int(400e8)}],
                          material_grade="C", material_checked=True)
        ctx = DayContext(date="2026-06-10", weekday=2, events_tomorrow=[], pre_holiday=False,
                         signal=MarketSignal("green", []), cfg=cfg)
        pipeline._validate_material(stock, ctx)
        self.assertIsNone(stock.material_grade)
        self.assertIn("고가권", stock.material_note)

    def test_corp_zip_parsing(self):
        import io
        import zipfile
        from jongga.material.dart import parse_corp_zip
        xml = ('<?xml version="1.0" encoding="UTF-8"?><result>'
               '<list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name>'
               '<stock_code>005930</stock_code></list>'
               '<list><corp_code>99999999</corp_code><corp_name>비상장사</corp_name>'
               '<stock_code> </stock_code></list></result>')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("CORPCODE.xml", xml)
        mapping = parse_corp_zip(buf.getvalue())
        self.assertEqual(mapping, {"005930": "00126380"})


if __name__ == "__main__":
    unittest.main()
