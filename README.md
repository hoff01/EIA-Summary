# EIA Summary

Builds the one-page DOE/EIA weekly PDF dashboard and optionally sends it through classic desktop Outlook. The independent stats image puller is at https://github.com/hoff01/EIA-Stats-Puller.

## Windows Setup

Install Python 3.11 or later and classic desktop Outlook. Extract anywhere, for example `%USERPROFILE%\Documents\EIA-Summary`. All scripts resolve paths relative to this folder. Create a fresh environment on each computer instead of copying `.venv`.

Run once from PowerShell in this folder:

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

**Release morning:** double-click `RUN_EIA_SUMMARY_DASHBOARD.bat`. Start early. It reads the official EIA schedule in New York/Eastern time, usually 10:30 a.m., handles holiday exceptions, and checks every five seconds for up to two minutes after release. Unchanged polls do not render PDFs. Downloaded weekly tables must agree on the release week, and missing required values stop the build. The PDF is built and sent once the expected week is ready.

Outlook opens automatically when needed. It gets a 12-second startup pause, then up to 60 seconds of readiness checks. Sign in and clear profile/security prompts beforehand. Optional overrides in `.env`: `DOE_SUMMARY_OUTLOOK_STARTUP_WAIT_SECONDS`, `DOE_SUMMARY_OUTLOOK_READY_TIMEOUT_SECONDS`, and `DOE_SUMMARY_OUTLOOK_ACCOUNT`.

**Task Scheduler:** run `scripts\install_windows_task.bat`. The configured 10:28 a.m. Eastern start is converted to the computer's local time when installed. Reinstall after moving the project or changing the computer's time zone.

**Intentional live email test:** `scripts\send_test_email.bat` sends to your local recipient list. It is not a dry run. Duplicate weekly sends are suppressed using local receipts in `logs/`; keep these when moving an existing installation to preserve that protection.

## Report Data

- Two sulfur panels share one blue outline beside Ethanol Inputs: stocks and refiner-plus-blender net production. Each shows 0-15 ppm and >15 ppm, Current, ΔWOW and ΔYOY. Production also shows 4W Avg and 4W ΔYOY (the four-week average minus the comparable prior-year four-week average). Last year's level is omitted in these panels.
- Stocks use the same units, one-decimal number formatting, delta headers and indented A/B/C labels as the main distillate stocks panel. They include PADDs I-V, PADD 1A/1B/1C and the U.S. total in million barrels. Production is in thousand barrels/day at PADD and U.S. level, shown as whole numbers like the other production tables. A narrow gap separates the stock and production sections inside one continuous blue border. EIA does not publish corresponding weekly sub-PADD production.
- Above 15 ppm is the sum of EIA's >15-500 ppm and >500 ppm series. It is calculated for each historical week before calculating changes. Missing components remain missing; negative net production is retained.
- EIA rounds regional/component series independently, so sums may differ slightly from headline totals.
- Distillate exports retain the weekly headline. EIA publishes no weekly sulfur export split, so no sulfur export rows are shown. This report includes weekly data only.
- Y/Y uses the comparable ISO week in the prior year. Standard flow cards retain four-week averages. The faint italic creator credit remains at bottom right.

Sources: [EIA WPSR](https://www.eia.gov/petroleum/supply/weekly/) and [weekly U.S. and PADD estimates](https://www.eia.gov/dnav/pet/pet_sum_sndw_dcus_nus_w.htm). Sulfur series and formulas are in `eia_summary/sulfur.py`.

## Outputs and Maintenance

Latest PDF/PNG: `output/latest.pdf` and `output/latest.png`. Dated PDFs: `archive/EIA_SUMMARY_YYYY-MM-DD.pdf`, indexed in `archive/manifest.csv`. Included source data supports offline previews; check the report's week before using it.

```powershell
# Fast offline rebuild, no email and no network:
.\.venv\Scripts\python.exe build.py --week latest --skip-email

# Refresh history after a long gap between runs:
.\.venv\Scripts\python.exe build.py --refresh-eia-weekly --force --skip-email

# Tests, with no email:
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Normal release runs overlay the latest two weeks on saved history. After missing several releases, refresh history so four-week averages have complete windows. SMTP is optional; configure `.env` from `.env.example`, including `DOE_SUMMARY_EMAIL_FROM`, before using SMTP.
