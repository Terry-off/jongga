"""판단 파이프라인 — 신호등 → 유니버스 → 단계별 베토 → 채점 → 판정·비중 (DESIGN.md 4장)

속도 원칙: 베토는 '하나라도 걸리면 탈락'이므로, 싼 데이터(거래대금·경보)로 걸리는 종목은
비싼 데이터(분봉·뉴스·수급)를 아예 조회하지 않는다. 결과는 전부 조회했을 때와 동일하다.
"""
from datetime import date as date_cls

from jongga import calendar_events
from jongga.engine import candle, market, position, score
from jongga.engine.models import Candidate, DayContext, DayResult, StockView, Veto
from jongga.engine.veto import (classify, stage_basic, stage_daily,
                                stage_material, stage_minutes)
from jongga.settings import cfg


def _base_stock(provider, row: dict, rank: int) -> StockView:
    """1단계용 — 스냅샷까지만 싣고, 비싼 데이터(일봉·분봉·수급)는 통과할 때마다 채운다"""
    code = row["code"]
    snapshot = provider.snapshot(code) or {}
    return StockView(
        code=code,
        name=row.get("name", ""),
        market=row.get("market", ""),
        price=row.get("price", 0),
        change_rate=row.get("change_rate", 0.0),
        trading_value=row.get("trading_value", 0),
        market_cap_eok=snapshot.get("market_cap_eok", 0),
        value_rank=rank,
        daily=[],
        minutes=[],
        investor=[],
        flags=snapshot,
        sources=row.get("sources", ""),
    )


def _value_criterion_ok(stock: StockView, ctx: DayContext) -> bool:
    cls = classify(stock, ctx.cfg)
    if cls == "large":
        return stock.value_rank <= ctx.cfg("trading_value.large_rank_max", 50)
    need = ctx.cfg("trading_value.theme_min_eok", 500) if cls == "theme" \
        else ctx.cfg("trading_value.midsmall_min_eok", 300)
    return stock.trading_value / 1e8 >= need


def _validate_material(stock: StockView, ctx: DayContext) -> None:
    """C급은 설계서대로 동반 조건(거래대금·종가 고가권·테마 동조) 충족 시에만 인정.
    확인 불가능한 조건(테마 데이터 없음)은 보수적으로 '제한 인정' 메모를 남긴다."""
    if stock.material_grade != "C" or not stock.daily:
        return
    reqs = ctx.cfg("material.c_grade_requires", ["trading_value", "sector_sync", "close_high"]) or []
    today = stock.daily[-1]
    failed, unknown = [], []
    if "close_high" in reqs:
        pos = candle.close_position(today["high"], today["low"], today["close"])
        if pos < ctx.cfg("candle.good_close_position", 0.70):
            failed.append("종가가 고가권이 아님")
    if "trading_value" in reqs and not _value_criterion_ok(stock, ctx):
        failed.append("거래대금 부족")
    if "sector_sync" in reqs:
        if ctx.theme_available:
            if stock.theme_sync_count < ctx.cfg("sector.sync_min_count", 3):
                failed.append("테마 동조 없음")
        else:
            unknown.append("테마 동조")
    if failed:
        stock.material_grade = None
        stock.material_note = ("'단독'류(C급) 재료인데 " + ", ".join(failed) +
                               " — 단독 신호만으로는 사지 않아요")
    elif unknown:
        stock.material_note = ("C급 동반 조건 중 " + ", ".join(unknown) +
                               "는 확인 불가 — 나머지 조건 충족으로 제한 인정")


def run(provider, trade_date: str | None = None, top_n: int | None = None,
        progress=lambda done, total, label: None) -> DayResult:
    d = date_cls.fromisoformat(trade_date) if trade_date else date_cls.today()
    top_n = top_n or cfg("universe.analyze_top", 40)

    progress(0, 0, "오늘 돈이 몰린 종목을 모으는 중")
    universe = sorted(provider.universe(), key=lambda r: r.get("trading_value", 0), reverse=True)
    events_tomorrow = calendar_events.events_for_next_session(d)
    pre_holiday = calendar_events.is_pre_holiday(d)
    progress(0, 0, "테마·시장 신호등 확인 중")
    theme_map = provider.theme_map()
    theme_available = bool(theme_map)
    resolver = None
    if theme_available:
        from jongga.theme.resolver import ThemeResolver
        resolver = ThemeResolver(theme_map, universe, cfg, daily_fn=provider.daily)

    material_available = bool(getattr(provider, "material_enabled", lambda: False)())
    signal = market.judge(provider.index(), events_tomorrow, pre_holiday,
                          theme_available=theme_available, sector_sync_exists=None)
    ctx = DayContext(
        date=d.isoformat(), weekday=d.weekday(),
        events_tomorrow=events_tomorrow, pre_holiday=pre_holiday,
        signal=signal, cfg=cfg,
        theme_available=theme_available, material_available=material_available,
    )

    candidates, rejected = [], []
    early_filtered = 0
    analyzed = universe[:top_n]
    for rank, row in enumerate(analyzed, start=1):
        progress(rank, len(analyzed), f"{row.get('name', row.get('code', ''))} 분석 중")

        # 1단계: 유니버스·스냅샷·테마만으로 — 거래대금·경보·이벤트·과열 후발주
        stock = _base_stock(provider, row, rank)
        if resolver:
            resolver.annotate(stock)
        vetoes = stage_basic(stock, ctx)
        if vetoes:
            rejected.append((stock, vetoes))
            early_filtered += 1
            continue

        # 2단계: 일봉 — 윗꼬리·힘없는 종가
        stock.daily = provider.daily(stock.code) or []
        vetoes = stage_daily(stock, ctx)
        if vetoes:
            rejected.append((stock, vetoes))
            continue

        # 3단계: 재료(뉴스·공시) — 재료 없음·물량 이벤트·금요일 비A급
        if material_available:
            mat = provider.materials(stock.code, stock.name) or {}
            stock.material_checked = bool(mat.get("checked"))
            stock.material_grade = mat.get("grade")
            stock.material_evidence = mat.get("evidence", [])
            stock.material_risks = mat.get("risks", [])
            _validate_material(stock, ctx)
        vetoes = stage_material(stock, ctx)
        if vetoes:
            rejected.append((stock, vetoes))
            continue

        # 4단계: 분봉(가장 비싼 조회) — 여기까지 살아남은 종목만
        stock.minutes = provider.minutes(stock.code) or []
        vetoes = stage_minutes(stock, ctx)
        if vetoes:
            rejected.append((stock, vetoes))
            continue

        # 최종 생존자만 수급까지 조회해 채점
        stock.investor = provider.investor(stock.code) or []
        items, earned, available_max, pct, unavailable = score.compute(stock, ctx)
        tier, label = score.verdict(pct, cfg)
        # 금요일·연휴 전일은 A급+85점이어도 절반 비중까지만 (설계서 제2부)
        if tier == "full" and (ctx.weekday == 4 or ctx.pre_holiday):
            tier, label = "half", "절반 비중 후보 (금요일·연휴 전일 제한)"
        if tier == "exclude":
            rejected.append((stock, [Veto("score", "기준 점수 미달",
                                          f"점수 {pct:.1f}점 — 관찰 기준(65점)에도 못 미쳐 제외했어요")]))
            continue
        stock_class = classify(stock, cfg)
        amount = position.position_amount(cfg, stock_class, tier)
        candidates.append(Candidate(
            stock=stock, items=items, earned=earned, available_max=available_max,
            pct=pct, verdict=tier, verdict_label=label,
            position_amount=amount, stock_class=stock_class, unavailable=unavailable,
        ))

    candidates.sort(key=lambda c: c.pct, reverse=True)

    notes = []
    if candidates and candidates[0].unavailable:
        notes.append("확인 못한 항목(" + ", ".join(candidates[0].unavailable) + ")은 만점에서 제외하고 채점했어요")
    if early_filtered:
        notes.append(f"{early_filtered}종목은 1차 조건(거래대금·경보 등)에서 일찍 걸러 분석 시간을 줄였어요")
    return DayResult(date=d.isoformat(), signal=signal, candidates=candidates,
                     rejected=rejected, analyzed=len(analyzed), notes=notes)
