"""Source preparation and codec round trips for matched codec benchmarks."""
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from scipy.signal import correlate

from gracefm import wavio

ROOT = Path(__file__).resolve().parents[2]


def source(entry, seconds):
    x, fs = wavio.read(ROOT / "eval_audio" / entry["file"])
    if len(x) < round((seconds + 1) * fs):
        raise ValueError(f"{entry['name']}: at least {seconds + 1:g}s required")
    x = x[fs:fs + round(seconds * fs)]
    x = wavio.resample(x, fs, 48000)
    x *= 0.89 / np.max(np.abs(x))
    n32 = int(seconds * 32000) // 64 * 64
    if n32 < 64:
        raise ValueError("Evaluation interval is too short")
    x48 = x[:n32 * 3 // 2]
    x32 = wavio.resample(x48, 48000, 32000)[:n32]
    common48 = wavio.resample(x32, 32000, 48000)
    return x48, x32, common48


def aptx_roundtrip(x, variant, ffmpeg):
    if variant not in ("aptx", "aptx_hd") or x.ndim != 2 or x.shape[1] != 2:
        raise ValueError("aptX requires stereo audio and a supported variant")
    pad = 512
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        original = directory / "source.wav"
        encoded = directory / f"audio.{variant}"
        decoded = directory / "decoded.wav"
        padded = np.pad(x, ((0, pad), (0, 0)))
        if variant == "aptx":
            from scipy.io import wavfile
            pcm16 = np.clip(np.rint(padded * 32767), -32768, 32767).astype(np.int16)
            wavfile.write(original, 48000, pcm16)
        else:
            wavio.write_pcm24(original, padded, 48000)
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                        "-i", str(original), "-c:a", variant, "-f", variant,
                        str(encoded)], check=True)
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                        "-f", variant, "-i", str(encoded), "-c:a", "pcm_f32le",
                        str(decoded)], check=True)
        y, fs = wavio.read(decoded)
        size = encoded.stat().st_size
    if fs != 48000 or len(y) < len(x) + 256:
        raise ValueError(f"{variant}: unexpected decoder length or sample rate")
    n = min(48000, len(x))
    delay = int(np.argmax(correlate(y[:n + 256, 0], x[:n, 0],
                                    mode="valid", method="fft")))
    y = y[delay:delay + len(x)]
    if len(y) != len(x):
        raise ValueError(f"{variant}: delay compensation failed")
    kbps = size * 8 * 48000 / (len(x) + pad) / 1000
    return y, round(kbps, 3), delay


def heaac_roundtrip(x, aot, bitrate, fdkaac, ffmpeg):
    """FDK HE-AAC v1 mono (AOT 5) or HE-AAC v2 stereo (AOT 29)."""
    expected_channels = {5: 1, 29: 2}.get(aot)
    if expected_channels is None or x.ndim != 2 or x.shape[1] != expected_channels:
        raise ValueError("HE-AAC profile and input channel count disagree")
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        original = directory / "input.wav"
        encoded = directory / "audio.m4a"
        decoded = directory / "decoded.wav"
        wavio.write_pcm24(original, x, 48000)
        subprocess.run([fdkaac, "-S", "-p", str(aot), "-b", str(bitrate),
                        "-o", str(encoded), str(original)], check=True)
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                        "-i", str(encoded), "-ac", str(expected_channels),
                        "-c:a", "pcm_f32le", str(decoded)],
                       check=True)
        import soundfile as sf
        y, fs = sf.read(decoded, dtype="float64", always_2d=True)
        size = encoded.stat().st_size
    if fs != 48000 or y.shape[1] != expected_channels or len(y) < len(x):
        raise ValueError(f"Unexpected HE-AAC decoder output: fs={fs}, channels={y.shape[1]}, samples={len(y)}, expected={len(x)}, AOT={aot}")
    search = min(8192, len(y) - len(x))
    n = min(48000, len(x))
    if search <= 0:
        raise ValueError("Insufficient decoder padding for alignment")
    correlation = sum(correlate(y[:n + search, ch], x[:n, ch],
                                mode="valid", method="fft")
                      for ch in range(expected_channels))
    delay = int(np.argmax(correlation))
    y = y[delay:delay + len(x)]
    if len(y) != len(x):
        raise ValueError("HE-AAC delay compensation failed")
    return y, size, delay


def prepare(entry, seconds):
    """ライセンス確認済みの原音から、32 kHz・モノラルを2チャンネルに複製した評価区間 (ピーク0.89) を作る"""
    path = ROOT / "eval_audio" / entry["file"]
    x, fs = wavio.read(path)
    # A one-second lead-in avoids a possibly silent file opening.
    first = fs
    if len(x) < first + round(seconds * fs):
        raise ValueError(f"{path}: at least {seconds + 1:g}s required")
    x = x[first:first + round(seconds * fs)].mean(axis=1)
    x = wavio.resample(x[:, None], fs, 32000)[:, 0] if fs != 32000 else x
    x = x[:round(seconds * 32000)]
    peak = float(np.max(np.abs(x)))
    if peak < 1e-4:
        raise ValueError(f"{path}: almost silent evaluation interval")
    x = x * (0.89 / peak)
    return np.repeat(x[:, None], 2, axis=1)
