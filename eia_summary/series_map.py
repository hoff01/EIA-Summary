from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .sulfur import REGIONS, sulfur_sources


REGION_ROWS = [
    ("I", "East Coast (PADD 1)"),
    ("II", "Midwest (PADD 2)"),
    ("III", "Gulf Coast (PADD 3)"),
    ("IV", "Rocky Mountain (PADD 4)"),
    ("V", "West Coast (PADD 5)"),
    ("TOT", "U.S."),
]

SUB_PADD1_ROWS = [
    ("A", "PADD 1 New England (A)"),
    ("B", "PADD 1 Central Atlantic (B)"),
    ("C", "PADD 1 Lower Atlantic (C)"),
]


@dataclass(frozen=True)
class SeriesDef:
    section: str
    card: str
    display_row: str
    source_column: str
    display_name: str
    unit: str
    scale: float
    fmt: str
    stock_flag: bool
    allowed_missing: bool
    direction: str
    sort_order: int


HEADER = [
    "section",
    "card",
    "display_row",
    "source_column",
    "display_name",
    "unit",
    "scale",
    "format",
    "stock_flag",
    "allowed_missing",
    "direction",
    "sort_order",
]


def read_series_lookup(series_path: Path) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    with series_path.open(newline="") as f:
        for row in csv.DictReader(f):
            if row.get("period_type") != "weekly":
                continue
            lookup.setdefault(row["series_name"], row)
    return lookup


def _add(rows: list[SeriesDef], lookup: dict[str, dict[str, str]], *, section: str, card: str,
         display_row: str, series_name: str, display_name: str, stock: bool, order: int,
         direction: str = "higher_green", allowed_missing: bool = False) -> None:
    row = lookup.get(series_name)
    if row is None:
        if not allowed_missing:
            rows.append(SeriesDef(section, card, display_row, "", display_name, "", 1.0, "number", stock, True, direction, order))
        return
    unit = row["unit"]
    if unit == "Thousand Barrels":
        scale, fmt = 1000.0, "mmb"
    elif unit == "Percent":
        scale, fmt = 1.0, "percent"
    else:
        scale, fmt = 1.0, "kbd"
    rows.append(SeriesDef(section, card, display_row, row["source_column"], display_name, unit, scale, fmt, stock, allowed_missing, direction, order))


def _add_calc(rows: list[SeriesDef], *, section: str, card: str, display_row: str, source_column: str,
              display_name: str, unit: str, fmt: str, stock: bool, order: int,
              direction: str = "higher_green") -> None:
    rows.append(SeriesDef(section, card, display_row, source_column, display_name, unit, 1.0, fmt, stock, False, direction, order))


def _region_series(section: str, card: str, lookup: dict[str, dict[str, str]], pattern: str,
                   display: str, stock: bool, direction: str, rows: list[SeriesDef], start: int) -> int:
    order = start
    for label, region in REGION_ROWS:
        _add(
            rows, lookup, section=section, card=card, display_row=label,
            series_name=f"weekly {region} {pattern}",
            display_name=f"{label} {display}", stock=stock, direction=direction, order=order,
            allowed_missing=label != "TOT" and card in {"Exports", "Demand"},
        )
        order += 1
    return order


def default_series_defs(series_path: Path) -> list[SeriesDef]:
    lookup = read_series_lookup(series_path)
    rows: list[SeriesDef] = []
    order = 1

    # Crude
    order = _region_series("CRUDE", "Stocks", lookup, "Ending Stocks excluding SPR of Crude Oil", "Stocks", True, "lower_green", rows, order)
    _add(rows, lookup, section="CRUDE", card="Stocks", display_row="CUSH", series_name="weekly Total Cushing, OK Ending Stocks excluding SPR of Crude Oil", display_name="CUSH Stocks", stock=True, direction="lower_green", order=order); order += 1
    _add(rows, lookup, section="CRUDE", card="Production", display_row="TOT", series_name="weekly U.S. Field Production of Crude Oil", display_name="TOT Production", stock=False, direction="higher_green", order=order); order += 1
    order = _region_series("CRUDE", "Crude Runs", lookup, "Refiner Net Input of Crude Oil", "Runs", False, "higher_green", rows, order)
    order = _region_series("CRUDE", "Gross Inputs", lookup, "Gross Inputs into Refineries", "Inputs", False, "higher_green", rows, order)
    order = _region_series("CRUDE", "Utilization", lookup, "Percent Utilization of Refinery Operable Capacity", "Utilization", False, "higher_green", rows, order)
    order = _region_series("CRUDE", "Imports", lookup, "Commercial Crude Oil Imports Excluding SPR", "Imports", False, "neutral", rows, order)
    order = _region_series("CRUDE", "Ethanol Inputs", lookup, "Refiner and Blender Net Input of Fuel Ethanol", "Ethanol Inputs", False, "neutral", rows, order)
    _add(rows, lookup, section="CRUDE", card="Exports", display_row="TOT", series_name="weekly U.S. Exports of Crude Oil", display_name="TOT Exports", stock=False, direction="neutral", order=order); order += 1

    product_specs = [
        ("GASOLINE", "Finished Motor Gasoline", "Finished Motor Gasoline"),
        ("DISTILLATES", "Distillate Fuel Oil", "Distillate Fuel Oil"),
        ("JET", "Kerosene-Type Jet Fuel", "Kerosene-Type Jet Fuel"),
        ("RFO", "Residual Fuel Oil", "Residual Fuel Oil"),
    ]
    for section, product, display_product in product_specs:
        stock_product = "Total Gasoline" if section == "GASOLINE" else product
        order = _region_series(section, "Stocks", lookup, f"Ending Stocks of {stock_product}", "Stocks", True, "lower_green", rows, order)
        if section in {"GASOLINE", "DISTILLATES", "RFO"}:
            for label, region in SUB_PADD1_ROWS:
                _add(rows, lookup, section=section, card="Stocks", display_row=label, series_name=f"weekly {region} Ending Stocks of {stock_product}", display_name=f"{label} Stocks", stock=True, direction="lower_green", order=order, allowed_missing=True)
                order += 1
        if section == "GASOLINE":
            for label, _region in REGION_ROWS:
                _add_calc(
                    rows, section=section, card="Production", display_row=label,
                    source_column=f"calc:gasoline_production:{label}",
                    display_name=f"{label} Production", unit="Thousand Barrels per Day",
                    fmt="kbd", stock=False, order=order,
                )
                order += 1
        else:
            order = _region_series(section, "Production", lookup, f"Refiner and Blender Net Production of {product}", "Production", False, "higher_green", rows, order)
        if section == "GASOLINE":
            for label, _region in REGION_ROWS:
                _add_calc(
                    rows, section=section, card="Imports", display_row=label,
                    source_column=f"calc:gasoline_imports:{label}",
                    display_name=f"{label} Imports", unit="Thousand Barrels per Day",
                    fmt="kbd", stock=False, order=order, direction="neutral",
                )
                order += 1
        else:
            order = _region_series(section, "Imports", lookup, f"Imports of {product}", "Imports", False, "neutral", rows, order)
        export_product = "Total Motor Gasoline" if section == "GASOLINE" else ("Total Distillate" if section == "DISTILLATES" else product)
        _add(rows, lookup, section=section, card="Exports/Demand", display_row="EXP", series_name=f"weekly U.S. Exports of {export_product}", display_name="Exports", stock=False, direction="neutral", order=order, allowed_missing=False); order += 1
        _add(rows, lookup, section=section, card="Exports/Demand", display_row="DEM", series_name=f"weekly U.S. Product Supplied of {product}", display_name="Demand", stock=False, direction="higher_green", order=order); order += 1
        for label, _region in REGION_ROWS:
            _add_calc(
                rows, section=section, card="Yield", display_row=label,
                source_column=f"calc:yield:{section}:{label}",
                display_name=f"{label} Yield", unit="Percent",
                fmt="percent", stock=False, order=order,
            )
            order += 1

    rows.extend(sulfur_series_defs(order))
    return [r for r in rows if r.source_column]


def sulfur_series_defs(start: int = 1000) -> list[SeriesDef]:
    rows = []
    for metric in ("stocks", "production"):
        for region, (_area, _stock, production) in REGIONS.items():
            if metric == "production" and production is None:
                continue
            for band in ("low", "high"):
                sources = sulfur_sources(metric, band, region)
                source = sources[0] if len(sources) == 1 else f"calc:sulfur:{metric}:{band}:{region}"
                stock = metric == "stocks"
                rows.append(SeriesDef(
                    "DISTILLATES", f"Sulfur {metric.title()}", f"{region}:{band}",
                    source, f"{region} {metric} {'0-15' if band == 'low' else '>15'} ppm",
                    "Thousand Barrels" if stock else "Thousand Barrels per Day",
                    1000.0 if stock else 1.0, "mmb" if stock else "kbd", stock,
                    False, "lower_green" if stock else "higher_green", start + len(rows),
                ))
    return rows


def write_series_map(path: Path, rows: list[SeriesDef]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "section": r.section, "card": r.card, "display_row": r.display_row,
                "source_column": r.source_column, "display_name": r.display_name,
                "unit": r.unit, "scale": r.scale, "format": r.fmt,
                "stock_flag": str(r.stock_flag).lower(),
                "allowed_missing": str(r.allowed_missing).lower(),
                "direction": r.direction, "sort_order": r.sort_order,
            })


def read_series_map(path: Path) -> list[SeriesDef]:
    rows: list[SeriesDef] = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            rows.append(SeriesDef(
                row["section"], row["card"], row["display_row"], row["source_column"],
                row["display_name"], row["unit"], float(row["scale"]), row["format"],
                row["stock_flag"].lower() == "true",
                row["allowed_missing"].lower() == "true",
                row["direction"], int(row["sort_order"]),
            ))
    return sorted(rows, key=lambda r: (r.section, r.card, r.sort_order))


def ensure_series_map(config_path: Path, series_path: Path) -> list[SeriesDef]:
    if not config_path.exists():
        rows = default_series_defs(series_path)
        write_series_map(config_path, rows)
    rows = read_series_map(config_path)
    keys = {(r.section, r.card, r.display_row) for r in rows}
    additions = [r for r in sulfur_series_defs() if (r.section, r.card, r.display_row) not in keys]
    if additions:
        rows.extend(additions)
        write_series_map(config_path, rows)
    return rows


def write_inventory(series_path: Path, output_path: Path) -> None:
    with series_path.open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("period_type") == "weekly"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["source_column", "series_name", "region", "subregion", "product", "metric", "unit", "period_type"]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        seen: set[str] = set()
        for row in rows:
            key = row["source_column"] + row["series_name"]
            if key in seen:
                continue
            seen.add(key)
            writer.writerow({k: row.get(k, "") for k in fieldnames})
