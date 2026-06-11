"""테마 수집 파서 + 동조/대장주 리졸버 테스트 (네트워크 불필요)"""
import unittest

from jongga.settings import cfg
from jongga.theme import scraper
from jongga.theme.resolver import ThemeResolver

# 네이버 테마 목록 페이지 일부를 본뜬 픽스처
THEME_LIST_HTML = """
<table class="type_1 theme">
  <tr><td class="col_type1">
    <a href="/sise/sise_group_detail.naver?type=theme&no=446">2차전지</a></td></tr>
  <tr><td class="col_type1">
    <a href="/sise/sise_group_detail.naver?type=theme&amp;no=64">바이오</a></td></tr>
  <tr><td class="col_type1">
    <a href="/sise/sise_group_detail.naver?type=theme&no=446">2차전지</a></td></tr>
</table>
"""

# 테마 상세 페이지 일부를 본뜬 픽스처 (class="tltle"는 네이버 실제 클래스)
THEME_DETAIL_HTML = """
<table class="type_5">
  <tr><td class="name">
    <a href="/item/main.naver?code=373220" class="tltle">LG에너지솔루션</a></td></tr>
  <tr><td class="name">
    <a href="/item/main.naver?code=006400" class="tltle">삼성SDI</a></td></tr>
  <tr><td class="name">
    <a href="/item/main.naver?code=373220" class="tltle">LG에너지솔루션</a></td></tr>
</table>
"""


class TestThemeParser(unittest.TestCase):
    def test_parse_theme_list_dedupes(self):
        themes = scraper.parse_theme_list(THEME_LIST_HTML)
        self.assertEqual(themes, [("446", "2차전지"), ("64", "바이오")])

    def test_parse_theme_detail_dedupes(self):
        members = scraper.parse_theme_detail(THEME_DETAIL_HTML)
        self.assertEqual(members, [("373220", "LG에너지솔루션"), ("006400", "삼성SDI")])

    def test_parse_empty(self):
        self.assertEqual(scraper.parse_theme_list("<html></html>"), [])
        self.assertEqual(scraper.parse_theme_detail("<html></html>"), [])


def _uni(code, change, value_eok):
    return {"code": code, "name": code, "change_rate": change, "trading_value": int(value_eok * 1e8)}


class _Stock:
    def __init__(self, code):
        self.code = code
        self.theme = None
        self.theme_sync_count = 0
        self.is_theme_leader = False
        self.theme_leader_3d_gain = 0.0


class TestThemeResolver(unittest.TestCase):
    def test_leader_and_sync(self):
        universe = [_uni("AAA", 12.0, 1000), _uni("BBB", 8.0, 600), _uni("CCC", 4.0, 300)]
        theme_map = {"테마": ["AAA", "BBB", "CCC", "DDD"]}  # DDD는 유니버스에 없음
        r = ThemeResolver(theme_map, universe, cfg)
        a = _Stock("AAA")
        r.annotate(a)
        self.assertEqual(a.theme, "테마")
        self.assertEqual(a.theme_sync_count, 3)   # AAA·BBB·CCC 모두 ≥3%·≥50억
        self.assertTrue(a.is_theme_leader)        # 거래대금 1위 + 상승률 1위

    def test_follower_not_leader(self):
        universe = [_uni("AAA", 12.0, 1000), _uni("BBB", 8.0, 600), _uni("CCC", 4.0, 300)]
        r = ThemeResolver({"테마": ["AAA", "BBB", "CCC"]}, universe, cfg)
        b = _Stock("BBB")
        r.annotate(b)
        self.assertFalse(b.is_theme_leader)

    def test_value_leader_must_be_top3_change(self):
        # 거래대금 1위지만 상승률이 4위로 밀리면 대장주 아님
        universe = [_uni("BIG", 2.0, 2000), _uni("X", 10, 100), _uni("Y", 9, 100),
                    _uni("Z", 8, 100)]
        r = ThemeResolver({"테마": ["BIG", "X", "Y", "Z"]}, universe, cfg)
        big = _Stock("BIG")
        r.annotate(big)
        self.assertFalse(big.is_theme_leader)

    def test_follower_gets_leader_3d_gain(self):
        # 후발주에 대장주의 3일 상승률이 실려 과열 베토(V5) 판단에 쓰인다
        universe = [_uni("LEAD", 12.0, 1000), _uni("FOLLOW", 5.0, 300), _uni("MID", 6.0, 300)]
        # 오늘(-1) 대비 3거래일 전(-4) 종가로 누적 상승률을 잰다: 130 vs 105
        leader_daily = [{"close": 100}, {"close": 105}, {"close": 110},
                        {"close": 120}, {"close": 130}]
        r = ThemeResolver({"테마": ["LEAD", "FOLLOW", "MID"]}, universe, cfg,
                          daily_fn=lambda c: leader_daily if c == "LEAD" else [])
        f = _Stock("FOLLOW")
        r.annotate(f)
        self.assertFalse(f.is_theme_leader)
        self.assertAlmostEqual(f.theme_leader_3d_gain, (130 - 105) / 105 * 100, places=1)

    def test_stock_without_theme_untouched(self):
        r = ThemeResolver({"테마": ["AAA"]}, [_uni("AAA", 5, 100)], cfg)
        s = _Stock("ZZZ")
        r.annotate(s)
        self.assertIsNone(s.theme)
        self.assertEqual(s.theme_sync_count, 0)


class TestOverheatFollowerVeto(unittest.TestCase):
    """V5: 과열 테마(대장주 3일 +20% 초과)의 후발주는 즉시 탈락"""

    def _ctx(self):
        from jongga.engine.models import DayContext, MarketSignal
        return DayContext(date="2026-06-10", weekday=2, events_tomorrow=[], pre_holiday=False,
                          signal=MarketSignal("green", []), cfg=cfg, theme_available=True)

    def _stock(self, leader):
        from jongga.engine.models import StockView
        return StockView(code="000002", name="후발주", market="KOSDAQ", price=10000,
                         change_rate=5.0, trading_value=int(600e8), market_cap_eok=2000,
                         value_rank=20, minutes=[], investor=[], flags={},
                         daily=[{"date": "20260610", "open": 9800, "high": 10100, "low": 9700,
                                 "close": 10000, "volume": 1, "trading_value": int(600e8)}],
                         material_grade="A", material_checked=True,
                         theme="과열테마", theme_sync_count=4, is_theme_leader=leader,
                         theme_leader_3d_gain=35.0)

    def test_follower_in_overheated_theme_vetoed(self):
        from jongga.engine.veto import run_vetoes
        codes = [v.code for v in run_vetoes(self._stock(leader=False), self._ctx())]
        self.assertIn("V5", codes)

    def test_leader_in_overheated_theme_not_vetoed_by_v5(self):
        # 대장주 본인은 후발주 베토 대상이 아니다
        from jongga.engine.veto import run_vetoes
        codes = [v.code for v in run_vetoes(self._stock(leader=True), self._ctx())]
        self.assertNotIn("V5", codes)


class TestThemeStore(unittest.TestCase):
    def tearDown(self):
        from jongga import settings
        if settings.DB_PATH.exists():
            settings.DB_PATH.unlink()

    def test_save_and_load_roundtrip(self):
        from jongga.db import latest_theme_date, load_theme_map, save_theme_map
        theme_map = {"2차전지": ["373220", "006400"], "바이오": ["207940"]}
        save_theme_map("2026-06-10", theme_map)
        self.assertEqual(load_theme_map("2026-06-10"), theme_map)
        self.assertEqual(load_theme_map("2026-06-09"), {})
        self.assertEqual(latest_theme_date(), "2026-06-10")


if __name__ == "__main__":
    unittest.main()
