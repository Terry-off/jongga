@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title 종가매매 추천 - 데모

echo ============================================
echo    종가매매 추천 - 데모 (가상 데이터)
echo    API 키나 인터넷 없이 화면만 구경해요.
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [멈춤] 파이썬이 없어요. https://www.python.org/downloads/ 에서 설치하세요.
  echo        설치 화면에서 "Add python.exe to PATH" 를 꼭 체크하세요!
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [준비] 처음이라 환경을 준비할게요. 1~2분 걸려요...
  python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip >nul 2>nul
  .venv\Scripts\python -m pip install -r requirements.txt
  echo.
)

echo [실행] 브라우저를 열어요: http://127.0.0.1:8765
echo  * 끄려면 이 창에서 Ctrl+C 를 누르세요.
echo.
start "" http://127.0.0.1:8765
.venv\Scripts\python -m jongga web --demo
pause
