"""테마 동조·대장주 판별 — 캐시된 테마맵 + 오늘 유니버스로 종목에 주입 (DESIGN.md 4.6)

동조 기준: 같은 테마에서 당일 등락률 ≥ sync_min_change, 거래대금 ≥ sync_min_value 인 종목 N개 이상
대장주 2요건: 테마 내 거래대금 1위 + 상승률 상위 3위 이내
후발주 베토용: 대장주의 3일 누적 상승률
"""


class ThemeResolver:
    def __init__(self, theme_map: dict, universe: list[dict], cfg, daily_fn=None):
        """theme_map: {테마명: [종목코드]}, universe: 유니버스 row 목록, daily_fn: code->일봉(대장주 3일 상승 계산)"""
        self.cfg = cfg
        self.daily_fn = daily_fn
        self.by_code = {r["code"]: r for r in universe}
        # 종목 → 소속 테마들
        self.themes_of: dict[str, list[str]] = {}
        self.members: dict[str, list[str]] = {}
        for theme, codes in theme_map.items():
            present = [c for c in codes if c in self.by_code]
            if not present:
                continue
            self.members[theme] = codes
            for c in present:
                self.themes_of.setdefault(c, []).append(theme)
        self._leader_3d_cache: dict[str, float] = {}

    def _risers(self, theme: str) -> list[str]:
        min_chg = self.cfg("sector.sync_min_change", 3.0)
        min_val = self.cfg("sector.sync_min_value_eok", 50) * 1e8
        out = []
        for code in self.members.get(theme, []):
            row = self.by_code.get(code)
            if row and row.get("change_rate", 0) >= min_chg and row.get("trading_value", 0) >= min_val:
                out.append(code)
        return out

    def _leader(self, theme: str) -> str | None:
        """테마 내 거래대금 1위 + 상승률 상위 3위 이내인 종목 (둘 다 만족해야 대장주)"""
        present = [(c, self.by_code[c]) for c in self.members.get(theme, []) if c in self.by_code]
        if not present:
            return None
        by_value = sorted(present, key=lambda x: x[1].get("trading_value", 0), reverse=True)
        top_value_code = by_value[0][0]
        by_change = sorted(present, key=lambda x: x[1].get("change_rate", 0), reverse=True)
        top3_change = {c for c, _ in by_change[:3]}
        return top_value_code if top_value_code in top3_change else None

    def _leader_3d_gain(self, leader_code: str) -> float:
        if leader_code in self._leader_3d_cache:
            return self._leader_3d_cache[leader_code]
        gain = 0.0
        if self.daily_fn:
            daily = self.daily_fn(leader_code) or []
            if len(daily) >= 4:
                base = daily[-4]["close"]
                if base > 0:
                    gain = (daily[-1]["close"] - base) / base * 100
        self._leader_3d_cache[leader_code] = gain
        return gain

    def annotate(self, stock) -> None:
        """stock.theme / theme_sync_count / is_theme_leader / theme_leader_3d_gain 설정"""
        themes = self.themes_of.get(stock.code)
        if not themes:
            return
        # 동반 상승 종목이 가장 많은(가장 강하게 움직인) 테마를 대표로 선택
        best_theme = max(themes, key=lambda t: len(self._risers(t)))
        risers = self._risers(best_theme)
        leader = self._leader(best_theme)
        stock.theme = best_theme
        stock.theme_sync_count = len(risers)
        stock.is_theme_leader = (leader == stock.code)
        if not stock.is_theme_leader and leader:
            stock.theme_leader_3d_gain = self._leader_3d_gain(leader)
