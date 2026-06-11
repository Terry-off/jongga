"""판단 파이프라인 — 신호등 → 유니버스 → 베토 → 채점 → 판정·비중 (DESIGN.md 4장)"""
from datetime import date as date_cls

from jongga import calendar_events
from jongga.engine import market, position, score
from jongga.engine.models import Candidate, DayContext, DayResult, StockView, Veto
from jongga.engine.veto import classify, run_vetoes
from jongga.settings import cfg


def _load_stock(provider, row: dict, rank: int) -> StockView:
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
        daily=provider.daily(code) or [],
        minutes=provider.minutes(code) or [],
        investor=provider.investor(code) or [],
        flags=snapshot,
        sources=row.get("sources", ""),
    )


def run(provider, trade_date: str | None = None, top_n: int | None = None) -> DayResult:
    d = date_cls.fromisoformat(trade_date) if trade_date else date_cls.today()
    top_n = top_n or cfg("universe.analyze_top", 40)

    universe = sorted(provider.universe(), key=lambda r: r.get("trading_value", 0), reverse=True)
    events_tomorrow = calendar_events.events_for_next_session(d)
    pre_holiday = calendar_events.is_pre_holiday(d)
    theme_map = provider.theme_map()
    theme_available = bool(theme_map)

    signal = market.judge(provider.index(), events_tomorrow, pre_holiday,
                          theme_available=theme_available, sector_sync_exists=None)
    ctx = DayContext(
        date=d.isoformat(), weekday=d.weekday(),
        events_tomorrow=events_tomorrow, pre_holiday=pre_holiday,
        signal=signal, cfg=cfg,
        theme_available=theme_available, material_available=False,
    )

    candidates, rejected = [], []
    analyzed = universe[:top_n]
    for rank, row in enumerate(analyzed, start=1):
        stock = _load_stock(provider, row, rank)
        vetoes = run_vetoes(stock, ctx)
        if vetoes:
            rejected.append((stock, vetoes))
            continue
        items, earned, available_max, pct, unavailable = score.compute(stock, ctx)
        tier, label = score.verdict(pct, cfg)
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
    return DayResult(date=d.isoformat(), signal=signal, candidates=candidates,
                     rejected=rejected, analyzed=len(analyzed), notes=notes)
