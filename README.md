# 종가매매 종목 추천 프로그램 (jongga)

장 마감 무렵, 오늘 시장이 돈(거래대금)·명분(재료)·구조(섹터·캔들)로 인정한 종목만 골라서
**"왜 추천하는지"를 쉬운 말로 설명**해 주는 개인용 스크리닝 도구입니다.

> ⚠️ 이 프로그램은 **추천만** 합니다. 매매를 실행하지 않으며, 모든 투자 판단과 책임은 사용자 본인에게 있습니다.

전체 설계는 [DESIGN.md](DESIGN.md) 참고. 판단 규칙의 원전은 『실패하지 않는 종가매매 시스템 설계서 v2』입니다.

> 🚀 **가장 쉬운 실행법**: [실행방법.md](실행방법.md)
> ① **exe 한 개** — 저장소 **Actions 탭 → "윈도우 exe 빌드" → Artifacts**에서 다운로드, 더블클릭 (파이썬 불필요)
> ② 파이썬이 있으면 `scripts\데모보기.bat` / `scripts\실행하기.bat` 더블클릭

---

## 빠른 시작 (윈도우 기준)

### 1. 파이썬 설치 확인
PowerShell을 열고:
```powershell
python --version
```
3.11 이상이 아니면 https://www.python.org/downloads/ 에서 설치 (설치 시 "Add python.exe to PATH" 체크).

### 2. 프로그램 받기 & 가상환경 만들기
```powershell
git clone <이 저장소 주소>
cd jongga
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 한국투자증권 API 키 넣기
`.env.example` 파일을 복사해서 `.env` 파일을 만들고, 본인의 **실전투자용** 앱키·시크릿을 붙여넣습니다:
```
KIS_APP_KEY=발급받은 앱키
KIS_APP_SECRET=발급받은 시크릿
```
> `.env` 파일은 절대 다른 사람에게 공유하거나 인터넷에 올리지 마세요. (git에는 자동으로 제외됩니다)

### 4. 연결 테스트 (스모크 테스트)
```powershell
python -m jongga smoke
```
토큰 발급 → 삼성전자 현재가 조회까지 성공하면 연결 완료입니다.

### 5. 오늘의 유니버스 보기
```powershell
python -m jongga universe
```
오늘 돈이 몰린 종목(거래대금 상위 + 상승률 상위)을 표로 보여줍니다. `--save`를 붙이면 DB에 저장됩니다.

> 한글이 깨져 보이면: Windows Terminal 사용을 권장하며, 구형 콘솔에서는 `chcp 65001` 실행 후 다시 시도하세요.

---

### 5. 웹 화면 열기 (API 키·인터넷 없이도 미리보기 가능)
```powershell
python -m jongga web --demo
```
브라우저에서 `http://127.0.0.1:8765` 를 열면 시장 신호등 → 추천 카드(점수·이유·차트) → 탈락 사유까지
전체 화면을 가상 데이터로 볼 수 있습니다. 실전은 `--demo`를 빼고 장 마감 무렵(14:30~15:30)에 실행하세요.
⚙️ 설정 화면에서 모든 필터 기준을 바꿀 수 있고, "기본값 복원" 한 번이면 설계서 수치로 돌아옵니다.

터미널 버전도 있습니다: `python -m jongga recommend --demo`

## 명령어

| 명령 | 설명 |
|---|---|
| `python -m jongga web [--demo] [--port 8765]` | **웹 대시보드** — 추천 카드·차트·필터 설정 화면 |
| `python -m jongga recommend [--demo] [--save] [--top 40]` | 터미널 버전 추천 — 신호등·점수·이유·비중까지 |
| `python -m jongga collect [--no-themes]` | **일일 스냅샷 수집** — 매일 18:10 자동 실행 권장 ([설정법](scripts/windows_scheduler.md)) |
| `python -m jongga dates` | 저장된(과거 조회 가능한) 거래일 목록 |
| `python -m jongga recommend --date 2026-06-10` | 저장된 과거 날짜를 그대로 재현 조회 |
| `python -m jongga collect-themes` | 네이버 테마-종목 매핑만 따로 수집 |
| `python -m jongga material 005930 삼성전자` | 종목 재료(뉴스·공시) 등급 즉석 확인 |
| `python -m jongga journal` | 매매일지 요약 — 킬스위치 상태·검증 리포트 (기록은 웹 📒 일지에서) |
| `python -m jongga smoke` | KIS API 연결 테스트 (토큰 + 삼성전자 현재가) |
| `python -m jongga universe [--save] [--top 30]` | 오늘 돈이 몰린 종목 목록 |
| `python -m jongga init-db` | DB 파일 생성 (--save 시 자동 실행됨) |

테스트 실행: `python -m unittest discover tests`

## 프로젝트 구조

```
jongga/
├── DESIGN.md            # 설계서 (규칙·기준값·화면 설계의 원천)
├── config/defaults.yaml # 모든 필터 기본값 — 여기 수치가 판단 기준
├── config/calendar.yaml # FOMC·휴장일 내장 캘린더 (직접 수정 가능)
├── jongga/
│   ├── engine/          # 판단 엔진: 베토 9개·100점 채점·신호등·비중 계산
│   ├── material/        # 재료 엔진: DART 공시 + 네이버 뉴스 → A/B/C 등급
│   ├── kis/             # 한국투자증권 API (토큰·호출제한·시세·분봉·수급)
│   ├── web/             # 웹 대시보드 (FastAPI + 템플릿 + 설정 화면)
│   ├── providers.py     # 데이터 공급자 (실시간 API / 시연 데이터)
│   ├── demo.py          # 시연용 '가상의 하루'
│   ├── universe.py      # 후보 종목 수집
│   ├── db.py            # SQLite 스키마·결과 저장
│   └── cli.py           # 터미널 명령
├── tests/               # 엔진 테스트 (네트워크 불필요)
└── data/                # 토큰 캐시·DB (git 제외)
```

## 로드맵

- [x] **M1** KIS 연동 기반 + 유니버스 수집 CLI
- [x] **M2** 베토 9개 + 채점 엔진 + 시장 신호등 + 추천 CLI
- [x] **M3** 재료 엔진 (DART 공시 + 네이버 뉴스 자동 등급)
- [x] **M3.5** 테마 동조·대장주 판별 (네이버 테마 수집)
- [x] **M4** 웹 대시보드 (카드 UI·차트·필터 설정 화면)
- [x] **M5** 일일 자동 스냅샷 수집기 + 과거 날짜 재현 조회
- [x] **M6** 매매일지 + 킬스위치 + 검증 리포트 ← 현재 (전 마일스톤 완료)

**다음 단계는 실데이터 검증입니다** — 본인 PC에서 실전 키로 돌리면서 점수 분포·키워드 오판을 보정하는 단계예요.
설계서 제9부의 순서 그대로: ① 20거래일 관찰(매일 `collect` + 결과 확인) → ② 소액 검증 30~50회(일지 기록) → ③ 통과 기준 충족 시 표준 운용.
