"""검증 리포트 — 시스템은 검증 전까지 가설이다 (설계서 제9부)

통과 기준 3개를 모두 충족해야 다음 단계(소액 → 표준 → 확대)로 간다:
  ① 규칙 준수율 95% 이상 (수익률보다 먼저 본다)
  ② 승률 55% 이상 또는 기대값 양수
  ③ 평균 손실이 1R 이내로 통제
"""


def compute(entries: list[dict], cfg) -> dict:
    closed = [e for e in entries if e.get("status") == "closed"]
    open_count = sum(1 for e in entries if e.get("status") == "open")
    n = len(closed)
    if n == 0:
        return {"closed": 0, "open": open_count, "enough_data": False, "min_trades": 30}

    rs = [float(e.get("pnl_r") or 0.0) for e in closed]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    violations = sum(1 for e in closed if e.get("rule_violation"))

    win_rate = len(wins) / n
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss
    compliance = 1 - violations / n
    max_loss = min(rs) if rs else 0.0

    checks = {
        "compliance": compliance >= 0.95,
        "edge": win_rate >= 0.55 or expectancy > 0,
        "loss_control": avg_loss <= 1.0,
    }
    return {
        "closed": n,
        "open": open_count,
        "enough_data": n >= 30,           # 설계서: 최소 30~50회 후 판정
        "min_trades": 30,
        "total_r": round(sum(rs), 2),
        "win_rate": round(win_rate * 100, 1),
        "avg_win_r": round(avg_win, 2),
        "avg_loss_r": round(avg_loss, 2),
        "expectancy_r": round(expectancy, 3),
        "compliance": round(compliance * 100, 1),
        "violations": violations,
        "max_loss_r": round(max_loss, 2),
        "losses_over_2r": sum(1 for r in rs if r <= -2.0),
        "checks": checks,
        "all_pass": all(checks.values()),
    }
