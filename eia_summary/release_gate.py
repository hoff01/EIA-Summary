from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from .paths import ROOT
from .release_schedule import EASTERN_TZ, eastern_now, next_release_events, release_datetime_eastern, release_event_for_date, schedule_cache


DEFAULT_MONITOR_START_ET = "10:28"
DEFAULT_POLL_SECONDS = 5
DEFAULT_MAX_WAIT_MINUTES = 2
DEFAULT_SCHEDULE_REFRESH_DAYS = 7


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily release gate for EIA weekly dashboard runs.")
    parser.add_argument("--force-schedule-refresh", action="store_true")
    parser.add_argument("--refresh-schedule-only", action="store_true")
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--show-decision", action="store_true")
    parser.add_argument("--latest", action="store_true", help="Fetch the latest published week immediately, without consulting the release calendar.")
    parser.add_argument("--now-eastern", help="Testing override in ISO format; naive values are interpreted as Eastern time.")
    parser.add_argument("--poll-seconds", type=int)
    parser.add_argument("--max-wait-minutes", type=int)
    return parser.parse_args()


def _load_project_config(root: Path) -> dict[str, str]:
    config: dict[str, str] = {}
    path = root / "project.env"
    if not path.exists():
        return config
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        clean = value.strip()
        if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in {"'", '"'}:
            clean = clean[1:-1]
        config[key.strip()] = clean
    return config


def _parse_clock_hhmm(value: str) -> tuple[int, int]:
    hour_text, minute_text = value.split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid HH:MM value: {value!r}")
    return hour, minute


def _monitor_start_datetime(event_date, config: dict[str, str]) -> datetime:
    hour, minute = _parse_clock_hhmm(config.get("RELEASE_MONITOR_START_ET", DEFAULT_MONITOR_START_ET))
    return datetime(event_date.year, event_date.month, event_date.day, hour, minute, tzinfo=EASTERN_TZ)


def _poll_seconds(config: dict[str, str], args: argparse.Namespace) -> int:
    if args.poll_seconds is not None:
        return max(args.poll_seconds, 5)
    return max(int(config.get("RELEASE_POLL_SECONDS", str(DEFAULT_POLL_SECONDS))), 5)


def _max_wait_minutes(config: dict[str, str], args: argparse.Namespace) -> int:
    if args.max_wait_minutes is not None:
        return max(args.max_wait_minutes, 1)
    return max(int(config.get("RELEASE_MAX_WAIT_MINUTES", str(DEFAULT_MAX_WAIT_MINUTES))), 1)


def _schedule_refresh_days(config: dict[str, str]) -> int:
    return max(int(config.get("RELEASE_SCHEDULE_REFRESH_DAYS", str(DEFAULT_SCHEDULE_REFRESH_DAYS))), 1)


def _resolve_now_eastern(raw_now: str | None) -> datetime:
    if raw_now is None:
        return eastern_now()
    parsed = datetime.fromisoformat(raw_now)
    return eastern_now(parsed)


def _run_build(args: list[str]) -> tuple[int, dict[str, str], str]:
    cmd = [sys.executable, str(ROOT / "build.py"), *args]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    combined = proc.stdout
    if proc.stderr:
        combined = combined + ("\n" if combined else "") + proc.stderr
    fields: dict[str, str] = {}
    for line in combined.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()
    return proc.returncode, fields, combined


def _emit_schedule_summary(config, today_et):
    upcoming = next_release_events(config, today_et, count=6)
    for idx, event in enumerate(upcoming, start=1):
        prefix = f"upcoming_release_{idx}"
        print(f"{prefix}_date_et={event.release_date.isoformat()}")
        print(f"{prefix}_week_ending={event.week_ending.isoformat()}")
        print(f"{prefix}_time_et={event.release_time_et}")
        print(f"{prefix}_is_exception={str(event.is_exception).lower()}")
        if event.holiday:
            print(f"{prefix}_holiday={event.holiday}")


def _poll_latest(config: dict[str, str], args: argparse.Namespace) -> int:
    print("release_gate_action=monitor")
    print("release_gate_mode=latest_available")
    if args.show_decision:
        return 0
    deadline = time.monotonic() + _max_wait_minutes(config, args) * 60
    while time.monotonic() < deadline:
        code, fields, output = _run_build(["--refresh-eia-latest", "--refresh-only"])
        if output:
            print(output.rstrip())
        week = fields.get("refreshed_week", "")
        if code == 0 and week:
            datetime.strptime(week, "%Y-%m-%d")
            print("release_gate_action=ready")
            print(f"release_gate_ready_week={week}")
            return 0
        remaining = deadline - time.monotonic()
        if args.no_wait or remaining <= 0:
            break
        time.sleep(min(_poll_seconds(config, args), remaining))
    print("release_gate_action=error")
    print("release_gate_reason=latest_data_unavailable")
    return 1


def main() -> int:
    args = _parse_args()
    config = _load_project_config(ROOT)
    now_et = _resolve_now_eastern(args.now_eastern)
    if args.latest and not args.refresh_schedule_only:
        return _poll_latest(config, args)
    try:
        schedule = schedule_cache(
            ROOT,
            force_refresh=args.force_schedule_refresh,
            max_age_days=_schedule_refresh_days(config),
            now=now_et,
        )
    except Exception as exc:
        if args.refresh_schedule_only:
            raise
        print(f"release_gate_schedule_warning={exc}")
        return _poll_latest(config, args)
    today_et = now_et.date()

    print(f"schedule_source_url={schedule.source_url}")
    print(f"schedule_fetched_at_utc={schedule.fetched_at_utc}")
    print(f"current_time_et={now_et.isoformat()}")

    if args.refresh_schedule_only:
        _emit_schedule_summary(schedule, today_et)
        return 0

    event = release_event_for_date(schedule, today_et)
    if event is None:
        return _poll_latest(config, args)

    print("release_gate_action=monitor")
    print(f"release_gate_week_ending={event.week_ending.isoformat()}")
    print(f"release_gate_release_date_et={event.release_date.isoformat()}")
    print(f"release_gate_release_time_et={event.release_time_et}")
    print(f"release_gate_is_exception={str(event.is_exception).lower()}")
    if event.holiday:
        print(f"release_gate_holiday={event.holiday}")
    if args.show_decision:
        return 0

    monitor_start = _monitor_start_datetime(event.release_date, config)
    release_dt = release_datetime_eastern(event)
    if not args.no_wait and now_et < monitor_start:
        wait_seconds = (monitor_start - now_et).total_seconds()
        print(f"release_gate_wait_until_et={monitor_start.isoformat()}")
        time.sleep(max(wait_seconds, 0))
        now_et = eastern_now()

    if not args.no_wait and now_et < release_dt:
        wait_seconds = (release_dt - now_et).total_seconds()
        print(f"release_gate_release_window_et={release_dt.isoformat()}")
        time.sleep(max(wait_seconds, 0))

    deadline = max(release_dt, eastern_now()) + timedelta(minutes=_max_wait_minutes(config, args))
    poll_seconds = _poll_seconds(config, args)
    expected_week = event.week_ending.isoformat()
    print(f"release_gate_deadline_et={deadline.isoformat()}")
    print(f"release_gate_poll_seconds={poll_seconds}")

    while True:
        attempt_started = eastern_now()
        print(f"release_gate_probe_started_et={attempt_started.isoformat()}")
        code, fields, output = _run_build(["--refresh-eia-latest", "--refresh-only"])
        if output:
            print(output.rstrip())
        if code == 0 and fields.get("refreshed_week", "") >= expected_week:
            print("release_gate_action=ready")
            print(f"release_gate_ready_week={fields.get('refreshed_week', '')}")
            return 0

        now_et = eastern_now()
        if args.no_wait:
            print("release_gate_action=wait")
            print(f"release_gate_expected_week={expected_week}")
            return 0
        if now_et >= deadline:
            print("release_gate_action=error")
            print("release_gate_reason=release_not_confirmed_before_deadline")
            print(f"release_gate_expected_week={expected_week}")
            return 1
        print(f"release_gate_poll_sleep_seconds={poll_seconds}")
        time.sleep(poll_seconds)
