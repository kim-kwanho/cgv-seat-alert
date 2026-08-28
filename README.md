# CGV Seat Alert

CGV 잔여석을 주기적으로 조회하고, **잔여석이 늘어나면**(취소표) ntfy / Telegram으로 푸시합니다.  
예매는 하지 않습니다. **감시할 상영(이벤트)은 사용자가 `config.json`(또는 환경변수)으로 직접 설정**합니다.

## 빠른 시작

```powershell
git clone https://github.com/kim-kwanho/cgv-seat-alert.git
cd cgv-seat-alert
copy config.example.json config.json
```

1. `config.json`에서 **극장·날짜**만 먼저 채웁니다 (`theater_code`, `theater_keyword`, `play_date`).
2. 상영 목록을 보고 회차를 고릅니다.

```powershell
python -u monitor.py --list
```

3. 출력된 `movie_code` / `movie_name` / `start_time` 을 `config.json`에 넣고, `ntfy_topic` 을 **본인만 아는 긴 토픽명**으로 바꿉니다.
4. 실행:

```powershell
python -u monitor.py --dry-run --once   # 조회만
python -u monitor.py --test-push        # 푸시 테스트
python -u monitor.py --status-push      # 감시 시작 + 현재 잔여 푸시
```

## 요구 사항

- Python **3.10+** (추가 pip 패키지 없음)
- Node.js **18+** (`npx daiso`로 시간표 조회)

## 이벤트(상영) 설정

| 필드 | 설명 | 예시 |
|------|------|------|
| `theater_code` | CGV 극장 코드 | `0199` |
| `theater_keyword` | 조회용 검색어 | `천호` |
| `theater_name` | 알림에 표시할 이름 | `CGV 천호` |
| `play_date` | 상영일 `YYYYMMDD` | `20261231` |
| `start_time` | 시작 시각 `HH:MM` | `19:30` |
| `movie_code` | 영화 코드 (`--list`로 확인) | `30001323` |
| `movie_name` | 이름 부분 일치도 가능 (코드 비우면 사용) | `영화제목` |

`movie_code` 또는 `movie_name` 중 **하나 이상** 필요합니다.  
같은 시각에 여러 관이 있으면 잔여가 가장 적은 회차를 고릅니다.

### 환경변수로 덮어쓰기

로컬 `config.json` 대신(또는 위에) 환경변수로도 설정할 수 있습니다. GitHub Actions에서는 **Variables / Secrets**에 넣는 방식을 권장합니다.

| 환경변수 | config 키 |
|----------|-----------|
| `THEATER_CODE` | `theater_code` |
| `THEATER_KEYWORD` | `theater_keyword` |
| `THEATER_NAME` | `theater_name` |
| `MOVIE_CODE` | `movie_code` |
| `MOVIE_NAME` | `movie_name` |
| `PLAY_DATE` | `play_date` |
| `START_TIME` | `start_time` |
| `NTFY_TOPIC` | `ntfy_topic` |
| `NTFY_SERVER` | `ntfy_server` |
| `TELEGRAM_BOT_TOKEN` | `telegram_bot_token` |
| `TELEGRAM_CHAT_ID` | `telegram_chat_id` |
| `POLL_INTERVAL_SEC` | `poll_interval_sec` |
| `ALERT_ON_INCREASE_ONLY` | `true` / `false` |
| `ALERT_SOURCE` | 알림 제목 접두사 (예: `Actions`) |

## 알림

### ntfy

1. 폰에 [ntfy](https://ntfy.sh) 설치
2. **추측하기 어려운 토픽명**으로 구독
3. 같은 값을 `ntfy_topic` 또는 Secret `NTFY_TOPIC`에 설정

### Telegram (선택)

`telegram_bot_token` + `telegram_chat_id` (또는 대응 Secrets)를 채우면 함께 전송합니다.

## 로컬 / Actions

| 경로 | 간격 | 용도 |
|------|------|------|
| 로컬 `monitor.py` | `poll_interval_sec` (기본 45초) | 집중 감시 |
| GitHub Actions | 5분 | PC 꺼둔 동안 백업 |

### GitHub Actions 설정

1. **Secrets:** `NTFY_TOPIC` (필수), `NTFY_SERVER` / Telegram (선택)
2. **Variables:** `THEATER_CODE`, `THEATER_KEYWORD`, `THEATER_NAME`, `MOVIE_CODE`, `MOVIE_NAME`, `PLAY_DATE`, `START_TIME`
3. Actions → `CGV seat alert` → Enable → **Run workflow**로 테스트

스케줄은 UTC `*/5`입니다. 무료 플랜에서는 지연될 수 있습니다.

## CLI

| 옵션 | 설명 |
|------|------|
| `--list` | 극장·날짜 상영 목록 (설정 도우미) |
| `--once` | 한 번만 조회 |
| `--dry-run` | 조회·로그만, 푸시 안 함 |
| `--test-push` | 테스트 푸시 |
| `--status-push` | 시작 시 현재 잔여 푸시 |
| `--any-seat` | 잔여 > 0 이면 알림 (기본은 **증가만**) |
| `--interval N` | 폴링 초 덮어쓰기 |

연속 조회 실패가 `fail_alert_threshold`(기본 3)회에 도달하면 실패 알림을 보냅니다.

## 주의

- 조회는 `npx daiso` 중계 API를 사용합니다. CGV·중계 측 정책 변경 시 동작이 깨질 수 있습니다.
- 좌석 맵(좋은 자리)은 판별하지 않습니다. 알림 후 CGV에서 직접 선택하세요.
- 로컬과 Actions를 동시에 돌리면 같은 증가에 알림이 두 번 올 수 있습니다 (`[Actions]` 접두사로 구분).
- `config.json`, `state.json` 은 gitignore 대상입니다. 템플릿만 `config.example.json`에 둡니다.
- 과도한 폴링은 자제하세요. 개인·비상업 용도를 전제로 합니다.

## 공개 전 체크리스트

레포를 Public으로 바꾸기 전에:

- [ ] `config.json` / `state.json` 이 커밋·푸시되지 않았는지 확인
- [ ] `ntfy_topic` 이 예시/추측 가능한 이름이 아닌지 확인 (과거 토픽을 썼다면 **새 토픽으로 교체**)
- [ ] Telegram 토큰·채팅 ID는 Secrets만 사용
- [ ] Actions Variables에 넣을 상영 정보가 “공개돼도 괜찮은지” 판단 (영화·극장·일시)
- [ ] 워크플로를 당장 쓰지 않으면 Actions에서 Disable

## License

MIT
