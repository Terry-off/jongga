"""터미널 명령 — M1: smoke / universe / init-db"""
import argparse
import sys
import unicodedata
from datetime import date

from jongga import __version__


def _pad(text: str, width: int) -> str:
    """한글(전각) 폭을 고려한 왼쪽 정렬"""
    display = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(text))
    return str(text) + " " * max(0, width - display)


def _eok(won: int) -> str:
    return f"{won / 1e8:,.0f}억"


def cmd_smoke(_args) -> int:
    from jongga.kis.api import current_price
    from jongga.kis.client import KisClient

    print("1) 한국투자증권 API 토큰 발급 중...")
    client = KisClient()
    print("2) 삼성전자(005930) 현재가 조회 중...")
    info = current_price(client, "005930")
    if info["price"] <= 0:
        print("응답은 받았지만 가격이 비어 있습니다. 장 운영 시간/휴장일 여부를 확인해주세요.")
        return 1
    print()
    print("✓ 연결 성공!")
    print(f"  삼성전자  {info['price']:,}원 ({info['change_rate']:+.2f}%)")
    print(f"  오늘 거래대금 {_eok(info['trading_value'])} / 시가총액 {info['market_cap_eok']:,}억")
    print(f"  시장 경보: {info['market_warn_code'] or '정보 없음'} (00=정상)")
    return 0


def cmd_universe(args) -> int:
    from jongga.universe import collect_universe

    print("오늘 돈이 몰린 종목을 모으는 중... (거래대금 상위 + 상승률 상위)")
    rows = collect_universe()
    if not rows:
        print("종목을 가져오지 못했습니다. 휴장일이거나 API 응답이 비어 있습니다.")
        return 1

    shown = rows[: args.top] if args.top else rows
    print()
    header = f"{_pad('순위', 6)}{_pad('종목명', 22)}{_pad('코드', 8)}{_pad('시장', 8)}{_pad('현재가', 12)}{_pad('등락률', 9)}{_pad('거래대금', 12)}편입 경로"
    print(header)
    print("-" * len(header))
    for i, r in enumerate(shown, start=1):
        price_s = f"{r['price']:,}원"
        rate_s = f"{r['change_rate']:+.1f}%"
        print(
            f"{_pad(i, 6)}{_pad(r['name'], 22)}{_pad(r['code'], 8)}{_pad(r['market'], 8)}"
            f"{_pad(price_s, 12)}{_pad(rate_s, 9)}{_pad(_eok(r['trading_value']), 12)}{r['sources']}"
        )
    print(f"\n총 {len(rows)}종목 (표시 {len(shown)}종목)")

    if args.save:
        from jongga.db import save_universe

        trade_date = date.today().isoformat()
        count = save_universe(trade_date, rows)
        print(f"✓ {trade_date} 기준 {count}종목을 DB에 저장했습니다 (data/jongga.sqlite3)")
    return 0


def cmd_init_db(_args) -> int:
    from jongga.db import init_db

    init_db()
    print("✓ DB 준비 완료 (data/jongga.sqlite3)")
    return 0


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="jongga",
        description="종가매매 종목 추천 프로그램 (추천 도구일 뿐, 투자 책임은 본인에게 있습니다)",
    )
    parser.add_argument("--version", action="version", version=f"jongga {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_smoke = sub.add_parser("smoke", help="KIS API 연결 테스트 (토큰 + 삼성전자 현재가)")
    p_smoke.set_defaults(func=cmd_smoke)

    p_uni = sub.add_parser("universe", help="오늘 돈이 몰린 종목 목록 (거래대금·상승률 상위)")
    p_uni.add_argument("--save", action="store_true", help="결과를 DB에 저장")
    p_uni.add_argument("--top", type=int, default=30, help="표시할 종목 수 (기본 30, 0=전체)")
    p_uni.set_defaults(func=cmd_universe)

    p_db = sub.add_parser("init-db", help="DB 파일 생성")
    p_db.set_defaults(func=cmd_init_db)

    args = parser.parse_args(argv)
    sys.exit(args.func(args))
