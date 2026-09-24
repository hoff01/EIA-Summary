from __future__ import annotations

import os
import platform
import shutil
import smtplib
import ssl
import subprocess
import time
from email.message import EmailMessage
from email.policy import SMTP
from html import escape
from pathlib import Path

from .metrics import MetricRow

HEADER_CID = "eia-weekly-summary-header"


def render_header_strip(pdf_path: Path, output_path: Path) -> None:
    import pymupdf

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(pdf_path) as doc:
        page = doc[0]
        left = (page.rect.width - 1960) / 2
        clip = pymupdf.Rect(left, 18, left + 1960, 225)
        page.get_pixmap(dpi=72, clip=clip).save(str(output_path))


def stock_change_preview(rows: list[MetricRow]) -> str:
    totals = {row.definition.section: row for row in rows
              if row.definition.card == "Stocks" and row.definition.display_row == "TOT"}
    parts = []
    for section, label in (("GASOLINE", "Gasoline"), ("DISTILLATES", "Distillates")):
        row = totals[section]
        if row.wow is None:
            value = "N/A"
        else:
            change = round(row.wow / row.definition.scale, 1)
            value = f"{change:+,.1f} MMB" if change else "0.0 MMB"
        parts.append(f"{label}: {value}")
    return " | ".join(parts) + " (w/w stock change)"


def _email_html(week: str, stock_preview: str) -> str:
    return f'''<html>
  <body style="font-family:Arial,Helvetica,sans-serif;">
    <p style="font-weight:bold;">{escape(stock_preview)}</p>
    <p>DOE Weekly Summary W/E {escape(week)}.</p>
    <p>Weekly stock changes (million barrels):</p>
    <img src="cid:{HEADER_CID}" width="980" alt="Weekly stock changes: C = Crude, G = Gasoline, D = Distillates, J = Jet, FO = Fuel Oil. Parentheses indicate a decrease."
         style="display:block;width:100%;max-width:980px;height:auto;border:0;">
    <p>C: Crude &nbsp; G: Gasoline &nbsp; D: Distillates &nbsp; J: Jet &nbsp; FO: Fuel Oil</p>
    <p>The full dashboard PDF is attached.</p>
  </body>
</html>
'''


def _applescript_string(value: str | Path) -> str:
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def read_recipients(path: Path) -> list[str]:
    if not path.exists():
        raise ValueError(f"Create {path.name} with one recipient email address per line before sending")
    recipients: list[str] = []
    for line in path.read_text().splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#"):
            recipients.append(clean)
    if not recipients:
        raise ValueError(f"No recipients configured in {path.name}")
    return recipients


def build_email(
    *,
    week: str,
    recipients: list[str],
    pdf_path: Path,
    header_png_path: Path,
    stock_preview: str,
    sender: str | None = None,
) -> EmailMessage:
    subject = f"DOE Summary W/E {week}"
    msg = EmailMessage()
    msg["Subject"] = subject
    from_address = sender or os.environ.get("DOE_SUMMARY_EMAIL_FROM")
    if from_address:
        msg["From"] = from_address
    msg["To"] = ", ".join(recipients)
    msg.set_content(
        f"{stock_preview}\n\n"
        f"DOE Weekly Summary W/E {week}\n\n"
        "The dashboard PDF is attached.\n"
    )
    msg.add_alternative(_email_html(week, stock_preview), subtype="html")
    msg.get_payload()[-1].add_related(
        header_png_path.read_bytes(), maintype="image", subtype="png",
        cid=f"<{HEADER_CID}>", disposition="inline", filename=header_png_path.name,
    )
    msg.add_attachment(pdf_path.read_bytes(), maintype="application", subtype="pdf", filename=pdf_path.name)
    return msg


def write_eml(msg: EmailMessage, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(msg.as_bytes(policy=SMTP))


def send_smtp(msg: EmailMessage, recipients: list[str]) -> None:
    host = os.environ.get("SMTP_HOST")
    if not host:
        raise RuntimeError("SMTP_HOST is not configured")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    sender = msg["From"]
    if not sender:
        raise ValueError("Set DOE_SUMMARY_EMAIL_FROM before sending through SMTP")
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context) as smtp:
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg, from_addr=sender, to_addrs=recipients)
    else:
        with smtplib.SMTP(host, port) as smtp:
            smtp.starttls(context=context)
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg, from_addr=sender, to_addrs=recipients)


def send_sendmail(msg: EmailMessage, recipients: list[str]) -> None:
    binary = shutil.which("sendmail")
    if not binary:
        raise RuntimeError("sendmail is not available")
    proc = subprocess.run([binary, "-t", "-oi"], input=msg.as_bytes(policy=SMTP), check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"sendmail failed with exit code {proc.returncode}")


def _load_win32com_client():
    if platform.system() != "Windows":
        raise RuntimeError("Outlook send mode is only available on Windows")
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("pywin32 is required for Outlook sending; run scripts\\setup_windows.bat") from exc
    return win32com.client


def _is_outlook_running() -> bool:
    if platform.system() != "Windows":
        return False
    proc = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq OUTLOOK.EXE"],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and "OUTLOOK.EXE" in proc.stdout.upper()


def _launch_outlook() -> None:
    try:
        os.startfile("outlook")  # type: ignore[attr-defined]
    except OSError:
        subprocess.Popen(
            ["cmd", "/c", "start", "", "outlook"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _get_ready_outlook_application():
    win32com_client = _load_win32com_client()
    was_running = _is_outlook_running()
    if not was_running:
        _launch_outlook()
        startup_wait = int(os.environ.get("DOE_SUMMARY_OUTLOOK_STARTUP_WAIT_SECONDS", "12"))
        time.sleep(max(startup_wait, 0))

    timeout_seconds = int(os.environ.get("DOE_SUMMARY_OUTLOOK_READY_TIMEOUT_SECONDS", "60"))
    deadline = time.monotonic() + max(timeout_seconds, 1)
    last_error: Exception | None = None
    while time.monotonic() <= deadline:
        try:
            outlook = win32com_client.Dispatch("Outlook.Application")
            if int(outlook.Session.Accounts.Count) < 1:
                raise RuntimeError("Outlook has no configured accounts")
            return outlook
        except Exception as exc:  # noqa: BLE001 - COM raises several pywin32 exception types here
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"Outlook did not become ready for automation: {last_error}") from last_error


def _set_outlook_account(mail, outlook, account_hint: str | None) -> None:
    if not account_hint:
        return
    wanted = account_hint.strip().lower()
    accounts = getattr(outlook.Session, "Accounts", None)
    if accounts is None:
        raise RuntimeError("Outlook accounts collection is not available")
    for index in range(1, int(accounts.Count) + 1):
        account = accounts.Item(index)
        candidates = [
            str(getattr(account, "SmtpAddress", "") or "").strip().lower(),
            str(getattr(account, "DisplayName", "") or "").strip().lower(),
        ]
        if wanted in candidates:
            mail.SendUsingAccount = account
            return
    raise RuntimeError(f"Outlook account {account_hint!r} was not found")


def _create_windows_outlook_message(
    *,
    recipients: list[str],
    subject: str,
    week: str,
    html_path: Path,
    pdf_path: Path,
    header_png_path: Path | None = None,
):
    if not recipients:
        raise RuntimeError("No email recipients were configured")
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    if not html_path.exists():
        raise FileNotFoundError(html_path)
    html = html_path.read_text(encoding="utf-8")
    if f"cid:{HEADER_CID}" in html and (header_png_path is None or not header_png_path.exists()):
        raise FileNotFoundError("The email summary strip is missing; rebuild before sending")

    outlook = _get_ready_outlook_application()
    mail = outlook.CreateItem(0)
    mail.Subject = subject
    mail.Body = (
        f"DOE Weekly Summary W/E {week}\r\n\r\n"
        "The dashboard PDF is attached."
    )
    _set_outlook_account(
        mail,
        outlook,
        os.environ.get("DOE_SUMMARY_OUTLOOK_ACCOUNT") or os.environ.get("OUTLOOK_ACCOUNT"),
    )
    for address in recipients:
        recipient = mail.Recipients.Add(address)
        recipient.Type = 1
    if not mail.Recipients.ResolveAll():
        unresolved: list[str] = []
        for index in range(1, int(mail.Recipients.Count) + 1):
            recipient = mail.Recipients.Item(index)
            if not bool(getattr(recipient, "Resolved", False)):
                unresolved.append(str(getattr(recipient, "Name", "") or getattr(recipient, "Address", "")))
        detail = ", ".join(unresolved) if unresolved else "unknown recipient"
        raise RuntimeError(f"Outlook could not resolve recipient(s): {detail}")
    mail.Attachments.Add(str(pdf_path.resolve()))
    if header_png_path is not None:
        attachment = mail.Attachments.Add(str(header_png_path.resolve()))
        attachment.PropertyAccessor.SetProperty("http://schemas.microsoft.com/mapi/proptag/0x3712001F", HEADER_CID)
        attachment.PropertyAccessor.SetProperty("http://schemas.microsoft.com/mapi/proptag/0x370E001F", "image/png")
        attachment.PropertyAccessor.SetProperty("http://schemas.microsoft.com/mapi/proptag/0x7FFE000B", True)
    mail.HTMLBody = html
    return mail


def send_outlook(*, recipients: list[str], subject: str, week: str, html_path: Path, pdf_path: Path, header_png_path: Path | None = None) -> None:
    try:
        mail = _create_windows_outlook_message(
            recipients=recipients,
            subject=subject,
            week=week,
            html_path=html_path,
            pdf_path=pdf_path,
            header_png_path=header_png_path,
        )
        mail.Send()
    except Exception as exc:
        raise RuntimeError(
            "Outlook send failed. Confirm classic desktop Outlook is signed in, "
            "connected, and not waiting on a profile or password prompt. The script "
            "will launch Outlook when it is closed, but it cannot clear profile, "
            "password, or security prompts."
        ) from exc


def create_apple_mail_draft(*, recipients: list[str], subject: str, html_path: Path, pdf_path: Path) -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("Apple Mail draft mode is only available on macOS")
    recipient_lines = "\n".join(
        f"make new to recipient at end of to recipients with properties {{address:{_applescript_string(r)}}}"
        for r in recipients
    )
    script = f'''
set htmlFile to POSIX file {_applescript_string(html_path)}
set pdfFile to POSIX file {_applescript_string(pdf_path)}
set htmlBody to read htmlFile
tell application "Mail"
    set newMessage to make new outgoing message with properties {{subject:{_applescript_string(subject)}, content:htmlBody, visible:true}}
    tell newMessage
        {recipient_lines}
        make new attachment with properties {{file name:pdfFile}} at after last paragraph
    end tell
    activate
end tell
'''
    proc = subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Apple Mail draft creation failed")


def send_apple_mail(*, recipients: list[str], subject: str, week: str, pdf_path: Path) -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("Apple Mail send mode is only available on macOS")
    recipient_lines = "\n".join(
        f"make new to recipient at end of to recipients with properties {{address:{_applescript_string(r)}}}"
        for r in recipients
    )
    body = (
        f"DOE Weekly Summary W/E {week}\n\n"
        "The dashboard PDF is attached."
    )
    script = f'''
set pdfFile to POSIX file {_applescript_string(pdf_path)}
tell application "Mail"
    set newMessage to make new outgoing message with properties {{subject:{_applescript_string(subject)}, content:{_applescript_string(body)}, visible:false}}
    tell newMessage
        {recipient_lines}
        make new attachment with properties {{file name:pdfFile}} at after last paragraph
        send
    end tell
end tell
'''
    proc = subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Apple Mail send failed")


def create_outlook_draft(*, recipients: list[str], subject: str, html_path: Path, pdf_path: Path, header_png_path: Path | None = None) -> None:
    if platform.system() == "Windows":
        mail = _create_windows_outlook_message(
            recipients=recipients,
            subject=subject,
            week=subject.rsplit(" ", 1)[-1],
            html_path=html_path,
            pdf_path=pdf_path,
            header_png_path=header_png_path,
        )
        mail.Display()
        return
    if platform.system() != "Darwin":
        raise RuntimeError("Outlook draft mode is only available on macOS in this script")
    to_value = "; ".join(recipients)
    recipient_properties = "{email address:{address:" + _applescript_string(to_value) + "}}"
    script = f'''
set htmlFile to POSIX file {_applescript_string(html_path)}
set pdfPath to {_applescript_string(pdf_path)}
set htmlBody to read htmlFile
tell application "Microsoft Outlook"
    set newMessage to make new outgoing message with properties {{subject:{_applescript_string(subject)}, content:htmlBody}}
    tell newMessage
        make new recipient at end of to recipients with properties {recipient_properties}
        make new attachment with properties {{file:pdfPath}}
        open
    end tell
    activate
end tell
'''
    proc = subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Outlook draft creation failed")


def write_email_html(*, week: str, output_path: Path, stock_preview: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_email_html(week, stock_preview), encoding="utf-8")


def try_send(msg: EmailMessage, recipients: list[str], modes: list[str]) -> str:
    errors: list[str] = []
    for mode in modes:
        try:
            if mode == "smtp":
                send_smtp(msg, recipients)
            elif mode == "sendmail":
                send_sendmail(msg, recipients)
            else:
                raise RuntimeError(f"unsupported email mode: {mode}")
            return mode
        except Exception as exc:  # noqa: BLE001 - collect fallback errors for CLI output
            errors.append(f"{mode}: {exc}")
    raise RuntimeError("; ".join(errors))
