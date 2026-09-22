`EIA_Dashboard_New.zip` is the preserved WPSR-ready package.

Use the working folder in this repository for the legacy weekly XLS workflow.
When EIA actually switches to the newer release path, unzip `EIA_Dashboard_New.zip` and work from the extracted `EIA_Dashboard_New/` folder.

For the current Windows handoff, use `scripts\setup_windows.bat`, then either `RUN_EIA_SUMMARY_DASHBOARD.bat` for a manual release run or `scripts\install_windows_task.bat` for Task Scheduler. The task start is configured from 10:28 a.m. New York/Eastern time and converted to local time on the target computer. It waits for the official EIA release window in Eastern time, polls every 5 seconds for up to 2 minutes, verifies the expected week is live, saves the PDF in `archive\`, and sends through desktop Outlook. If Outlook is not already running, the sender starts classic desktop Outlook and waits for it to become automation-ready before sending. Duplicate weekly sends are skipped per recipient using `logs\email_send_history.json`; Task Scheduler retries are also guarded by `logs\last_successful_outlook_send.json`.
