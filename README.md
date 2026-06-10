# 종가매매 종목 추천 프로그램 (jongga)

장 마감 무렵, 오늘 시장이 돈(거래대금)·명분(재료)·구조(섹터·캔들)로 인정한 종목만 골라서
**"왜 추천하는지"를 쉬운 말로 설명**해 주는 개인용 스크리닝 도구입니다.

> ⚠️ 이 프로그램은 **추천만** 합니다. 매매를 실행하지 않으며, 모든 투자 판단과 책임은 사용자 본인에게 있습니다.

전체 설계는 [DESIGN.md](DESIGN.md) 참고. 판단 규칙의 원전은 『실패하지 않는 종가매매 시스템 설계서 v2』입니다.

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

## 명령어

| 명령 | 설명 |
|---|---|
| `python -m jongga smoke` | KIS API 연결 테스트 (토큰 + 삼성전자 현재가) |
| `python -m jongga universe [--save] [--top 30]` | 오늘 돈이 몰린 종목 목록 |
| `python -m jongga init-db` | DB 파일 생성 (universe --save 시 자동 실행됨) |

## 프로젝트 구조

```
jongga/
├── DESIGN.md            # 설계서 (규칙·기준값·화면 설계의 원천)
├── config/defaults.yaml # 모든 필터 기본값 — 여기 수치가 판단 기준
├── jongga/
│   ├── settings.py      # 설정·환경변수 로딩
│   ├── db.py            # SQLite 스키마
│   ├── kis/             # 한국투자증권 API (토큰·호출제한·시세)
│   ├── universe.py      # 후보 종목 수집
│   └── cli.py           # 터미널 명령
└── data/                # 토큰 캐시·DB (git 제외)
```

## 로드맵

- [x] **M1** KIS 연동 기반 + 유니버스 수집 CLI ← 현재
- [ ] **M2** 베토 9개 + 채점 엔진 + 시장 신호등
- [ ] **M3** 재료 엔진 (DART 공시 + 네이버 뉴스 자동 등급)
- [ ] **M4** 웹 대시보드 (토스 스타일 카드 UI)
- [ ] **M5** 일일 자동 스냅샷 수집기 + 과거 조회
- [ ] **M6** 매매일지 + 킬스위치 + 검증 리포트
