#!/usr/bin/env python3
"""CGV 잔여석(취소표) 감지 → 푸시 알림. 예매는 하지 않음."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.json"
STATE_FILE = ROOT / "state.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def http_post(url: str, data: bytes, headers: dict[str, str], timeout: float = 20.0) -> None:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()


def now_kst() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fetch_timetable_via_daiso(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """daiso CLI로 CGV 시간표/잔여석 조회 (직접 HTTP는 403되는 경우가 많음)."""
    keyword = cfg.get("theater_keyword") or "천호"
    npx = "npx.cmd" if sys.platform == "win32" else "npx"
    cmd = [
        npx,
        "--yes",
        "daiso",
        "get",
        "/api/cgv/timetable",
        "--keyword",
        keyword,
        "--theaterId",
        str(cfg["theater_code"]),
        "--playDate",
        str(cfg["play_date"]),
        "--json",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        shell=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"daiso 실패 (code={proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )

    raw = proc.stdout.strip()
    # stdout에 npm 로그가 섞일 수 있어 JSON 객체만 추출
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0:
        raise RuntimeError(f"daiso JSON 파싱 실패: {raw[:300]}")
    payload = json.loads(raw[start : end + 1])
    if not payload.get("success"):
        raise RuntimeError(f"API 실패: {payload}")
    return list(payload.get("data", {}).get("timetable") or [])


def fetch_target(cfg: dict[str, Any]) -> dict[str, Any] | None:
    """특정 상영의 잔여석을 timetable에서 찾는다."""
    rows = fetch_timetable_via_daiso(cfg)
    start = cfg["start_time"]
    movie = cfg["movie_code"]
    theater = cfg["theater_code"]
    movie_name = cfg.get("movie_name", "")

    matches = [
        r
        for r in rows
        if r.get("theaterCode") == theater
        and r.get("startTime") == start
        and (
            r.get("movieCode") == movie
            or (movie_name and movie_name in str(r.get("movieName") or ""))
        )
    ]
    if not matches:
        return None
    # 동일 시각이 여러 관이면 잔여가 가장 적은(매진에 가까운) 회차 우선
    return min(matches, key=lambda r: int(r.get("remainingSeats") or 0))


def send_ntfy_safe(cfg: dict[str, Any], title: str, body: str, priority: str = "high") -> None:
    topic = (cfg.get("ntfy_topic") or "").strip()
    if not topic:
        return
    server = cfg.get("ntfy_server", "https://ntfy.sh").rstrip("/")
    url = f"{server}/{urllib.parse.quote(topic)}"
    # ntfy Title 헤더는 ASCII 권장 → UTF-8 본문에 제목 포함
    message = f"{title}\n\n{body}"
    req = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        headers={
            "Priority": priority,
            "Tags": "movie_camera,ticket",
            "Content-Type": "text/plain; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def send_telegram(cfg: dict[str, Any], text: str) -> None:
    token = (cfg.get("telegram_bot_token") or "").strip()
    chat_id = (cfg.get("telegram_chat_id") or "").strip()
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode("utf-8")
    http_post(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def apply_env_overrides(cfg: dict[str, Any]) -> dict[str, Any]:
    """환경변수로 config 덮어쓰기 (GitHub Actions secrets용)."""
    mapping = {
        "NTFY_TOPIC": "ntfy_topic",
        "NTFY_SERVER": "ntfy_server",
        "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
        "TELEGRAM_CHAT_ID": "telegram_chat_id",
    }
    for env_key, cfg_key in mapping.items():
        val = (os.environ.get(env_key) or "").strip()
        if val:
            cfg[cfg_key] = val
    source = (os.environ.get("ALERT_SOURCE") or "").strip()
    if source:
        cfg["alert_source"] = source
    return cfg


def notify(cfg: dict[str, Any], title: str, body: str) -> None:
    source = (cfg.get("alert_source") or "").strip()
    if source:
        title = f"[{source}] {title}"
    if cfg.get("_dry_run"):
        print(f"[{now_kst()}] DRY-RUN (푸시 생략): {title} | {body}")
        return
    print(f"[{now_kst()}] PUSH: {title} | {body}")
    errors: list[str] = []
    try:
        send_ntfy_safe(cfg, title, body)
    except Exception as e:  # noqa: BLE001
        errors.append(f"ntfy: {e}")
    try:
        send_telegram(cfg, f"{title}\n{body}")
    except Exception as e:  # noqa: BLE001
        errors.append(f"telegram: {e}")
    if errors:
        print(f"[{now_kst()}] 푸시 일부 실패: {'; '.join(errors)}", file=sys.stderr)


def format_show(cfg: dict[str, Any], show: dict[str, Any]) -> str:
    rem = show.get("remainingSeats")
    total = show.get("totalSeats")
    return (
        f"{cfg['movie_name']} / {cfg['theater_name']}\n"
        f"{cfg['play_date'][:4]}-{cfg['play_date'][4:6]}-{cfg['play_date'][6:]} "
        f"{cfg['start_time']}\n"
        f"잔여 {rem}/{total}\n"
        f"예매: {cfg.get('booking_url', 'https://cgv.co.kr/cnm/movieBook')}"
    )


def should_alert(
    cfg: dict[str, Any],
    prev: int | None,
    curr: int,
    last_alert_ts: float,
) -> tuple[bool, str]:
    cooldown = float(cfg.get("cooldown_sec", 120))
    if time.time() - last_alert_ts < cooldown and prev is not None:
        return False, "cooldown"

    if cfg.get("alert_on_increase_only", True):
        if prev is None:
            return False, "baseline"
        if curr > prev:
            return True, f"취소표 감지 (+{curr - prev})"
        return False, "no_increase"

    if curr > 0 and (prev is None or prev == 0 or curr > prev):
        reason = "잔여석 있음" if prev in (None, 0) else f"증가 (+{curr - prev})"
        return True, reason
    return False, "skip"


def once(cfg: dict[str, Any], state: dict[str, Any], *, force_status: bool = False) -> dict[str, Any]:
    show = fetch_target(cfg)
    if show is None:
        msg = (
            f"상영 정보를 찾지 못함: {cfg['movie_name']} "
            f"{cfg['theater_name']} {cfg['play_date']} {cfg['start_time']}"
        )
        print(f"[{now_kst()}] {msg}")
        state["last_error"] = msg
        state["last_check"] = now_kst()
        return state

    curr = int(show.get("remainingSeats") or 0)
    total = int(show.get("totalSeats") or 0)
    prev = state.get("remaining_seats")
    prev_i = int(prev) if prev is not None else None
    last_alert = float(state.get("last_alert_ts") or 0)

    print(
        f"[{now_kst()}] {cfg['movie_name']} {cfg['start_time']} "
        f"잔여 {curr}/{total} (이전 {prev_i})"
    )

    if force_status:
        notify(cfg, "모니터 시작", format_show(cfg, show))
        state["last_alert_ts"] = time.time()

    ok, reason = should_alert(cfg, prev_i, curr, last_alert)
    if ok:
        notify(cfg, reason, format_show(cfg, show))
        state["last_alert_ts"] = time.time()
    elif reason not in ("baseline", "cooldown", "no_increase", "skip"):
        print(f"[{now_kst()}] skip: {reason}")

    state.update(
        {
            "remaining_seats": curr,
            "total_seats": total,
            "last_check": now_kst(),
            "last_error": None,
            "movie_name": show.get("movieName") or cfg["movie_name"],
            "start_time": show.get("startTime") or cfg["start_time"],
        }
    )
    return state


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CGV 취소표(잔여석 증가) 감지 푸시")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--once", action="store_true", help="한 번만 조회")
    p.add_argument("--test-push", action="store_true", help="테스트 푸시 후 종료")
    p.add_argument("--status-push", action="store_true", help="시작 시 현재 잔여석 푸시")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="조회·로그만 하고 푸시는 보내지 않음",
    )
    p.add_argument("--interval", type=int, default=None, help="폴링 초 (config 덮어쓰기)")
    p.add_argument(
        "--any-seat",
        action="store_true",
        help="잔여>0이면 알림 (기본은 증가=취소표만)",
    )
    return p.parse_args()


def resolve_config_path(path: Path) -> Path:
    """config.json이 없으면 config.example.json을 안내한다."""
    if path.exists():
        return path
    example = ROOT / "config.example.json"
    if path == DEFAULT_CONFIG and example.exists():
        raise FileNotFoundError(
            f"{path.name} 없음. 먼저 복사하세요: "
            f"copy config.example.json config.json  (또는 cp config.example.json config.json)"
        )
    raise FileNotFoundError(path)


def main() -> int:
    args = parse_args()
    cfg = apply_env_overrides(load_json(resolve_config_path(args.config)))
    if args.interval:
        cfg["poll_interval_sec"] = args.interval
    if args.any_seat:
        cfg["alert_on_increase_only"] = False
    if args.dry_run:
        cfg["_dry_run"] = True

    if args.test_push:
        notify(
            cfg,
            "테스트 알림",
            f"{cfg['movie_name']} / {cfg['theater_name']} {cfg['start_time']}\n설정 OK",
        )
        return 0

    state: dict[str, Any] = {}
    if STATE_FILE.exists():
        try:
            state = load_json(STATE_FILE)
        except json.JSONDecodeError:
            state = {}

    print(
        f"[{now_kst()}] 감시 시작: {cfg['movie_name']} | {cfg['theater_name']} | "
        f"{cfg['play_date']} {cfg['start_time']} | 간격 {cfg['poll_interval_sec']}s"
    )
    print(f"[{now_kst()}] ntfy 토픽: {cfg.get('ntfy_topic')} @ {cfg.get('ntfy_server')}")
    mode = "잔여석 증가(취소표)" if cfg.get("alert_on_increase_only", True) else "잔여>0"
    if cfg.get("_dry_run"):
        mode = f"{mode} + dry-run"
    print(f"[{now_kst()}] 모드: {mode}")

    try:
        state = once(cfg, state, force_status=args.status_push)
        save_json(STATE_FILE, state)
    except Exception as e:  # noqa: BLE001
        print(f"[{now_kst()}] 초기 조회 실패: {e}", file=sys.stderr)
        if args.once:
            return 1

    if args.once:
        return 0

    interval = max(15, int(cfg.get("poll_interval_sec", 45)))
    while True:
        time.sleep(interval)
        try:
            state = once(cfg, state)
            save_json(STATE_FILE, state)
        except urllib.error.HTTPError as e:
            print(f"[{now_kst()}] HTTP {e.code}: {e}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"[{now_kst()}] 조회 오류: {e}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
