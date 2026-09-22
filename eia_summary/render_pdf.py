from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from .metrics import MetricRow


PAGE_W = 2821
PAGE_H = 2629

SECTION_COLORS = {
    "CRUDE": colors.HexColor("#d8d8d0"),
    "GASOLINE": colors.HexColor("#23b64b"),
    "DISTILLATES": colors.HexColor("#34b9e6"),
    "JET": colors.HexColor("#f2a11b"),
    "RFO": colors.HexColor("#8b44d8"),
}

PANEL = colors.HexColor("#20211f")
BG = colors.HexColor("#0b0c0d")
GRID = colors.HexColor("#5b5d58")
TEXT = colors.HexColor("#f3f3ee")
MUTED = colors.HexColor("#b8bbb8")
BLUE = colors.HexColor("#76baff")
UP = colors.HexColor("#7ee0aa")
DOWN = colors.HexColor("#ff3b30")
FLAT = colors.HexColor("#f0c84b")

SUMMARY_FONT_BUMP = 7
DASHBOARD_FONT_BUMP = 1
CREDIT_TEXT = "Created by: Alex Hoffmann"


@dataclass
class DrawnBox:
    kind: str
    x: float
    y: float
    w: float
    h: float


def _fmt(value: float | None, fmt: str, scale: float = 1.0, delta: bool = False) -> str:
    if value is None:
        return "-"
    v = value / scale
    if fmt == "percent":
        text = f"{abs(v):.1f}%"
    elif fmt == "mmb":
        text = f"{abs(v):,.1f}"
    else:
        text = f"{abs(v):,.0f}"
    if v < 0:
        return f"({text})" if delta else f"-{text}"
    return text


def _delta_color(value: float | None):
    if value is None or abs(value) < 1e-9:
        return FLAT
    return UP if value > 0 else DOWN


def _text(c: canvas.Canvas, text: str, x: float, y: float, size: float, color=TEXT, bold=False, align="left") -> DrawnBox:
    font = "Helvetica-Bold" if bold else "Helvetica"
    c.setFont(font, size)
    c.setFillColor(color)
    width = stringWidth(text, font, size)
    if align == "right":
        c.drawRightString(x, y, text)
        tx = x - width
    elif align == "center":
        c.drawCentredString(x, y, text)
        tx = x - width / 2
    else:
        c.drawString(x, y, text)
        tx = x
    return DrawnBox("text", tx, y - 2, width, size + 2)


def _value(c: canvas.Canvas, value: float | None, fmt: str, scale: float, x: float, y: float, size: float, delta=False, color=TEXT) -> DrawnBox:
    return _text(c, _fmt(value, fmt, scale, delta), x, y, size, color, bold=True, align="right")


def _draw_credit(c: canvas.Canvas, boxes: list[DrawnBox]) -> None:
    font = "Helvetica-Oblique"
    size = 13
    pad_x = 10
    pad_y = 5
    width = stringWidth(CREDIT_TEXT, font, size)
    box_w = width + pad_x * 2
    box_h = size + pad_y * 2
    x = PAGE_W - 28 - box_w
    y = 9
    c.setFillColor(colors.HexColor("#181916"))
    c.rect(x, y, box_w, box_h, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#80837d"))
    c.setFont(font, size)
    c.drawRightString(x + box_w - pad_x, y + pad_y + 2, CREDIT_TEXT)
    boxes.append(DrawnBox("credit", x, y, box_w, box_h))


def _draw_card(c: canvas.Canvas, title: str, unit: str, rows: list[MetricRow], x: float, y: float, w: float, h: float, section: str, boxes: list[DrawnBox]) -> None:
    c.setFillColor(PANEL)
    c.setStrokeColor(colors.HexColor("#74766f"))
    c.setLineWidth(1.2)
    c.rect(x, y, w, h, stroke=1, fill=1)
    accent = SECTION_COLORS.get(section, BLUE)
    c.setFillColor(accent)
    c.rect(x + 10, y + h - 31, 10, 18, stroke=0, fill=1)
    boxes.append(_text(c, title.upper(), x + 26, y + h - 30, 19 + DASHBOARD_FONT_BUMP, TEXT, bold=True))
    boxes.append(_text(c, unit, x + w - 18, y + h - 27, 14 + DASHBOARD_FONT_BUMP, BLUE, bold=True, align="right"))
    c.setStrokeColor(GRID)
    c.setLineWidth(0.65)
    c.line(x + 16, y + h - 42, x + w - 16, y + h - 42)

    stock = all(r.definition.stock_flag for r in rows)
    headers = ["", "Current", "Last Yr", "ΔWOW", "ΔYOY"] if stock else ["", "Current", "Last Yr", "ΔWOW", "ΔYOY", "4W Avg", "4W ΔWOW", "4W ΔYOY"]
    row_count = max(len(rows), 1)
    header_y = y + h - 66
    row_h = min(30, (h - 96) / max(row_count, 1))
    body_size = (13 if row_h >= 26 else 11) + DASHBOARD_FONT_BUMP
    header_size = (10 if not stock else 11) + DASHBOARD_FONT_BUMP
    label_w = 48
    usable_w = w - 34 - label_w
    col_count = len(headers) - 1
    col_w = usable_w / col_count
    start_x = x + 18
    for i, hd in enumerate(headers):
        if i == 0:
            continue
        boxes.append(_text(c, hd, start_x + label_w + col_w * i - 10, header_y, header_size, MUTED, bold=True, align="right"))
    c.line(x + 14, header_y - 10, x + w - 14, header_y - 10)

    for idx, row in enumerate(rows):
        ry = header_y - 28 - idx * row_h
        if ry < y + 12:
            break
        if idx % 2 == 1:
            c.setFillColor(colors.HexColor("#252621"))
            c.rect(x + 8, ry - 7, w - 16, row_h, stroke=0, fill=1)
        is_sub_padd = row.definition.display_row in {"A", "B", "C"}
        label_x = start_x + label_w + 7 if is_sub_padd else start_x + label_w - 8
        label_color = MUTED if is_sub_padd else TEXT
        boxes.append(_text(c, row.definition.display_row, label_x, ry, body_size, label_color, bold=True, align="right"))
        vals = [row.current, row.last_year, row.wow, row.yoy]
        fmts = [row.definition.fmt, row.definition.fmt, row.definition.fmt, row.definition.fmt]
        scales = [row.definition.scale, row.definition.scale, row.definition.scale, row.definition.scale]
        if not stock:
            vals += [row.avg4, row.avg4_wow, row.avg4_yoy]
            fmts += [row.definition.fmt, row.definition.fmt, row.definition.fmt]
            scales += [row.definition.scale, row.definition.scale, row.definition.scale]
        for j, val in enumerate(vals):
            vx = start_x + label_w + col_w * (j + 1) - 10
            is_colored_delta = j in (2, 3, 5, 6)
            color = _delta_color(val) if is_colored_delta else TEXT
            boxes.append(_value(c, val, fmts[j], scales[j], vx, ry, body_size, delta=j >= 2, color=color))
        c.setStrokeColor(colors.HexColor("#3e413c"))
        c.line(x + 12, ry - 10, x + w - 12, ry - 10)


def _draw_exports_demand_card(c: canvas.Canvas, rows: list[MetricRow], x: float, y: float, w: float, h: float, section: str, boxes: list[DrawnBox]) -> None:
    c.setFillColor(PANEL)
    c.setStrokeColor(colors.HexColor("#74766f"))
    c.setLineWidth(1.2)
    c.rect(x, y, w, h, stroke=1, fill=1)
    accent = SECTION_COLORS.get(section, BLUE)

    by_row = {row.definition.display_row: row for row in rows}
    groups = [("EXPORTS", by_row.get("EXP")), ("DEMAND", by_row.get("DEM"))]
    group_gap = 120
    top_y = y + h - 32
    label_w = 46
    col_headers = ["Current", "Last Yr", "ΔW/W", "ΔY/Y", "4W Avg", "4W ΔW/W", "4W ΔY/Y"]
    col_w = (w - 52 - label_w) / len(col_headers)

    for idx, (title, row) in enumerate(groups):
        gy = top_y - idx * group_gap
        c.setFillColor(accent)
        c.rect(x + 12, gy - 1, 10, 18, stroke=0, fill=1)
        boxes.append(_text(c, title, x + 28, gy, 18 + DASHBOARD_FONT_BUMP, TEXT, bold=True))
        boxes.append(_text(c, "KBD", x + w - 18, gy + 2, 13 + DASHBOARD_FONT_BUMP, BLUE, bold=True, align="right"))
        c.setStrokeColor(GRID)
        c.setLineWidth(0.65)
        c.line(x + 16, gy - 12, x + w - 16, gy - 12)

        header_y = gy - 35
        for j, header in enumerate(col_headers):
            hx = x + 24 + label_w + col_w * (j + 1) - 8
            boxes.append(_text(c, header, hx, header_y, 8 + DASHBOARD_FONT_BUMP, MUTED, bold=True, align="right"))
        if row is None:
            continue

        ry = header_y - 26
        values = [row.current, row.last_year, row.wow, row.yoy, row.avg4, row.avg4_wow, row.avg4_yoy]
        boxes.append(_text(c, "TOT", x + 24 + label_w - 10, ry, 13 + DASHBOARD_FONT_BUMP, TEXT, bold=True, align="right"))
        for j, val in enumerate(values):
            vx = x + 24 + label_w + col_w * (j + 1) - 8
            color = _delta_color(val) if j in (2, 3, 5, 6) else TEXT
            boxes.append(_value(c, val, row.definition.fmt, row.definition.scale, vx, ry, 13 + DASHBOARD_FONT_BUMP, delta=j in (2, 3, 5, 6), color=color))


def _ordered_rows(rows: list[MetricRow]) -> list[MetricRow]:
    if not rows or not all(row.definition.stock_flag for row in rows):
        return sorted(rows, key=lambda r: r.definition.sort_order)
    order = {"I": 0, "A": 1, "B": 2, "C": 3, "II": 4, "III": 5, "IV": 6, "V": 7, "TOT": 8, "CUSH": 9}
    return sorted(rows, key=lambda r: (order.get(r.definition.display_row, 50), r.definition.sort_order))


def _draw_sulfur_card(c, rows, x, y, w, h, metric, boxes):
    c.setFillColor(PANEL)
    c.rect(x, y, w, h, stroke=0, fill=1)
    c.setFillColor(SECTION_COLORS["DISTILLATES"])
    c.rect(x + 10, y + h - 31, 10, 18, stroke=0, fill=1)
    title = "DISTILLATE STOCK SPLIT" if metric == "stocks" else "DISTILLATE PRODUCTION SPLIT"
    boxes.append(_text(c, title, x + 26, y + h - 30, 20, TEXT, bold=True))
    boxes.append(_text(c, "MMB" if metric == "stocks" else "KBD", x + w - 18, y + h - 27, 15, BLUE, bold=True, align="right"))
    c.setStrokeColor(GRID)
    c.setLineWidth(0.65)
    c.line(x + 16, y + h - 42, x + w - 16, y + h - 42)
    stock = metric == "stocks"
    columns = [("Current", "current", False), ("ΔWOW", "wow", True), ("ΔYOY", "yoy", True)]
    if not stock:
        columns += [("4W Avg", "avg4", False), ("4W ΔYOY", "avg4_yoy", True)]
    label_w = 48
    data_x = x + 18 + label_w
    group_w = (w - 36 - label_w) / 2
    col_w = group_w / len(columns)
    for group, title in enumerate(("0-15 PPM SULFUR", ">15 PPM SULFUR")):
        left = data_x + group * group_w
        boxes.append(_text(c, title, left + group_w / 2, y + h - 62, 12, BLUE, bold=True, align="center"))
        for j, (header, _attribute, _delta) in enumerate(columns):
            boxes.append(_text(c, header, left + (j + 1) * col_w - 7, y + h - 81, 12 if stock else 11, MUTED, bold=True, align="right"))
    c.line(x + 14, y + h - 89, x + w - 14, y + h - 89)
    by_row = {r.definition.display_row: r for r in rows}
    regions = ["I", "A", "B", "C", "II", "III", "IV", "V", "TOT"] if metric == "stocks" else ["I", "II", "III", "IV", "V", "TOT"]
    row_h = 19 if metric == "stocks" else 25
    for i, region in enumerate(regions):
        ry = y + h - 105 - i * row_h
        if i % 2:
            c.setFillColor(colors.HexColor("#252621"))
            c.rect(x + 8, ry - 5, w - 16, row_h, stroke=0, fill=1)
        sub = region in {"A", "B", "C"}
        label_x = data_x + 7 if sub else data_x - 8
        boxes.append(_text(c, region, label_x, ry, 12, MUTED if sub else TEXT, bold=True, align="right"))
        for group, band in enumerate(("low", "high")):
            row = by_row.get(f"{region}:{band}")
            if row is None:
                continue
            for j, (_header, attribute, delta) in enumerate(columns):
                value = getattr(row, attribute)
                right = data_x + group * group_w + (j + 1) * col_w - 7
                boxes.append(_value(c, value, "mmb" if stock else "kbd", row.definition.scale, right, ry, 12, delta=delta, color=_delta_color(value) if delta else TEXT))
        c.setStrokeColor(colors.HexColor("#3e413c"))
        c.line(x + 12, ry - 7, x + w - 12, ry - 7)
    c.setStrokeColor(GRID)
    c.line(data_x + group_w, y + 34, data_x + group_w, y + h - 48)
    note = ">15 = >15-500 + >500 ppm" if metric == "stocks" else "Refiner + blender; weekly sub-PADD detail not published"
    boxes.append(_text(c, note, x + 16, y + 13, 10, MUTED))


def render_pdf(output_path: Path, rows: list[MetricRow], week: date, release_date: str) -> list[DrawnBox]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=(PAGE_W, PAGE_H), pageCompression=1)
    boxes: list[DrawnBox] = []
    c.setFillColor(BG)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)

    title_size = 38 + SUMMARY_FONT_BUMP
    title_gap = 8
    doe_w = stringWidth("DOE", "Helvetica-Bold", title_size)
    weekly_w = stringWidth("WEEKLY SUMMARY", "Helvetica-Bold", title_size)
    title_x = (PAGE_W - doe_w - title_gap - weekly_w) / 2
    boxes.append(_text(c, "DOE", title_x, PAGE_H - 58, title_size, TEXT, bold=True, align="left"))
    boxes.append(_text(c, "WEEKLY SUMMARY", title_x + doe_w + title_gap, PAGE_H - 58, title_size, BLUE, bold=True, align="left"))
    boxes.append(_text(c, f"Week Ending {week.isoformat()}", PAGE_W / 2, PAGE_H - 96, 19 + SUMMARY_FONT_BUMP, BLUE, bold=True, align="center"))

    by_key: dict[tuple[str, str], list[MetricRow]] = defaultdict(list)
    for row in rows:
        by_key[(row.definition.section, row.definition.card)].append(row)
    for key in by_key:
        by_key[key] = _ordered_rows(by_key[key])

    # Top ticker row uses total stocks by product.
    tickers = [("C", "CRUDE", "Stocks"), ("G", "GASOLINE", "Stocks"), ("D", "DISTILLATES", "Stocks"), ("J", "JET", "Stocks"), ("FO", "RFO", "Stocks")]
    tile_w = 296
    tile_step = 390
    strip_w = tile_step * (len(tickers) - 1) + tile_w
    tx = (PAGE_W - strip_w) / 2
    for label, section, card in tickers:
        total = next((r for r in by_key.get((section, card), []) if r.definition.display_row == "TOT"), None)
        x = tx
        y = PAGE_H - 205
        color = SECTION_COLORS.get(section, BLUE)
        c.setFillColor(color)
        c.rect(x, y, 98, 74, stroke=0, fill=1)
        boxes.append(_text(c, label, x + 49, y + 22, 34 + SUMMARY_FONT_BUMP, TEXT if label != "C" else BG, bold=True, align="center"))
        c.setFillColor(colors.HexColor("#24251f"))
        c.rect(x + 106, y, 190, 74, stroke=0, fill=1)
        val = total.wow if total else None
        ticker_size = 21 + SUMMARY_FONT_BUMP
        ticker_text = _fmt(val, "mmb", 1000, delta=True)
        boxes.append(_text(c, ticker_text, x + 201, y + 25, ticker_size, _delta_color(val), bold=True, align="center"))
        tx += 390

    layout = {
        "CRUDE": (28, 1960, ["Stocks", "Production", "Crude Runs", "Exports", "Gross Inputs", "Utilization", "Imports", "Ethanol Inputs"]),
        "GASOLINE": (28, 1242, ["Stocks", "Production", "Imports", "Exports/Demand", "Yield"]),
        "DISTILLATES": (28, 842, ["Stocks", "Production", "Imports", "Exports/Demand", "Yield"]),
        "JET": (28, 442, ["Stocks", "Production", "Imports", "Exports/Demand", "Yield"]),
        "RFO": (28, 42, ["Stocks", "Production", "Imports", "Exports/Demand", "Yield"]),
    }
    col_gap = 18
    col_w = (PAGE_W - 56 - col_gap * 4) / 5
    card_h_default = 300

    for section, (x0, y0, cards) in layout.items():
        sec_color = SECTION_COLORS[section]
        c.setFillColor(sec_color)
        c.rect(28, y0 + card_h_default + 18, PAGE_W - 56, 5, stroke=0, fill=1)
        boxes.append(_text(c, section, 34, y0 + card_h_default + 31, 22 + DASHBOARD_FONT_BUMP, TEXT, bold=True))
        for i, card in enumerate(cards):
            row = i // 5
            col = i % 5
            h = card_h_default
            cy = y0 - row * (h + 26)
            cx = x0 + col * (col_w + col_gap)
            card_rows = by_key.get((section, card), [])
            if card == "Exports/Demand":
                _draw_exports_demand_card(c, card_rows, cx, cy, col_w, h, section, boxes)
            else:
                title = "Yield (Gross Inputs)" if section == "GASOLINE" and card == "Yield" else card
                _draw_card(c, title, _unit_for_card(card_rows), card_rows, cx, cy, col_w, h, section, boxes)

    split_x = 28 + 3 * (col_w + col_gap)
    split_y = 1634
    split_w = 2 * col_w + col_gap
    stock_w = col_w - 110
    production_x = split_x + stock_w + col_gap
    c.setFillColor(PANEL)
    c.rect(split_x, split_y, split_w, card_h_default, stroke=0, fill=1)
    for metric, x, width in (("stocks", split_x, stock_w),
                             ("production", production_x, split_w - stock_w - col_gap)):
        _draw_sulfur_card(c, by_key[("DISTILLATES", f"Sulfur {metric.title()}")],
                          x, split_y, width, card_h_default, metric, boxes)
    c.setFillColor(BG)
    c.rect(split_x + stock_w, split_y + 8, col_gap, card_h_default - 16, stroke=0, fill=1)
    c.setStrokeColor(SECTION_COLORS["DISTILLATES"])
    c.setLineWidth(1.8)
    c.rect(split_x, split_y, split_w, card_h_default, stroke=1, fill=0)

    _draw_credit(c, boxes)
    c.showPage()
    c.save()
    return boxes


def _unit_for_card(rows: list[MetricRow]) -> str:
    if not rows:
        return ""
    fmt = rows[0].definition.fmt
    if fmt == "mmb":
        return "MMB"
    if fmt == "percent":
        return "%"
    return "KBD"
