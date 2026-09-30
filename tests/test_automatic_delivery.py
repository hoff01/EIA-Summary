import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "nt", "Windows batch launchers")
class AutomaticDeliveryTests(unittest.TestCase):
    def test_default_button_polls_immediately_then_sends_once_and_never_on_failure(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="EIA automatic delivery ") as directory:
            root = Path(directory) / "Package with spaces"
            scripts = root / "scripts"
            scripts.mkdir(parents=True)
            shutil.copy2(source / "RUN_EIA_SUMMARY_DASHBOARD.bat", root)
            shutil.copy2(source / "scripts/run_daily_release_gate.ps1", scripts)
            (scripts / "setup_windows.bat").write_text("@echo off\nexit /b 0\n")
            (root / "email_recipients.txt").write_text("reader@example.com\n")
            (scripts / "windows_common.ps1").write_text(r'''
function Get-ProjectRoot { return $env:TEST_ROOT }
function Get-ProjectConfig { return @{} }
function Import-ProjectEnvironment {}
function Invoke-ProjectPythonOutput {
    param([string[]]$Arguments)
    if ($Arguments[0] -eq 'run_release_gate.py') {
        if ($Arguments -contains '--scheduled') { throw 'Default run waited for schedule' }
        if ($Arguments[$Arguments.IndexOf('--max-attempts') + 1] -ne '120') { throw 'Wrong attempt limit' }
        if ($Arguments[$Arguments.IndexOf('--poll-seconds') + 1] -ne '0.4') { throw 'Wrong interval' }
        if ($env:TEST_FETCH_FAIL -eq '1') { return [pscustomobject]@{ExitCode=1; Lines=@('release_gate_action=error')} }
        return [pscustomobject]@{ExitCode=0; Lines=@('release_gate_action=ready','release_gate_ready_week=2026-09-25')}
    }
    if ($Arguments -notcontains '--send-email' -or $Arguments -notcontains 'outlook') { throw 'Automatic Outlook send missing' }
    if ($Arguments[$Arguments.IndexOf('--week') + 1] -ne '2026-09-25') { throw 'Sent wrong week' }
    Add-Content -LiteralPath (Join-Path $env:TEST_ROOT 'send-calls.txt') -Value 'submitted'
    return [pscustomobject]@{ExitCode=0; Lines=@('validated_week=2026-09-25','email_sent_mode=outlook')}
}
''')
            env = {**os.environ, "EIA_NO_PAUSE": "1", "TEST_ROOT": str(root)}
            command = f'cmd.exe /d /s /c ""{root / "RUN_EIA_SUMMARY_DASHBOARD.bat"}""'
            for _ in range(2):
                result = subprocess.run(command, cwd=directory, env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((root / "send-calls.txt").read_text().splitlines(), ["submitted"])
            result = subprocess.run(command, cwd=directory, env={**env, "TEST_FETCH_FAIL": "1"},
                                    capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((root / "send-calls.txt").read_text().splitlines(), ["submitted"])


if __name__ == "__main__":
    unittest.main()
