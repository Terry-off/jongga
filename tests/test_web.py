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

    @classmethod
    def tearDownClass(cls):
        settings.clear_overrides()

    def test_home_renders_demo(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("시장 신호등", res.text)
        self.assertIn("알파전자", res.text)
        self.assertIn("정상 비중 후보", res.text)
        self.assertIn("재료 없음", res.text)  # 델타소재 탈락 사유

    def test_chart_api(self):
        self.client.get("/")
        res = self.client.get("/api/chart/201010")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertGreater(len(body["daily"]), 50)
        self.assertGreater(len(body["minutes"]), 300)
        self.assertEqual(len(body["daily"][0]["time"]), 10)  # YYYY-MM-DD

    def test_chart_api_unknown_code(self):
        self.client.get("/")
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


if __name__ == "__main__":
    unittest.main()
