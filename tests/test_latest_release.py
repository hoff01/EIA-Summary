import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from eia_summary import refresh_weekly, release_gate
from eia_summary.release_schedule import EASTERN_TZ, ReleaseEvent


class LatestReleaseTests(unittest.TestCase):
    def args(self, **overrides):
        values = dict(latest=False, scheduled=False, max_attempts=120, now_eastern="2026-09-25T12:00:00",
                      force_schedule_refresh=False, refresh_schedule_only=False,
                      show_decision=False, no_wait=True, poll_seconds=0.4, max_wait_minutes=None)
        return SimpleNamespace(**(values | overrides))

    def test_non_release_day_refreshes_and_uses_live_week(self):
        schedule = SimpleNamespace(source_url="test", fetched_at_utc="test")
        with patch.object(release_gate, "_parse_args", return_value=self.args()), \
             patch.object(release_gate, "schedule_cache", return_value=schedule), \
             patch.object(release_gate, "release_event_for_date", return_value=None), \
             patch.object(release_gate, "_run_build", return_value=(0, {"refreshed_week": "2026-09-18"}, "")) as build, \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(release_gate.main(), 0)
        build.assert_called_once_with(["--refresh-eia-latest", "--refresh-only"])
        self.assertIn("release_gate_ready_week=2026-09-18", output.getvalue())
        self.assertNotIn("release_gate_action=skip", output.getvalue())

    def test_latest_override_does_not_consult_calendar(self):
        with patch.object(release_gate, "_parse_args", return_value=self.args(latest=True)), \
             patch.object(release_gate, "schedule_cache", side_effect=AssertionError("calendar used")), \
             patch.object(release_gate, "_run_build", return_value=(0, {"refreshed_week": "2026-09-18"}, "")), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(release_gate.main(), 0)

    def test_unavailable_schedule_does_not_block_data(self):
        with patch.object(release_gate, "_parse_args", return_value=self.args()), \
             patch.object(release_gate, "schedule_cache", side_effect=OSError("unavailable")), \
             patch.object(release_gate, "_run_build", return_value=(0, {"refreshed_week": "2026-09-18"}, "")), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(release_gate.main(), 0)

    def test_failed_refresh_never_marks_cached_data_ready(self):
        with patch.object(release_gate, "_parse_args", return_value=self.args(latest=True)), \
             patch.object(release_gate, "_run_build", return_value=(1, {}, "blank response")), \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(release_gate.main(), 1)
        self.assertNotIn("release_gate_ready_week=", output.getvalue())

    def test_latest_makes_120_attempts_with_119_point_four_second_sleeps(self):
        now = [0.0]
        def sleep(seconds):
            now[0] += seconds
        with patch.object(release_gate.time, "monotonic", side_effect=lambda: now[0]), \
             patch.object(release_gate.time, "sleep", side_effect=sleep) as sleeps, \
             patch.object(release_gate, "_run_build", return_value=(1, {}, "")) as build, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(release_gate._poll_latest({}, self.args(no_wait=False)), 1)
        self.assertEqual(build.call_count, 120)
        self.assertEqual(sleeps.call_count, 119)
        self.assertTrue(all(call.args == (0.4,) for call in sleeps.call_args_list))
        self.assertAlmostEqual(now[0], 47.6)

    def test_show_decision_is_read_only(self):
        with patch.object(release_gate, "_parse_args", return_value=self.args(latest=True, show_decision=True)), \
             patch.object(release_gate, "_run_build") as build, redirect_stdout(io.StringIO()):
            self.assertEqual(release_gate.main(), 0)
        build.assert_not_called()

    def test_late_release_day_start_still_retries(self):
        now = datetime(2026, 9, 23, 14, 0, tzinfo=EASTERN_TZ)
        event = ReleaseEvent(date(2026, 9, 18), now.date(), "Wednesday", "10:30 a.m.", "", False)
        schedule = SimpleNamespace(source_url="test", fetched_at_utc="test")
        attempts = [(1, {}, "blank"), (0, {"refreshed_week": "2026-09-18"}, "")]
        with patch.object(release_gate, "_parse_args", return_value=self.args(no_wait=False, now_eastern=now.isoformat())), \
             patch.object(release_gate, "schedule_cache", return_value=schedule), \
             patch.object(release_gate, "release_event_for_date", return_value=event), \
             patch.object(release_gate, "eastern_now", return_value=now), \
             patch.object(release_gate, "_run_build", side_effect=attempts) as build, \
             patch.object(release_gate.time, "sleep") as sleep, redirect_stdout(io.StringIO()):
            self.assertEqual(release_gate.main(), 0)
        self.assertEqual(build.call_count, 2)
        sleep.assert_called_once_with(0.4)

    def test_standard_run_starts_before_release_without_reading_schedule(self):
        with patch("sys.argv", ["run_release_gate.py", "--now-eastern", "2026-09-30T09:00:00"]), \
             patch.object(release_gate, "schedule_cache", side_effect=AssertionError("calendar used")), \
             patch.object(release_gate, "_run_build", side_effect=[(1, {}, "blank"), (0, {"refreshed_week": "2026-09-25"}, "")]) as build, \
             patch.object(release_gate.time, "sleep") as sleep, redirect_stdout(io.StringIO()):
            self.assertEqual(release_gate.main(), 0)
        self.assertEqual(build.call_count, 2)
        sleep.assert_called_once_with(0.4)

    def test_slow_requests_do_not_use_up_attempt_budget_by_elapsed_time(self):
        now = [0.0]
        def slow(*args):
            now[0] += 2
            return (1, {}, "unavailable")
        with patch.object(release_gate.time, "monotonic", side_effect=lambda: now[0]), \
             patch.object(release_gate.time, "sleep", side_effect=lambda seconds: now.__setitem__(0, now[0] + seconds)), \
             patch.object(release_gate, "_run_build", side_effect=slow) as build, redirect_stdout(io.StringIO()):
            self.assertEqual(release_gate._poll_latest({}, self.args(no_wait=False)), 1)
        self.assertEqual(build.call_count, 120)
        self.assertAlmostEqual(now[0], 287.6)

    def test_missing_source_archive_bootstraps_history(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(refresh_weekly, "refresh_weekly_data", return_value=(10, 2, "2026-09-18")) as bootstrap:
            root = Path(directory)
            self.assertEqual(refresh_weekly.refresh_wpsr_latest_data(root), (10, 2, "2026-09-18"))
        bootstrap.assert_called_once_with(root)

    def test_downloaded_week_is_added_when_not_in_archive(self):
        previous = {"week_ending": "2026-09-11", "period_type": "weekly", "source_column": "A", "value": "1"}
        latest = dict(previous, week_ending="2026-09-18", value="2")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw.csv.tar.xz").touch()
            with patch.object(refresh_weekly, "_download_latest_wpsr_xls_rows", return_value=([latest], {}, "2026-09-23", "{}")), \
                 patch.object(refresh_weekly, "_validate_latest_sources"), \
                 patch.object(refresh_weekly, "_read_raw_archive", return_value=[previous]), \
                 patch.object(refresh_weekly, "_read_series", return_value={}), \
                 patch.object(refresh_weekly, "_write_data_files", return_value=(2, 1, "2026-09-18")) as write:
                self.assertEqual(refresh_weekly.refresh_wpsr_latest_data(root)[2], "2026-09-18")
            self.assertEqual({row["week_ending"] for row in write.call_args.args[1]}, {"2026-09-11", "2026-09-18"})


if __name__ == "__main__":
    unittest.main()
