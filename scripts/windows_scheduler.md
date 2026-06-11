# 윈도우 자동 수집 설정 (매일 18:10)

종가매매의 분봉·시간외·경보 데이터는 **그날 지나가면 다시 못 받아요.** 그래서 매 거래일 장 마감 뒤
한 번 자동으로 수집해 두면, 나중에 어떤 과거 날짜든 그대로 다시 볼 수 있어요.

## 1. 수집 명령 확인
먼저 가상환경에서 한 번 직접 돌려보세요 (장 마감 후 시간대 권장):
```powershell
cd C:\경로\jongga
.venv\Scripts\activate
python -m jongga collect
```
`✓ ... 수집 완료` 가 나오면 성공이에요.

## 2. 자동 실행 등록 (작업 스케줄러)

### 방법 A — 명령 한 줄 (관리자 PowerShell)
아래에서 `C:\경로\jongga` 부분만 본인 폴더로 바꾸세요:
```powershell
$proj = "C:\경로\jongga"
$action = New-ScheduledTaskAction -Execute "$proj\.venv\Scripts\python.exe" `
    -Argument "-m jongga collect" -WorkingDirectory $proj
$trigger = New-ScheduledTaskTrigger -Daily -At 18:10
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun
Register-ScheduledTask -TaskName "종가매매 일일수집" -Action $action `
    -Trigger $trigger -Settings $settings -Description "매일 18:10 종가매매 데이터 수집"
```
- `-StartWhenAvailable`: 그 시간에 PC가 꺼져 있었으면, 켜진 직후에 한 번 실행해요.
- `-WakeToRun`: 절전 상태면 깨워서 실행해요 (노트북은 전원 연결 시에만 동작).

### 방법 B — 화면으로 등록
1. 시작 메뉴 → "작업 스케줄러" 실행
2. 오른쪽 "기본 작업 만들기" → 이름 `종가매매 일일수집`
3. 트리거: **매일**, 시작 시간 **18:10**
4. 동작: **프로그램 시작**
   - 프로그램: `C:\경로\jongga\.venv\Scripts\python.exe`
   - 인수: `-m jongga collect`
   - 시작 위치: `C:\경로\jongga`
5. 마침 → 속성에서 "사용할 수 있는 경우 가능한 한 빨리 시작" 체크

## 3. 확인
다음 날 이렇게 저장된 날짜가 늘어나는지 보세요:
```powershell
python -m jongga dates
```

## 참고
- 주말·공휴일에 실행돼도 해롭지 않아요(빈 데이터를 저장할 뿐).
- 수집이 빠진 날의 과거 조회는 "데이터 없음"으로 나와요 — 분봉·시간외는 사후 복구가 안 되기 때문이에요.
- 테마까지 매일 수집하면 1~3분 걸려요. 빠르게 하려면 `-m jongga collect --no-themes` 로 등록하고,
  테마는 따로 `collect-themes`를 가끔 돌리는 방법도 있어요.
