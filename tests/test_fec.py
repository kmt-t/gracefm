"""整数ビタビ (gracefm.fec_fixed) が、雑音のある整数の軟値から元のビットを復元することを検査する。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import fec  # noqa: E402
from gracefm.fec import LLR_MAX, PM_MIN, rsc_decode as rsc_decode_int, viterbi_decode as viterbi_decode_int  # noqa: E402


def quantize_llr(llr, scale):
    """試験用: 実数の LLR を整数 (LLR_MAX で飽和) にする。実機では最初から整数で作る"""
    return np.clip(np.rint(np.asarray(llr, float) * scale), -LLR_MAX, LLR_MAX).astype(np.int64)


def _noisy_soft(bits, sigma, rng):
    tx = 1.0 - 2.0 * np.asarray(bits)                          # 0 → +1
    rx = tx + sigma * rng.standard_normal(len(tx))
    return quantize_llr(2.0 * rx / sigma ** 2, 4.0)


def test_viterbi_int_recovers_bits_at_moderate_noise():
    rng = np.random.default_rng(5)
    errors = 0
    for _ in range(40):
        bits = rng.integers(0, 2, 120)
        coded = fec.conv_encode(bits)
        soft = _noisy_soft(coded, 0.5, rng)
        assert np.abs(soft).max() <= LLR_MAX
        errors += int(np.sum(viterbi_decode_int(soft, len(bits)) != bits))
    assert errors == 0


def test_viterbi_int_beats_hard_decisions_in_heavy_noise():
    rng = np.random.default_rng(6)
    soft_err = hard_err = total = 0
    for _ in range(40):
        bits = rng.integers(0, 2, 120)
        coded = fec.conv_encode(bits)
        soft = _noisy_soft(coded, 0.7, rng)
        soft_err += int(np.sum(viterbi_decode_int(soft, len(bits)) != bits))
        hard_err += int(np.sum(viterbi_decode_int(np.where(soft >= 0, 1, -1), len(bits)) != bits))
        total += len(bits)
    assert soft_err < hard_err
    assert soft_err / total < 0.02


def test_rsc_decode_int_recovers_information_bits():
    rng = np.random.default_rng(7)
    x = rng.integers(0, 2, 90)
    parity, tail = fec.rsc_parity(x)
    to_soft = lambda b: quantize_llr(8.0 * (1.0 - 2.0 * np.asarray(b)), 1.0)
    decoded = rsc_decode_int(to_soft(x), to_soft(parity), to_soft(tail))
    assert np.array_equal(decoded, x)
    noisy = to_soft(x).copy()
    noisy[::7] *= -1                                           # 14個の誤った軟値
    assert np.array_equal(rsc_decode_int(noisy, to_soft(parity), to_soft(tail)), x)


def test_path_metrics_stay_in_range():
    assert PM_MIN == -(1 << 13)
