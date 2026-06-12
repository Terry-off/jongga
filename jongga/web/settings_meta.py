"""설정 화면에 보여줄 항목 정의 — defaults.yaml 카탈로그(DESIGN.md 5장)와 1:1"""
from dataclasses import dataclass

from jongga import settings


@dataclass
class Item:
    key: str
    label: str
    unit: str
    desc: str
    step: float = 1
    min: float | None = None
    max: float | None = None


GROUPS: list[tuple[str, list[Item]]] = [
    ("💰 계좌·비중 (제1방어선)", [
        Item("account.total_asset", "계좌 자산", "원",
             "비중 계산의 기준이 되는 총 투자금이에요", step=1_000_000, min=0),
        Item("account.risk_per_trade_pct", "1R — 한 번에 감수할 손실", "%",
             "한 종목이 틀렸을 때 잃어도 되는 금액의 비율. 설계서 권장 0.3~0.5%", step=0.1, min=0.1, max=2),
        Item("account.worst_gap_large_pct", "대형주 최악 갭 가정", "%",
             "대형·실적주가 하룻밤에 떨어질 수 있다고 가정하는 폭", step=0.5, min=1, max=30),
        Item("account.worst_gap_theme_pct", "테마·중소형주 최악 갭 가정", "%",
             "테마·중소형주가 하룻밤에 떨어질 수 있다고 가정하는 폭", step=0.5, min=1, max=30),
    ]),
    ("💧 거래대금 기준 (돈이 몰렸는가)", [
        Item("trading_value.midsmall_min_eok", "중소형주 최소 거래대금", "억",
             "이보다 적게 거래된 중소형주는 탈락 — 내가 팔 때 받아줄 사람이 없어요", step=50, min=0),
        Item("trading_value.theme_min_eok", "테마주 최소 거래대금", "억",
             "강한 테마로 움직이는 종목에 요구하는 더 높은 기준", step=50, min=0),
        Item("trading_value.large_rank_max", "대형주 거래대금 순위 기준", "위",
             "대형주는 금액 대신 '오늘 시장에서 몇 번째로 돈이 몰렸나'로 판단", step=5, min=1, max=200),
        Item("trading_value.surge_vs_prev_ratio", "거래대금 급증 가점 기준", "배",
             "어제보다 이 배수 이상 돈이 몰리면 가점 — 시장의 관심이 새로 붙은 신호", step=0.5, min=1),
        Item("trading_value.large_cap_threshold_eok", "대형주 구분 시가총액", "억",
             "이 시총 이상이면 대형주로 분류 (갭 가정·거래대금 기준이 달라져요)", step=1000, min=0),
    ]),
    ("🕯️ 캔들 모양 (베토 기준)", [
        Item("candle.max_upper_shadow_ratio", "윗꼬리 허용 한도", "",
             "윗꼬리가 하루 변동폭에서 차지하는 비율이 이보다 크면 탈락", step=0.05, min=0, max=1),
        Item("candle.min_close_position", "종가 위치 최소 기준", "",
             "0.5 = 하루 변동폭의 중간. 이보다 아래에서 마감하면 탈락", step=0.05, min=0, max=1),
        Item("candle.good_close_position", "종가 고가권 가점 기준", "",
             "이 위치 이상에서 마감하면 '고가권 마감' 가점", step=0.05, min=0, max=1),
    ]),
    ("🚀 막판 급등 차단 (베토 4)", [
        Item("late_surge.max_late_gain_share", "14시 이후 상승 비중 한도", "",
             "하루 상승분 중 오후 2시 이후 비중이 이보다 크면 탈락 — 차익 매물 폭탄 예약", step=0.05, min=0, max=1),
        Item("late_surge.min_day_gain_for_check", "점검 대상 최소 등락률", "%",
             "이 정도는 올라야 막판 급등 여부를 점검해요", step=0.5, min=0),
    ]),
    ("🎯 점수 기준", [
        Item("score.full_weight_cut", "정상 비중 점수", "점",
             "이 점수 이상이면 공식 한도의 100% 비중 후보", step=1, min=50, max=100),
        Item("score.half_weight_cut", "절반 비중 점수", "점",
             "이 점수 이상이면 한도의 50%만", step=1, min=50, max=100),
        Item("score.watch_cut", "관찰 기준 점수", "점",
             "이 점수 이상이면 매매는 금지하되 기록용으로 표시", step=1, min=0, max=100),
    ]),
    ("🔍 분석 범위", [
        Item("universe.analyze_top", "분석 종목 수 상한", "종목",
             "0 = 제한 없음(거래대금 기준을 통과할 수 있는 전 종목 — 누락 없음). 숫자를 넣으면 거래대금 상위 그 수까지만 봐서 더 빨라져요", step=10, min=0, max=500),
        Item("universe.min_change_rate", "상승률 상위 편입 컷", "%",
             "이 등락률 이상인 종목을 상승률 경로로 후보에 추가", step=0.5, min=0),
    ]),
    ("🛑 킬스위치 (제1방어선)", [
        Item("killswitch.daily_loss_r", "하루 손실 한도", "R",
             "하루 손실 합계가 이만큼이면 당일 추가 매매 금지 — 복구 매매를 차단해요", step=0.5, min=0.5, max=10),
        Item("killswitch.weekly_loss_r", "한 주 손실 한도", "R",
             "이번 주 손실이 이만큼이면 그 주 매매 종료, 주말 복기", step=0.5, min=1, max=20),
        Item("killswitch.monthly_loss_r", "한 달 손실 한도", "R",
             "한 달 손실이 이만큼이면 실전 중단, 소액 검증 모드로 복귀", step=0.5, min=2, max=40),
        Item("killswitch.consecutive_losses", "연속 손절 휴식 기준", "회",
             "연속으로 이만큼 손절하면 1거래일 휴식 + 다음 비중 절반", step=1, min=2, max=10),
    ]),
    ("🛡️ 위험 관리", [
        Item("risk_stock.exclude_warning", "거래소 경보 종목 제외", "",
             "투자주의·경고·위험·단기과열·관리종목을 무조건 탈락시켜요 (강력 권장: 켜기)"),
        Item("risk_stock.cb_lookback_days", "유증·CB 공시 소급 기간", "일",
             "최근 이 기간 안에 유상증자·전환사채 공시가 있으면 탈락", step=5, min=0, max=120),
        Item("calendar.friday_requires_a_grade", "금요일·연휴 전일 제한", "",
             "금요일엔 A급 재료 + 85점만 절반 비중 허용 (켜기 권장)"),
        Item("sector.smallcap_supply_realloc", "소형주 수급 항목 제외", "",
             "시총이 작은 회사는 외국인·기관 수급 대신 거래대금·분봉으로 판단"),
        Item("sector.smallcap_threshold_eok", "소형주 구분 시가총액", "억",
             "이 시총 미만이면 소형주로 보고 수급 배점을 재배분", step=500, min=0),
    ]),
]


def render() -> list[tuple[str, list[dict]]]:
    ovr = settings.overrides()
    out = []
    for group, items in GROUPS:
        rows = []
        for it in items:
            default = settings.yaml_default(it.key)
            rows.append({
                "key": it.key, "label": it.label, "unit": it.unit, "desc": it.desc,
                "step": it.step, "min": it.min, "max": it.max,
                "type": "bool" if isinstance(default, bool) else "number",
                "default": default,
                "value": settings.cfg(it.key),
                "overridden": it.key in ovr,
            })
        out.append((group, rows))
    return out


def all_items() -> list[dict]:
    return [row for _, rows in render() for row in rows]
