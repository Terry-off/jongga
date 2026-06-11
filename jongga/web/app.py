"""웹 대시보드 — 추천 화면·설정 화면 (DESIGN.md 6장)

실행: python -m jongga web [--demo] [--port 8765]
결과는 메모리에 캐시되고 '다시 스캔' 버튼으로 갱신한다.
설정 저장 시 캐시를 비워 다음 조회부터 새 기준이 적용된다.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from jongga import settings
from jongga.engine import pipeline
from jongga.engine.position import explain_position
from jongga.web import settings_meta

TEMPLATES_DIR = Path(__file__).parent / "templates"
KST = timezone(timedelta(hours=9))

SIGNAL_STYLE = {
    "green": {"icon": "🟢", "text": "매매해도 좋은 환경이에요",
              "cls": "bg-emerald-50 border-emerald-200 text-emerald-900"},
    "yellow": {"icon": "🟡", "text": "조심해야 하는 날이에요",
               "cls": "bg-amber-50 border-amber-200 text-amber-900"},
    "red": {"icon": "🔴", "text": "오늘은 쉬는 날이에요",
            "cls": "bg-red-50 border-red-200 text-red-900"},
}


def _eok(won) -> str:
    return f"{won / 1e8:,.0f}억"


def create_app(demo: bool = False) -> FastAPI:
    app = FastAPI(title="종가매매 추천")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["eok"] = _eok
    templates.env.filters["comma"] = lambda v: f"{v:,}"

    state = {"result": None, "ran_at": None, "error": None, "demo": demo, "viewing": None}

    def run_pipeline(date_arg: str | None = None):
        from datetime import date as _date
        if state["demo"]:
            from jongga.demo import DEMO_DATE
            from jongga.providers import DemoProvider
            state["result"] = pipeline.run(DemoProvider(), trade_date=DEMO_DATE)
            state["viewing"] = None
        elif date_arg and date_arg != _date.today().isoformat():
            from jongga.providers import DBProvider
            provider = DBProvider(date_arg)
            if not provider.has_data():
                raise RuntimeError(
                    f"{date_arg}에 저장된 데이터가 없어요. 그날 수집(collect)이 돌지 않았다면 "
                    "분봉·시간외는 복구할 수 없어요. 저장된 날짜만 조회할 수 있어요.")
            state["result"] = pipeline.run(provider, trade_date=date_arg)
            state["viewing"] = date_arg
        else:
            from jongga.providers import LiveProvider
            state["result"] = pipeline.run(LiveProvider())
            state["viewing"] = None
        state["ran_at"] = datetime.now().strftime("%H:%M")
        state["error"] = None

    def _cards(result):
        cards = []
        for c in result.candidates:
            if c.verdict not in ("full", "half"):
                continue
            notes = [n for it in c.items if it.available and it.key != "market" for n in it.notes][:4]
            pos = explain_position(settings.cfg, c.stock_class, c.verdict, c.position_amount) \
                if c.position_amount else ""
            cards.append({"c": c, "notes": notes, "pos": pos})
        return cards

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, date: str | None = None):
        # 날짜 파라미터가 바뀌었거나 첫 진입이면 다시 계산
        if date != state["viewing"] or (state["result"] is None and state["error"] is None):
            try:
                run_pipeline(date)
            except Exception as exc:
                state["error"] = str(exc)
                state["result"] = None
        result = state["result"]
        from jongga.db import collected_dates
        killswitch = None
        if not state["demo"]:
            try:
                from jongga.journal import killswitch as ks_mod
                from jongga.journal import store as journal_store
                killswitch = ks_mod.evaluate(journal_store.list_entries(), settings.cfg)
            except Exception:
                killswitch = None
        return templates.TemplateResponse(request, "index.html", {
            "result": result,
            "demo": state["demo"],
            "ran_at": state["ran_at"],
            "error": state["error"],
            "viewing": state["viewing"],
            "killswitch": killswitch,
            "past_dates": [] if state["demo"] else collected_dates()[:60],
            "signal": SIGNAL_STYLE.get(result.signal.color) if result else None,
            "cards": _cards(result) if result else [],
            "watch": [c for c in result.candidates if c.verdict == "watch"] if result else [],
        })

    @app.post("/scan")
    def scan():
        try:
            run_pipeline()
        except Exception as exc:
            state["error"] = str(exc)
            state["result"] = None
        return RedirectResponse("/", status_code=303)

    @app.get("/api/chart/{code}")
    def chart(code: str):
        result = state["result"]
        stock = None
        if result:
            for c in result.candidates:
                if c.stock.code == code:
                    stock = c.stock
                    break
            if stock is None:
                for s, _ in result.rejected:
                    if s.code == code:
                        stock = s
                        break
        if stock is None:
            return JSONResponse({"daily": [], "minutes": []}, status_code=404)
        daily = [
            {"time": f"{d['date'][:4]}-{d['date'][4:6]}-{d['date'][6:]}",
             "open": d["open"], "high": d["high"], "low": d["low"], "close": d["close"]}
            for d in stock.daily[-60:] if len(str(d.get("date", ""))) == 8
        ]
        base = datetime.fromisoformat(result.date).replace(tzinfo=KST)
        minutes = [
            {"time": int(base.replace(hour=int(m["time"][:2]), minute=int(m["time"][2:])).timestamp()),
             "value": m["close"]}
            for m in stock.minutes
        ]
        return JSONResponse({"daily": daily, "minutes": minutes})

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, saved: int = 0, reset: int = 0):
        return templates.TemplateResponse(request, "settings.html", {
            "groups": settings_meta.render(),
            "saved": saved,
            "reset": reset,
            "override_count": len(settings.overrides()),
        })

    @app.post("/settings")
    async def settings_save(request: Request):
        form = await request.form()
        for it in settings_meta.all_items():
            key = it["key"]
            if it["type"] == "bool":
                new_raw = "true" if form.get(key) else "false"
                same = (new_raw == "true") == bool(it["default"])
            else:
                raw = str(form.get(key) or "").strip()
                if raw == "":
                    continue
                try:
                    same = abs(float(raw) - float(it["default"])) < 1e-9
                except (TypeError, ValueError):
                    continue
                new_raw = raw
            if same:
                settings.remove_override(key)
            else:
                settings.set_override(key, new_raw)
        state["result"] = None  # 다음 조회부터 새 기준 적용
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.post("/settings/reset")
    def settings_reset():
        settings.clear_overrides()
        state["result"] = None
        return RedirectResponse("/settings?reset=1", status_code=303)

    # ─── 매매일지·킬스위치·검증 리포트 (설계서 제1부·제9부) ───

    @app.get("/journal", response_class=HTMLResponse)
    def journal_page(request: Request, saved: int = 0, done: int = 0, deleted: int = 0, err: str = ""):
        from datetime import date as _date

        from jongga.journal import killswitch as ks_mod
        from jongga.journal import report, store
        entries = store.list_entries()
        return templates.TemplateResponse(request, "journal.html", {
            "open_entries": [e for e in entries if e["status"] == "open"],
            "closed_entries": [e for e in entries if e["status"] == "closed"],
            "ks": ks_mod.evaluate(entries, settings.cfg),
            "rep": report.compute(entries, settings.cfg),
            "candidates": store.recent_screening_candidates(),
            "one_r": store.current_one_r(),
            "today": _date.today().isoformat(),
            "saved": saved, "done": done, "deleted": deleted, "err": err,
        })

    @app.post("/journal/add")
    async def journal_add(request: Request):
        from jongga.journal import store
        form = await request.form()
        try:
            store.add_entry(
                trade_date=str(form.get("trade_date") or "").strip(),
                code=str(form.get("code") or "").strip(),
                name=str(form.get("name") or "").strip(),
                buy_price=float(form.get("buy_price")),
                quantity=int(form.get("quantity")),
                score_pct=float(form.get("score_pct")) if form.get("score_pct") else None,
                material_grade=str(form.get("material_grade") or "").strip(),
                after_hours=str(form.get("after_hours") or "").strip(),
            )
        except (TypeError, ValueError):
            return RedirectResponse("/journal?err=add", status_code=303)
        return RedirectResponse("/journal?saved=1", status_code=303)

    @app.post("/journal/{entry_id}/close")
    async def journal_close(entry_id: int, request: Request):
        from jongga.journal import store
        form = await request.form()
        try:
            store.close_entry(
                entry_id,
                exit_date=str(form.get("exit_date") or "").strip(),
                exit_price=float(form.get("exit_price")),
                rule_violation=bool(form.get("rule_violation")),
                violation_note=str(form.get("violation_note") or "").strip(),
                lesson=str(form.get("lesson") or "").strip(),
            )
        except (TypeError, ValueError):
            return RedirectResponse("/journal?err=close", status_code=303)
        return RedirectResponse("/journal?done=1", status_code=303)

    @app.post("/journal/{entry_id}/delete")
    def journal_delete(entry_id: int):
        from jongga.journal import store
        store.delete_entry(entry_id)
        return RedirectResponse("/journal?deleted=1", status_code=303)

    return app
