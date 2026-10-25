"""wav・FLAC の読み書きとサンプリング周波数の変換 (FLAC は soundfile を使う)"""
from fractions import Fraction

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly


def read(path):
    if str(path).lower().endswith(".flac"):
        import soundfile as sf
        x, fs = sf.read(path, dtype="float64", always_2d=True)
        if x.shape[1] == 1:
            x = np.repeat(x, 2, axis=1)
        return x[:, :2], fs
    fs, x = wavfile.read(path)
    if x.dtype == np.int16:
        x = x.astype(float) / 32768.0
    elif x.dtype == np.int32:
        x = x.astype(float) / 2147483648.0
    elif x.dtype == np.uint8:
        x = (x.astype(float) - 128.0) / 128.0
    else:
        x = x.astype(float)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    return x[:, :2], fs


def write(path, x, fs):
    """32bit float で書き出す"""
    wavfile.write(path, fs, np.clip(x, -1.0, 1.0).astype(np.float32))


def write_int32(path, x, fs):
    """int32 PCM の WAV で書き出す (x は int32)"""
    wavfile.write(path, fs, np.asarray(x, np.int32))


def write_pcm24(path, x, fs):
    """24bit 整数 PCM で書き出す (リトルエンディアン, 標準の WAVE ヘッダ)"""
    x = np.atleast_2d(np.asarray(x, float).T).T
    nch = x.shape[1]
    q = np.clip(np.round(x * 8388607.0), -8388608, 8388607).astype("<i4")
    b = q.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    import struct
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(b)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, nch, fs, fs * nch * 3, nch * 3, 24))
        f.write(b"data" + struct.pack("<I", len(b)) + b)


def write_flac16(path, x, fs, seed=0):
    """16bit の FLAC で書き出す (TPDF ディザ ±1LSB)"""
    import soundfile as sf
    x = np.atleast_2d(np.asarray(x, float).T).T
    rng = np.random.default_rng(seed)
    d = (rng.random(x.shape) - rng.random(x.shape)) / 32768.0
    q = np.clip(np.round((x + d) * 32767.0), -32768, 32767).astype(np.int16)
    sf.write(path, q, fs, subtype="PCM_16", format="FLAC")


def write_flac24(path, x, fs):
    """24bit の FLAC で書き出す。"""
    import soundfile as sf
    x = np.atleast_2d(np.asarray(x, float).T).T
    sf.write(path, np.clip(x, -1.0, 1.0), fs, subtype="PCM_24", format="FLAC")


def resample(x, fs_in, fs_out):
    if fs_in == fs_out:
        return x
    r = Fraction(fs_out, fs_in).limit_denominator(1000)
    return resample_poly(x, r.numerator, r.denominator, axis=0)
