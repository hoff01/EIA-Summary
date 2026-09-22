# Plan: Self-Contained EIA Weekly Summary Dashboard PDFs

## Goal

Build a standalone dashboard generator under `eia_summary_dashboard/` that reads the weekly long-form data from the local `raw.csv.tar.xz`, recreates the visual structure of the local `reference/dashboard.pdf`, adds 4-week-average week-over-week and ISO-week year-over-year comparisons for every non-stock metric, and writes one archived PDF per report week.

Final weekly PDFs must be named:

```text
archive/EIA_SUMMARY_YYYY-MM-DD.pdf
```

Example:

```text
archive/EIA_SUMMARY_2026-05-08.pdf
```

The generator must run on its own from this folder without importing the existing `src/` pipeline and without requiring files from `../eia_weekly/` during normal operation. It may copy small mapping/config ideas from the existing weekly work, but the dashboard runner must be self-contained.

## Current Inputs

Source files inside this folder:

```text
raw.csv.tar.xz
series.csv
reference/dashboard.pdf
```

The parent project files are only a refresh source, not a runtime dependency:

```text
../eia_weekly/raw.csv.tar.xz
../eia_weekly/series.csv
../eia_weekly/dashboard.pdf
```

`raw.csv.tar.xz` contains one `raw.csv` with this schema:

```text
week_ending
release_date
source_table
source_sheet
section
metric
product
region
subregion
unit
period_type
value
source_column
source_row_index
```

The reference dashboard PDF is image-only, one page, with a page box of `2821 x 2629`. Because the PDF has no extractable table text, exact recreation must be done from a layout template plus rendered visual comparison, not PDF text extraction.

Current local asset baseline:

```text
raw.csv.tar.xz: 2,979,872 bytes, sha256 5ac6fa42fe458918ccaa14dd216973b2398fc1d8129c17529e42697ce2084dee
series.csv: 366,175 bytes, sha256 8953185b57633b2541924812d42a8a649858329b0f3408463e75ecd721b18224
reference/dashboard.pdf: 1,949,749 bytes, sha256 5ea7347ed159f7b58bf757f05797538206475b04b78fbe45a26c7a4e916b54d7
```

## Folder Layout

Create this structure:

```text
eia_summary_dashboard/
  plan.md
  README.md
  requirements.txt
  raw.csv.tar.xz
  series.csv
  build.py
  config/
    dashboard.yml
    series_map.csv
    style.yml
    quality.yml
  eia_summary/
    __init__.py
    archive_io.py
    data_load.py
    metrics.py
    series_lookup.py
    layout.py
    render_pdf.py
    validate.py
  reference/
    dashboard.pdf
    dashboard.png
  output/
    latest.pdf
  archive/
    EIA_SUMMARY_YYYY-MM-DD.pdf
```

Self-contained means:

- `build.py` is the only command needed.
- The code can run from inside `eia_summary_dashboard/`.
- It must not import files from `../src`.
- It must not modify `../eia_weekly/`, `../src/`, or any other parent-project file.
- It reads `./raw.csv.tar.xz` by default.
- It reads `./series.csv` by default for lookup/mapping assistance.
- It reads `./reference/dashboard.pdf` by default for layout reference and visual validation.
- It should support `--raw-archive path/to/raw.csv.tar.xz`, but that option is for explicit overrides only.
- It should support `--refresh-from-weekly ../eia_weekly` to copy in a newer raw archive, series lookup, and reference PDF when the upstream weekly pipeline is rebuilt.
- After refresh, it should keep using local copies.

## Self-Contained Data Policy

The folder must be portable. If `eia_summary_dashboard/` is copied to another machine, these files are enough to build dashboards without the parent project:

```text
raw.csv.tar.xz
series.csv
reference/dashboard.pdf
build.py
config/
eia_summary/
requirements.txt
```

No generated PDF should depend on `../eia_weekly/` existing. Parent paths are allowed only for one explicit refresh command, and that command is read-only with respect to the parent folder:

```text
python3 build.py --refresh-from-weekly ../eia_weekly
```

Refresh behavior:

1. Copy `../eia_weekly/raw.csv.tar.xz` to `./raw.csv.tar.xz`.
2. Copy `../eia_weekly/series.csv` to `./series.csv`.
3. Copy `../eia_weekly/dashboard.pdf` to `./reference/dashboard.pdf`.
4. Compute and record SHA256 hashes for all three local copies.
5. Do not rebuild dashboard PDFs unless the user also passes `--week`, `--all-weeks`, or runs the default build after refresh.

Manual update behavior:

- The user can update the dashboard by replacing files inside `eia_summary_dashboard/` directly:
  - `raw.csv.tar.xz`
  - `series.csv`
  - `reference/dashboard.pdf`
  - files under `config/`
- After local replacement, `python3 build.py --validate` must use those local files.
- No code should silently go back to `../eia_weekly/` if a local file is missing. Missing local files should produce a clear error with the exact file path.

## Write Boundary

All generated files must stay under `eia_summary_dashboard/`:

```text
archive/
output/
reference/dashboard.png
output/series_inventory.csv, if requested
local_manifest.json
```

The implementation must resolve every output path against the dashboard folder root and reject writes that escape it. This protects the existing weekly pipeline and makes the dashboard code safe to work on independently.

Forbidden writes:

```text
../eia_weekly/*
../src/*
../eia_monthly/*
../plan.md
../plan.me
```

Forbidden imports:

```text
../src/*
```

Allowed parent reads:

- None during default `python3 build.py`.
- Only `--refresh-from-weekly ../eia_weekly`, which copies from the parent weekly folder into local dashboard files and never writes back to the parent.

## Command Contract

Primary command:

```text
python3 build.py
```

Useful options:

```text
python3 build.py --week latest
python3 build.py --week 2026-05-08
python3 build.py --all-weeks
python3 build.py --raw-archive raw.csv.tar.xz
python3 build.py --reference-pdf reference/dashboard.pdf
python3 build.py --refresh-from-weekly ../eia_weekly
python3 build.py --validate
```

Default behavior:

- Read `./raw.csv.tar.xz`.
- Read `./series.csv`.
- Read `./reference/dashboard.pdf`.
- Build only the latest available `week_ending`.
- Write `archive/EIA_SUMMARY_YYYY-MM-DD.pdf`.
- Copy the same file to `output/latest.pdf`.
- Print the output path, week ending date, release date, row count, series count, and runtime.

## Dependencies

Keep dependencies small and cross-platform:

```text
reportlab
pypdf
pymupdf
```

Roles:

- `reportlab`: deterministic PDF generation.
- `pypdf`: page-count and page-size validation.
- `pymupdf`: cross-platform PDF-to-PNG rendering for visual QA on Windows and macOS.

Do not add pandas, numpy, browser tooling, or a web server to the default path. The data volume and transformations are small enough for streaming CSV plus dictionaries.

## Data Loading

Implement `data_load.py` to stream the compressed archive directly:

1. Open `raw.csv.tar.xz` with Python `tarfile` in XZ mode.
2. Require exactly one member named `raw.csv`.
3. Stream rows with `csv.DictReader`.
4. Keep only `period_type == "weekly"`.
5. Parse `week_ending` as an ISO-8601 calendar date.
6. Parse `value` as float, preserving missing values as `None`.
7. Index by `(source_column, week_ending)`.

Do not extract a persistent full CSV. Temporary files are allowed only when needed for validation and must be deleted before completion.

## Series Mapping

Use stable `source_column` IDs for data selection. Do not select by display name, because EIA display names can change.

`config/series_map.csv` should be the dashboard contract:

```text
section,card,display_row,source_column,display_name,unit,scale,format,stock_flag,allowed_missing,direction,sort_order
```

Rules:

- `source_column` is required and unique within each card row.
- `display_name` is only for labels and validation.
- `stock_flag=true` for ending stocks only.
- If EIA names change, the lookup still works because the pull is by `source_column`.
- If a `source_column` is missing from the raw archive, render the row as blank and report it in validation output.

Generate a helper inventory file when requested:

```text
python3 build.py --write-series-inventory
```

Output:

```text
output/series_inventory.csv
```

Inventory columns:

```text
source_column,series_name,region,subregion,product,metric,unit,first_week,last_week,row_count
```

Mapping workflow:

1. Generate `output/series_inventory.csv` from the local `raw.csv.tar.xz`.
2. Build `config/series_map.csv` from `source_column` IDs in that inventory.
3. Keep `display_name` in `series_map.csv` as the human-readable label used in the PDF.
4. Keep any obsolete or intentionally skipped source columns out of `series_map.csv`; do not delete them from `raw.csv.tar.xz`.
5. Add an `allowed_missing` column only when a row is deliberately optional. Missing required series must fail validation.

`direction` values remain in `series_map.csv` for future styling, but current dashboard change styling must be sign-based:

```text
higher_green
lower_green
neutral
```

Change styling rule:

- Positive change: green text.
- Negative change: red text.
- Zero, missing, or flat change: yellow text.
- Do not invert colors for stocks, imports, or any other metric.

## Dashboard Sections

Recreate the current visual hierarchy from `dashboard.pdf`:

```text
DOE WEEKLY SUMMARY
Top ticker row: C, G, D, J, FO

CRUDE
  Stocks
  Production
  Crude Runs
  Exports
  Refinery Gross Inputs
  Utilization
  Imports
  Ethanol Inputs

GASOLINE
  Stocks
  Production
  Imports
  Exports/Demand
  Yield

DISTILLATES
  Stocks
  Production
  Imports
  Exports/Demand
  Yield

JET
  Stocks
  Production
  Imports
  Exports/Demand
  Yield

RFO / residual-fuel section if present in the mapped source columns
```

Calculated dashboard series:

- Product `Yield` rows are calculated historically as `Production / Crude Runs * 100` for PADD I-V and `TOT`, except gasoline.
- Gasoline `Yield` rows are calculated historically as `(Gasoline Production - Ethanol Inputs) / Crude Runs * 100`.
- Yield is displayed as a percent with one decimal place; WoW, YoY, 4-week WoW, and 4-week YoY are percentage-point differences.
- Gasoline production is calculated historically as `Refiner Net Production of Finished Motor Gasoline + Blender Net Production of Finished Motor Gasoline - Refiner and Blender Net Input of Gasoline Blending Components`.
- Gasoline imports are calculated historically as `Imports of Finished Motor Gasoline + Imports of Gasoline Blending Components`.
- `Exports/Demand` cards use the compact reference layout with separate `Exports` and `Demand` mini sections, each showing `Current`, `Last Yr`, `W/W`, `Y/Y`, `4W Avg`, `4W W/W`, and `4W Y/Y` for `TOT`.
- Only gasoline uses the adjusted production formula; other product production rows use the mapped EIA source columns directly.

Rows must follow the reference dashboard order:

```text
I
II
III
IV
V
TOT
```

Where the dashboard has PADD 1 subrows, use:

```text
A
B
C
```

and keep them directly under PADD I.

## Metrics

For every mapped row and report week:

```text
current = value at week
last_yr = value at matching ISO week in the prior ISO year
wow = current - previous_week
yoy = current - last_yr
avg_4wk = mean(current week and prior 3 available weekly observations)
avg_4wk_wow = avg_4wk(current week) - avg_4wk(previous week)
avg_4wk_yoy = avg_4wk(current ISO week) - avg_4wk(matching ISO week in the prior ISO year)
```

Date matching:

- Use `week_ending - 7 days` for previous week.
- Use ISO calendar matching for prior-year comparisons:
  - Compute `iso_year`, `iso_week`, and `iso_weekday` from `week_ending`.
  - Target the same `iso_week` and `iso_weekday` in `iso_year - 1`.
  - Example: a Friday in ISO week 19 of 2026 compares to Friday of ISO week 19 of 2025.
  - If the prior ISO year does not contain that week, use the last ISO week available in that prior year and flag the fallback in validation.
- If the exact ISO target date is missing from the series, allow the nearest available weekly date within `+/- 3 days`.
- If no acceptable date exists, leave the comparison blank and flag it in validation.

Implementation detail for ISO-week matching:

```text
iso = week_ending.isocalendar()
target_iso_year = iso.year - 1
target_iso_week = iso.week
target_iso_weekday = iso.weekday
target_date = date.fromisocalendar(target_iso_year, target_iso_week, target_iso_weekday)
```

If `date.fromisocalendar()` fails because the prior ISO year does not have that ISO week, retry with the maximum valid ISO week for `target_iso_year`.

4-week ISO YoY matching:

- Compute each 4-week average as the selected week plus the prior three weekly observations for that same source column.
- For `avg_4wk_yoy`, anchor the prior-year 4-week average on the ISO-week matched prior-year date.
- Do not compare against a simple `-364 days` offset unless that date is also the ISO-week matched target.
- Require four observations for a full 4-week average. If fewer than four are available, render blank and flag it unless the row is explicitly allowed to start later.

Stock exception:

- For `stock_flag=true`, do not render `avg_4wk`, `avg_4wk_wow`, or `avg_4wk_yoy`.
- Stocks should keep `current`, `last_yr`, `wow`, and `yoy`.

Units and formatting:

- Barrels-per-day flow series: display in `KBD`.
- Stock series: display in `MMB`.
- Percent/yield/utilization series: display as `%`.
- Percent changes are percentage-point differences, not percent changes.
- Negative values render in parentheses.
- Positive changes render as green text, negative changes render as red text, and flat changes render as yellow text.

## Added 4-Week Average Columns

The new non-stock card layout should be:

```text
row | current | last yr | wow | yoy | 4wk avg | 4wk wow | 4wk yoy
```

The stock card layout should remain:

```text
row | current | last yr | wow | yoy
```

If the extra columns make a card too dense, reduce font size within the same card width before changing the grid. The target is to preserve the reference dashboard's dark table-card look while adding the new data.

Column density rules:

- Keep row labels fixed-width and right aligned for PADD numerals.
- Keep numeric values right aligned.
- Do not draw arrow icons; change values carry the signal through text color.
- Use green text for positive changes, red text for negative changes, and yellow text for flat changes.
- Use compact labels:
  - `CUR`
  - `LY`
  - `ΔWOW`
  - `ΔYOY`
  - `4W`
  - `4W ΔWOW`
  - `4W ΔYOY`
- If the card cannot fit the full non-stock layout at the minimum font size, split the metric into two stacked subrows:
  - row A: `CUR`, `LY`, `ΔWOW`, `ΔYOY`
  - row B: `4W Avg`, `4W ΔWOW`, `4W ΔYOY`
- Do not shrink below the minimum font sizes in `config/quality.yml`.

## Professional Output Standard

The generated PDF should be a clean professional recreation, not a low-fidelity screenshot clone. It should preserve the reference dashboard's dense dark trading-screen feel while making the generated text crisper and more readable than the photo-like reference image.

Visual direction:

- Dark background with subtle panel contrast.
- Thin, consistent gridlines.
- Clear white text with blue unit labels.
- Product section bars with distinct colors:
  - Crude: white/gray
  - Gasoline: green
  - Distillates: cyan/blue
  - Jet: amber/orange
  - RFO/residual fuel: purple
- Compact cards with no rounded corners beyond 4 px equivalent.
- No decorative gradients, shadows, or ornamental shapes.
- No emoji.
- Numbers must line up by decimal point where possible.
- Parentheses must be used for negative values.

Typography:

- Use built-in Helvetica/Helvetica-Bold unless a local TTF is added under `fonts/`.
- Header: bold, centered, high contrast.
- Section labels: uppercase, bold, left aligned.
- Card titles: uppercase, bold, compact.
- Column headers: uppercase, small, readable.
- Row labels and values: tabular-looking alignment using consistent widths.
- Use the Greek delta symbol (`Δ`) on all week-over-week and year-over-year change headers, including 4-week change headers.

Minimum quality gates:

```text
header_font_size >= 34
section_font_size >= 18
card_title_font_size >= 14
column_header_font_size >= 9
body_font_size >= 9
min_cell_padding_x >= 4
min_cell_padding_y >= 2
min_gridline_width >= 0.5
```

If the rendered output fails any minimum, adjust the layout instead of accepting cramped text.

## Config Files

`config/style.yml` should hold colors and typography:

```text
page:
  background: "#0b0c0d"
  text: "#f4f4f1"
  muted_text: "#b8bbb8"
  gridline: "#595b55"
  panel_fill: "#20211f"
  panel_border: "#74766f"
units:
  blue: "#76baff"
direction:
  up: "#7ee0aa"
  down: "#ff6a22"
  flat: "#f0c84b"
sections:
  crude: "#d8d8d0"
  gasoline: "#23b64b"
  distillates: "#34b9e6"
  jet: "#f2a11b"
  pfo: "#8b44d8"
```

`config/quality.yml` should hold render gates:

```text
page_width: 2821
page_height: 2629
minimum_font_sizes:
  header: 34
  section: 18
  card_title: 14
  column_header: 9
  body: 9
maximum_allowed_overlap_count: 0
maximum_missing_required_series: 0
render_png_required: true
```

`config/dashboard.yml` should hold only layout coordinates and card wiring. Do not hardcode coordinates in `render_pdf.py` except for defaults used in tests.

## PDF Rendering

Use ReportLab canvas for deterministic, absolute-position PDF drawing:

- Page size: `2821 x 2629`.
- Background: near-black.
- Header: centered `DOE WEEKLY SUMMARY`.
- Centered week-ending label below the main header.
- Section bars: colored horizontal dividers matching the reference.
- Cards: dark rectangular panels, compact title rows, thin gridlines, white labels, blue unit labels.
- Direction indicators: change values are color-coded text, not arrows or emoji.

Rendering code should live in `render_pdf.py`.

Use a layout template in `config/dashboard.yml`:

```text
page:
  width: 2821
  height: 2629
cards:
  - id: crude_stocks
    section: CRUDE
    x: 24
    y: 2050
    w: 540
    h: 390
```

Keep all coordinates in config so the visual can be tuned without rewriting Python code.

## Visual Matching

Because `dashboard.pdf` is image-only, validation needs rendered image comparison:

1. Render `reference/dashboard.pdf` to `reference/dashboard.png`.
2. Render generated PDF to `output/latest.png`.
3. Compare dimensions.
4. Run a perceptual or pixel-level diff after masking data-value cells, because values will change by week.
5. Validate fixed layout regions:
   - header position
   - top ticker boxes
   - section bars
   - card frames
   - card title positions
   - column alignment

Preferred cross-platform rendering:

```text
python3 -c "import pymupdf; doc=pymupdf.open('output/latest.pdf'); doc[0].get_pixmap(dpi=72).save('output/latest.png')"
```

macOS fallback rendering:

```text
sips -s format png input.pdf --out output.png
```

Optional if installed:

```text
pdftoppm -png input.pdf output_prefix
```

Implementation rule:

- `validate.py` should use PyMuPDF first because it works on Windows and macOS.
- `sips` and `pdftoppm` are only fallback/manual tools.
- If PyMuPDF is unavailable, validation should print the missing dependency and fail the visual QA gate rather than silently skipping it.

The visual validator should fail on:

- missing pages
- wrong page size
- clipped title/header
- overlapping text
- missing card frame
- missing section bar
- unreadable text below minimum configured font size

Professional visual QA procedure:

1. Render the reference PDF to `reference/dashboard.png`.
2. Render the generated PDF to `output/latest.png`.
3. Confirm both PNG files are the same pixel dimensions.
4. Run structural checks from `config/dashboard.yml`:
   - every card rectangle exists
   - every card has a title
   - every section bar spans the intended card group
   - top ticker labels are centered
   - all numeric cells are inside card bounds
   - no text bounding boxes overlap
5. Run a masked visual diff:
   - mask value cells and dates because data changes by week
   - compare fixed layout regions only
   - fail if the fixed-region difference exceeds the threshold in `quality.yml`
6. Open or inspect `output/latest.png` before accepting the final layout.

The reference render has already been created locally at:

```text
reference/dashboard.png
```

Use it as the visual baseline while tuning the layout.

## Archive Rules

Every generated week is immutable once written:

```text
archive/EIA_SUMMARY_YYYY-MM-DD.pdf
```

If the file already exists:

- Default: overwrite only when the source archive hash changed.
- `--force`: always overwrite.
- Always update `output/latest.pdf` for the latest generated week.

Write a manifest:

```text
archive/manifest.csv
```

Columns:

```text
week_ending,release_date,output_pdf,raw_archive_sha256,series_count,generated_at_utc,bytes
```

## Validation

Implement `validate.py` checks:

- `raw.csv.tar.xz` exists and contains `raw.csv`.
- Default inputs resolve inside `eia_summary_dashboard/`.
- All output paths resolve inside `eia_summary_dashboard/`.
- Required columns exist.
- At least one weekly row exists.
- The selected week exists.
- Every mapped `source_column` is present or explicitly allowed missing.
- Every non-stock mapped row has enough history for previous-week, ISO-week prior-year, and 4-week calculations.
- Stock cards do not include 4-week-average columns.
- Output PDF exists and has one page.
- Output PDF page size is `2821 x 2629`.
- Manifest row exists for the generated week.
- `reference/dashboard.png` exists or can be generated from `reference/dashboard.pdf`.
- `output/latest.png` exists after validation when PNG rendering is available.
- No text bounding boxes overlap.
- Every rendered table cell stays within its card rectangle.
- No body text uses a font smaller than `quality.yml` minimums.
- The default run leaves `../eia_weekly/` file sizes and hashes unchanged.

Validation should print missing series grouped by section and card.

Recommended validation output:

```text
validated_week=YYYY-MM-DD
raw_archive_sha256=...
mapped_series=N
missing_required_series=0
missing_optional_series=N
cards_rendered=N
overlap_count=0
min_body_font_size=...
reference_png=reference/dashboard.png
latest_png=output/latest.png
pdf=archive/EIA_SUMMARY_YYYY-MM-DD.pdf
elapsed_ms=...
```

## Performance Requirements

This should stay fast on Windows and macOS:

- Latest-week build target: under 5 seconds after Python startup.
- All-weeks archive build: stream data once, then render week-by-week.
- Avoid pandas for the default path unless benchmarks prove it is faster for this archive.
- Use standard `csv`, `tarfile`, and dictionaries for the hot path.
- Load only needed mapped source columns unless `--write-series-inventory` is requested.
- Do not materialize the full raw CSV to disk.
- Do not create IndexedDB, browser cache, or long-lived local cache files.

Memory target:

- Latest-week generation should stay under 250 MB peak RSS.
- All-weeks generation should avoid holding duplicate string-heavy row copies.

## Implementation Steps

1. Create the package skeleton and keep all files inside `eia_summary_dashboard/`.
2. Write `requirements.txt` with only required packages: `reportlab`, `pypdf`, and `pymupdf`.
3. Build `data_load.py` to stream `raw.csv.tar.xz` and index only mapped `source_column` values.
4. Build `series_lookup.py` to generate `output/series_inventory.csv` from raw when requested.
5. Create `config/series_map.csv` from visible dashboard sections and available EIA source columns.
6. Create `config/style.yml`, `config/quality.yml`, and `config/dashboard.yml`.
7. Implement `metrics.py` with current, last-year, WoW, YoY, 4-week average, 4-week WoW, and ISO-week 4-week YoY calculations.
8. Implement ReportLab drawing primitives in `render_pdf.py`: page, centered header, section bars, cards, tables, color-coded change values, and week-ending label.
9. Implement text measurement and bounding-box tracking so validation can detect clipping and overlap.
10. Add archive writing and manifest updates in `archive_io.py`.
11. Add validation checks in `validate.py`, including local path boundaries and PNG render checks.
12. Render the latest week and inspect `output/latest.png` against `reference/dashboard.png`.
13. Tune `config/dashboard.yml` until fixed layout regions match the reference and every card remains readable.
14. Run `python3 build.py --week latest --validate`.
15. Run `python3 build.py --all-weeks --validate` to create one `EIA_SUMMARY_YYYY-MM-DD.pdf` per week.
16. Run a boundary test that proves default runs do not read from or write to `../eia_weekly/`.
17. Document the final command and output paths in `README.md`.

## Verification Commands

Run these from `eia_summary_dashboard/`:

```text
python3 build.py --write-series-inventory
python3 build.py --week latest --validate
python3 build.py --all-weeks --validate
```

Optional visual render commands:

```text
python3 -c "import pymupdf; doc=pymupdf.open('reference/dashboard.pdf'); doc[0].get_pixmap(dpi=72).save('reference/dashboard.png')"
python3 -c "import pymupdf; doc=pymupdf.open('output/latest.pdf'); doc[0].get_pixmap(dpi=72).save('output/latest.png')"
sips -s format png reference/dashboard.pdf --out reference/dashboard.png
sips -s format png output/latest.pdf --out output/latest.png
```

Boundary verification from the parent project:

```text
python3 -c "import hashlib,pathlib; [print(p, pathlib.Path(p).stat().st_size, hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()) for p in ['eia_weekly/raw.csv.tar.xz','eia_weekly/series.csv','eia_weekly/dashboard.pdf']]"
```

The before and after hashes for those three parent files must match.

## Acceptance Criteria

The work is complete when:

- `python3 build.py --week latest --validate` succeeds.
- `output/latest.pdf` exists.
- `archive/EIA_SUMMARY_YYYY-MM-DD.pdf` exists for the latest week.
- `python3 build.py --all-weeks --validate` creates a PDF for every available week.
- The generated page size matches `dashboard.pdf`.
- The visual structure matches the reference dashboard: header, top ticker row, product sections, cards, card titles, gridlines, rows, units, and color-coded change values.
- Non-stock cards include 4-week average, 4-week WoW, and 4-week YoY.
- Stock cards exclude 4-week-average columns.
- Data selection is by `source_column`, not by mutable EIA names.
- The folder can be moved and run independently with its local `raw.csv.tar.xz`, `series.csv`, and `reference/dashboard.pdf`.
- Running the dashboard generator does not modify any file in `../eia_weekly/`.
- `output/latest.png` has been inspected and has no clipped text, overlapping table values, missing cards, or broken section bars.
- Validation reports `overlap_count=0`.
- Validation reports no font size below the configured minimums.
- The archived PDF and `output/latest.pdf` have identical bytes for the latest week.
