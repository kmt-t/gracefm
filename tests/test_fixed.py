"""整数コーデック経路 (gracefm.fixed) が DSP48E1 の幅 (乗算器 25 bit) に収まり、元の音声との SNR が出ることを検査する。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm.codec import (
    BlockData,
    encode_block,
    haar_forward,
    haar_inverse,
)
from gracefm.decoder import reconstruct, roundtrip
from gracefm.dsp import CONST_BITS, MULT_MAX, MULT_MIN, SQ2_INV
from gracefm.profiles import PROFILES


def _music_like(n, fs, seed=3):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    x = sum(a * np.sin(2 * np.pi * f * t + p) for a, f, p in
            ((0.4, 220, 0.1), (0.2, 880, 1.3), (0.1, 3520, 2.1), (0.02, 9000, 0.4)))
    x = x + 0.01 * rng.standard_normal(n)
    return np.stack([x, 0.8 * x + 0.05 * np.sin(2 * np.pi * 330 * t)], axis=1)


def test_multiplier_constant_fits_18_bit_signed():
    assert 0 < SQ2_INV < (1 << (CONST_BITS - 1))


def test_wide_products_are_exact_and_split_into_dsp_widths():
    """広い積は、乗算器の幅の片に分けて足す。結果は正確な積と同じ (int64 の範囲で)"""
    from gracefm.dsp import PIECE_BITS, wide_matmul, wide_mul
    rng = np.random.default_rng(7)
    a = rng.integers(-2**40, 2**40, size=200)
    b = rng.integers(-2**20, 2**20, size=200)
    assert all(int(g) == int(p) * int(q) for g, p, q in zip(wide_mul(a, b), a, b))
    A = rng.integers(-2**22, 2**22, size=(30, 5))
    B = rng.integers(-2**30, 2**30, size=(5, 4))
    G = wide_matmul(A, B)
    assert all(int(G[i, j]) == sum(int(A[i, k]) * int(B[k, j]) for k in range(5)) for i in range(30) for j in range(4))
    assert PIECE_BITS + PIECE_BITS <= 18 + 4          # 片どうしの積は 22 bit 以内


def test_postfilter_datapath_fits_dsp_widths():
    """ポストフィルタの信号は 25 bit (乗算器の A 入力)、係数は 18 bit (B 入力)、積和は 48 bit (アキュムレータ) に収まる"""
    from gracefm import postfilter, tables
    from gracefm.dsp import ACC_BITS, CONST_BITS, MULT_BITS, MULT_MIN
    assert postfilter.GUARD_BITS + 24 == MULT_BITS
    for name, table in (("LANCZOS", tables.LANCZOS_Q16), ("LPF_32K", tables.LPF_32K_Q17), ("LPF_48K", tables.LPF_48K_Q17),
                        ("RESAMPLE_3_8", tables.RESAMPLE_3_8_Q16), ("RESAMPLE_1_4", tables.RESAMPLE_1_4_Q16)):
        c = np.abs(np.array(table, np.int64))
        assert int(c.max()) < 1 << (CONST_BITS - 1), name
        # 最悪の積和: 入力の最大 (|x| = 2^(MULT_BITS-1)) × 係数の絶対値の和
        assert int(c.sum()) * (-MULT_MIN) < 1 << (ACC_BITS - 1), name


def test_haar_stays_within_multiplier_width_and_inverts():
    rng = np.random.default_rng(1)
    for levels in (4,):
        x = rng.integers(-(1 << 22), 1 << 22, (50, 1 << levels * 2)).astype(np.int64)
        bands = haar_forward(x, levels)
        assert all(b.max() <= MULT_MAX and b.min() >= MULT_MIN for b in bands)
        y = haar_inverse(bands)
        assert np.abs(y - x).max() <= 64                # 定数46341/65536の誤差 (約1e-6) と丸めの累積。22 bitの満点 2^22 に対し約 -96 dB 以下
    full = np.full((1, 64), 1 << 22, np.int64)                  # 満点の直流: 最低域が最大 (4倍)
    peak = max(np.abs(b).max() for b in haar_forward(full, 4))
    assert peak <= (1 << 24) + 64                               # 満点の直流は 25 bitの上限 2^24 - 1 を 1 LSB (2^-22) だけ超え、飽和で切る


def test_roundtrip_matches_original_audio_for_all_profiles():
    for name, p in PROFILES.items():
        x = np.clip(np.rint(_music_like(p.block * 40, p.fs) * 2 ** 23), -2 ** 23 + 1, 2 ** 23 - 1).astype(np.int64)
        if not any(p.bits_s):
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
    assert reconstruct(bd, p).dtype == np.int64


def test_hardware_modules_contain_no_floating_point():
    """ハードウェア向けのモジュール (gracefm/ のすべて。アナログの通信路を模擬する channel.py を除く) では float を使わない (リテラル、float 型、真の除算、浮動小数点の関数)"""
    import ast
    import pathlib
    forbidden_names = {"float", "float32", "float64", "sqrt", "log", "log2", "exp", "exp2", "sin", "cos", "rint",
                       "mean", "std", "power", "pi", "nan", "inf"}
    root = pathlib.Path(__file__).resolve().parents[1] / "gracefm"
    found = []
    for name in sorted(p.name for p in root.glob("*.py") if p.name not in ("channel.py", "__init__.py")):
        tree = ast.parse((root / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                found.append(f"{name}:{node.lineno} float literal {node.value}")
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                found.append(f"{name}:{node.lineno} true division")
            ident = node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None
            if ident in forbidden_names:
                found.append(f"{name}:{node.lineno} forbidden name {ident}")
    assert not found, found


def test_log_and_exp_without_tables_are_accurate():
    import math

    from gracefm.dsp import inv1p2pow_q15, log2_q8, pow2_neg_q15, sigmoid_q15
    for k in range(40):
        assert log2_q8(1 << k) == k * 256
    for x in (3, 5, 7, 100, 1234, 987654321):
        assert abs(log2_q8(x) - 256 * math.log2(x)) <= 2                          # 小数 8 bit の誤差
    for d in range(0, 16 * 256, 7):
        assert abs(int(pow2_neg_q15(d)) - 32768 * 2 ** (-d / 256)) <= 3
    for llr in range(-127, 128):
        assert abs(int(sigmoid_q15(llr)) - 32768 / (1 + math.exp(llr / 4))) <= 12
    assert int(sigmoid_q15(0)) == 16384 and int(inv1p2pow_q15(0)) == 16384
