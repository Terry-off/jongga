"""킬스위치 — 시스템이 나를 강제로 멈추는 장치 (설계서 제1부)

연속 손실 뒤의 매매는 '복구 매매'가 되고, 복구 매매는 규칙을 무시한다.
판단력이 무너진 상태에서 판단하지 않도록, 멈춤을 데이터로 자동 판정한다.
"""
from dataclasses import dataclass, field
from datetime import date as date_cls

from jongga.calendar_events import next_trading_day, prev_trading_day


@dataclass
class KillStatus:
    active: bool                       # True = 오늘 매매 금지
    reasons: list[str] = field(default_factory=list)   # 발동 사유 (쉬운 말)
    cautions: list[str] = field(default_factory=list)  # 금지는 아니지만 지켜야 할 제한


def _r(value) -> float:
    return float(value or 0.0)


def evaluate(entries: list[dict], cfg, today: date_cls | None = None) -> KillStatus:
    """closed 일지 기준으로 5개 트리거 판정. today 주입 가능(테스트·과거 복기용)"""
    today = today or date_cls.today()
    status = KillStatus(active=False)
    closed = [e for e in entries if e.get("status") == "closed" and e.get("exit_date")]
    if not closed:
        return status

    day_r = week_r = month_r = 0.0
    iso_today = today.isocalendar()[:2]
    for e in closed:
        try:
            d = date_cls.fromisoformat(e["exit_date"])
        except ValueError:
            continue
        r = _r(e.get("pnl_r"))
        if d == today:
            day_r += r
        if d.isocalendar()[:2] == iso_today:
            week_r += r
        if (d.year, d.month) == (today.year, today.month):
            month_r += r

    if month_r <= -cfg("killswitch.monthly_loss_r", 8.0):
        status.active = True
        status.reasons.append(
            f"이번 달 손실이 {month_r:+.1f}R이에요 — 실전을 멈추고 소액 검증 모드로 돌아갈 때예요. "
            "시스템 자체를 복기해야 하는 신호예요.")
    if week_r <= -cfg("killswitch.weekly_loss_r", 4.0):
        status.active = True
        status.reasons.append(
            f"이번 주 손실이 {week_r:+.1f}R이에요 — 이번 주 매매는 여기서 끝내고 주말에 복기해요.")
    if day_r <= -cfg("killswitch.daily_loss_r", 2.0):
        status.active = True
        status.reasons.append(
            f"오늘 손실이 {day_r:+.1f}R이에요 — 오늘은 더 매매하지 않아요. 잃은 날 더 하면 복구 매매가 돼요.")

    # 연속 손절: 청산 순서대로 뒤에서부터 음수 R 카운트
    closed_sorted = sorted(closed, key=lambda e: (e["exit_date"], e["id"]))
    streak = 0
    for e in reversed(closed_sorted):
        if _r(e.get("pnl_r")) < 0:
            streak += 1
        else:
            break
    need = cfg("killswitch.consecutive_losses", 3)
    if streak >= need:
        last_exit = date_cls.fromisoformat(closed_sorted[-1]["exit_date"])
        rest_until = next_trading_day(last_exit)
        if today <= rest_until:
            status.active = True
            status.reasons.append(
                f"{streak}번 연속 손절이에요 — 최소 1거래일({rest_until.strftime('%m/%d')}까지) 쉬어요. "
                "연속으로 틀릴 때는 시장이 내 방식과 안 맞는 날이에요.")
        else:
            status.cautions.append(
                f"최근 {streak}번 연속 손절 — 다음 매매는 평소 비중의 절반으로 줄이세요.")

    # 규칙 위반: 위반한 날의 '다음 거래일' 매매 금지 (수익이어도 위반은 위반)
    for e in closed:
        if e.get("rule_violation"):
            d = date_cls.fromisoformat(e["exit_date"])
            if next_trading_day(d) == today or d == today:
                status.active = True
                note = (e.get("violation_note") or "").strip()
                status.reasons.append(
                    f"규칙 위반 매매({e.get('name', '')}{' — ' + note if note else ''})가 있었어요. "
                    "결과가 수익이어도 위반 다음 날은 쉬는 규칙이에요. 위반 수익은 부채예요.")
                break

    return status
