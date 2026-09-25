import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == 'nt', 'Windows batch launchers')
class WindowsLauncherTests(unittest.TestCase):
    def test_first_run_recipient_prompt_stays_local_and_is_not_repeated(self):
        source = Path(__file__).resolve().parents[1] / 'scripts' / 'run_daily_release_gate.ps1'
        with tempfile.TemporaryDirectory(prefix='EIA recipients ') as directory:
            command = r'''
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:TEST_SOURCE, [ref]$tokens, [ref]$errors)
if ($errors.Count -gt 0) { throw 'Invalid PowerShell syntax' }
$ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in @('Initialize-EmailRecipients','Get-EmailRecipients') }, $true) | ForEach-Object { Invoke-Expression $_.Extent.Text }
$Root = $env:TEST_ROOT
function Read-Host { return 'one@example.com;two@example.com' }
Initialize-EmailRecipients
if (@(Get-EmailRecipients).Count -ne 2) { throw 'Recipients were not saved' }
function Read-Host { throw 'Should not prompt again' }
Initialize-EmailRecipients
'''
            result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                                    env={**os.environ, 'TEST_SOURCE': str(source), 'TEST_ROOT': directory},
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = (Path(directory) / 'email_recipients.txt').read_bytes()
            self.assertFalse(data.startswith(b'\xef\xbb\xbf'))
            self.assertEqual(data.decode().splitlines(), ['one@example.com', 'two@example.com'])

    def test_bootstrap_arguments_and_exit_code_from_path_with_spaces(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='EIA summary test ') as directory:
            root = Path(directory) / 'Project with spaces'
            (root / 'scripts').mkdir(parents=True)
            shutil.copy2(source / 'RUN_EIA_SUMMARY_DASHBOARD.bat', root)
            (root / 'scripts' / 'setup_windows.bat').write_text(
                '@echo off\r\necho setup>"%~dp0..\\setup-ran.txt"\r\nexit /b 0\r\n')
            (root / 'scripts' / 'run_daily_release_gate.ps1').write_text(
                'param([switch]$ShowDecision,[int]$PollSeconds,[switch]$ConfigureRecipients,[switch]$Latest,[switch]$NoEmail)\n'
                'if (-not $ShowDecision -or -not $ConfigureRecipients -or -not $Latest -or -not $NoEmail -or $PollSeconds -ne 7) { exit 99 }\n'
                'Write-Host "Arguments forwarded"\nexit 37\n')
            result = subprocess.run(
                f'cmd.exe /d /s /c ""{root / "RUN_EIA_SUMMARY_DASHBOARD.bat"}" -ShowDecision -Latest -NoEmail -PollSeconds 7"',
                cwd=directory, env={**os.environ, 'EIA_NO_PAUSE': '1'},
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
            self.assertIn('Arguments forwarded', result.stdout)
            self.assertTrue((root / 'setup-ran.txt').exists())

    def test_setup_failure_stops_before_release_runner(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='EIA setup failure ') as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            shutil.copy2(source / 'RUN_EIA_SUMMARY_DASHBOARD.bat', root)
            (root / 'scripts' / 'setup_windows.bat').write_text('@echo off\r\nexit /b 23\r\n')
            result = subprocess.run(
                f'cmd.exe /d /s /c ""{root / "RUN_EIA_SUMMARY_DASHBOARD.bat"}""',
                env={**os.environ, 'EIA_NO_PAUSE': '1'}, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 23, result.stdout + result.stderr)

    def test_setup_button_preserves_failure_code(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='EIA setup button ') as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            shutil.copy2(source / 'SETUP_WINDOWS.bat', root)
            (root / 'scripts' / 'setup_windows.bat').write_text('@echo off\r\nexit /b 29\r\n')
            result = subprocess.run(
                f'cmd.exe /d /s /c ""{root / "SETUP_WINDOWS.bat"}""',
                env={**os.environ, 'EIA_NO_PAUSE': '1'}, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 29, result.stdout + result.stderr)
