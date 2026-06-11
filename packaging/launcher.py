"""PyInstaller exe 진입점 — 더블클릭하면 웹 서버를 켜고 브라우저를 연다

동작 규칙:
  - exe 옆에 .env가 없으면 템플릿을 만들어 주고 '데모 모드'로 시작 (첫 경험이 항상 성공하도록)
  - .env에 KIS 키가 채워져 있으면 자동으로 '실전 모드'
  - 번들된 config/(필터 기본값·캘린더·키워드 사전)는 최초 1회 exe 옆으로 복사 → 사용자가 직접 수정 가능
"""
import shutil
import sys
import threading
import webbrowser
from pathlib import Path

PORT = 8765

ENV_TEMPLATE = """# 이 파일에 본인의 API 키를 넣고 저장하면, 다음 실행부터 '실전 모드'로 켜져요.
# (비워두면 가상 데이터 데모 모드로 실행됩니다)

# 한국투자증권 Open API (실전투자용)
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_BASE_URL=https://openapi.koreainvestment.com:9443

# 재료(뉴스·공시) 분석용 — 없어도 작동해요 (해당 점수만 '확인 불가' 처리)
DART_API_KEY=
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
"""


def prepare_portable_files() -> Path:
    """exe 옆에 config/와 .env를 준비 (jongga 모듈 import 전에 호출해야 한다)"""
    if not getattr(sys, "frozen", False):
        return Path(".").resolve()
    exe_dir = Path(sys.executable).resolve().parent
    bundle = Path(getattr(sys, "_MEIPASS", exe_dir))
    config_dst = exe_dir / "config"
    if not config_dst.exists() and (bundle / "config").exists():
        shutil.copytree(bundle / "config", config_dst)
    env_path = exe_dir / ".env"
    if not env_path.exists():
        env_path.write_text(ENV_TEMPLATE, encoding="utf-8")
    return exe_dir


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    exe_dir = prepare_portable_files()

    from jongga.settings import env  # prepare 이후에 import (.env를 읽어야 하므로)

    has_keys = bool(env("KIS_APP_KEY") and env("KIS_APP_SECRET"))
    demo = ("--demo" in sys.argv) or not has_keys

    line = "─" * 52
    print(line)
    print("  종가매매 추천 프로그램")
    if demo and not has_keys:
        print("  모드: 데모 (가상 데이터)")
        print(f"  → 실전으로 바꾸려면 {exe_dir / '.env'} 파일에")
        print("    한국투자증권 앱키·시크릿을 넣고 다시 실행하세요.")
    elif demo:
        print("  모드: 데모 (가상 데이터, --demo 옵션)")
    else:
        print("  모드: 실전 (한국투자증권 API)")
    print(f"  화면 주소: http://127.0.0.1:{PORT}  (자동으로 열려요)")
    print("  끄기: 이 창에서 Ctrl+C 또는 창 닫기")
    print(line, flush=True)

    from jongga.web.app import create_app
    import uvicorn

    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    try:
        uvicorn.run(create_app(demo=demo), host="127.0.0.1", port=PORT, log_level="warning")
    except SystemExit:
        raise
    except OSError as exc:
        print(f"\n서버를 켜지 못했어요: {exc}")
        print("이미 프로그램이 켜져 있는지 확인해주세요 (같은 주소는 한 번만 켤 수 있어요).")
        input("닫으려면 Enter...")


if __name__ == "__main__":
    main()
