"""유니버스 수집 — "오늘 돈이 몰린 종목"을 최대한 넓게 모은다 (DESIGN.md 4.2)

세 경로의 합집합 (놓침을 줄이는 순서):
  ① 거래대금 상위 (코스피·코스닥 각 30) — KIS 순위 API
  ② 상승률 상위 (코스피·코스닥 각각) — KIS 순위 API
  ③ KRX 전 종목 시세 — 장 마감 후 제공되면 거래대금 기준 통과 종목 전부 합류
     (장중에는 비어 있어 자동 생략 → 장중 커버리지는 ①+②)
기준 미달 확정 종목의 제거는 파이프라인의 _eligible(베토 2와 동일 컷)이 담당한다.
"""
import sys
from datetime import date

from jongga.kis.api import current_price, fluctuation_rank, volume_rank
from jongga.kis.client import KisApiError, KisClient
from jongga.settings import cfg

SOURCE_VALUE = "거래대금상위"
SOURCE_RISE = "상승률상위"
SOURCE_KRX = "전종목(KRX)"

_MARKET_NAME = {"0001": "KOSPI", "1001": "KOSDAQ"}


def collect_universe(client: KisClient | None = None) -> list[dict]:
    client = client or KisClient()
    rows: dict[str, dict] = {}

    for market_code, market_name in _MARKET_NAME.items():
        for item in volume_rank(client, market=market_code, sort="3"):
            if not item["code"]:
                continue
            rows[item["code"]] = {
                "code": item["code"],
                "name": item["name"],
                "market": market_name,
                "price": item["price"],
                "change_rate": item["change_rate"],
                "volume": item["volume"],
                "trading_value": item["trading_value"],
                "sources": SOURCE_VALUE,
            }

    min_rate = float(cfg("universe.min_change_rate", 3.0))
    for market_code, market_name in _MARKET_NAME.items():
        try:
            for item in fluctuation_rank(client, market=market_code):
                if not item["code"] or item["change_rate"] < min_rate:
                    continue
                if item["code"] in rows:
                    if SOURCE_RISE not in rows[item["code"]]["sources"]:
                        rows[item["code"]]["sources"] += f",{SOURCE_RISE}"
                    continue
                # 순위 응답에 거래대금이 없어 현재가로 보강
                detail = current_price(client, item["code"])
                rows[item["code"]] = {
                    "code": item["code"],
                    "name": item["name"],
                    "market": detail["market"] or market_name,
                    "price": item["price"],
                    "change_rate": item["change_rate"],
                    "volume": item["volume"],
                    "trading_value": detail["trading_value"],
                    "sources": SOURCE_RISE,
                }
        except KisApiError as exc:
            print(f"(안내) {market_name} 상승률 순위 조회 실패 — 다른 경로로 진행: {exc}", file=sys.stderr)

    # 장 마감 후라면 KRX 전 종목으로 빈틈을 메운다 (순위 30위 밖 + 300억 이상 종목)
    try:
        from jongga import krx
        floor = float(cfg("trading_value.midsmall_min_eok", 300)) * 1e8
        added = 0
        for r in krx.fetch_day(date.today().strftime("%Y%m%d")):
            if r["trading_value"] >= floor and r["code"] not in rows:
                rows[r["code"]] = {
                    "code": r["code"], "name": r["name"], "market": r["market"],
                    "price": r["price"], "change_rate": r["change_rate"],
                    "volume": r["volume"], "trading_value": r["trading_value"],
                    "sources": SOURCE_KRX,
                }
                added += 1
        if added:
            print(f"(안내) KRX 전 종목 데이터로 {added}종목을 추가 확보했어요 (장 마감 집계)", file=sys.stderr)
    except Exception:
        pass  # 장중에는 KRX 일별 집계가 없다 — 순위 경로만으로 진행

    return sorted(rows.values(), key=lambda r: r["trading_value"], reverse=True)
