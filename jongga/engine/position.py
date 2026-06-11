"""비중 계산기 — R 기반 포지션 사이징 (DESIGN.md 4.7)

질문은 "이 종목 좋아 보이나?"가 아니라
"내일 최악의 갭하락이 와도 손실이 1R 안에서 끝나는가?"다.
"""


def position_amount(cfg, stock_class: str, tier: str) -> int:
    """최대 매수금액(원). tier: full/half, stock_class: large/theme/midsmall"""
    if tier not in ("full", "half"):
        return 0
    asset = cfg("account.total_asset", 10_000_000)
    one_r = asset * cfg("account.risk_per_trade_pct", 0.4) / 100
    gap_pct = cfg("account.worst_gap_large_pct", 5.0) if stock_class == "large" \
        else cfg("account.worst_gap_theme_pct", 10.0)
    base = one_r / (gap_pct / 100)
    multiplier = 1.0 if tier == "full" else 0.5
    return int(base * multiplier)


def explain_position(cfg, stock_class: str, tier: str, amount: int) -> str:
    asset = cfg("account.total_asset", 10_000_000)
    gap_pct = cfg("account.worst_gap_large_pct", 5.0) if stock_class == "large" \
        else cfg("account.worst_gap_theme_pct", 10.0)
    one_r = asset * cfg("account.risk_per_trade_pct", 0.4) / 100
    kind = "대형·실적주" if stock_class == "large" else "테마·중소형주"
    half = " (점수가 85점 미만이라 절반만)" if tier == "half" else ""
    return (f"계좌 {asset / 10000:,.0f}만원 기준 최대 {amount / 10000:,.0f}만원{half} — "
            f"{kind}라 내일 -{gap_pct:.0f}% 갭하락을 가정해도 손실이 {one_r / 10000:,.0f}만원(1R) 안에서 끝나요")
