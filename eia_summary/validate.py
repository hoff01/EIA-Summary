from __future__ import annotations

import hashlib
from pathlib import Path

from pypdf import PdfReader

from .render_pdf import DrawnBox, PAGE_H, PAGE_W


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_pdf(path: Path) -> None:
    reader = PdfReader(str(path))
    if len(reader.pages) != 1:
        raise ValueError(f"{path} must have exactly one page")
    page = reader.pages[0]
    box = page.mediabox
    w = float(box.width)
    h = float(box.height)
    if abs(w - PAGE_W) > 0.1 or abs(h - PAGE_H) > 0.1:
        raise ValueError(f"{path} page size {w}x{h}, expected {PAGE_W}x{PAGE_H}")


def validate_boxes(boxes: list[DrawnBox]) -> tuple[int, int]:
    clipped = 0
    overlaps = 0
    for b in boxes:
        if b.x < -1 or b.y < -1 or b.x + b.w > PAGE_W + 1 or b.y + b.h > PAGE_H + 1:
            clipped += 1
    # Only detect egregious text overlaps among nearby boxes.
    text_boxes = sorted((b for b in boxes if b.kind == "text" and b.w > 0 and b.h > 0), key=lambda b: b.y)
    for i, a in enumerate(text_boxes):
        for b in text_boxes[i + 1:]:
            if b.y >= a.y + a.h:
                break
            if abs(a.y - b.y) > max(a.h, b.h):
                continue
            if a.x < b.x + b.w and a.x + a.w > b.x and a.y < b.y + b.h and a.y + a.h > b.y:
                overlaps += 1
    return clipped, overlaps


def render_png(pdf_path: Path, png_path: Path) -> None:
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    try:
        doc[0].get_pixmap(dpi=72).save(str(png_path))
    finally:
        doc.close()
