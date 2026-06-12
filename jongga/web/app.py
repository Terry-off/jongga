"""웹 대시보드 — 추천 화면·설정 화면 (DESIGN.md 6장)

실행: python -m jongga web [--demo] [--port 8765]
스캔은 자동으로 돌지 않는다 — 사용자가 날짜를 고르고 ▶ 실행(POST /run)을
눌러야 시작한다. 결과는 메모리에 캐시되고 '다시 스캔' 버튼으로 갱신하며,
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

    import threading

    state = {"result": None, "ran_at": None, "error": None, "error_date": None,
             "demo": demo, "viewing": None,
             "scanning": False, "progress": "", "scan_target": None, "recon": False,
             "theme_collecting": False, "theme_progress": "", "theme_msg": ""}
    scan_lock = threading.Lock()

    def run_demo():
        from jongga.demo import DEMO_DATE
        from jongga.providers import DemoProvider
        state["result"] = pipeline.run(DemoProvider(), trade_date=DEMO_DATE)
        state["viewing"] = None
        state["ran_at"] = datetime.now().strftime("%H:%M")
        state["error"] = None

    def load_past(date_arg: str):
        from jongga.providers import DBProvider
        provider = DBProvider(date_arg)
        if not provider.has_data():
            raise RuntimeError(
                f"{date_arg}에 저장된 데이터가 없어요. 그날 수집(collect)이 돌지 않았다면 "
                "분봉·시간외는 복구할 수 없어요. 저장된 날짜만 조회할 수 있어요.")
        state["result"] = pipeline.run(provider, trade_date=date_arg)
        state["viewing"] = date_arg
        state["ran_at"] = datetime.now().strftime("%H:%M")
        state["error"] = None

    def _scan_worker(date_arg: str | None):
        # 실전/재구성 스캔은 종목당 호출이 많아 몇 분 걸린다 → 백그라운드에서 돌리고
        # 화면은 진행상황을 보여주며 자동 새로고침한다
        def on_progress(done, total, label):
            state["progress"] = f"{done}/{total} · {label}" if total else label
        try:
            if date_arg:
                from jongga.providers import HistoricalProvider
                result = pipeline.run(HistoricalProvider(date_arg), trade_date=date_arg,
                                      progress=on_progress)
                state["viewing"] = date_arg
                state["recon"] = True
            else:
                from jongga.providers import LiveProvider
                result = pipeline.run(LiveProvider(), progress=on_progress)
                state["viewing"] = None
                state["recon"] = False
            state["result"] = result
            state["ran_at"] = datetime.now().strftime("%H:%M")
            state["error"] = None
        except Exception as exc:
            state["error"] = str(exc)
            state["error_date"] = date_arg or "__live__"   # 실패한 날짜 — 자동 재시도 방지
            state["result"] = None
        finally:
            state["scanning"] = False
            state["scan_target"] = None

    def start_scan(date_arg: str | None = None):
        with scan_lock:
            if state["scanning"]:
                return
            state["scanning"] = True
            state["scan_target"] = date_arg
            state["progress"] = "준비 중..."
            state["error"] = None
            threading.Thread(target=_scan_worker, args=(date_arg,), daemon=True).start()

    def _theme_collect_worker():
        from datetime import date as _date
        from jongga.db import save_theme_map
        from jongga.theme import scraper
        def on_progress(i, total, name):
            state["theme_progress"] = f"{i}/{total} · {name}"
        try:
            theme_map = scraper.collect(progress=on_progress)
            if theme_map:
                save_theme_map(_date.today().isoformat(), theme_map)
                state["theme_msg"] = f"✓ 테마 {len(theme_map)}개 수집 완료 — 🔄 다시 스캔하면 '테마 동조' 점수가 반영돼요"
            else:
                state["theme_msg"] = "테마 수집에 실패했어요 — 인터넷 연결을 확인하고 다시 시도해주세요"
        except Exception as exc:
            state["theme_msg"] = f"테마 수집 실패: {exc}"
        finally:
            state["theme_collecting"] = False

    def _theme_banner() -> str:
        from datetime import date as _date
        from jongga.db import latest_theme_date
        latest = latest_theme_date()
        if latest is None:
            return "테마 데이터가 아직 없어요 — '테마 동조' 15점이 확인 불가로 빠져 있어요"
        if latest < _date.today().isoformat():
            return f"테마 데이터가 {latest} 기준이에요 — 새로 수집하면 더 정확해져요"
        return ""

    def _is_market_holiday(date_iso: str) -> bool:
        from datetime import date as _date
        from jongga.calendar_events import is_holiday
        try:
            return is_holiday(_date.fromisoformat(date_iso))
        except ValueError:
            return False

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
    def home(request: Request):
        # 화면은 현재 상태를 보여주기만 한다 — 스캔은 사용자가 ▶ 실행을 눌러야 시작 (POST /run)
        from datetime import date as _date
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
            "scanning": state["scanning"],
            "progress": state["progress"],
            "scan_target": state["scan_target"],
            "recon": state["recon"],
            "today": _date.today().isoformat(),
            "theme_banner": "" if state["demo"] else _theme_banner(),
            "theme_collecting": state["theme_collecting"],
            "theme_progress": state["theme_progress"],
            "theme_msg": state["theme_msg"],
            "past_dates": [] if state["demo"] else collected_dates()[:60],
            "signal": SIGNAL_STYLE.get(result.signal.color) if result else None,
            "cards": _cards(result) if result else [],
            "watch": [c for c in result.candidates if c.verdict == "watch"] if result else [],
        })

    @app.post("/run")
    async def run(request: Request):
        """달력에서 고른 날짜로 스캔 시작 — 사용자가 ▶ 실행을 눌렀을 때만 동작"""
        from datetime import date as _date
        if state["demo"]:
            try:
                run_demo()
            except Exception as exc:
                state["error"], state["result"] = str(exc), None
            return RedirectResponse("/", status_code=303)
        if state["scanning"]:
            return RedirectResponse("/", status_code=303)  # 진행 중엔 새 요청 무시
        form = await request.form()
        today = _date.today().isoformat()
        date_arg = str(form.get("date") or "").strip() or today
        state["error"], state["error_date"], state["theme_msg"] = None, None, ""
        if date_arg > today:
            state["result"], state["viewing"] = None, None
            state["error"] = f"{date_arg}는 아직 오지 않은 날짜예요. 오늘이나 과거 거래일을 선택해주세요."
            state["error_date"] = date_arg
        elif _is_market_holiday(date_arg):
            # 휴장일은 KRX·KIS 호출 없이 즉시 안내
            state["result"], state["viewing"] = None, None
            state["error"] = f"{date_arg}은 증시 휴장일이에요 (주말·공휴일·임시휴장일). 거래가 있었던 평일을 선택해주세요."
            state["error_date"] = date_arg
        elif date_arg == today:
            state["result"], state["viewing"] = None, None
            start_scan()                       # 오늘 = 실시간 스캔 (백그라운드)
        else:
            from jongga.providers import DBProvider
            provider = DBProvider(date_arg)
            if provider.has_data():            # 저장본이 있으면 즉시 재현
                try:
                    load_past(date_arg)
                    state["recon"] = False
                except Exception as exc:
                    state["error"], state["error_date"], state["result"] = str(exc), date_arg, None
            else:                              # 없으면 KRX·KIS로 재구성 (백그라운드)
                state["result"], state["viewing"] = None, None
                start_scan(date_arg)
        return RedirectResponse("/", status_code=303)

    @app.post("/scan")
    def scan():
        if state["demo"]:
            try:
                run_demo()
            except Exception as exc:
                state["error"] = str(exc)
                state["result"] = None
        else:
            from datetime import date as _date
            # 보고 있던 날짜, 또는 방금 실패한 날짜를 다시 계산 (없으면 오늘)
            target = state["viewing"]
            if not target and state["error_date"] and state["error_date"] != "__live__":
                target = state["error_date"]
            state["result"], state["viewing"] = None, None
            state["error"], state["error_date"] = None, None
            state["theme_msg"] = ""
            if target and (target > _date.today().isoformat() or _is_market_holiday(target)):
                # 휴장일·미래 날짜는 다시 시도해도 같다 → 대기 화면에서 새 날짜 선택 유도
                return RedirectResponse("/", status_code=303)
            start_scan(target)
        return RedirectResponse("/", status_code=303)

    @app.post("/themes/collect")
    def themes_collect():
        if not state["theme_collecting"]:
            state["theme_collecting"] = True
            state["theme_progress"] = "테마 목록 받는 중..."
            state["theme_msg"] = ""
            import threading as _t
            _t.Thread(target=_theme_collect_worker, daemon=True).start()
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
