import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from eia_summary import emailer


class EmailSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.pdf = self.root / "summary.pdf"
        self.pdf.write_bytes(b"test-pdf")
        self.png = self.root / "header.png"
        Image.new("RGB", (980, 104), "black").save(self.png)
        self.html = self.root / "summary.html"
        self.preview = "Gasoline: +0.8 MMB | Distillates: -1.6 MMB (w/w stock change)"
        emailer.write_email_html(week="2026-09-11", output_path=self.html, stock_preview=self.preview)

    def test_mime_contains_inline_snapshot_and_unchanged_pdf(self):
        msg = emailer.build_email(week="2026-09-11", recipients=["reader@example.com"],
                                  pdf_path=self.pdf, header_png_path=self.png, stock_preview=self.preview)
        parsed = BytesParser(policy=policy.default).parsebytes(msg.as_bytes())
        self.assertTrue(parsed.get_body(preferencelist=("plain",)).get_content().startswith(self.preview))
        html = parsed.get_body(preferencelist=("html",)).get_content()
        self.assertLess(html.index(self.preview), html.index("DOE Weekly Summary"))
        self.assertIn(f"cid:{emailer.HEADER_CID}", parsed.get_body(preferencelist=("html",)).get_content())
        images = [p for p in parsed.walk() if p.get_content_type() == "image/png"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["Content-ID"], f"<{emailer.HEADER_CID}>")
        self.assertEqual(images[0].get_content_disposition(), "inline")
        self.assertEqual(images[0].get_payload(decode=True), self.png.read_bytes())
        attachments = list(parsed.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_payload(decode=True), self.pdf.read_bytes())

    def test_outlook_binds_snapshot_to_html_and_keeps_pdf(self):
        outlook = Mock()
        mail = outlook.CreateItem.return_value
        mail.Recipients.ResolveAll.return_value = True
        with patch.object(emailer, "_get_ready_outlook_application", return_value=outlook), \
             patch.object(emailer, "_set_outlook_account"):
            result = emailer._create_windows_outlook_message(
                recipients=["reader@example.com"], subject="Test", week="2026-09-11",
                html_path=self.html, pdf_path=self.pdf, header_png_path=self.png)
        self.assertIs(result, mail)
        self.assertEqual([call.args[0] for call in mail.Attachments.Add.call_args_list],
                         [str(self.pdf.resolve()), str(self.png.resolve())])
        mail.Attachments.Add.return_value.PropertyAccessor.SetProperty.assert_any_call(
            "http://schemas.microsoft.com/mapi/proptag/0x3712001F", emailer.HEADER_CID)
        self.assertIn(f"cid:{emailer.HEADER_CID}", mail.HTMLBody)
        self.assertIn(self.preview, mail.HTMLBody)
        mail.Send.assert_not_called()

    def test_missing_inline_image_stops_before_outlook(self):
        with patch.object(emailer, "_get_ready_outlook_application") as outlook:
            with self.assertRaises(FileNotFoundError):
                emailer._create_windows_outlook_message(
                    recipients=["reader@example.com"], subject="Test", week="2026-09-11",
                    html_path=self.html, pdf_path=self.pdf)
            outlook.assert_not_called()

    def test_direct_header_render_is_small_and_contains_tickers(self):
        from eia_summary.paths import ROOT
        pdf = ROOT / "archive" / "EIA_SUMMARY_2026-09-11.pdf"
        emailer.render_header_strip(pdf, self.png)
        with Image.open(self.png) as image:
            self.assertLess(image.height, 220)
            self.assertLess(image.width, 2000)
            self.assertGreater(len(image.getcolors(image.width * image.height)), 100)

    def test_preview_uses_only_weekly_total_stock_changes(self):
        def row(section, wow, card="Stocks", region="TOT"):
            return SimpleNamespace(wow=wow, current=999999,
                                   definition=SimpleNamespace(section=section, card=card, display_row=region, scale=1000))
        rows = [row("GASOLINE", 800), row("DISTILLATES", -1600), row("CRUDE", 5000),
                row("GASOLINE", 12345, region="I"), row("DISTILLATES", 8888, card="Production")]
        self.assertEqual(emailer.stock_change_preview(rows), self.preview)
        self.assertEqual(emailer.stock_change_preview([row("GASOLINE", None), row("DISTILLATES", -1)]),
                         "Gasoline: N/A | Distillates: 0.0 MMB (w/w stock change)")
