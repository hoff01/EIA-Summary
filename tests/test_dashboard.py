import csv
import io
import random
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fitz

from eia_summary.data_load import RawDataset, load_raw
from eia_summary.emailer import read_recipients
from eia_summary.metrics import build_rows, dependency_source_columns, iso_prior_year_day
from eia_summary.refresh_weekly import _download_latest_wpsr_xls_rows, _validate_latest_sources
from eia_summary import release_gate
from eia_summary.release_schedule import EASTERN_TZ, ReleaseEvent
from eia_summary.render_pdf import DrawnBox, render_pdf
from eia_summary.series_map import sulfur_series_defs
from eia_summary.sulfur import sulfur_sources
from eia_summary.validate import validate_boxes


class DashboardTests(unittest.TestCase):
    def test_render_has_no_creator_footer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.pdf"
            boxes = render_pdf(path, [], date(2026, 9, 11), "2026-09-16")
            self.assertFalse(any(box.kind == "credit" for box in boxes))
            with fitz.open(path) as document:
                page = document[0]
                self.assertNotIn("Created by:", page.get_text())
                footer = page.get_pixmap(clip=fitz.Rect(2600, 2590, 2810, 2625))
                background = page.get_pixmap(clip=fitz.Rect(1, 1, 2, 2)).pixel(0, 0)
                self.assertEqual(footer.samples, bytes(background) * footer.width * footer.height)

    def test_sulfur_sum_and_changes_preserve_negative_net_production(self):
        week = date(2026, 9, 11)
        previous, prior_year = week - timedelta(days=7), iso_prior_year_day(week)
        definition = next(d for d in sulfur_series_defs() if d.display_row == "I:high" and not d.stock_flag)
        a, b = sulfur_sources("production", "high", "I")
        values = {a: {week: -5, previous: -3, prior_year: 1}, b: {week: 3, previous: 2, prior_year: 1}}
        row = build_rows(RawDataset(values, {}, sorted([prior_year, previous, week]), 6), [definition], week)[0]
        self.assertEqual((row.current, row.wow, row.yoy), (-2, -1, -4))
        self.assertEqual(set(dependency_source_columns([definition])), {a, b})

    def test_missing_component_is_not_zero(self):
        week = date(2026, 9, 11)
        definition = next(d for d in sulfur_series_defs() if d.display_row == "A:high")
        a, _b = sulfur_sources("stocks", "high", "A")
        row = build_rows(RawDataset({a: {week: 8}}, {}, [week], 1), [definition], week)[0]
        self.assertIsNone(row.current)

    def test_no_invented_subpadd_production(self):
        with self.assertRaises(ValueError):
            sulfur_sources("production", "low", "A")
        definitions = sulfur_series_defs()
        self.assertEqual(len([d for d in definitions if d.stock_flag]), 18)
        self.assertEqual(len([d for d in definitions if not d.stock_flag]), 12)

    def test_loader_filters_and_keeps_last_duplicate(self):
        fields = ["week_ending", "release_date", "source_column", "period_type", "value"]
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(fields)
        for source, period, value in [("A", "weekly", "1"), ("A", "weekly", "2"),
                                      ("B", "weekly", "8"), ("A", "4-week", "9"),
                                      ("C", "weekly", "NA"), ("C", "weekly", "")]:
            writer.writerow(["2026-09-11", "2026-09-16", source, period, value])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.tar.gz"
            payload = stream.getvalue().encode()
            with tarfile.open(path, "w:gz") as archive:
                info = tarfile.TarInfo("raw.csv")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            loaded = load_raw(path, ["A"])
            self.assertEqual(loaded.values, {"A": {date(2026, 9, 11): 2.0}})
            self.assertEqual(loaded.row_count, 2)
            self.assertEqual(load_raw(path).row_count, 3)

    def test_empty_recipients_never_fall_back_to_personal_address(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "email_recipients.txt"
            with self.assertRaises(ValueError):
                read_recipients(path)
            path.write_text("# add recipients locally\n")
            with self.assertRaises(ValueError):
                read_recipients(path)
            path.write_text("reader@example.com\n")
            self.assertEqual(read_recipients(path), ["reader@example.com"])

    def test_mixed_release_tables_are_rejected(self):
        def fake_fetch(root, table, url):
            week = "2026-09-11" if table == "PSW01" else "2026-09-04"
            return ([{"week_ending": week, "period_type": "weekly"}], {}, "2026-09-16", {})
        with patch("eia_summary.refresh_weekly.WPSR_XLS_TABLES", [("PSW01", "a"), ("PSW09", "b")]), \
             patch("eia_summary.refresh_weekly._fetch_parse_latest_wpsr_xls_table", side_effect=fake_fetch):
            with self.assertRaisesRegex(ValueError, "same release week"):
                _download_latest_wpsr_xls_rows(Path("unused"))

    def test_partial_new_release_cannot_be_cached_as_ready(self):
        definition = next(d for d in sulfur_series_defs() if d.display_row == "A:high")
        a, _b = sulfur_sources("stocks", "high", "A")
        rows = [{"week_ending": "2026-09-11", "period_type": "weekly", "source_column": a, "value": "8"}]
        with patch("eia_summary.series_map.ensure_series_map", return_value=[definition]):
            with self.assertRaisesRegex(ValueError, "missing required series"):
                _validate_latest_sources(Path("unused"), rows)

    def test_fast_overlap_check_matches_pairwise_geometry(self):
        rng = random.Random(17)
        boxes = [DrawnBox("text", rng.randrange(300), rng.randrange(300), rng.randrange(1, 80), rng.randrange(1, 25)) for _ in range(300)]
        expected = sum(a.x < b.x + b.w and a.x + a.w > b.x and a.y < b.y + b.h and a.y + a.h > b.y
                       for i, a in enumerate(boxes) for b in boxes[i + 1:])
        self.assertEqual(validate_boxes(boxes), (0, expected))

    def test_release_gate_retries_blank_and_stale_without_rendering(self):
        args = SimpleNamespace(now_eastern=None, force_schedule_refresh=False, refresh_schedule_only=False,
                               show_decision=False, latest=False, no_wait=False, poll_seconds=5, max_wait_minutes=2)
        now = datetime(2026, 9, 16, 10, 30, tzinfo=EASTERN_TZ)
        event = ReleaseEvent(date(2026, 9, 11), now.date(), "Wednesday", "10:30 a.m.", "", False)
        attempts = [(1, {}, "blank response"), (0, {"refreshed_week": "2026-09-04"}, ""),
                    (0, {"refreshed_week": "2026-09-11"}, "")]
        schedule = SimpleNamespace(source_url="https://example.com", fetched_at_utc="2026-09-16")
        with patch.object(release_gate, "_parse_args", return_value=args), \
             patch.object(release_gate, "_load_project_config", return_value={}), \
             patch.object(release_gate, "schedule_cache", return_value=schedule), \
             patch.object(release_gate, "release_event_for_date", return_value=event), \
             patch.object(release_gate, "eastern_now", return_value=now), \
             patch.object(release_gate, "_run_build", side_effect=attempts) as build, \
             patch.object(release_gate.time, "sleep") as sleep, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(release_gate.main(), 0)
            self.assertEqual(sleep.call_count, 2)
            self.assertEqual(build.call_count, 3)
            for call in build.call_args_list:
                self.assertEqual(call.args[0], ["--refresh-eia-latest", "--refresh-only"])
            self.assertIn("release_gate_ready_week=2026-09-11", output.getvalue())


if __name__ == "__main__":
    unittest.main()
