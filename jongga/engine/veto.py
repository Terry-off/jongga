"""베토 조건 — 하나라도 걸리면 점수 계산 없이 탈락 (DESIGN.md 4.3)

속도를 위해 '데이터 비용' 순서로 4단계로 나눠 평가한다 (결과는 동일):
  stage_basic    유니버스·스냅샷·테마만 필요 (호출 거의 없음) — 거래대금·경보·이벤트·과열 후발주
  stage_daily    일봉 1회 — 윗꼬리·힘없는 종가
  stage_material 뉴스·공시 — 재료 없음·물량 이벤트·금요일 비A급
  stage_minutes  분봉(가장 비쌈) — 막판 수직 급등
앞 단계에서 걸린 종목은 뒤 단계의 비싼 데이터를 아예 조회하지 않는다.

베토 9(매매 금지일)는 종목이 아닌 '날'의 속성이므로 여기서 처리하지 않고,
시장 신호등이 🔴인 날은 화면 전체 경고로 처리한다 (분석 결과는 보여줌).
"""
from jongga.engine import candle
from jongga.engine.models import DayContext, StockView, Veto

STATUS_NAMES = {"51": "관리종목", "52": "투자위험", "53": "투자경고", "54": "투자주의", "58": "거래정지", "59": "단기과열"}
WARN_NAMES = {"01": "투자주의", "02": "투자경고", "03": "투자위험"}


def classify(s: StockView, cfg) -> str:
    """large / theme / midsmall — 거래대금 기준과 최악 갭 가정에 사용"""
    if s.market_cap_eok >= cfg("trading_value.large_cap_threshold_eok", 20000):
        return "large"
    if s.theme and s.theme_sync_count >= cfg("sector.sync_min_count", 3):
        return "theme"
    return "midsmall"


def risky_flags(flags: dict) -> list[str]:
    found = []
    status = STATUS_NAMES.get(str(flags.get("status_code", "")))
    if status:
        found.append(status)
    warn = WARN_NAMES.get(str(flags.get("market_warn_code", "")))
    if warn and warn not in found:
        found.append(warn)
    if flags.get("short_overheat_yn") == "Y" and "단기과열" not in found:
        found.append("단기과열")
    if flags.get("halt_yn") == "Y":
        found.append("거래정지")
    if flags.get("delisting_yn") == "Y":
        found.append("정리매매")
    return found


def stage_basic(s: StockView, ctx: DayContext) -> list[Veto]:
    """1차 필터 — 유니버스 row·스냅샷·테마 캐시만으로 판정 (추가 조회 없음)"""
    cfg = ctx.cfg
    vetoes: list[Veto] = []

    # 베토 2. 거래대금 미달
    eok = s.trading_value / 1e8
    cls = classify(s, cfg)
    if cls == "large":
        rank_max = cfg("trading_value.large_rank_max", 50)
        if s.value_rank > rank_max:
            vetoes.append(Veto("V2", "거래대금 부족",
                               f"대형주인데 오늘 거래대금 순위가 {s.value_rank}위예요 (기준: {rank_max}위 이내). "
                               "돈이 충분히 몰리지 않으면 내일 이어가기 어려워요."))
    else:
        need = cfg("trading_value.theme_min_eok", 500) if cls == "theme" else cfg("trading_value.midsmall_min_eok", 300)
        if eok < need:
            vetoes.append(Veto("V2", "거래대금 부족",
                               f"오늘 거래대금이 {eok:,.0f}억이에요 (기준: {need:,.0f}억 이상). "
                               "돈이 적게 몰린 종목은 내가 팔고 싶을 때 받아줄 사람이 없어요."))

    # 베토 5. 과열 테마의 후발주
    if ctx.theme_available and s.theme and not s.is_theme_leader:
        if s.theme_leader_3d_gain > cfg("sector.overheat_3day_gain", 20.0):
            vetoes.append(Veto("V5", "과열 테마의 2등주",
                               f"'{s.theme}' 테마 1등이 이미 3일간 {s.theme_leader_3d_gain:.0f}% 올랐어요. "
                               "뒤따라 오른 종목은 조정이 오면 가장 먼저 버려져요."))

    # 베토 6. 위험종목 (거래소 경보 — 스냅샷 플래그)
    if cfg("risk_stock.exclude_warning", True):
        risks = risky_flags(s.flags)
        if risks:
            vetoes.append(Veto("V6", f"위험 지정: {', '.join(risks)}",
                               "거래소가 경고 딱지를 붙인 종목이에요. 차트가 아무리 좋아도 "
                               "내가 통제할 수 없는 이유로 급락할 수 있어 무조건 제외해요."))

    # 베토 7. 익일 대형 이벤트
    if ctx.events_tomorrow:
        vetoes.append(Veto("V7", "내일 큰 발표가 있어요",
                           f"다음 거래일 전에 {', '.join(ctx.events_tomorrow)} 일정이 있어요. "
                           "밤사이 결과에 따라 종목과 상관없이 갭이 결정돼요."))

    return vetoes


def stage_daily(s: StockView, ctx: DayContext) -> list[Veto]:
    """2차 필터 — 일봉 필요"""
    cfg = ctx.cfg
    vetoes: list[Veto] = []
    today = s.daily[-1] if s.daily else None

    # 베토 3. 장대 윗꼬리 / 종가가 캔들 중간 이하
    if today:
        shadow = candle.upper_shadow_ratio(today["high"], today["low"], today["close"])
        pos = candle.close_position(today["high"], today["low"], today["close"])
        if shadow > cfg("candle.max_upper_shadow_ratio", 0.40):
            vetoes.append(Veto("V3", "윗꼬리가 길어요",
                               f"오늘 가장 높았던 가격에서 {shadow:.0%}나 밀려 내려왔어요. "
                               "위에서 판 사람들의 물량이 내일 아침에 다시 나올 수 있어요."))
        if pos < cfg("candle.min_close_position", 0.50):
            vetoes.append(Veto("V3", "종가가 힘없이 마감",
                               "마감 가격이 오늘 움직인 범위의 절반 아래예요. "
                               "장 막판까지 사려는 힘이 약했다는 뜻이에요."))

    return vetoes


def stage_material(s: StockView, ctx: DayContext) -> list[Veto]:
    """3차 필터 — 재료(뉴스·공시) 필요"""
    cfg = ctx.cfg
    vetoes: list[Veto] = []

    # 베토 1. 재료 불명확 — 엔진이 켜져 있고 조회도 성공했는데 재료가 없을 때만
    #          (조회 실패는 베토가 아니라 '확인 불가' 처리)
    if ctx.material_available and s.material_checked and s.material_grade is None:
        easy = s.material_note or "오를 만한 이유(뉴스·공시)를 찾지 못했어요. 이유 없는 급등은 따라가지 않아요."
        vetoes.append(Veto("V1", "재료 없음", easy))

    # 베토 6b. 최근 유증·CB 등 물량 이벤트 (DART)
    if s.material_risks:
        vetoes.append(Veto("V6", "최근 물량 이벤트",
                           f"최근 한 달 안에 '{s.material_risks[0]}' 공시가 있었어요. "
                           "새 주식이 풀리는 이벤트는 언제든 내 머리 위에서 매물이 쏟아질 수 있다는 뜻이에요."))

    # 베토 8. 금요일·연휴 전일 — A급 재료가 아니면 쉰다
    if (ctx.weekday == 4 or ctx.pre_holiday) and cfg("calendar.friday_requires_a_grade", True):
        if s.material_grade != "A":
            day_name = "금요일" if ctx.weekday == 4 else "연휴 전날"
            grade_note = "재료가 A급이 아니라서" if ctx.material_available else "재료를 아직 확인하지 못해서"
            vetoes.append(Veto("V8", f"{day_name}이에요",
                               f"주말·연휴 동안 뉴스 위험에 길게 노출돼요. {grade_note} 이날은 쉬어가요."))

    return vetoes


def stage_minutes(s: StockView, ctx: DayContext) -> list[Veto]:
    """4차 필터 — 분봉(가장 비싼 데이터) 필요"""
    cfg = ctx.cfg
    vetoes: list[Veto] = []

    # 베토 4. 막판(14시 이후) 수직 급등
    if s.minutes and s.change_rate >= cfg("late_surge.min_day_gain_for_check", 5.0) and len(s.daily) >= 2:
        share = candle.late_gain_share(s.minutes, s.daily[-2]["close"],
                                       cfg("late_surge.threshold_time", "14:00").replace(":", ""))
        if share is not None and share > cfg("late_surge.max_late_gain_share", 0.60):
            vetoes.append(Veto("V4", "막판 수직 급등",
                               f"오늘 오른 폭의 {share:.0%}가 오후 2시 이후에 한꺼번에 나왔어요. "
                               "내일 아침 차익 매물이 쏟아질 수 있는 가장 위험한 모양이에요."))

    return vetoes


def run_vetoes(s: StockView, ctx: DayContext) -> list[Veto]:
    """모든 단계를 한 번에 평가 (데이터가 이미 다 있을 때 — 테스트·완전 재현 경로)"""
    return (stage_basic(s, ctx) + stage_daily(s, ctx)
            + stage_material(s, ctx) + stage_minutes(s, ctx))
