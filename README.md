# CGV 취소표 감지 푸시

CGV 천호 **오디세이** `2026-08-11 19:30` 잔여석을 조회하고, **잔여석이 늘어나면**(취소표) 푸시합니다. 예매는 하지 않습니다.

## 역할 분담

| 경로 | 간격 | 용도 |
|------|------|------|
| **로컬** `monitor.py` | 45초 | 집중해서 잡을 때 (본진) |
| **GitHub Actions** | 5분 | PC 꺼둔 동안 백업 감시 |

## 타겟

| 항목 | 값 |
|------|-----|
| 영화 | 오디세이 (`30001323`) |
| 극장 | CGV 천호 (`0199`) |
| 일시 | 2026-08-11 19:30 |
| 알림 | 잔여석 **증가** |

## ntfy

1. 폰에 [ntfy](https://ntfy.sh) 설치
2. 토픽 구독: `cgv-cheonho-odyssey-1930` (바꾸면 config/시크릿도 맞출 것)

## 로컬 실행

```powershell
cd "C:\Users\Kwanho Kim\Projects\cgv-seat-alert"
python -u monitor.py --status-push
```

## GitHub Actions (무료, 5분)

1. 이 폴더를 **private** 레포로 푸시
2. Repo → Settings → Secrets → Actions 에 추가:
   - `NTFY_TOPIC` = ntfy 토픽명 (필수 권장)
   - `NTFY_SERVER` = `https://ntfy.sh` (생략 가능, config 기본값 사용)
3. Actions 탭에서 `CGV seat alert` 워크플로 확인
4. **Run workflow**로 1회 테스트

스케줄은 UTC `*/5`. 무료 플랜에선 수 분 지연될 수 있습니다.
예매가 끝나면 Actions에서 워크플로를 Disable 하세요.

## 알림 모드

- 기본: 잔여석 **증가**만
- `--any-seat`: 잔여 > 0 이면 알림

## 주의

- 조회는 `npx daiso` 중계 API 사용
- 좌석 맵(좋은 자리)은 판별하지 않음 → 알림 후 CGV에서 직접 선택
- 로컬+Actions 동시 가동 시 같은 증가에 알림이 두 번 올 수 있음 (`[Actions]` 접두사로 구분)
