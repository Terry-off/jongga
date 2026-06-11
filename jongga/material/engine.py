"""재료 엔진 — 공시(DART) + 뉴스(네이버)를 합쳐 종목별 등급·근거·위험을 만든다

반환 형식 (StockView에 그대로 실림):
  {"checked": bool,      # 조회 자체가 성공했는가 — False면 '확인 불가'(베토 아님)
   "grade": "A"|"B"|"C"|None,   # None+checked=True 는 '재료 없음'(베토 1)
   "evidence": [...],    # 카드에 보여줄 근거 문장
   "risks": [...]}       # 유증·CB 등 — 베토 6 연동
"""
import sys
from datetime import datetime, timedelta

from jongga.material import dart, news, rules
from jongga.settings import cfg, env


def enabled() -> bool:
    return bool(env("DART_API_KEY")) or bool(env("NAVER_CLIENT_ID") and env("NAVER_CLIENT_SECRET"))


class MaterialEngine:
    def __init__(self, trade_date: datetime | None = None, use_news: bool = True):
        # use_news=False: 네이버 뉴스 검색은 최신 기사만 닿아 오래된 과거 날짜엔
        # '재료 없음'과 '검색이 안 닿음'을 구분할 수 없다 → 공시(DART)만 사용
        self.trade_date = trade_date or datetime.now()
        self.use_news = use_news
        self._corp_map: dict | None = None
        self._corp_map_failed = False

    def _corp(self, code: str) -> str | None:
        if self._corp_map is None and not self._corp_map_failed:
            try:
                self._corp_map = dart.corp_map()
            except Exception as exc:
                self._corp_map_failed = True
                print(f"(안내) DART 종목 매핑 실패 — 공시 분석 생략: {exc}", file=sys.stderr)
        return (self._corp_map or {}).get(code)

    def evaluate(self, code: str, name: str) -> dict:
        evidence, risks = [], []
        news_grade = dart_grade = None
        checked = False

        if self.use_news and env("NAVER_CLIENT_ID") and env("NAVER_CLIENT_SECRET"):
            try:
                items = news.filter_for_trade_date(news.search_news(name), self.trade_date, name)
                checked = True
                news_grade, hits = rules.grade_news_titles([it["title"] for it in items])
                for grade, title in hits[:3]:
                    evidence.append(f"기사({grade}급 신호): {title}")
            except Exception as exc:
                print(f"(안내) {name} 뉴스 조회 실패: {exc}", file=sys.stderr)

        if env("DART_API_KEY"):
            corp = self._corp(code)
            if corp:
                try:
                    lookback = cfg("risk_stock.cb_lookback_days", 30)
                    bgn = (self.trade_date - timedelta(days=lookback)).strftime("%Y%m%d")
                    end = self.trade_date.strftime("%Y%m%d")
                    rows = dart.disclosures(corp, bgn, end)
                    checked = True
                    today = self.trade_date.strftime("%Y%m%d")
                    today_titles = [r["title"] for r in rows if r["date"] == today]
                    dart_grade, hits = rules.grade_dart_titles(today_titles)
                    for grade, title in hits[:2]:
                        evidence.append(f"공시({grade}급): {title}")
                    risks = [f"{r['title']} ({r['date'][4:6]}/{r['date'][6:8]})"
                             for r in rows if r["title"] in set(rules.dart_risk_titles([x["title"] for x in rows]))][:3]
                except Exception as exc:
                    print(f"(안내) {name} 공시 조회 실패: {exc}", file=sys.stderr)

        return {
            "checked": checked,
            "grade": rules.best_grade(news_grade, dart_grade),
            "evidence": evidence,
            "risks": risks,
        }
