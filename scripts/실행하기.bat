@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title 종가매매 추천 프로그램

echo ============================================
echo    종가매매 추천 프로그램
echo ============================================
echo.

REM 1) 파이썬 확인
where python >nul 2>nul
if errorlevel 1 (
  echo [멈춤] 파이썬이 설치되어 있지 않아요.
  echo        https://www.python.org/downloads/ 에서 설치하세요.
  echo        설치 화면에서 "Add python.exe to PATH" 를 꼭 체크하세요!
  echo.
  pause
  exit /b 1
)

REM 2) 최초 1회: 가상환경 + 라이브러리 설치
if not exist ".venv\Scripts\python.exe" (
  echo [준비] 처음 실행이라 환경을 준비할게요. 1~2분 걸려요...
  python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip >nul 2>nul
  .venv\Scripts\python -m pip install -r requirements.txt
  echo.
)

REM 3) API 키 파일 확인
if not exist ".env" (
  copy .env.example .env >nul
  echo [중요] API 키를 넣어야 해요.
  echo        잠시 후 메모장이 열리면 KIS 앱키/시크릿을 붙여넣고 저장한 뒤 닫으세요.
  echo.
  pause
  notepad .env
)

echo [실행] 브라우저를 열어요. 안 열리면 주소창에 직접 입력하세요:
echo        http://127.0.0.1:8765
echo.
echo  * 끄려면 이 검은 창에서 Ctrl+C 를 누르거나 창을 닫으세요.
echo.
start "" http://127.0.0.1:8765
.venv\Scripts\python -m jongga web
pause
