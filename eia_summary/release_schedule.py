from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import urllib.request
from zoneinfo import ZoneInfo


EIA_WPSR_SCHEDULE_URL = "https://www.eia.gov/petroleum/supply/weekly/schedule.php"
RELEASE_TIME_ZONE = os.environ.get("RELEASE_TIME_ZONE", "America/New_York")
EASTERN_TZ = ZoneInfo(RELEASE_TIME_ZONE)
UTC = timezone.utc
SCHEDULE_CACHE_NAME = "wpsr_release_schedule.json"
SCHEDULE_SEED_NAME = "wpsr_release_schedule_seed.json"
STANDARD_RELEASE_DAY = "Wednesday"
STANDARD_RELEASE_TIME_TEXT = "10:30 a.m."
DATA_WEEK_ENDING_WEEKDAY = 4

DAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

DEFAULT_RELEASE_RE = re.compile(
    r"after\s+(?P<time>\d{1,2}:\d{2}\s+[ap]\.m\.)\s+eastern time on\s+(?P<day>[A-Za-z]+)",
    re.IGNORECASE,
)
HOLIDAY_ROW_RE = re.compile(
    r"^(?P<week_ending>[A-Za-z]+\s+\d{1,2},\s+\d{4})\s+"
    r"(?P<release_date>[A-Za-z]+\s+\d{1,2},\s+\d{4})\s+"
    r"(?P<release_day>[A-Za-z]+)\s+"
    r"(?P<release_time>\d{1,2}:\d{2}\s+[ap]\.m\.)\s+"
    r"(?P<holiday>.+)$"
)
DATE_LINE_RE = re.compile(r"^[A-Za-z]+\s+\d{1,2},\s+\d{4}$")
DAY_LINE_RE = re.compile(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$", re.IGNORECASE)
TIME_LINE_RE = re.compile(r"^\d{1,2}:\d{2}\s+[ap]\.m\.$", re.IGNORECASE)
BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "main",
    "header",
    "footer",
    "li",
    "ul",
    "ol",
    "table",
    "thead",
    "tbody",
    "tr",
    "td",
    "th",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "br",
}


@dataclass(frozen=True)
class HolidayException:
    week_ending: date
    default_release_date: date
    release_date: date
    release_day_name: str
    release_time_eastern: str
    holiday: str


@dataclass(frozen=True)
class ScheduleCache:
    source_url: str
    fetched_at: datetime
    default_release_day_name: str
    default_release_weekday: int
    default_release_time_eastern: str
    holiday_exceptions: list[HolidayException]

    @property
    def fetched_at_utc(self) -> str:
        return self.fetched_at.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class ReleaseEvent:
    week_ending: date
    release_date: date
    release_day: str
    release_time_et: str
    holiday: str
    is_exception: bool


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)


def _parse_date(value: str) -> date:
    text = " ".join(value.split()).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return date.fromisoformat(text)


def _parse_time(value: str) -> time:
    normalized = " ".join(value.split()).strip().lower().replace(".", "")
    return datetime.strptime(normalized, "%I:%M %p").time()


def _cache_path(root: Path) -> Path:
    return root / "cache" / SCHEDULE_CACHE_NAME


def _seed_path(root: Path) -> Path:
    return root / SCHEDULE_SEED_NAME


def _request_headers() -> dict[str, str]:
    return {
        "Accept": "text/html,*/*",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "eia-summary-dashboard/1.0",
    }


def _download_schedule_html() -> str:
    request = urllib.request.Request(EIA_WPSR_SCHEDULE_URL, headers=_request_headers())
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def _html_to_lines(raw_html: str) -> list[str]:
    extractor = _TextExtractor()
    extractor.feed(raw_html)
    text = unescape("".join(extractor.parts))
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if line:
            lines.append(line)
    return lines


def _days_until_release(week_ending: date, release_weekday: int) -> int:
    delta = (release_weekday - week_ending.weekday()) % 7
    if delta == 0:
        delta = 7
    return delta


def _default_release_offset_days(default_release_weekday: int) -> int:
    delta = (default_release_weekday - DATA_WEEK_ENDING_WEEKDAY) % 7
    if delta == 0:
        delta = 7
    return delta


def _holiday_exceptions_from_lines(lines: list[str], default_release_weekday: int) -> list[HolidayException]:
    section_index = next((idx for idx, line in enumerate(lines) if line == "Holiday Release Schedule"), -1)
    if section_index < 0:
        raise ValueError("could not find Holiday Release Schedule section")

    header_lines = {
        "The standard release time and day of the week will be at 10:30 a.m. eastern time on Wednesdays with the following exceptions. All times are eastern.",
        "Data for the week ending",
        "Alternate release date",
        "Release day",
        "Release time",
        "Holiday",
    }
    payload: list[str] = []
    for line in lines[section_index + 1:]:
        if line == "Top":
            break
        if line in header_lines:
            continue
        if not payload and not (HOLIDAY_ROW_RE.match(line) or DATE_LINE_RE.match(line)):
            continue
        payload.append(line)

    holiday_exceptions: list[HolidayException] = []
    idx = 0
    while idx < len(payload):
        direct_match = HOLIDAY_ROW_RE.match(payload[idx])
        if direct_match is not None:
            week_ending = _parse_date(direct_match.group("week_ending"))
            holiday_exceptions.append(
                HolidayException(
                    week_ending=week_ending,
                    default_release_date=week_ending + timedelta(days=_days_until_release(week_ending, default_release_weekday)),
                    release_date=_parse_date(direct_match.group("release_date")),
                    release_day_name=direct_match.group("release_day"),
                    release_time_eastern=direct_match.group("release_time"),
                    holiday=direct_match.group("holiday"),
                )
            )
            idx += 1
            continue

        row = payload[idx:idx + 5]
        if len(row) < 5:
            break
        if not (
            DATE_LINE_RE.match(row[0])
            and DATE_LINE_RE.match(row[1])
            and DAY_LINE_RE.match(row[2])
            and TIME_LINE_RE.match(row[3])
        ):
            idx += 1
            continue
        week_ending = _parse_date(row[0])
        holiday_exceptions.append(
            HolidayException(
                week_ending=week_ending,
                default_release_date=week_ending + timedelta(days=_days_until_release(week_ending, default_release_weekday)),
                release_date=_parse_date(row[1]),
                release_day_name=row[2],
                release_time_eastern=row[3],
                holiday=row[4],
            )
        )
        idx += 5

    if not holiday_exceptions:
        raise ValueError("no holiday exceptions parsed from schedule page")
    return holiday_exceptions


def _parse_schedule_html(raw_html: str) -> ScheduleCache:
    lines = _html_to_lines(raw_html)

    default_match = None
    for line in lines:
        default_match = DEFAULT_RELEASE_RE.search(line)
        if default_match:
            break
    if default_match is None:
        raise ValueError("could not find the default WPSR release schedule on the EIA page")

    default_release_day_name = default_match.group("day")
    default_release_time_eastern = default_match.group("time")
    default_release_weekday = DAY_NAMES[default_release_day_name.lower()]
    holiday_exceptions = _holiday_exceptions_from_lines(lines, default_release_weekday)

    return ScheduleCache(
        source_url=EIA_WPSR_SCHEDULE_URL,
        fetched_at=datetime.now(tz=EASTERN_TZ),
        default_release_day_name=default_release_day_name,
        default_release_weekday=default_release_weekday,
        default_release_time_eastern=default_release_time_eastern,
        holiday_exceptions=holiday_exceptions,
    )


def _schedule_to_json(schedule: ScheduleCache) -> dict[str, object]:
    return {
        "source_url": schedule.source_url,
        "fetched_at": schedule.fetched_at.isoformat(),
        "default_release_day_name": schedule.default_release_day_name,
        "default_release_weekday": schedule.default_release_weekday,
        "default_release_time_eastern": schedule.default_release_time_eastern,
        "holiday_exceptions": [
            {
                "week_ending": item.week_ending.isoformat(),
                "default_release_date": item.default_release_date.isoformat(),
                "release_date": item.release_date.isoformat(),
                "release_day_name": item.release_day_name,
                "release_time_eastern": item.release_time_eastern,
                "holiday": item.holiday,
            }
            for item in schedule.holiday_exceptions
        ],
    }


def _schedule_from_current_json(payload: dict[str, object]) -> ScheduleCache:
    return ScheduleCache(
        source_url=str(payload["source_url"]),
        fetched_at=datetime.fromisoformat(str(payload["fetched_at"])),
        default_release_day_name=str(payload["default_release_day_name"]),
        default_release_weekday=int(payload["default_release_weekday"]),
        default_release_time_eastern=str(payload["default_release_time_eastern"]),
        holiday_exceptions=[
            HolidayException(
                week_ending=date.fromisoformat(str(item["week_ending"])),
                default_release_date=date.fromisoformat(str(item["default_release_date"])),
                release_date=date.fromisoformat(str(item["release_date"])),
                release_day_name=str(item["release_day_name"]),
                release_time_eastern=str(item["release_time_eastern"]),
                holiday=str(item["holiday"]),
            )
            for item in payload.get("holiday_exceptions", [])
        ],
    )


def _schedule_from_legacy_json(payload: dict[str, object]) -> ScheduleCache:
    default_release_day_name = str(payload.get("standard_release_day", STANDARD_RELEASE_DAY))
    default_release_weekday = DAY_NAMES.get(default_release_day_name.lower(), DAY_NAMES["wednesday"])
    default_release_time_eastern = str(payload.get("standard_release_time_et", STANDARD_RELEASE_TIME_TEXT))
    fetched_at_raw = str(payload.get("fetched_at_utc", datetime.now(tz=UTC).isoformat()))
    fetched_at = datetime.fromisoformat(fetched_at_raw).astimezone(EASTERN_TZ)

    holiday_exceptions: list[HolidayException] = []
    for item in payload.get("overrides", []):
        week_ending = date.fromisoformat(str(item["week_ending"]))
        holiday_exceptions.append(
            HolidayException(
                week_ending=week_ending,
                default_release_date=week_ending + timedelta(days=_days_until_release(week_ending, default_release_weekday)),
                release_date=date.fromisoformat(str(item["release_date"])),
                release_day_name=str(item["release_day"]),
                release_time_eastern=str(item["release_time_et"]),
                holiday=str(item["holiday"]),
            )
        )

    return ScheduleCache(
        source_url=str(payload.get("source_url", EIA_WPSR_SCHEDULE_URL)),
        fetched_at=fetched_at,
        default_release_day_name=default_release_day_name,
        default_release_weekday=default_release_weekday,
        default_release_time_eastern=default_release_time_eastern,
        holiday_exceptions=holiday_exceptions,
    )


def _load_schedule_file(path: Path) -> ScheduleCache | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if "holiday_exceptions" in payload:
        try:
            return _schedule_from_current_json(payload)
        except (KeyError, TypeError, ValueError):
            return None
    if "overrides" in payload:
        try:
            return _schedule_from_legacy_json(payload)
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _write_cache(path: Path, schedule: ScheduleCache) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_schedule_to_json(schedule), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _should_refresh(schedule: ScheduleCache | None, now_et: datetime, refresh_days: int) -> bool:
    if schedule is None:
        return True
    age = now_et - schedule.fetched_at.astimezone(EASTERN_TZ)
    return age >= timedelta(days=refresh_days)


def schedule_cache(root: Path, *, force_refresh: bool = False, max_age_days: int = 7, now: datetime | None = None) -> ScheduleCache:
    now_et = eastern_now(now)
    cache_path = _cache_path(root)
    seed_path = _seed_path(root)
    cache_schedule = _load_schedule_file(cache_path)
    seed_schedule = _load_schedule_file(seed_path)
    active_schedule = cache_schedule or seed_schedule

    needs_refresh = force_refresh or cache_schedule is None or _should_refresh(active_schedule, now_et, max_age_days)
    if needs_refresh:
        try:
            refreshed = _parse_schedule_html(_download_schedule_html())
            _write_cache(cache_path, refreshed)
            return refreshed
        except Exception:
            if active_schedule is not None:
                return active_schedule
            raise

    return active_schedule


def release_event_for_date(schedule: ScheduleCache, target_date: date) -> ReleaseEvent | None:
    exceptions_by_release_date = {
        item.release_date: item
        for item in schedule.holiday_exceptions
    }
    overridden_default_dates = {
        item.default_release_date
        for item in schedule.holiday_exceptions
    }

    if target_date in exceptions_by_release_date:
        item = exceptions_by_release_date[target_date]
        return ReleaseEvent(
            week_ending=item.week_ending,
            release_date=target_date,
            release_day=item.release_day_name,
            release_time_et=item.release_time_eastern,
            holiday=item.holiday,
            is_exception=True,
        )

    if target_date.weekday() != schedule.default_release_weekday or target_date in overridden_default_dates:
        return None

    return ReleaseEvent(
        week_ending=target_date - timedelta(days=_default_release_offset_days(schedule.default_release_weekday)),
        release_date=target_date,
        release_day=schedule.default_release_day_name,
        release_time_et=schedule.default_release_time_eastern,
        holiday="",
        is_exception=False,
    )


def next_release_events(schedule: ScheduleCache, start_date: date, count: int = 8) -> list[ReleaseEvent]:
    events: list[ReleaseEvent] = []
    cursor = start_date
    while len(events) < count:
        event = release_event_for_date(schedule, cursor)
        if event is not None:
            events.append(event)
        cursor += timedelta(days=1)
    return events


def release_datetime_eastern(event: ReleaseEvent) -> datetime:
    return datetime.combine(event.release_date, _parse_time(event.release_time_et), tzinfo=EASTERN_TZ)


def eastern_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(tz=EASTERN_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=EASTERN_TZ)
    return now.astimezone(EASTERN_TZ)
