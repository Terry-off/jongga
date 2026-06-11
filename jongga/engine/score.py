"""100점 채점 — DESIGN.md 4.4

데이터가 없는 항목은 available=False로 만점에서 제외하고(확인 불가),
백분율 = 획득 점수 ÷ 확인 가능한 만점 × 100 으로 판정한다.
없는 데이터를 추측으로 채우지 않는 보수 원칙.
"""
from jongga.engine import candle
from jongga.engine.models import DayContext, ScoreItem, StockView
from jongga.engine.veto import classify


def score_market(ctx: DayContext) -> ScoreItem:
    sig = ctx.signal
    earned, notes = 0.0, []
    max_points = 15.0
    if sig.index_available:
        if sig.day_pct is not None and sig.day_pct >= 0 and sig.closed_strong:
            earned += 7
            notes.append(f"시장 전체가 안정적이에요 — 코스피 {sig.day_pct:+.1f}%, 윗부분에서 마감")
        elif sig.day_pct is not None and sig.day_pct >= 0:
            earned += 3
            notes.append(f"코스피 {sig.day_pct:+.1f}% — 보통 수준")
        if sig.afternoon_higher_lows:
            earned += 4
            notes.append("지수가 오후에 바닥을 점점 높였어요")
    else:
        max_points = 4.0
        notes.append("지수 분봉을 확인할 수 없어 이벤트 항목만 반영했어요")
    if not ctx.events_tomorrow:
        earned += 4
        notes.append("내일 예정된 큰 발표가 없어요")
    return ScoreItem("market", "시장 분위기", earned, max_points, True, notes)


def score_material(s: StockView, ctx: DayContext) -> ScoreItem:
    if not ctx.material_available:
        return ScoreItem("material", "재료(뉴스·공시)", 0, 20, False,
                         ["재료 자동 분석은 M3 단계에서 합류해요"])
    grade_points = {"A": 20.0, "B": 12.0, "C": 6.0}
    earned = grade_points.get(s.material_grade or "", 0.0)
    return ScoreItem("material", "재료(뉴스·공시)", earned, 20, True,
                     [f"재료 등급 {s.material_grade}급"] if s.material_grade else [])


def score_sector(s: StockView, ctx: DayContext) -> ScoreItem:
    if not ctx.theme_available:
        return ScoreItem("sector", "테마 동조", 0, 15, False,
                         ["테마 데이터 수집은 M3 단계에서 합류해요"])
    earned, notes = 0.0, []
    if s.theme_sync_count >= ctx.cfg("sector.sync_min_count", 3):
        earned += 8
        notes.append(f"'{s.theme}' 테마에서 {s.theme_sync_count}종목이 같이 올랐어요 — 혼자가 아니에요")
    if s.is_theme_leader:
        earned += 7
        notes.append("이 테마에서 돈이 가장 많이 몰린 1등(대장주)이에요")
    return ScoreItem("sector", "테마 동조", earned, 15, True, notes)


def score_value(s: StockView, ctx: DayContext) -> ScoreItem:
    cfg = ctx.cfg
    earned, notes = 0.0, []
    eok = s.trading_value / 1e8
    cls = classify(s, cfg)
    if cls == "large":
        need_txt = f"거래대금 {s.value_rank}위 (기준: {cfg('trading_value.large_rank_max', 50)}위 이내)"
    else:
        need = cfg("trading_value.theme_min_eok", 500) if cls == "theme" else cfg("trading_value.midsmall_min_eok", 300)
        need_txt = f"거래대금 {eok:,.0f}억 (기준 {need:,.0f}억의 {eok / need:.1f}배)"
    earned += 10  # 베토 2를 통과한 종목만 채점되므로 기준 충족
    notes.append(f"돈이 몰렸어요 — {need_txt}")
    if len(s.daily) >= 2 and s.daily[-2]["trading_value"] > 0:
        ratio = s.trading_value / s.daily[-2]["trading_value"]
        if ratio >= cfg("trading_value.surge_vs_prev_ratio", 3.0):
            earned += 5
            notes.append(f"어제보다 거래대금이 {ratio:.1f}배로 급증 — 시장의 관심이 새로 붙었어요")
    return ScoreItem("value", "거래대금", earned, 15, True, notes)


def score_daily(s: StockView, ctx: DayContext) -> ScoreItem:
    cfg = ctx.cfg
    if not s.daily:
        return ScoreItem("daily", "일봉 위치", 0, 15, False, ["일봉 데이터 없음"])
    earned, notes = 0.0, []
    today = s.daily[-1]
    prior = s.daily[:-1]

    if prior:
        prior_high = max(d["high"] for d in prior[-59:])
        if today["close"] >= 0.95 * prior_high:
            earned += 6
            if today["close"] > prior_high:
                notes.append("최근 고점을 뚫었어요 — 위에 물려 있는 사람이 없는 자리예요")
            else:
                notes.append("최근 고점 바로 아래까지 왔어요 — 돌파를 노리는 자리예요")

    pos = candle.close_position(today["high"], today["low"], today["close"])
    if pos >= cfg("candle.good_close_position", 0.70):
        earned += 5
        notes.append(f"오늘 가장 높은 가격 근처에서 마감했어요 (상위 {(1 - pos) * 100:.0f}% 지점)")

    closes = [d["close"] for d in s.daily]
    mas = [candle.sma(closes, n) for n in (5, 10, 20)]
    if all(m is not None and today["close"] >= m for m in mas):
        earned += 2
        notes.append("5·10·20일 평균선 위에 있어요 — 추세가 살아 있어요")

    if len(prior) >= 10:
        prior10 = prior[-10:]
        broke = today["close"] > max(d["close"] for d in prior10)
        vol_up = today["volume"] > 1.5 * (sum(d["volume"] for d in prior10) / 10)
        if broke and vol_up:
            earned += 2
            notes.append("쉬어가던 구간을 거래량과 함께 다시 뚫었어요 (검증된 패턴)")

    return ScoreItem("daily", "일봉 위치", earned, 15, True, notes)


def score_minutes(s: StockView, ctx: DayContext) -> ScoreItem:
    if not s.minutes:
        return ScoreItem("minutes", "오후 분봉", 0, 10, False, ["분봉 데이터를 확인할 수 없어요"])
    earned, notes = 0.0, []
    steps = candle.afternoon_low_steps(s.minutes)
    if steps is not None and steps >= 2:
        earned += 5
        notes.append("오후 내내 바닥을 점점 높였어요 — '안 무너진 종목'이에요")
    elif steps == 1:
        earned += 2
    reinflow = candle.volume_reinflow_ratio(s.minutes)
    if reinflow is not None and reinflow >= 1.3:
        earned += 3
        notes.append("마감 직전(15:10 이후)에 거래가 다시 활발해졌어요 — 내일을 노리는 매수세")
    vw = candle.vwap(s.minutes)
    if vw is not None and s.minutes[-1]["close"] >= vw:
        earned += 2
        notes.append("오늘 산 사람들의 평균 단가보다 위에서 마감 — 보유자 대부분이 수익 중")
    return ScoreItem("minutes", "오후 분봉", earned, 10, True, notes)


def score_investor(s: StockView, ctx: DayContext) -> ScoreItem:
    cfg = ctx.cfg
    if cfg("sector.smallcap_supply_realloc", True) and s.market_cap_eok < cfg("sector.smallcap_threshold_eok", 3000):
        return ScoreItem("investor", "수급(외국인·기관)", 0, 10, False,
                         ["작은 회사는 외국인·기관 움직임의 의미가 약해서 거래대금·분봉으로 대신 판단해요"])
    if not s.investor:
        return ScoreItem("investor", "수급(외국인·기관)", 0, 10, False, ["수급 데이터를 확인할 수 없어요"])
    latest = s.investor[-1]
    f, i, p = latest.get("foreign_net", 0), latest.get("inst_net", 0), latest.get("person_net", 0)
    notes = []
    if latest.get("date") and latest["date"] != ctx.date.replace("-", ""):
        notes.append("(어제까지 확정된 수급 기준이에요)")
    if f > 0 and i > 0:
        earned = 10.0
        notes.insert(0, "외국인과 기관이 같이 샀어요 — 큰돈이 내일을 보고 들어왔다는 신호")
    elif f > 0 or i > 0:
        earned = 6.0
        who = "외국인" if f > 0 else "기관"
        notes.insert(0, f"{who}이 샀어요")
    elif f < 0 and i < 0 and p > 0:
        earned = 0.0
        notes.insert(0, "외국인·기관은 팔고 개인만 샀어요 — 내일 매물 부담이 커요")
    else:
        earned = 3.0
    return ScoreItem("investor", "수급(외국인·기관)", earned, 10, True, notes)


def compute(s: StockView, ctx: DayContext) -> tuple[list[ScoreItem], float, float, float, list[str]]:
    items = [
        score_market(ctx),
        score_material(s, ctx),
        score_sector(s, ctx),
        score_value(s, ctx),
        score_daily(s, ctx),
        score_minutes(s, ctx),
        score_investor(s, ctx),
    ]
    earned = sum(it.earned for it in items if it.available)
    available_max = sum(it.max_points for it in items if it.available)
    pct = earned / available_max * 100 if available_max > 0 else 0.0
    unavailable = [it.title for it in items if not it.available]
    return items, earned, available_max, pct, unavailable


def verdict(pct: float, cfg) -> tuple[str, str]:
    if pct >= cfg("score.full_weight_cut", 85):
        return "full", "정상 비중 후보"
    if pct >= cfg("score.half_weight_cut", 75):
        return "half", "절반 비중 후보"
    if pct >= cfg("score.watch_cut", 65):
        return "watch", "관찰만 (매매 금지)"
    return "exclude", "기준 미달"
