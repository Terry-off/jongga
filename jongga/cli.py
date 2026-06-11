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


_SIGNAL_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
_SIGNAL_TEXT = {"green": "매매해도 좋은 환경이에요", "yellow": "조심해야 하는 날이에요", "red": "오늘은 쉬는 날이에요"}


def _render_day(result) -> None:
    from jongga.engine.position import explain_position
    from jongga.settings import cfg

    line = "─" * 66
    print(line)
    print(f"{_SIGNAL_ICON[result.signal.color]} 시장 신호등 — {_SIGNAL_TEXT[result.signal.color]}   ({result.date} 기준)")
    for reason in result.signal.reasons:
        print(f"   · {reason}")
    if result.signal.color == "red":
        print("   ⛔ 쉬는 것도 포지션이에요. 아래 분석은 참고만 하고 오늘은 매매하지 마세요.")
    print(line)

    recs = [c for c in result.candidates if c.verdict in ("full", "half")]
    watch = [c for c in result.candidates if c.verdict == "watch"]

    print(f"\n📌 추천 후보 — 분석 {result.analyzed}종목 중 {len(recs)}종목")
    if not recs:
        print("   오늘은 기준(75점)을 넘은 종목이 없어요. 기준 미달인데 '그나마 나은 것'을 사는 건 시스템 위반이에요.")
    for i, c in enumerate(recs, start=1):
        s = c.stock
        star = "★" if c.verdict == "full" else "☆"
        print(f"\n[{i}] {s.name} ({s.code} · {s.market})  {c.pct:.1f}점  {star} {c.verdict_label}")
        print(f"    {s.price:,}원 ({s.change_rate:+.1f}%) · 오늘 거래대금 {_eok(s.trading_value)}")
        # 시장 분위기는 상단 신호등에 이미 표시 → 카드에는 종목 고유의 이유만
        notes = [n for it in c.items if it.available and it.key != "market" for n in it.notes][:5]
        if notes:
            print("    이런 점이 좋아요:")
            for n in notes:
                print(f"      · {n}")
        if c.position_amount:
            print(f"    💰 {explain_position(cfg, c.stock_class, c.verdict, c.position_amount)}")
        if c.unavailable:
            print(f"    ❓ 확인 못한 항목: {', '.join(c.unavailable)} — 만점에서 빼고 채점했어요")

    if watch:
        print("\n👀 관찰만 — 추천 기준(75점)에 못 미쳐요. 내일을 위한 기록용이에요")
        for c in watch:
            print(f"   · {c.stock.name} ({c.stock.code})  {c.pct:.1f}점")

    if result.rejected:
        print("\n🚫 오늘 탈락한 종목과 이유")
        for s, vetoes in result.rejected:
            v = vetoes[0]
            print(f"   ✕ {s.name} — {v.title}: {v.easy}")

    for note in result.notes:
        print(f"\nℹ️  {note}")
    print("\n⚠️  이 프로그램은 추천 도구일 뿐이에요. 최종 판단과 책임은 투자자 본인에게 있어요.")


def cmd_recommend(args) -> int:
    from jongga.engine import pipeline

    if args.demo:
        from jongga.demo import DEMO_DATE
        from jongga.providers import DemoProvider

        provider = DemoProvider()
        trade_date = args.date or DEMO_DATE
        print("(시연 모드 — 내장된 '가상의 하루' 데이터로 판단 과정 전체를 보여드려요)\n")
    else:
        from jongga.providers import LiveProvider

        provider = LiveProvider()
        trade_date = args.date
        if args.date:
            print("(안내) 실시간 모드는 오늘 데이터 기준이에요 — 과거 날짜 재현은 M5에서 지원돼요.\n")

    result = pipeline.run(provider, trade_date=trade_date, top_n=args.top)
    _render_day(result)

    if args.save:
        from jongga.db import save_screening

        count = save_screening(result)
        print(f"\n✓ 결과 {count}건을 DB에 저장했어요 (복기용)")
    return 0


def cmd_material(args) -> int:
    from jongga.material.engine import MaterialEngine, enabled

    if not enabled():
        print("재료 분석 키가 없습니다. .env에 DART_API_KEY 또는 NAVER_CLIENT_ID/SECRET을 넣어주세요.")
        return 1
    print(f"'{args.name}' ({args.code}) 재료 확인 중... (오늘 기사 + 최근 30일 공시)")
    res = MaterialEngine().evaluate(args.code, args.name)
    if not res["checked"]:
        print("조회에 실패했어요. 인터넷 연결을 확인해주세요.")
        return 1
    grade = res["grade"]
    label = {"A": "A급 — 강한 재료", "B": "B급 — 테마 확산 확인 필요", "C": "C급 — 단독 신호, 동반 조건 필요"}
    print(f"\n판정: {label.get(grade, '재료 없음 — 이유 없는 급등일 수 있어요')}")
    for e in res["evidence"]:
        print(f"  · {e}")
    if res["risks"]:
        print("⚠️ 물량 이벤트 (베토 대상):")
        for r in res["risks"]:
            print(f"  · {r}")
    return 0


def cmd_web(args) -> int:
    try:
        import uvicorn
    except ImportError:
        print("웹 화면 구성 요소가 없습니다. 먼저 실행해주세요:  pip install -r requirements.txt")
        return 1
    from jongga.web.app import create_app

    app = create_app(demo=args.demo)
    mode = "시연 모드 (가상 데이터)" if args.demo else "실전 모드 (한국투자증권 API)"
    print("─" * 56)
    print(f"  종가매매 추천 대시보드 — {mode}")
    print(f"  브라우저에서 열기 →  http://127.0.0.1:{args.port}")
    print("  끄려면 이 창에서 Ctrl+C")
    print("─" * 56)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_init_db(_args) -> int:
    from jongga.db import init_db

    init_db()
    print("✓ DB 준비 완료 (data/jongga.sqlite3)")
    return 0


def main(argv=None) -> None:
    # 윈도우 구형 콘솔(cp949)에서 이모지로 인한 비정상 종료 방지
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
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

    p_rec = sub.add_parser("recommend", help="종가매매 후보 추천 (--demo: 가상 데이터로 시연)")
    p_rec.add_argument("--demo", action="store_true", help="API 키·네트워크 없이 내장 가상 데이터로 시연")
    p_rec.add_argument("--date", help="기준 날짜 YYYY-MM-DD (시연·테스트용)")
    p_rec.add_argument("--top", type=int, default=None, help="분석할 종목 수 (기본: 설정의 40)")
    p_rec.add_argument("--save", action="store_true", help="결과를 DB에 저장 (복기용)")
    p_rec.set_defaults(func=cmd_recommend)

    p_web = sub.add_parser("web", help="웹 대시보드 실행 (브라우저 화면)")
    p_web.add_argument("--demo", action="store_true", help="가상 데이터로 화면 구경")
    p_web.add_argument("--port", type=int, default=8765)
    p_web.add_argument("--host", default="127.0.0.1")
    p_web.set_defaults(func=cmd_web)

    p_mat = sub.add_parser("material", help="종목 재료(뉴스·공시) 등급 즉석 확인")
    p_mat.add_argument("code", help="종목코드 6자리 (예: 005930)")
    p_mat.add_argument("name", help="종목명 (예: 삼성전자)")
    p_mat.set_defaults(func=cmd_material)

    p_db = sub.add_parser("init-db", help="DB 파일 생성")
    p_db.set_defaults(func=cmd_init_db)

    args = parser.parse_args(argv)
    try:
        sys.exit(args.func(args))
    except Exception as exc:
        from jongga.kis.client import KisApiError

        if isinstance(exc, (KisApiError, SystemExit)):
            raise
        print(f"\n오류가 발생했습니다: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
