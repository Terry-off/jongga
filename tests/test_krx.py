"""KRX 전종목 시세 파서 + 과거 유니버스 재구성 테스트 (네트워크 불필요)"""
import unittest

from jongga import krx
from jongga.settings import cfg

SAMPLE = [
    {"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자", "MKT_NM": "KOSPI",
     "TDD_CLSPRC": "81,000", "FLUC_RT": "1.25", "ACC_TRDVOL": "12,345,678",
     "ACC_TRDVAL": "1,000,000,000,000", "MKTCAP": "483,000,000,000,000"},
    {"ISU_SRT_CD": "201010", "ISU_ABBRV": "알파전자", "MKT_NM": "KOSDAQ",
     "TDD_CLSPRC": "11,500", "FLUC_RT": "15.00", "ACC_TRDVOL": "700,000",
     "ACC_TRDVAL": "130,000,000,000", "MKTCAP": "800,000,000,000"},
    {"ISU_SRT_CD": "999999", "ISU_ABBRV": "코넥스주", "MKT_NM": "KONEX",
     "TDD_CLSPRC": "1,000", "FLUC_RT": "20.0", "ACC_TRDVOL": "10",
     "ACC_TRDVAL": "10,000", "MKTCAP": "1,000,000"},
]


class TestKrxParser(unittest.TestCase):
    def test_parse_rows(self):
        rows = krx.parse_rows(SAMPLE)
        self.assertEqual(len(rows), 2)  # KONEX 제외
        samsung = rows[0]
        self.assertEqual(samsung["code"], "005930")
        self.assertEqual(samsung["price"], 81000)
        self.assertAlmostEqual(samsung["change_rate"], 1.25)
        self.assertEqual(samsung["trading_value"], 1_000_000_000_000)
        self.assertEqual(samsung["market_cap_eok"], 4_830_000)

    def test_parse_garbage_safe(self):
        rows = krx.parse_rows([{"ISU_SRT_CD": "00", "MKT_NM": "KOSPI"},
                               {"MKT_NM": "ETF"}])
        self.assertEqual(rows, [])


def _row(code, change, value_eok):
    return {"code": code, "name": code, "market": "KOSPI", "price": 10000,
            "change_rate": change, "volume": 1,
            "trading_value": int(value_eok * 1e8), "market_cap_eok": 5000}


class TestBuildUniverse(unittest.TestCase):
    """포함 규칙 = 베토 2와 동일: 거래대금 ≥ 300억 또는 순위 ≤ 50위 → 누락 0"""

    def test_all_above_floor_included_regardless_of_rank(self):
        # 거래대금 80위(310억)도 300억 이상이면 포함 — 기존 '상위 40개' 상한 제거 검증
        rows = [_row(f"V{i:05d}", 1.0, 1000 - i * 8) for i in range(88)]  # 1000억 → 304억
        uni = krx.build_universe(rows, cfg)
        self.assertEqual(len(uni), 88)  # 전부 300억 이상 → 전부 포함

    def test_below_floor_excluded_even_if_riser(self):
        rows = [_row(f"V{i:05d}", 1.0, 1000 - i) for i in range(60)] \
            + [_row("TINY00", 25.0, 10)]  # +25%지만 10억 — 베토 2 확정 탈락
        uni = krx.build_universe(rows, cfg)
        self.assertNotIn("TINY00", {r["code"] for r in uni})

    def test_top_rank_kept_below_floor(self):
        # 한산한 날: 전부 300억 미만이어도 거래대금 50위까지는 대형주 경로로 포함
        rows = [_row(f"V{i:05d}", 1.0, 290 - i) for i in range(60)]
        uni = krx.build_universe(rows, cfg)
        self.assertEqual(len(uni), 50)

    def test_sources_tagging_and_order(self):
        rows = [_row(f"V{i:05d}", 1.0, 1000 - i) for i in range(55)] \
            + [_row("RISER1", 12.0, 320)]
        uni = krx.build_universe(rows, cfg)
        top1 = uni[0]
        self.assertIn("거래대금상위", top1["sources"])
        riser = next(r for r in uni if r["code"] == "RISER1")
        self.assertIn("상승률상위", riser["sources"])
        values = [r["trading_value"] for r in uni]
        self.assertEqual(values, sorted(values, reverse=True))


if __name__ == "__main__":
    unittest.main()
