from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .data_load import RawDataset
from .series_map import SeriesDef
from .sulfur import sulfur_sources

GASOLINE_PRODUCTION_SOURCES = {
    "I": ("WGFRPP12", "WBCRI_R10_2"),
    "II": ("WGFRPP22", "WBCRI_R20_2"),
    "III": ("WGFRPP32", "WBCRI_R30_2"),
    "IV": ("WGFRPP42", "WBCRI_R40_2"),
    "V": ("WGFRPP52", "WBCRI_R50_2"),
    "TOT": ("W_EPM0F_YPR_NUS_MBBLD", "WBCRI_NUS_2"),
}

ETHANOL_INPUT_SOURCES = {
    "I": "W_EPOOXE_YIR_R10_MBBLD",
    "II": "W_EPOOXE_YIR_R20_MBBLD",
    "III": "W_EPOOXE_YIR_R30_MBBLD",
    "IV": "W_EPOOXE_YIR_R40_MBBLD",
    "V": "W_EPOOXE_YIR_R50_MBBLD",
    "TOT": "W_EPOOXE_YIR_NUS_MBBLD",
}

GASOLINE_IMPORT_SOURCES = {
    "I": ("W_EPM0F_IM0_R10-Z00_MBBLD", "WBCIM_R10-Z00_2"),
    "II": ("W_EPM0F_IM0_R20-Z00_MBBLD", "WBCIM_R20-Z00_2"),
    "III": ("W_EPM0F_IM0_R30-Z00_MBBLD", "WBCIM_R30-Z00_2"),
    "IV": ("W_EPM0F_IM0_R40-Z00_MBBLD", "WBCIM_R40-Z00_2"),
    "V": ("W_EPM0F_IM0_R50-Z00_MBBLD", "WBCIM_R50-Z00_2"),
    "TOT": ("W_EPM0F_IM0_NUS-Z00_MBBLD", "WBCIMUS2"),
}


@dataclass(frozen=True)
class MetricRow:
    definition: SeriesDef
    current: float | None
    last_year: float | None
    wow: float | None
    yoy: float | None
    avg4: float | None
    avg4_wow: float | None
    avg4_yoy: float | None


def _nearest(series: dict[date, float], target: date, tolerance_days: int = 3) -> tuple[date, float] | None:
    if target in series:
        return target, series[target]
    for delta in range(1, tolerance_days + 1):
        for candidate in (target - timedelta(days=delta), target + timedelta(days=delta)):
            if candidate in series:
                return candidate, series[candidate]
    return None


def _max_iso_week(year: int) -> int:
    return date(year, 12, 28).isocalendar().week


def iso_prior_year_day(day: date) -> date:
    iso = day.isocalendar()
    week = min(iso.week, _max_iso_week(iso.year - 1))
    return date.fromisocalendar(iso.year - 1, week, iso.weekday)


def _avg4(series: dict[date, float], anchor: date) -> float | None:
    values = []
    for i in range(4):
        match = _nearest(series, anchor - timedelta(days=7 * i))
        if match is None:
            return None
        values.append(match[1])
    return sum(values) / 4.0


def _combine_series(
    values: dict[str, dict[date, float]],
    source_columns: tuple[str, ...],
    calc,
) -> dict[date, float]:
    source_series = [values.get(source, {}) for source in source_columns]
    weeks = set.intersection(*(set(series) for series in source_series)) if source_series else set()
    out: dict[date, float] = {}
    for week in weeks:
        try:
            out[week] = calc(*(series[week] for series in source_series))
        except ZeroDivisionError:
            continue
    return out


def _gasoline_production_source(row: str) -> str:
    return f"calc:gasoline_production:{row}"


def _gasoline_import_source(row: str) -> str:
    return f"calc:gasoline_imports:{row}"


def _yield_source(section: str, row: str) -> str:
    return f"calc:yield:{section}:{row}"


def _raw_dependencies(source_column: str, definitions: dict[tuple[str, str, str], SeriesDef]) -> set[str]:
    if not source_column.startswith("calc:"):
        return {source_column}
    parts = source_column.split(":")
    if parts[:2] == ["calc", "sulfur"]:
        return set(sulfur_sources(*parts[2:]))
    if parts[:2] == ["calc", "gasoline_production"]:
        return set(GASOLINE_PRODUCTION_SOURCES[parts[2]])
    if parts[:2] == ["calc", "gasoline_imports"]:
        return set(GASOLINE_IMPORT_SOURCES[parts[2]])
    if parts[:2] == ["calc", "yield"]:
        section, row = parts[2], parts[3]
        deps: set[str] = set()
        production = definitions.get((section, "Production", row))
        crude_runs = definitions.get(("CRUDE", "Crude Runs", row))
        gross_inputs = definitions.get(("CRUDE", "Gross Inputs", row))
        ethanol_inputs = definitions.get(("CRUDE", "Ethanol Inputs", row))
        if production:
            deps.update(_raw_dependencies(production.source_column, definitions))
        if section == "GASOLINE":
            if gross_inputs:
                deps.update(_raw_dependencies(gross_inputs.source_column, definitions))
            if ethanol_inputs:
                deps.update(_raw_dependencies(ethanol_inputs.source_column, definitions))
        elif crude_runs:
            deps.update(_raw_dependencies(crude_runs.source_column, definitions))
        return deps
    return set()


def dependency_source_columns(definitions: list[SeriesDef]) -> list[str]:
    definitions_by_key = {(d.section, d.card, d.display_row): d for d in definitions}
    selected: set[str] = set()
    for definition in definitions:
        selected.update(_raw_dependencies(definition.source_column, definitions_by_key))
    return sorted(source for source in selected if source)


def _with_calculated_series(dataset: RawDataset, definitions: list[SeriesDef]) -> RawDataset:
    values = {source: dict(series) for source, series in dataset.values.items()}
    definitions_by_key = {(d.section, d.card, d.display_row): d for d in definitions}

    for row, sources in GASOLINE_PRODUCTION_SOURCES.items():
        values[_gasoline_production_source(row)] = _combine_series(
            values,
            sources,
            lambda production, blending_component_inputs: production - blending_component_inputs,
        )

    for row, sources in GASOLINE_IMPORT_SOURCES.items():
        values[_gasoline_import_source(row)] = _combine_series(
            values,
            sources,
            lambda finished_gasoline, blending_components: finished_gasoline + blending_components,
        )

    for definition in definitions:
        if definition.source_column.startswith("calc:sulfur:"):
            sources = sulfur_sources(*definition.source_column.split(":")[2:])
            values[definition.source_column] = _combine_series(values, sources, lambda *parts: sum(parts))
        if not definition.source_column.startswith("calc:yield:"):
            continue
        _calc, _kind, section, row = definition.source_column.split(":")
        production = definitions_by_key.get((section, "Production", row))
        crude_runs = definitions_by_key.get(("CRUDE", "Crude Runs", row))
        gross_inputs = definitions_by_key.get(("CRUDE", "Gross Inputs", row))
        ethanol_inputs = definitions_by_key.get(("CRUDE", "Ethanol Inputs", row))
        if section == "GASOLINE":
            if not production or not gross_inputs:
                values[definition.source_column] = {}
                continue
            if ethanol_inputs:
                values[definition.source_column] = _combine_series(
                    values,
                    (production.source_column, ethanol_inputs.source_column, gross_inputs.source_column),
                    lambda production_value, ethanol_input_value, gross_inputs_value:
                        (production_value - ethanol_input_value) / gross_inputs_value * 100.0,
                )
            else:
                values[definition.source_column] = _combine_series(
                    values,
                    (production.source_column, gross_inputs.source_column),
                    lambda production_value, gross_inputs_value: production_value / gross_inputs_value * 100.0,
                )
            continue
        if not production or not crude_runs:
            values[definition.source_column] = {}
            continue
        values[definition.source_column] = _combine_series(
            values,
            (production.source_column, crude_runs.source_column),
            lambda production_value, crude_runs_value: production_value / crude_runs_value * 100.0,
        )

    return RawDataset(values, dataset.release_dates, dataset.weeks, dataset.row_count)


def calc_row(dataset: RawDataset, definition: SeriesDef, week: date) -> MetricRow:
    series = dataset.values.get(definition.source_column, {})
    current_match = _nearest(series, week, 0)
    current = current_match[1] if current_match else None
    prev_match = _nearest(series, week - timedelta(days=7))
    prior_anchor = iso_prior_year_day(week)
    ly_match = _nearest(series, prior_anchor)
    last_year = ly_match[1] if ly_match else None
    wow = current - prev_match[1] if current is not None and prev_match else None
    yoy = current - last_year if current is not None and last_year is not None else None

    avg4 = avg4_wow = avg4_yoy = None
    if not definition.stock_flag:
        avg4 = _avg4(series, week)
        prev_avg4 = _avg4(series, week - timedelta(days=7))
        prior_avg4 = _avg4(series, prior_anchor)
        avg4_wow = avg4 - prev_avg4 if avg4 is not None and prev_avg4 is not None else None
        avg4_yoy = avg4 - prior_avg4 if avg4 is not None and prior_avg4 is not None else None

    return MetricRow(definition, current, last_year, wow, yoy, avg4, avg4_wow, avg4_yoy)


def build_rows(dataset: RawDataset, definitions: list[SeriesDef], week: date) -> list[MetricRow]:
    dataset = _with_calculated_series(dataset, definitions)
    return [calc_row(dataset, d, week) for d in definitions]
