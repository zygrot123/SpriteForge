"""Microphone → text. Windows Speech, local, no cloud.

Starts the engine first, beeps READY, then listens. The old path started
listening after you had already spoken, so the mic looked broken.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

_PS1 = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech

function New-Engine {
  $infos = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
  $info = $infos | Where-Object { $_.Culture.Name -eq 'en-US' } | Select-Object -First 1
  if (-not $info) { $info = $infos | Select-Object -First 1 }
  if ($info) {
    return New-Object System.Speech.Recognition.SpeechRecognitionEngine($info)
  }
  return New-Object System.Speech.Recognition.SpeechRecognitionEngine (New-Object System.Globalization.CultureInfo 'en-US')
}

$eng = New-Engine
try {
  $eng.SetInputToDefaultAudioDevice()
} catch {
  Write-Output ('ERROR: No microphone. Windows Settings > Privacy > Microphone: allow desktop apps. ' + $_.Exception.Message)
  exit 2
}

$eng.UnloadAllGrammars()
$dict = New-Object System.Speech.Recognition.DictationGrammar
$dict.Enabled = $true
$eng.LoadGrammar($dict)

$eng.InitialSilenceTimeout = [TimeSpan]::FromSeconds(14)
$eng.BabbleTimeout = [TimeSpan]::FromSeconds(8)
$eng.EndSilenceTimeout = [TimeSpan]::FromSeconds(1.4)
$eng.EndSilenceTimeoutAmbiguous = [TimeSpan]::FromSeconds(1.8)

try { [console]::Beep(980, 160) } catch { }

$bits = Join-Path $env:TEMP 'spriteforge_mic_bits.txt'
'' | Set-Content -Path $bits -Encoding UTF8

Write-Output 'READY'
[Console]::Out.Flush()

$null = Register-ObjectEvent -InputObject $eng -EventName SpeechRecognized -SourceIdentifier SFMic -Action {
  $t = $Event.SourceEventArgs.Result.Text
  if ($t) { Add-Content -Path (Join-Path $env:TEMP 'spriteforge_mic_bits.txt') -Value $t -Encoding UTF8 }
}

$eng.RecognizeAsync([System.Speech.Recognition.RecognizeMode]::Multiple)
Start-Sleep -Seconds 12
try { $eng.RecognizeAsyncStop() } catch { }
Start-Sleep -Milliseconds 600
Unregister-Event -SourceIdentifier SFMic -ErrorAction SilentlyContinue
Get-Event -SourceIdentifier SFMic -ErrorAction SilentlyContinue | Remove-Event -ErrorAction SilentlyContinue

$eng.Dispose()
$text = ''
if (Test-Path $bits) {
  $text = ((Get-Content -Path $bits -Encoding UTF8 | Where-Object { $_.Trim() }) -join ' ').Trim()
}
if ($text) {
  Write-Output ('TEXT:' + $text)
  exit 0
}
Write-Output 'ERROR: Heard nothing. Wait for the beep, then speak a full sentence.'
exit 1
"""


class VoiceError(RuntimeError):
    pass


def _powershell() -> str:
    windir = os.environ.get("SystemRoot") or r"C:\Windows"
    exe = Path(windir) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if exe.is_file():
        return str(exe)
    return "powershell"


def listen_once(timeout: float = 40, on_ready: Callable[[], None] | None = None) -> str:
    """Listen on the default microphone and return transcribed text."""
    tmp = Path(tempfile.gettempdir()) / "spriteforge_listen.ps1"
    tmp.write_text(_PS1.lstrip("\n"), encoding="ascii")
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            [
                _powershell(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(tmp),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
        )
    except OSError as exc:
        raise VoiceError(f"Could not start speech recognition: {exc}") from exc

    text = ""
    err_line = ""
    try:
        assert proc.stdout is not None
        deadline_ready = False
        while True:
            line = proc.stdout.readline()
            if line == "" and proc.poll() is not None:
                break
            line = (line or "").strip()
            if not line:
                continue
            if line == "READY":
                deadline_ready = True
                if on_ready:
                    on_ready()
                continue
            if line.startswith("TEXT:"):
                text = line[5:].strip()
                continue
            if line.startswith("ERROR:"):
                err_line = line[6:].strip()
        proc.wait(timeout=max(5, timeout))
    except subprocess.TimeoutExpired:
        proc.kill()
        raise VoiceError("Listening timed out. Wait for the beep, then speak.") from None
    finally:
        if proc.poll() is None:
            proc.kill()

    if text:
        return " ".join(text.split())
    stderr = ""
    if proc.stderr:
        stderr = (proc.stderr.read() or "").strip()
    if err_line:
        raise VoiceError(err_line)
    if proc.returncode not in (0, 1, None):
        raise VoiceError(stderr[-240:] if stderr else "Speech recognition failed.")
    raise VoiceError("Heard nothing. Wait for the beep, then speak clearly.")
