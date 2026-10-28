"""整数の変調・復調 (gracefm.modem_fixed): 無雑音で正しく戻り、雑音があっても LLR の符号が硬判定と一致し、誤りが少ないことを検査する。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import modem_fixed as mf  # noqa: E402


def _roundtrip(mod, alpha, nsym, sigma_lsb, seed):
    rng = np.random.default_rng(seed)
    nbits = nsym * mf.bits_per_symbol(mod)
    bits = rng.integers(0, 2, nbits)
    i_sym, q_sym = mf.modulate(bits, nsym, mod, alpha)
    i_sym, q_sym = i_sym[mf.N_PREAMBLE:], q_sym[mf.N_PREAMBLE:]
    noise = lambda: np.rint(sigma_lsb * rng.standard_normal(nsym)).astype(np.int64)      # 通信路のモデル (試験用)
    llr, hard, var = mf.demodulate(i_sym + noise(), q_sym + noise(), nbits, mod, alpha)
    return bits, llr, hard, var


def test_constellation_has_unit_average_energy():
    for mod, alpha in (("qpsk", 1), ("qam16h", 5)):
        vals = mf.axis_points(mod, alpha)[0]
        energy = 2 * np.mean(vals.astype(np.int64) ** 2) / (1 << (2 * mf.FRAC))
        assert abs(energy - 1.0) < 1e-3


def test_noiseless_roundtrip_is_exact():
    for mod, alpha in (("qpsk", 1), ("qam16h", 5)):
        bits, llr, hard, _ = _roundtrip(mod, alpha, 200, 0, 1)
        assert np.array_equal(hard, bits)
        assert np.all((llr > 0) == (bits == 0)) or np.all(llr[llr != 0] * (1 - 2 * bits[llr != 0]) > 0)


def test_llr_sign_matches_hard_decision_and_errors_are_rare():
    for mod, alpha, sigma in (("qpsk", 1, 0.08), ("qam16h", 5, 0.04)):      # 16QAM の弱い位置は点の間隔が約 0.23
        bits, llr, hard, var = _roundtrip(mod, alpha, 400, sigma * (1 << mf.FRAC), 2)
        assert np.all(np.abs(llr) <= mf.LLR_MAX)
        confident = llr != 0
        assert np.all((llr[confident] > 0) == (hard[confident] == 0))
        assert np.mean(hard != bits) < 0.02, mod


def test_llr_magnitude_is_larger_where_errors_are_less_likely():
    bits, llr, hard, _ = _roundtrip("qpsk", 1, 2000, 0.25 * (1 << mf.FRAC), 3)
    wrong = hard != bits
    assert np.abs(llr[wrong]).mean() < np.abs(llr[~wrong]).mean()
