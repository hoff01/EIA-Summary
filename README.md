# EIA Summary

Builds the one-page DOE/EIA weekly PDF dashboard and optionally sends it through classic desktop Outlook. The independent stats image puller is at https://github.com/hoff01/EIA-Stats-Puller.

## Windows Setup

Install Python 3.11 or later and classic desktop Outlook. Extract anywhere, for example `%USERPROFILE%\Documents\EIA-Summary`. All scripts resolve paths relative to this folder. Create a fresh environment on each computer instead of copying `.venv`.

**One-button use:** double-click `RUN_EIA_SUMMARY_DASHBOARD.bat`. It creates the environment, installs dependencies when needed, asks for recipients if the local list is empty, immediately fetches live EIA data and automatically sends the validated summary through Outlook. There is no weekday or release-time gate, including before 10:30 a.m. Eastern (9:30 a.m. Central). No separate setup step or `-Latest` flag is required. Python 3.11+, internet access and classic Outlook signed in are prerequisites.

**Optional setup only:** `SETUP_WINDOWS.bat` installs dependencies without sending email. Alternatively, run from PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

Setup creates `.venv`, installs `requirements.txt` (including `python-certifi-win32` on Windows), and creates an empty `email_recipients.txt`. Add one recipient address per line. Recipient files, `.env`, delivery receipts, and logs stay local and are ignored by Git. No email address is built into the code.

## Which File to Run

**Preview without sending:**

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_latest.ps1
Invoke-Item .\output\latest.pdf
```

**Standard live run, any day:** `RUN_EIA_SUMMARY_DASHBOARD.bat`. It uses the latest week EIA currently publishes, so it may return the previous week if the new release is not out yet. `-Latest` remains a compatibility alias for this default behavior. Add `-NoEmail` to fetch and build without prompting for recipients or sending: `RUN_EIA_SUMMARY_DASHBOARD.bat -NoEmail`.

The latest week comes from EIA, not from the day of the week or existing PDFs. Missing report PDFs are built from downloaded data; if the source archive itself is absent, history is bootstrapped automatically. The standard run does not consult the calendar. Blank or unavailable data is retried for **up to 120 total attempts**, with **0.4 seconds between completed attempts**, stopping on the first valid result. Attempts do not overlap. All 120 failed attempts involve 119 pauses (47.6 seconds) plus network, validation and processing time; this is an attempt limit, not a two-minute timer. No old local report is silently substituted for unavailable live data. `-ShowDecision` remains read-only.

Downloaded weekly tables must agree on the report week, and missing required values stop the build. No PDF is rendered for an unsuccessful fetch. Once valid data is ready, the PDF is built and automatically submitted to Outlook. Use `-MaxAttempts` or `-PollSeconds` only to override the defaults; `-MaxWaitMinutes` adds an optional time limit.

**Optional scheduled mode:** `RUN_EIA_SUMMARY_DASHBOARD.bat -Scheduled` explicitly restores the older calendar/release-time wait and expected-week checks. This is not the default. Its release watch retains the separate two-minute limit. Start the standard launcher near the time you want to fetch; it will not sit idle until the scheduled release.

The run button skips package installation when the environment and requirements hash are unchanged, and checks your recipient list before fetching. Recipient setup is a one-time prompt; later runs reuse your local file. Double-click runs stay open so errors can be read. Both root batch files work from paths containing spaces and do not require administrator rights. For unattended use, configure recipients first and set `EIA_NO_PAUSE=1`. To check the immediate-run settings without fetching or sending, run `RUN_EIA_SUMMARY_DASHBOARD.bat -ShowDecision`. Add `-Scheduled` to inspect the calendar instead.

Outlook opens automatically when needed. It gets a 12-second startup pause, then up to 60 seconds of readiness checks. Sign in and clear profile/security prompts beforehand. Optional overrides in `.env`: `DOE_SUMMARY_OUTLOOK_STARTUP_WAIT_SECONDS`, `DOE_SUMMARY_OUTLOOK_READY_TIMEOUT_SECONDS`, and `DOE_SUMMARY_OUTLOOK_ACCOUNT`.

Classic Windows Outlook and SMTP emails include the compact colored summary strip in the message body, with the full PDF attached. The strip shows weekly stock changes in million barrels for crude, gasoline, distillates, jet and fuel oil. It is embedded in the message, not fetched from a website. Email clients may still hide images according to the recipient's settings. Legacy Apple Mail sending remains text plus PDF.

The first line of the HTML and plain-text email shows only the U.S. gasoline and distillate weekly stock changes, in million barrels, for the Outlook inbox preview. It uses the same validated totals as the PDF, with no stock levels, production figures or PADD detail. Preview truncation depends on the recipient's Outlook settings.

For quicker delivery, the strip is rendered directly from the validated PDF; full-page PNG preview rendering happens after email submission. Required-data checks, weekly-date matching, duplicate protection, certificate verification and Outlook startup waits are unchanged. Outlook accepting a message means it was submitted, not that it reached the recipient: check Outbox/Sent Items if delivery is delayed.

**Task Scheduler:** run `scripts\install_windows_task.bat`. `WINDOWS_TASK_SCHEDULE_TIME_EASTERN` in `project.env` controls the trigger (currently 10:28 a.m. Eastern), converted to the computer's local time when installed. The task fetches immediately when triggered, without waiting for release time; choose a trigger at or near when you want the data. A 10:28 start is not guaranteed to span a 10:30 release and may use the previous published week. Reinstall after changing the trigger, moving the project or changing the computer's time zone. Updating these files does not alter an already installed task's trigger.

**Intentional live email test:** `scripts\send_test_email.bat` sends to your local recipient list. It is not a dry run. Duplicate weekly sends are suppressed using local receipts in `logs/`; keep these when moving an existing installation to preserve that protection.

## Report Data

- Two sulfur panels share one blue outline beside Ethanol Inputs: stocks and refiner-plus-blender net production. Each shows 0-15 ppm and >15 ppm, Current, ΔWOW and ΔYOY. Production also shows 4W Avg and 4W ΔYOY (the four-week average minus the comparable prior-year four-week average). Last year's level is omitted in these panels.
- Stocks use the same units, one-decimal number formatting, delta headers and indented A/B/C labels as the main distillate stocks panel. They include PADDs I-V, PADD 1A/1B/1C and the U.S. total in million barrels. Production is in thousand barrels/day at PADD and U.S. level, shown as whole numbers like the other production tables. A narrow gap separates the stock and production sections inside one continuous blue border. EIA does not publish corresponding weekly sub-PADD production.
- Above 15 ppm is the sum of EIA's >15-500 ppm and >500 ppm series. It is calculated for each historical week before calculating changes. Missing components remain missing; negative net production is retained.
- EIA rounds regional/component series independently, so sums may differ slightly from headline totals.
- Distillate exports retain the weekly headline. EIA publishes no weekly sulfur export split, so no sulfur export rows are shown. This report includes weekly data only.
- Y/Y uses the comparable ISO week in the prior year. Standard flow cards retain four-week averages.

Sources: [EIA WPSR](https://www.eia.gov/petroleum/supply/weekly/) and [weekly U.S. and PADD estimates](https://www.eia.gov/dnav/pet/pet_sum_sndw_dcus_nus_w.htm). Sulfur series and formulas are in `eia_summary/sulfur.py`.

## Outputs and Maintenance

Latest PDF/PNG: `output/latest.pdf` and `output/latest.png`. Dated PDFs: `archive/EIA_SUMMARY_YYYY-MM-DD.pdf`, indexed in `archive/manifest.csv`. Included source data supports explicit offline previews; the normal Windows launcher refreshes EIA first. Check the report's week before using it.

```powershell
# Fast offline rebuild, no email and no network:
.\.venv\Scripts\python.exe build.py --week latest --skip-email

# Refresh history after a long gap between runs:
.\.venv\Scripts\python.exe build.py --refresh-eia-weekly --force --skip-email

# Tests, with no email:
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Normal release runs overlay the latest two weeks on saved history. After missing several releases, refresh history so four-week averages have complete windows. SMTP is optional; configure `.env` from `.env.example`, including `DOE_SUMMARY_EMAIL_FROM`, before using SMTP.
