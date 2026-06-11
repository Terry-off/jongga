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


def _select_provider(demo: bool, date_arg: str | None):
    """(provider, trade_date, banner) 결정 — demo / 과거(DB) / 오늘(실시간)"""
    from datetime import date as _date

    if demo:
        from jongga.demo import DEMO_DATE
        from jongga.providers import DemoProvider
        return DemoProvider(), (date_arg or DEMO_DATE), \
            "(시연 모드 — 내장된 '가상의 하루' 데이터로 판단 과정 전체를 보여드려요)\n"

    today = _date.today().isoformat()
    if date_arg and date_arg != today:
        from jongga.providers import DBProvider
        provider = DBProvider(date_arg)
        if not provider.has_data():
            raise SystemExit(
                f"{date_arg}에 저장된 데이터가 없어요.\n"
                "그날 18:10 수집(python -m jongga collect)이 돌지 않았다면 과거를 재현할 수 없어요 "
                "(분봉·시간외는 지나가면 복구가 안 돼요). 저장된 날짜는 'python -m jongga dates'로 볼 수 있어요."
            )
        return provider, date_arg, f"(과거 조회 — {date_arg}에 저장해 둔 데이터를 그대로 재현해요)\n"

    from jongga.providers import LiveProvider
    return LiveProvider(), None, ""


def cmd_recommend(args) -> int:
    from jongga.engine import pipeline

    provider, trade_date, banner = _select_provider(args.demo, args.date)
    if banner:
        print(banner)

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


def cmd_journal(_args) -> int:
    from jongga.journal import killswitch, report, store
    from jongga.settings import cfg

    entries = store.list_entries()
    ks = killswitch.evaluate(entries, cfg)
    print("── 킬스위치 상태 ──")
    if ks.active:
        print("🛑 발동 — 오늘은 매매 금지예요")
        for r in ks.reasons:
            print(f"   · {r}")
    else:
        print("✓ 정상 (하루 -2R · 주 -4R · 월 -8R · 연속 손절 · 규칙 위반 감시 중)")
        for c in ks.cautions:
            print(f"   ⚠️ {c}")

    rep = report.compute(entries, cfg)
    print("\n── 검증 리포트 ──")
    if rep["closed"] == 0:
        print("마감된 매매가 아직 없어요. 웹 화면(📒 일지)에서 기록을 시작하세요.")
        return 0
    print(f"마감 {rep['closed']}회 (보유 중 {rep['open']}건) · 누적 {rep['total_r']:+.1f}R")
    print(f"{'✅' if rep['checks']['compliance'] else '❌'} 규칙 준수율 {rep['compliance']}% (기준 95%)")
    print(f"{'✅' if rep['checks']['edge'] else '❌'} 승률 {rep['win_rate']}% / 기대값 {rep['expectancy_r']:+.2f}R")
    print(f"{'✅' if rep['checks']['loss_control'] else '❌'} 평균 손실 {rep['avg_loss_r']}R (1R 이내), 최대 {rep['max_loss_r']}R")
    if not rep["enough_data"]:
        print(f"(판정까지 최소 {rep['min_trades']}회 필요 — {rep['min_trades'] - rep['closed']}회 남음)")
    return 0


def cmd_collect(args) -> int:
    from jongga.collector import collect_day

    collect_day(with_themes=not args.no_themes, top_n=args.top)
    return 0


def cmd_dates(_args) -> int:
    from jongga.db import collected_dates

    dates = collected_dates()
    if not dates:
        print("아직 수집된 날짜가 없어요. 'python -m jongga collect'로 오늘 데이터를 저장해보세요.")
        return 0
    print(f"저장된 거래일 {len(dates)}개 (최신순):")
    for d in dates[:60]:
        print(f"  · {d}")
    print("\n과거 조회:  python -m jongga recommend --date YYYY-MM-DD")
    return 0


def cmd_collect_themes(_args) -> int:
    from datetime import date

    from jongga.db import save_theme_map
    from jongga.theme import scraper

    print("네이버 금융에서 테마-종목 매핑을 수집 중이에요... (수백 개 테마라 1~3분 걸려요)")

    def progress(i, total, name):
        if i % 25 == 0 or i == total:
            print(f"  {i}/{total} 테마 처리 중... (최근: {name})")

    theme_map = scraper.collect(progress=progress)
    if not theme_map:
        print("테마를 수집하지 못했어요. 인터넷 연결을 확인하거나 잠시 후 다시 시도해주세요.")
        return 1
    today = date.today().isoformat()
    count = save_theme_map(today, theme_map)
    total_codes = sum(len(v) for v in theme_map.values())
    print(f"✓ {today} 기준 테마 {count}개 / 종목 매핑 {total_codes}건을 저장했어요.")
    print("  이제 recommend·web에서 '테마 동조' 점수(15점)가 채워져요.")
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

    p_col = sub.add_parser("collect", help="오늘 전체 스냅샷 수집·저장 (매일 18:10 자동 실행 권장)")
    p_col.add_argument("--no-themes", action="store_true", help="테마 수집 생략 (빠르게)")
    p_col.add_argument("--top", type=int, default=None, help="정밀 수집할 종목 수 (기본: 설정값)")
    p_col.set_defaults(func=cmd_collect)

    p_dates = sub.add_parser("dates", help="저장된(과거 조회 가능한) 거래일 목록")
    p_dates.set_defaults(func=cmd_dates)

    p_journal = sub.add_parser("journal", help="매매일지 — 킬스위치 상태·검증 리포트 요약")
    p_journal.set_defaults(func=cmd_journal)

    p_theme = sub.add_parser("collect-themes", help="네이버 테마-종목 매핑 수집 (하루 1회 권장)")
    p_theme.set_defaults(func=cmd_collect_themes)

    p_db = sub.add_parser("init-db", help="DB 파일 생성")
    p_db.set_defaults(func=cmd_init_db)

    args = parser.parse_args(argv)
    try:
        sys.exit(args.func(args))
    except SystemExit:
        raise
    except RuntimeError as exc:
        # KisApiError 포함 — 사용자 안내 메시지만 출력 (traceback 없이)
        print(f"\n{exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n오류가 발생했습니다: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
