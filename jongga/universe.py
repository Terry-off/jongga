"""유니버스 압축 — "오늘 돈이 몰린 종목"만 추출 (DESIGN.md 4.2)

거래대금 상위(코스피+코스닥)와 상승률 상위를 합쳐 100~200개로 압축한다.
전 종목을 훑지 않는 이 단계 자체가 1차 필터다.
"""
import sys

from jongga.kis.api import current_price, fluctuation_rank, volume_rank
from jongga.kis.client import KisApiError, KisClient
from jongga.settings import cfg

SOURCE_VALUE = "거래대금상위"
SOURCE_RISE = "상승률상위"

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
    try:
        for item in fluctuation_rank(client):
            if not item["code"] or item["change_rate"] < min_rate:
                continue
            if item["code"] in rows:
                rows[item["code"]]["sources"] += f",{SOURCE_RISE}"
                continue
            # 순위 응답에 거래대금·시장 구분이 없어 현재가로 보강
            detail = current_price(client, item["code"])
            rows[item["code"]] = {
                "code": item["code"],
                "name": item["name"],
                "market": detail["market"] or "?",
                "price": item["price"],
                "change_rate": item["change_rate"],
                "volume": item["volume"],
                "trading_value": detail["trading_value"],
                "sources": SOURCE_RISE,
            }
    except KisApiError as exc:
        # 상승률 순위는 보조 경로 — 실패해도 거래대금 상위만으로 진행
        print(f"(안내) 상승률 순위 조회 실패, 거래대금 상위만 사용합니다: {exc}", file=sys.stderr)

    return sorted(rows.values(), key=lambda r: r["trading_value"], reverse=True)
