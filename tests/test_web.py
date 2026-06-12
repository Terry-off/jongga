"""웹 대시보드 + 설정 덮어쓰기 테스트 (시연 데이터 기반, 네트워크 불필요)"""
import unittest

from fastapi.testclient import TestClient

from jongga import settings
from jongga.web.app import create_app
from jongga.web.settings_meta import all_items


class TestSettingsOverride(unittest.TestCase):
    def tearDown(self):
        settings.clear_overrides()

    def test_override_and_restore(self):
        self.assertEqual(settings.cfg("score.full_weight_cut"), 85)
        settings.set_override("score.full_weight_cut", "90")
        self.assertEqual(settings.cfg("score.full_weight_cut"), 90)  # int로 변환됨
        settings.clear_overrides()
        self.assertEqual(settings.cfg("score.full_weight_cut"), 85)

    def test_bool_coercion(self):
        settings.set_override("risk_stock.exclude_warning", "false")
        self.assertIs(settings.cfg("risk_stock.exclude_warning"), False)


class TestWebApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app(demo=True))
        cls.client.post("/run")   # 스캔은 자동으로 돌지 않으므로 ▶ 실행을 누른 상태를 만든다

    @classmethod
    def tearDownClass(cls):
        settings.clear_overrides()

    def test_home_idle_before_run(self):
        # 첫 화면은 대기 상태 — 사용자가 ▶ 실행을 누르기 전엔 스캔하지 않는다
        fresh = TestClient(create_app(demo=True))
        res = fresh.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("실행을 눌러주세요", res.text)
        self.assertNotIn("시장 신호등", res.text)

    def test_home_renders_demo(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("시장 신호등", res.text)
        self.assertIn("알파전자", res.text)
        self.assertIn("정상 비중 후보", res.text)
        self.assertIn("재료 없음", res.text)  # 델타소재 탈락 사유

    def test_chart_api(self):
        res = self.client.get("/api/chart/201010")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertGreater(len(body["daily"]), 50)
        self.assertGreater(len(body["minutes"]), 300)
        self.assertEqual(len(body["daily"][0]["time"]), 10)  # YYYY-MM-DD

    def test_chart_api_unknown_code(self):
        self.assertEqual(self.client.get("/api/chart/999999").status_code, 404)

    def test_settings_page(self):
        res = self.client.get("/settings")
        self.assertEqual(res.status_code, 200)
        self.assertIn("필터 설정", res.text)
        self.assertIn("중소형주 최소 거래대금", res.text)

    def test_settings_save_and_reset(self):
        # 전체 폼을 기본값으로 채우고 거래대금 컷 하나만 변경
        form = {}
        for it in all_items():
            if it["type"] == "bool":
                if it["default"]:
                    form[it["key"]] = "true"
            else:
                form[it["key"]] = str(it["default"])
        form["trading_value.midsmall_min_eok"] = "500"

        res = self.client.post("/settings", data=form, follow_redirects=False)
        self.assertEqual(res.status_code, 303)
        self.assertEqual(settings.cfg("trading_value.midsmall_min_eok"), 500)
        # 기본값과 같은 항목은 저장되지 않아야 함
        self.assertEqual(len(settings.overrides()), 1)

        res = self.client.post("/settings/reset", follow_redirects=False)
        self.assertEqual(res.status_code, 303)
        self.assertEqual(settings.cfg("trading_value.midsmall_min_eok"), 300)


class TestRunGuards(unittest.TestCase):
    """▶ 실행의 사전 안내 — 네트워크를 부르기 전에 휴장일·미래 날짜를 걸러낸다"""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app(demo=False))

    @classmethod
    def tearDownClass(cls):
        settings.clear_overrides()

    def test_home_is_idle_without_run(self):
        # 실전 모드도 접속만으로는 스캔하지 않는다 — 시작 화면만 보여준다
        fresh = TestClient(create_app(demo=False))
        res = fresh.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("실행을 눌러주세요", res.text)
        self.assertNotIn("분석하고 있어요", res.text)

    def test_election_holiday_immediate_message(self):
        # 2026-06-03 지방선거(증시 휴장) — KRX 호출 없이 즉시 안내
        res = self.client.post("/run", data={"date": "2026-06-03"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("휴장일이에요", res.text)

    def test_weekend_immediate_message(self):
        res = self.client.post("/run", data={"date": "2026-06-07"})  # 일요일
        self.assertEqual(res.status_code, 200)
        self.assertIn("휴장일이에요", res.text)

    def test_future_date_immediate_message(self):
        res = self.client.post("/run", data={"date": "2099-01-01"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("아직 오지 않은 날짜", res.text)

    def test_other_date_clears_previous_error(self):
        # 휴장일 오류가 떠 있어도 다른 날짜로 실행하면 새로 진행(스캔 시작)되어야 한다
        # (백그라운드 스캔이 시작되므로 다른 테스트와 상태를 공유하지 않게 새 앱 사용)
        fresh = TestClient(create_app(demo=False))
        fresh.post("/run", data={"date": "2026-06-03"})
        res = fresh.post("/run", data={"date": "2026-06-04"})
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("2026-06-03은 증시 휴장일", res.text)


if __name__ == "__main__":
    unittest.main()
