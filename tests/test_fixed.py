"""整数コーデック経路 (gracefm.fixed) が DSP48E1 の幅 (乗算器 25 bit) に収まり、元の音声との SNR が出ることを検査する。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm.codec import BlockData  # noqa: E402
from gracefm.dsp import CONST_BITS, MULT_MAX, MULT_MIN, SQ2_INV  # noqa: E402
from gracefm.codec import decode_block, encode_block, haar_forward, haar_inverse, roundtrip  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402


def _music_like(n, fs, seed=3):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    x = sum(a * np.sin(2 * np.pi * f * t + p) for a, f, p in
            ((0.4, 220, 0.1), (0.2, 880, 1.3), (0.1, 3520, 2.1), (0.02, 9000, 0.4)))
    x = x + 0.01 * rng.standard_normal(n)
    return np.stack([x, 0.8 * x + 0.05 * np.sin(2 * np.pi * 330 * t)], axis=1)


def test_multiplier_constant_fits_18_bit_signed():
    assert 0 < SQ2_INV < (1 << (CONST_BITS - 1))


def test_haar_stays_within_multiplier_width_and_inverts():
    rng = np.random.default_rng(1)
    for levels in (4,):
        x = rng.integers(-(1 << 21), 1 << 21, (50, 1 << levels * 2)).astype(np.int64)
        bands = haar_forward(x, levels)
        assert all(b.max() <= MULT_MAX and b.min() >= MULT_MIN for b in bands)
        y = haar_inverse(bands)
        assert np.abs(y - x).max() <= 64                # 定数46341/65536の誤差 (約1e-6) と丸めの累積。21 bitの満点 2^21 に対し約 -90 dB 以下
    full = np.full((1, 64), 1 << 21, np.int64)                  # 満点の直流: 最低域が最大 (4倍)
    peak = max(np.abs(b).max() for b in haar_forward(full, 4))
    assert peak <= (1 << 23) + 64                               # 25 bitの上限 2^24 に届かず、飽和は起きない


def test_roundtrip_matches_original_audio_for_all_profiles():
    for name, p in PROFILES.items():
        x = np.clip(np.rint(_music_like(p.block * 40, p.fs) * 2 ** 23), -2 ** 23 + 1, 2 ** 23 - 1).astype(np.int64)
        if name.endswith(("M", "MY")) or name == "SUB50M":
            x[:, 1] = x[:, 0]
        y = roundtrip(x, p)
        assert np.abs(y).max() < 2 ** 23
        err = (x - y).astype(float)
        snr = 10 * np.log10((x.astype(float) ** 2).sum() / (err ** 2).sum())
        assert snr > (10 if name.startswith("SUB") else 40), (name, snr)


def test_encoder_output_is_block_data_with_integer_fields():
    p = PROFILES["B200"]
    bd = encode_block(np.zeros((p.block, 2), np.int64) + 1000, p)
    assert isinstance(bd, BlockData)
    assert all(isinstance(e, int) for e in bd.eidx["M"] if e is not None)
    assert decode_block(bd, p).dtype == np.int64


def test_hardware_modules_contain_no_floating_point():
    """ハードウェア向けのモジュールでは float を使わない (リテラル、float 型、真の除算、浮動小数点の関数)"""
    import ast
    import pathlib
    forbidden_names = {"float", "float32", "float64", "sqrt", "log", "log2", "exp", "exp2", "sin", "cos", "rint",
                       "mean", "std", "power", "pi", "nan", "inf"}
    root = pathlib.Path(__file__).resolve().parents[1] / "gracefm"
    for name in ("dsp.py", "codec.py", "fec_fixed.py", "modem_fixed.py", "link_fixed.py"):
        tree = ast.parse((root / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                raise AssertionError(f"{name}:{node.lineno} float literal {node.value}")
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                raise AssertionError(f"{name}:{node.lineno} true division")
            ident = node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None
            if ident in forbidden_names:
                raise AssertionError(f"{name}:{node.lineno} forbidden name {ident}")
