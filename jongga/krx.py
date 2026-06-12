"""KRX 일자별 전종목 시세 — 과거 날짜의 '그날 돈이 몰린 종목'을 재구성한다

저장(collect)이 없던 과거 날짜도 조회할 수 있게 하는 원천.
KRX 정보데이터시스템의 공개 통계(전종목 시세, MDCSTAT01501)를 사용한다.
응답에는 종가·등락률·거래대금·시가총액이 전 종목분 들어 있어
유니버스(거래대금 상위 + 상승률 상위)를 그날 기준으로 그대로 다시 만들 수 있다.
"""
import requests

URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (jongga historical lookup)",
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
}


def _num(value) -> int:
    try:
        return int(str(value).replace(",", "").strip() or 0)
    except ValueError:
        return 0


def _rate(value) -> float:
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def parse_rows(out_block: list[dict]) -> list[dict]:
    """KRX OutBlock_1 → 유니버스 row 형식 (코스피·코스닥만)"""
    rows = []
    for r in out_block:
        market = (r.get("MKT_NM") or "").strip()
        if market not in ("KOSPI", "KOSDAQ"):
            continue
        code = (r.get("ISU_SRT_CD") or "").strip()
        if len(code) != 6:
            continue
        rows.append({
            "code": code,
            "name": (r.get("ISU_ABBRV") or "").strip(),
            "market": market,
            "price": _num(r.get("TDD_CLSPRC")),
            "change_rate": _rate(r.get("FLUC_RT")),
            "volume": _num(r.get("ACC_TRDVOL")),
            "trading_value": _num(r.get("ACC_TRDVAL")),       # 원
            "market_cap_eok": _num(r.get("MKTCAP")) // 100_000_000,
        })
    return rows


def fetch_day(date_yyyymmdd: str, timeout: int = 20) -> list[dict]:
    """해당 거래일의 전 종목 시세. 휴장일·실패 시 빈 리스트"""
    try:
        resp = requests.post(URL, headers=HEADERS, timeout=timeout, data={
            "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
            "locale": "ko_KR",
            "mktId": "ALL",
            "trdDd": date_yyyymmdd,
            "share": "1",
            "money": "1",
            "csvxls_isNo": "false",
        })
        if resp.status_code != 200:
            return []
        return parse_rows(resp.json().get("OutBlock_1", []))
    except (requests.RequestException, ValueError):
        return []


def build_universe(rows: list[dict], cfg) -> list[dict]:
    """전 종목에서 '베토 2(거래대금)를 통과할 가능성이 있는' 종목을 전부 뽑는다 — 누락 0

    포함 조건 (베토 2와 수학적으로 동일):
      ① 거래대금 ≥ 중소형 최소 기준(기본 300억) — 중소형·테마주가 통과할 수 있는 최저선
      ② 거래대금 순위 ≤ 대형주 기준(기본 50위) — 대형주 판정 경로
    이 컷 아래 종목은 어떤 분류로도 베토 2를 통과할 수 없으므로 제외해도 결과가 같다.
    """
    floor = float(cfg("trading_value.midsmall_min_eok", 300)) * 1e8
    rank_max = int(cfg("trading_value.large_rank_max", 50))
    min_chg = float(cfg("universe.min_change_rate", 3.0))

    by_value = sorted((r for r in rows if r["trading_value"] > 0),
                      key=lambda r: r["trading_value"], reverse=True)
    out = []
    for rank, r in enumerate(by_value, start=1):
        if r["trading_value"] < floor and rank > rank_max:
            break  # 거래대금 내림차순이므로 이후는 전부 기준 미달
        src = []
        if rank <= rank_max:
            src.append("거래대금상위")
        if r["change_rate"] >= min_chg:
            src.append("상승률상위")
        out.append(dict(r, sources=",".join(src) or "거래대금 기준 통과"))
    return out
