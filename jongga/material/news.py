"""네이버 뉴스 검색 클라이언트 — 종목 이름으로 당일 기사 제목을 가져온다"""
import html
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests

from jongga.settings import env

URL = "https://openapi.naver.com/v1/search/news.json"
_TAG = re.compile(r"<[^>]+>")


class NaverError(RuntimeError):
    pass


def _keys() -> tuple[str, str]:
    cid, secret = env("NAVER_CLIENT_ID"), env("NAVER_CLIENT_SECRET")
    if not cid or not secret:
        raise NaverError("네이버 API 키가 없습니다 (.env의 NAVER_CLIENT_ID/SECRET)")
    return cid, secret


def clean_title(raw: str) -> str:
    return html.unescape(_TAG.sub("", raw or "")).strip()


def search_news(query: str, display: int = 30) -> list[dict]:
    """최신순 뉴스. 반환: [{title, link, published(datetime)}]"""
    cid, secret = _keys()
    resp = requests.get(
        URL,
        headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret},
        params={"query": query, "display": display, "sort": "date"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise NaverError(f"네이버 뉴스 조회 실패 (HTTP {resp.status_code}) {resp.text[:120]}")
    items = []
    for it in resp.json().get("items", []):
        try:
            published = parsedate_to_datetime(it.get("pubDate", ""))
        except (TypeError, ValueError):
            continue
        items.append({
            "title": clean_title(it.get("title", "")),
            "link": it.get("originallink") or it.get("link", ""),
            "published": published.replace(tzinfo=None) if published.tzinfo else published,
        })
    return items


def filter_for_trade_date(items: list[dict], trade_date: datetime, name: str) -> list[dict]:
    """당일 기사 + 전일 저녁(18시 이후) 기사만, 제목에 종목명이 들어간 것만"""
    compact = name.replace(" ", "")
    out = []
    for it in items:
        if compact not in it["title"].replace(" ", ""):
            continue
        d = it["published"]
        same_day = d.date() == trade_date.date()
        prev_evening = (trade_date.date() - d.date()).days == 1 and d.hour >= 18
        if same_day or prev_evening:
            out.append(it)
    return out
