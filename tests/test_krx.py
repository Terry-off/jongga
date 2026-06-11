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
    def test_top_value_and_risers_merge(self):
        rows = (
            # 거래대금 상위권 (등락률 낮음)
            [_row(f"V{i:05d}", 1.0, 1000 - i) for i in range(70)]
            # 상승률 상위 (거래대금 60위 밖이지만 50억 이상)
            + [_row("RISER1", 12.0, 80), _row("RISER2", 8.0, 70)]
            # 상승해도 거래대금이 너무 작으면 제외
            + [_row("TINY00", 25.0, 10)]
        )
        uni = krx.build_universe(rows, cfg)
        codes = {r["code"] for r in uni}
        self.assertIn("RISER1", codes)
        self.assertIn("RISER2", codes)
        self.assertNotIn("TINY00", codes)
        self.assertNotIn("V00065", codes)  # 거래대금 60위 밖 + 등락률 미달
        # 거래대금 내림차순 정렬
        values = [r["trading_value"] for r in uni]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_overlap_gets_both_sources(self):
        rows = [_row("BOTH00", 10.0, 500)] + [_row(f"V{i:05d}", 0.5, 400 - i) for i in range(30)]
        uni = krx.build_universe(rows, cfg)
        both = next(r for r in uni if r["code"] == "BOTH00")
        self.assertIn("거래대금상위", both["sources"])
        self.assertIn("상승률상위", both["sources"])


if __name__ == "__main__":
    unittest.main()
