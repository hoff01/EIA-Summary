from __future__ import annotations

import csv
import io
import tarfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import polars as pl


REQUIRED_RAW_COLUMNS = {
    "week_ending",
    "release_date",
    "source_column",
    "period_type",
    "value",
}


@dataclass(frozen=True)
class RawDataset:
    values: dict[str, dict[date, float]]
    release_dates: dict[date, str]
    weeks: list[date]
    row_count: int


def _open_raw_csv(archive_path: Path):
    tf = tarfile.open(archive_path, "r:*")
    members = [m for m in tf.getmembers() if m.isfile()]
    if len(members) != 1 or members[0].name != "raw.csv":
        tf.close()
        names = ", ".join(m.name for m in members)
        raise ValueError(f"{archive_path} must contain exactly raw.csv; found {names}")
    raw = tf.extractfile(members[0])
    if raw is None:
        tf.close()
        raise ValueError("could not extract raw.csv from archive")
    return tf, io.TextIOWrapper(raw, encoding="utf-8", newline="")


def scan_weeks(archive_path: Path) -> tuple[list[date], dict[date, str], int]:
    tf, handle = _open_raw_csv(archive_path)
    try:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_RAW_COLUMNS.issubset(reader.fieldnames):
            raise ValueError(f"raw.csv missing required columns: {sorted(REQUIRED_RAW_COLUMNS)}")
        weeks: set[date] = set()
        release_dates: dict[date, str] = {}
        row_count = 0
        for row in reader:
            if row["period_type"] != "weekly":
                continue
            week = date.fromisoformat(row["week_ending"])
            weeks.add(week)
            release_dates[week] = row.get("release_date", "")
            row_count += 1
        return sorted(weeks), release_dates, row_count
    finally:
        handle.close()
        tf.close()


def load_raw(archive_path: Path, source_columns: Iterable[str] | None = None) -> RawDataset:
    selected = set(source_columns or [])
    keep_all = not selected
    values: dict[str, dict[date, float]] = defaultdict(dict)
    release_dates: dict[date, str] = {}
    weeks: set[date] = set()
    row_count = 0

    tf, handle = _open_raw_csv(archive_path)
    try:
        # Parse only the five used columns in Rust instead of Python dictionaries
        # for every field in the full historical archive.
        frame = pl.read_csv(handle.read().encode("utf-8"), columns=sorted(REQUIRED_RAW_COLUMNS),
                            infer_schema=False).filter(pl.col("period_type") == "weekly")
        if not keep_all:
            frame = frame.filter(pl.col("source_column").is_in(sorted(selected)))
        frame = frame.with_columns(pl.col("value").cast(pl.Float64, strict=False)).drop_nulls("value")
        for source_column, week_text, release_date, value in frame.select(
            "source_column", "week_ending", "release_date", "value"
        ).iter_rows():
            week = date.fromisoformat(week_text)
            values[source_column][week] = value
            weeks.add(week)
            release_dates[week] = release_date or ""
            row_count += 1
    finally:
        handle.close()
        tf.close()

    return RawDataset(dict(values), release_dates, sorted(weeks), row_count)
