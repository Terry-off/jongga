"""재료 등급 판정 규칙 — 키워드 사전(config/material_keywords.yaml) 기반

핵심 질문: "이 명분으로 내일 아침에 새로운 매수자가 들어올 것인가?"
등급 우선순위 A > B > C. '단독' 기사는 C급(보조 신호)일 뿐이다.
"""
from functools import lru_cache

import yaml

from jongga.settings import BASE_DIR

KEYWORDS_PATH = BASE_DIR / "config" / "material_keywords.yaml"
_ORDER = {"A": 3, "B": 2, "C": 1}


@lru_cache(maxsize=1)
def keywords() -> dict:
    with open(KEYWORDS_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return {k: [str(w) for w in (raw.get(k) or [])] for k in
            ("news_a", "news_b", "news_c", "dart_a", "dart_b", "dart_risk")}


def best_grade(*grades: str | None) -> str | None:
    found = [g for g in grades if g]
    return max(found, key=lambda g: _ORDER[g]) if found else None


def grade_news_titles(titles: list[str]) -> tuple[str | None, list[tuple[str, str]]]:
    """반환: (최고 등급, [(등급, 근거 제목)])"""
    kw = keywords()
    hits = []
    for title in titles:
        for grade, key in (("A", "news_a"), ("B", "news_b"), ("C", "news_c")):
            if any(w in title for w in kw[key]):
                hits.append((grade, title))
                break
    return best_grade(*(g for g, _ in hits)), hits


def grade_dart_titles(titles: list[str]) -> tuple[str | None, list[tuple[str, str]]]:
    kw = keywords()
    hits = []
    for title in titles:
        for grade, key in (("A", "dart_a"), ("B", "dart_b")):
            if any(w in title for w in kw[key]):
                hits.append((grade, title))
                break
    return best_grade(*(g for g, _ in hits)), hits


def dart_risk_titles(titles: list[str]) -> list[str]:
    kw = keywords()
    return [t for t in titles if any(w in t for w in kw["dart_risk"])]
