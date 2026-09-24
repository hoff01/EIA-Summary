import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

from eia_summary.render_pdf import PAGE_H, PAGE_W
from eia_summary.validate import validate_pdf


class PdfValidationTests(unittest.TestCase):
    def test_archived_summary_still_validates(self):
        root = Path(__file__).resolve().parents[1]
        validate_pdf(root / "archive" / "EIA_SUMMARY_2026-09-11.pdf")

    def test_incorrect_page_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "two-pages.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=PAGE_W, height=PAGE_H)
            writer.add_blank_page(width=PAGE_W, height=PAGE_H)
            writer.write(path)
            with self.assertRaisesRegex(ValueError, "exactly one page"):
                validate_pdf(path)

    def test_incorrect_page_dimensions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong-size.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.write(path)
            with self.assertRaisesRegex(ValueError, "page size"):
                validate_pdf(path)


if __name__ == "__main__":
    unittest.main()
