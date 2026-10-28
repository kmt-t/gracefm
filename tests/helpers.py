"""テストで使う補助。"""
import os
import sys
from dataclasses import replace
from fractions import Fraction
from math import gcd
from typing import Optional, Tuple

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import fec  # noqa: E402
from gracefm.channel import symbol_rate  # noqa: E402
from gracefm.profiles import Profile  # noqa: E402
from tools.common.layers import balanced, default_split  # noqa: E402
from gracefm.timing import Timing  # noqa: E402


def header_info(lay, stream):
    """送信ビット列からヘッダの情報bit (CRC込み) を取り出す (振幅部にある)"""
    return np.asarray(stream)[lay.hdata_idx].copy()


def with_header(lay, stream, header_x):
    """ヘッダの情報bitを差し替え、パリティと終端を作り直した送信ビット列を返す"""
    out = np.array(stream, np.int64)
    parity, tail = fec.rsc_parity(np.asarray(header_x, np.int64))
    out[lay.hpar_idx] = parity
    out[lay.hdata_idx] = header_x
    out[lay.htail_idx] = tail
    return out


def _reduce(num, den):
    g = gcd(num, den)
    return (num // g, den // g)


def make_y_profile(base: Profile, name: str, pid: int, start_k: Optional[int] = None,
                amplitude: Tuple[int, int] = (2, 25), mantissa_bits: int = 7,
                channels: Tuple[str, ...] = ("M",), format_id: int = 3,
                bits_m: Optional[Tuple[int, ...]] = None,
                bits_s: Optional[Tuple[int, ...]] = None) -> Profile:
    """対象成分の境界以上だけをY(位相・半径シンボル)にし、他の成分は既存主系のままにする。

    amplitude = (分子, 分母) は半径の段が64 (仮数7bit) のときの隣接半径間隔 (既定 2/25 = 0.08) で、幅変更時は最大変調度を保つ。
    bits_m / bits_s を指定すると、M / Sの仮数幅を主系と別の値にする (Y系だけ音質と帯域の釣り合いを変えるとき)。
    """
    if not 5 <= mantissa_bits <= 16:
        raise ValueError("Y仮数幅は5〜16bitにしてください")
    if start_k is None:
        start_k = base.nbands - 3

    def widths(ch, bits):
        return tuple(b if k < start_k or b == 0 or ch not in channels else mantissa_bits
                     for k, b in enumerate(bits))

    attenuator_s = base.attn_group_s
    if bits_s is not None:
        top = max((k for k, w in enumerate(bits_s) if w), default=None)
        attenuator_s = tuple(min(4, base.ncoef(k)) if k == top else 0 for k in range(base.nbands))
    if "S" in channels:                                  # SもY帯域にするときは、MのY帯域と同じ4区間ずつ
        sbits = base.bits_s if bits_s is None else bits_s
        groups_s = list(attenuator_s or (0,) * base.nbands)
        for k in range(start_k, base.nbands):
            if sbits[k]:
                groups_s[k] = max(1, base.ncoef(k) // 4)
        attenuator_s = tuple(groups_s)
    attenuator_m = base.attn_group_m
    if "M" in channels:
        groups = list(attenuator_m or (0,) * base.nbands)
        for k in range(start_k, base.nbands):
            groups[k] = max(1, base.ncoef(k) // 4)
        attenuator_m = tuple(groups)
    new_m = widths("M", base.bits_m if bits_m is None else bits_m)
    new_s = widths("S", base.bits_s if bits_s is None else bits_s)

    def keep_where_width_unchanged(groups, new, old):
        """主系と仮数幅が変わった非Y帯域のアッテネータは引き継がない"""
        return None if groups is None else tuple(0 if k < start_k and new[k] != old[k] else g for k, g in enumerate(groups))
    attenuator_m = keep_where_width_unchanged(attenuator_m, new_m, base.bits_m)
    attenuator_s = keep_where_width_unchanged(attenuator_s, new_s, base.bits_s)
    y = replace(base, pid=pid, name=name, bits_m=new_m, bits_s=new_s,
                base_m=default_split(new_m, base.protect_bits) if base.layered else None,
                base_s=default_split(new_s, base.protect_bits) if base.layered else None,
                attn_group_m=attenuator_m, attn_group_s=attenuator_s,
                y_start_k=start_k,
                y_step=_reduce(15 * amplitude[0], amplitude[1] * (2 ** (mantissa_bits - 1) - 1)),
                y_bits=mantissa_bits, y_channels=channels,
                format_id=format_id)
    if not y.layered:
        return y
    # Yの専用シンボル分だけ強弱の釣り合いが変わるので配分を取り直す
    return balanced(y)


def rrc_equalizer_delay(profile: Profile, lookahead_symbols=0):
    """Transmit plus receive RRC group delay and FIR equalizer lookahead [s]."""
    if lookahead_symbols < 0:
        raise ValueError("lookahead_symbols must be nonnegative")
    return Fraction(profile.pulse_span + lookahead_symbols, symbol_rate(profile))


def waveform_timing(main: Profile, sub: Profile | None = None, lookahead_symbols=4):
    """Timing for the reference static equalizer, excluding compute time."""
    return Timing(t_filt=rrc_equalizer_delay(main, lookahead_symbols),
                  t_filt_b=None if sub is None else rrc_equalizer_delay(sub, lookahead_symbols))
