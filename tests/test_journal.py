"""M6 매매일지·킬스위치·검증 리포트 테스트 (네트워크 불필요)"""
import unittest
from datetime import date

from jongga import settings
from jongga.journal import killswitch, report
from jongga.settings import cfg


def closed(id_, exit_date, pnl_r, violation=False):
    return {"id": id_, "status": "closed", "exit_date": exit_date,
            "pnl_r": pnl_r, "rule_violation": violation, "name": "테스트종목"}


class TestKillSwitch(unittest.TestCase):
    """설계서 제1부의 5개 트리거 — 날짜를 주입해 결정적으로 검증"""

    def test_no_entries_inactive(self):
        st = killswitch.evaluate([], cfg, today=date(2026, 6, 11))
        self.assertFalse(st.active)

    def test_daily_2r_blocks_today(self):
        entries = [closed(1, "2026-06-11", -1.0), closed(2, "2026-06-11", -1.0)]
        st = killswitch.evaluate(entries, cfg, today=date(2026, 6, 11))
        self.assertTrue(st.active)
        self.assertTrue(any("오늘 손실" in r for r in st.reasons))
        # 다음 날은 해제 (단, 2연속 손절이라 휴식 트리거는 아님)
        st2 = killswitch.evaluate(entries, cfg, today=date(2026, 6, 12))
        self.assertFalse(st2.active)

    def test_weekly_4r_blocks_week(self):
        entries = [closed(i, d, -1.0) for i, d in enumerate(
            ["2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11"])]
        st = killswitch.evaluate(entries, cfg, today=date(2026, 6, 11))
        self.assertTrue(st.active)
        self.assertTrue(any("이번 주" in r for r in st.reasons))
        # 다음 주 월요일에는 주간 한도 해제
        st2 = killswitch.evaluate(entries, cfg, today=date(2026, 6, 16))
        self.assertFalse(any("이번 주" in r for r in st2.reasons))

    def test_monthly_8r_forces_stop(self):
        entries = [closed(1, "2026-06-02", -3.0), closed(2, "2026-06-09", -3.0),
                   closed(3, "2026-06-16", -2.0)]
        st = killswitch.evaluate(entries, cfg, today=date(2026, 6, 17))
        self.assertTrue(st.active)
        self.assertTrue(any("이번 달" in r for r in st.reasons))

    def test_three_consecutive_losses_rest_then_half(self):
        entries = [closed(1, "2026-06-08", -0.5), closed(2, "2026-06-09", -0.5),
                   closed(3, "2026-06-10", -0.5)]
        # 마지막 손절(수) 다음 거래일(목)까지 휴식
        st = killswitch.evaluate(entries, cfg, today=date(2026, 6, 11))
        self.assertTrue(st.active)
        self.assertTrue(any("연속 손절" in r for r in st.reasons))
        # 휴식이 끝나면 금지는 풀리되 '비중 절반' 주의가 남는다
        st2 = killswitch.evaluate(entries, cfg, today=date(2026, 6, 12))
        self.assertFalse(st2.active)
        self.assertTrue(any("절반" in c for c in st2.cautions))

    def test_streak_resets_on_win(self):
        entries = [closed(1, "2026-06-08", -0.5), closed(2, "2026-06-09", -0.5),
                   closed(3, "2026-06-10", +0.5)]
        st = killswitch.evaluate(entries, cfg, today=date(2026, 6, 11))
        self.assertFalse(st.active)
        self.assertEqual(st.cautions, [])

    def test_violation_blocks_next_trading_day_even_if_profitable(self):
        entries = [closed(1, "2026-06-10", +1.5, violation=True)]
        st = killswitch.evaluate(entries, cfg, today=date(2026, 6, 11))
        self.assertTrue(st.active)
        self.assertTrue(any("규칙 위반" in r for r in st.reasons))
        # 하루 지나면 해제
        st2 = killswitch.evaluate(entries, cfg, today=date(2026, 6, 12))
        self.assertFalse(st2.active)


class TestReport(unittest.TestCase):
    def test_passing_system(self):
        entries = [closed(i, "2026-06-10", +1.0) for i in range(6)] + \
                  [closed(10 + i, "2026-06-10", -0.8) for i in range(4)]
        rep = report.compute(entries, cfg)
        self.assertEqual(rep["closed"], 10)
        self.assertEqual(rep["win_rate"], 60.0)
        self.assertTrue(rep["checks"]["compliance"])
        self.assertTrue(rep["checks"]["edge"])
        self.assertTrue(rep["checks"]["loss_control"])
        self.assertFalse(rep["enough_data"])  # 30회 미만이라 아직 판정 보류

    def test_violation_breaks_compliance(self):
        entries = [closed(i, "2026-06-10", +1.0) for i in range(9)] + \
                  [closed(99, "2026-06-10", +2.0, violation=True)]
        rep = report.compute(entries, cfg)
        self.assertEqual(rep["compliance"], 90.0)
        self.assertFalse(rep["checks"]["compliance"])  # 수익이어도 위반은 위반

    def test_loss_control_fails_on_big_losses(self):
        entries = [closed(1, "2026-06-10", +1.0), closed(2, "2026-06-10", -2.5)]
        rep = report.compute(entries, cfg)
        self.assertFalse(rep["checks"]["loss_control"])
        self.assertEqual(rep["losses_over_2r"], 1)


class TestJournalStore(unittest.TestCase):
    def setUp(self):
        if settings.DB_PATH.exists():
            settings.DB_PATH.unlink()

    def tearDown(self):
        if settings.DB_PATH.exists():
            settings.DB_PATH.unlink()

    def test_add_close_roundtrip_r_math(self):
        from jongga.journal import store
        # 1R을 4만 원으로 고정 → 10,000원 × 40주 매수, 11,000원 청산 = +40,000원 = +1R
        entry_id = store.add_entry("2026-06-10", "201010", "알파전자",
                                   buy_price=10000, quantity=40, one_r=40000)
        row = store.close_entry(entry_id, "2026-06-11", 11000, lesson="갭상승 50% 익절")
        self.assertEqual(row["pnl_amount"], 40000)
        self.assertAlmostEqual(row["pnl_r"], 1.0)
        self.assertEqual(row["status"], "closed")

        opens = store.list_entries(status="open")
        self.assertEqual(opens, [])
        self.assertEqual(len(store.list_entries(status="closed")), 1)


class TestJournalWeb(unittest.TestCase):
    def setUp(self):
        if settings.DB_PATH.exists():
            settings.DB_PATH.unlink()

    def tearDown(self):
        if settings.DB_PATH.exists():
            settings.DB_PATH.unlink()
        settings.clear_overrides()

    def test_full_flow(self):
        from fastapi.testclient import TestClient

        from jongga.web.app import create_app
        client = TestClient(create_app(demo=True))

        res = client.get("/journal")
        self.assertEqual(res.status_code, 200)
        self.assertIn("매매일지", res.text)
        self.assertIn("킬스위치 정상", res.text)

        res = client.post("/journal/add", data={
            "trade_date": "2026-06-10", "code": "201010", "name": "알파전자",
            "buy_price": "10000", "quantity": "40",
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 303)

        from jongga.journal import store
        entry_id = store.list_entries(status="open")[0]["id"]
        res = client.post(f"/journal/{entry_id}/close", data={
            "exit_date": "2026-06-11", "exit_price": "10800",
            "lesson": "9:05 규칙대로 정리",
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 303)

        page = client.get("/journal").text
        self.assertIn("마감 기록", page)
        self.assertIn("알파전자", page)
        self.assertIn("9:05 규칙대로 정리", page)


if __name__ == "__main__":
    unittest.main()
