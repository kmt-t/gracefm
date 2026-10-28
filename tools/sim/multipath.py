"""
静的マルチパスの評価用の通信路 (アナログの通信路を模擬するので、浮動小数点を使う)。

送受信の RRC の組から 8 サンプル/シンボルでインパルス応答を作り、シンボル時刻で標本化する。この応答との畳み込みは、
パルス成形、静的な線形通信路、整合フィルタ、理想的なタイミング回復と等価である。雑音は整合フィルタの出力に与えた
Es/N0 で加え、12 bit の ADC で量子化して、受信側の整数 (Q FRAC) に直す。搬送波とタイミングの獲得はこのモデルの外。
"""
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.signal import fftconvolve

from gracefm import modem
from gracefm.channel import DEFAULT_SUB, adc, symbol_rate
from gracefm.equalizer import equalize_static
from gracefm.profiles import PROFILES, Profile
from gracefm.txrx import Transmitter, receive
from tools.common.pulse import rrc_taps


def matched_channel_taps(profile: Profile, paths=(), rf_offset_hz=0.0, sps=8):
    """単位直接波と (遅延 s, dB, 位相) のエコーに対する (ラグ, タップ)。別の搬送波でのエコーの位相は
    位相 - 2π·rf_offset_hz·遅延。C/N0 は直接波を基準にするので、エコーを足した後の電力の正規化はしない。"""
    paths = tuple(paths)
    rs = symbol_rate(profile)
    root = rrc_taps(profile.pulse_beta_pct / 100, sps, profile.pulse_span)
    pulse = np.convolve(root, root[::-1])
    t = (np.arange(len(pulse)) - (len(pulse) - 1) / 2) / sps
    interp = CubicSpline(t, pulse, extrapolate=False)
    max_delay = max((delay * rs for delay, _, _ in paths), default=0.0)
    lags = np.arange(-profile.pulse_span, profile.pulse_span + int(np.ceil(max_delay)) + 1)

    def sample(at):
        out = interp(at)
        return np.where(np.isfinite(out), out, 0.0)

    taps = sample(lags).astype(complex)
    for delay, rel_db, phase in paths:
        if delay < 0:
            raise ValueError("echo delay must be nonnegative")
        gain = 10 ** (rel_db / 20) * np.exp(1j * (phase - 2 * np.pi * rf_offset_hz * delay))
        taps += gain * sample(lags - delay * rs)
    return lags, taps


def through_matched_channel(frames, profile: Profile, esn0_db, paths=(), rf_offset_hz=0.0, seed=1):
    """連続フレーム (整数のシンボル (n, 2) のリスト) を静的な RRC マルチパスと AWGN に通す。
    返り値: 受信フレーム (整数、nf × n × 2) と、雑音のない通信路 (ラグ, タップ)。固定の乱数で等化あり・なしを対にして比べられる。"""
    scale = float(1 << modem.SYM_FRAC)
    symbols = np.concatenate(frames) / scale
    z = symbols[:, 0] + 1j * symbols[:, 1]
    lags, taps = matched_channel_taps(profile, paths, rf_offset_hz)
    y = fftconvolve(z, taps, mode="full")[int(-lags[0]):int(-lags[0]) + len(z)]
    n0 = 10 ** (-esn0_db / 10)
    rng = np.random.default_rng(seed)
    y = y + np.sqrt(n0 / 2) * (rng.standard_normal(len(y)) + 1j * rng.standard_normal(len(y)))
    out = adc(np.stack([y.real, y.imag], axis=1))
    return out.reshape(len(frames), len(frames[0]), 2), (lags, taps)


def link_static_multipath(x, main, cn0, paths=(), sub="auto", cn0_sub=None,
                          frequency_spacing_hz=0.0, equalize=True, training_frames=100,
                          equalizer_taps=11, max_lookahead=4, decision_passes=2, seed=1,
                          cipher=None, **rx_kw):
    """静的な RRC マルチパス + 理想同期 + 任意で MMSE FIR。副系は同じ物理経路を、主系との搬送波間隔による位相差で通る。
    較正は各系統の最初の training_frames だけを使う。定常状態の評価は、その後のフレームで行うこと。"""
    pm = main if isinstance(main, Profile) else PROFILES[main]
    if sub == "auto":
        sub = DEFAULT_SUB.get(pm.name)
    ps = (sub if isinstance(sub, Profile) else PROFILES[sub]) if sub else None
    esm = cn0 - 10 * np.log10(symbol_rate(pm))
    fa = Transmitter(pm, 0, 0, cipher=cipher).run(x)
    fa, _ = through_matched_channel(fa, pm, esm, paths, seed=seed)
    diagnostics = {}
    if equalize:
        fa, diagnostics["main"] = equalize_static(fa, pm, 0, training_frames, equalizer_taps, max_lookahead,
                                                  decision_passes, encrypted=cipher is not None)
    fb, ess = None, None
    if ps:
        ess = (cn0 if cn0_sub is None else cn0_sub) - 10 * np.log10(symbol_rate(ps))
        fb = Transmitter(ps, 1, 0, cipher=cipher).run(x)
        fb, _ = through_matched_channel(fb, ps, ess, paths, frequency_spacing_hz, seed + 1)
        if equalize:
            fb, diagnostics["sub"] = equalize_static(fb, ps, 1, training_frames, equalizer_taps, max_lookahead,
                                                     decision_passes, encrypted=cipher is not None)
    y, st = receive(pm, list(fa), None if fb is None else list(fb), len(x), 0,
                    profile_b=ps, cipher=cipher, **rx_kw)
    return y, st, {"esn0_main": esm, "esn0_sub": ess, "equalizer": diagnostics}
