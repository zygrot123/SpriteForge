"""Local microphone → text using Windows Speech Recognition (no cloud)."""
from __future__ import annotations

import subprocess
from pathlib import Path

_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
$culture = [System.Globalization.CultureInfo]::CurrentCulture
try {
  $eng = New-Object System.Speech.Recognition.SpeechRecognitionEngine($culture)
} catch {
  $eng = New-Object System.Speech.Recognition.SpeechRecognitionEngine (New-Object System.Globalization.CultureInfo 'en-US')
}
try {
  $eng.SetInputToDefaultAudioDevice()
} catch {
  Write-Output 'ERROR: No microphone. Allow mic access in Windows Settings > Privacy > Microphone.'
  exit 2
}
$eng.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
$eng.InitialSilenceTimeout = [TimeSpan]::FromSeconds(5)
$eng.BabbleTimeout = [TimeSpan]::FromSeconds(4)
$eng.EndSilenceTimeout = [TimeSpan]::FromSeconds(0.9)
$eng.EndSilenceTimeoutAmbiguous = [TimeSpan]::FromSeconds(1.2)
$result = $eng.Recognize([TimeSpan]::FromSeconds(16))
if ($result -and $result.Text) {
  Write-Output $result.Text
} else {
  Write-Output 'ERROR: Heard nothing. Speak after the click, then pause.'
  exit 1
}
$eng.Dispose()
"""


class VoiceError(RuntimeError):
    pass


def listen_once(timeout: float = 22) -> str:
    """Listen on the default microphone and return transcribed text."""
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _SCRIPT,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.home()),
        )
    except subprocess.TimeoutExpired as exc:
        raise VoiceError("Listening timed out. Try again and speak sooner.") from exc
    except OSError as exc:
        raise VoiceError(f"Could not start speech recognition: {exc}") from exc
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if out.startswith("ERROR:"):
        raise VoiceError(out[6:].strip())
    if proc.returncode != 0 and not out:
        raise VoiceError(err or "Speech recognition failed. Install the Windows speech pack.")
    if not out:
        raise VoiceError("Heard nothing. Check the microphone and try again.")
    return " ".join(out.split())
