"""整数の送受信 (gracefm.link_fixed): 無雑音で整数コーデックの出力と一致し、雑音のもとで音が戻ることを検査する。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm.fixed import decode_block_int, encode_block_int  # noqa: E402
from gracefm.link_fixed import FixedLink  # noqa: E402
from gracefm.modem_fixed import FRAC  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402

NAMES = ("B200M", "B200", "M700M", "M700")


def _blocks(p, n, seed=4):
    rng = np.random.default_rng(seed)
    t = np.arange(p.block * n) / p.fs
    x = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 3000 * t) + 0.01 * rng.standard_normal(len(t))
    x = np.stack([x, 0.7 * x], axis=1)
    if p.name.endswith("M"):
        x[:, 1] = x[:, 0]
    return np.clip(np.rint(x * 2 ** 23), -2 ** 23 + 1, 2 ** 23 - 1).astype(np.int64).reshape(n, p.block, 2)


def test_noiseless_link_equals_integer_codec_output():
    for name in NAMES:
        p = PROFILES[name]
        tx, rx = FixedLink(p), FixedLink(p)
        for block in _blocks(p, 6):
            i_sym, q_sym = tx.transmit(block)
            out = rx.receive(i_sym, q_sym)
            assert out is not None
            assert np.array_equal(out, decode_block_int(encode_block_int(block, p), p)), name


def test_link_survives_moderate_noise():
    rng = np.random.default_rng(9)
    for name in NAMES:
        p = PROFILES[name]
        tx, rx = FixedLink(p), FixedLink(p)
        sigma = 0.02 * (1 << FRAC)                                  # 軸あたりの雑音の標準偏差 (試験用の通信路モデル)
        lost = 0
        err = ref = 0.0
        for block in _blocks(p, 20):
            i_sym, q_sym = tx.transmit(block)
            i_sym = i_sym + np.rint(sigma * rng.standard_normal(len(i_sym))).astype(np.int64)
            q_sym = q_sym + np.rint(sigma * rng.standard_normal(len(q_sym))).astype(np.int64)
            out = rx.receive(i_sym, q_sym)
            if out is None:
                lost += 1
                continue
            err += float(((out - block) ** 2).sum())
            ref += float((block.astype(float) ** 2).sum())
        assert lost == 0, (name, lost)
        assert 10 * np.log10(ref / max(err, 1.0)) > 30, name
