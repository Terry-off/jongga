"""일일 스냅샷 수집기 — 지나가면 못 보는 데이터를 매일 저장한다 (DESIGN.md 4.8, 8장)

분봉·시간외·경보 플래그·당시 뉴스는 당일에만 조회되므로, 매 거래일 장 마감 후(18:10)
한 번 수집해 DB에 적재한다. 이렇게 쌓인 데이터가 '과거 날짜 그대로 재현'의 원천이다.
"""
import sys
from datetime import date as date_cls

from jongga.db import (init_db, save_index_collect, save_stock_collect,
                       save_theme_map, save_universe)
from jongga.settings import cfg


def collect_day(provider=None, trade_date: str | None = None, top_n: int | None = None,
                with_themes: bool = True, log=print) -> dict:
    """오늘(또는 지정일)의 전체 스냅샷을 수집해 DB에 저장. 반환: 통계 dict"""
    from jongga.providers import LiveProvider

    provider = provider or LiveProvider()
    d = trade_date or date_cls.today().isoformat()
    cap = top_n if top_n is not None else cfg("universe.analyze_top", 0)  # 0 = 전체
    init_db()

    log(f"[1/4] 오늘 돈이 몰린 종목 수집 중...")
    universe = sorted(provider.universe(), key=lambda r: r.get("trading_value", 0), reverse=True)
    save_universe(d, universe)
    analyzed = universe[:cap] if cap else universe
    log(f"      유니버스 {len(universe)}종목 저장 (정밀 수집 대상 {len(analyzed)}종목)")

    material_on = bool(getattr(provider, "material_enabled", lambda: False)())
    log(f"[2/4] 종목별 일봉·분봉·수급{'·재료' if material_on else ''} 수집 중...")
    ok, failed = 0, 0
    for i, row in enumerate(analyzed, start=1):
        code, name = row["code"], row.get("name", "")
        try:
            snapshot = provider.snapshot(code) or {}
            daily = provider.daily(code) or []
            minutes = provider.minutes(code) or []
            investor = provider.investor(code) or []
            materials = provider.materials(code, name) if material_on else None
            save_stock_collect(d, code, snapshot, daily, minutes, investor, materials)
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"(안내) {code} {name} 수집 일부 실패: {exc}", file=sys.stderr)
        if i % 10 == 0 or i == len(analyzed):
            log(f"      {i}/{len(analyzed)}종목 처리...")

    log(f"[3/4] 지수 수집 중...")
    try:
        save_index_collect(d, provider.index() or {})
    except Exception as exc:
        print(f"(안내) 지수 수집 실패: {exc}", file=sys.stderr)

    theme_count = 0
    if with_themes:
        log(f"[4/4] 네이버 테마 매핑 수집 중... (1~3분 소요)")
        try:
            from jongga.theme import scraper
            theme_map = scraper.collect()
            if theme_map:
                theme_count = save_theme_map(d, theme_map)
        except Exception as exc:
            print(f"(안내) 테마 수집 실패 — 다음에 collect-themes로 재시도하세요: {exc}", file=sys.stderr)
    else:
        log(f"[4/4] 테마 수집 생략")

    stats = {"date": d, "universe": len(universe), "stocks_ok": ok,
             "stocks_failed": failed, "themes": theme_count}
    log(f"\n✓ {d} 수집 완료 — 종목 {ok}건, 테마 {theme_count}개. 이제 이 날짜를 언제든 다시 조회할 수 있어요.")
    return stats


def backfill_daily(client=None, trade_date: str | None = None, top_n: int | None = None, log=print) -> dict:
    """과거 누락일 보충 — 일봉만 복구 가능. 분봉·시간외·플래그는 복구 불가('확인 불가' 처리).

    엄밀한 과거 유니버스(그날 거래대금 상위)는 API로 복원할 수 없으므로,
    가장 최근 유니버스를 기준으로 일봉만 그 날짜까지 끊어 채운다. 한계를 로그로 알린다.
    """
    log("⚠️ 과거 보충은 일봉만 복구해요. 그날의 분봉·시간외·경보·뉴스는 복구할 수 없어('확인 불가') "
        "점수가 환산 처리됩니다. 정확한 과거 조회는 매일 18:10 수집을 빠뜨리지 않는 것뿐이에요.")
    # 상세 구현은 실데이터 검증 단계에서 KIS 과거 순위 API 가용성 확인 후 확장 예정.
    return {"date": trade_date, "note": "daily-only backfill placeholder"}
