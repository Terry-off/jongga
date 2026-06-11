"""판단 엔진의 데이터 모델 — DESIGN.md 4장"""
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Veto:
    code: str    # 베토 번호·식별자
    title: str   # 짧은 제목
    easy: str    # 쉬운 말 설명


@dataclass
class ScoreItem:
    key: str
    title: str
    earned: float
    max_points: float
    available: bool              # False = 데이터가 없어 "확인 불가" (만점에서 제외)
    notes: list[str] = field(default_factory=list)


@dataclass
class MarketSignal:
    color: str                   # green / yellow / red
    reasons: list[str]
    day_pct: float | None = None         # 코스피 등락률
    closed_strong: bool | None = None    # 지수가 당일 가격대 상단에서 마감
    afternoon_higher_lows: bool | None = None
    index_available: bool = False


@dataclass
class DayContext:
    date: str                    # YYYY-MM-DD
    weekday: int                 # 0=월
    events_tomorrow: list[str]
    pre_holiday: bool
    signal: MarketSignal
    cfg: Callable                # settings.cfg
    theme_available: bool = False
    material_available: bool = False


@dataclass
class StockView:
    """채점에 필요한 한 종목의 모든 데이터"""
    code: str
    name: str
    market: str
    price: int
    change_rate: float
    trading_value: int           # 원
    market_cap_eok: int
    value_rank: int              # 유니버스 내 거래대금 순위 (1부터)
    daily: list                  # 과거→오늘 오름차순 일봉 (오늘 포함)
    minutes: list                # 당일 분봉 [{time:"HHMM", open, high, low, close, volume}]
    investor: list               # 일별 수급 [{date, foreign_net, inst_net, person_net}]
    flags: dict                  # 경보·과열 등 상태 플래그 (current_price 형태)
    sources: str = ""
    theme: str | None = None
    theme_sync_count: int = 0
    is_theme_leader: bool = False
    theme_leader_3d_gain: float = 0.0
    material_grade: str | None = None   # A/B/C — M3에서 채움


@dataclass
class Candidate:
    stock: StockView
    items: list[ScoreItem]
    earned: float
    available_max: float
    pct: float                   # earned / available_max × 100
    verdict: str                 # full / half / watch
    verdict_label: str
    position_amount: int         # 원 (watch는 0)
    stock_class: str             # large / theme / midsmall
    unavailable: list[str]       # 확인 불가 항목 이름들


@dataclass
class DayResult:
    date: str
    signal: MarketSignal
    candidates: list[Candidate]
    rejected: list[tuple[StockView, list[Veto]]]
    analyzed: int
    notes: list[str] = field(default_factory=list)
