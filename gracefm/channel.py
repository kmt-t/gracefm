"""
評価用の通信路モデル。link は同期済みシンボルに直接雑音を加える。
link_static_multipath は RRC 送受信フィルタと静的マルチパスの等価応答を使い、
等化器も選択できる。どちらもシンボル時刻・搬送波位相の同期は理想とする。

電波の強さは C/N0 [dB-Hz] (受信電力 ÷ 1Hz あたりの雑音) で与え、方式・系統ごとに
    Es/N0 [dB] = C/N0 + 10·log10(電力の割合) - 10·log10(シンボルレート [シンボル/秒])
に換算する。C/N [dB] (雑音帯域 Bn) = C/N0 - 10·log10(Bn)。
"""
import numpy as np

from . import modem
from .profiles import PROFILES, Profile
from .txrx import Transmitter, receive

# 主系に組み合わせる副系 (主系より低いビットレートで、別の周波数で送る受け皿)
DEFAULT_SUB = {
    "B200MH": "SUB50M", "B200MHY": "SUB50M",
    "B200H": "SUB100", "B200Y": "SUB100", "B200HY": "SUB100",
    "M700": "SUB100-48K", "M700H": "SUB100-48K",
    "M700Y": "SUB100-48K", "M700HY": "SUB100-48K",
}


def symbol_rate(p):
    """1系統のシンボルレート [シンボル/秒] (プリアンブル込み)"""
    return (len(modem.PREAMBLE) + Transmitter(p).nsym) * p.frames_per_sec


def cn_db(cn0, bn=180e3):
    return cn0 - 10 * np.log10(bn)


def fading_gains(nfr, kind, rng, tau_frames=50):
    """
    フレームごとの電力利得 (平均 1)。
    awgn: 1。fade10: 0.1 (10dB 落ちたまま)。
    rayleigh: レイリーフェージング。複素利得を AR(1) で相関させる (時定数 tau_frames、既定 50 フレーム = 100ms)。
    受信側は理想的な AGC とし、利得の分だけ Es/N0 が変わるモデル。
    """
    if kind == "awgn":
        return np.ones(nfr)
    if kind == "fade10":
        return np.full(nfr, 0.1)
    if kind == "rayleigh":
        rho = np.exp(-1.0 / tau_frames)
        cn = lambda: (rng.normal() + 1j * rng.normal()) / np.sqrt(2)  # noqa: E731
        h = np.empty(nfr, complex)
        h[0] = cn()
        for i in range(1, nfr):
            h[i] = rho * h[i - 1] + np.sqrt(1 - rho ** 2) * cn()
        return np.abs(h) ** 2
    raise ValueError(kind)


def through(frames, esn0, gains, rng):
    return [modem.awgn(f, esn0 + 10 * np.log10(max(g, 1e-6)), rng) for f, g in zip(frames, gains)]


def link(x, main, cn0, sub="auto", power_main=0.5, kind_main="awgn", kind_sub="awgn", seed=1, cipher=None,
         **rx_kw):
    """
    送信 → 通信路 → 受信。送信電力の合計を C/N0 で与える。
    main, sub: プロファイル名または Profile。sub="auto" なら DEFAULT_SUB、None なら 1系統 (全電力を主系に)。
    power_main: 主系に回す電力の割合 (2系統のとき。既定は等分)。
    cipher: 暗号化するとき gracefm.crypto.StreamCipher (送受信で同じもの)。
    返り値: (音声, 受信の統計, {"esn0_main": .., "esn0_sub": ..})
    """
    pm = main if isinstance(main, Profile) else PROFILES[main]
    if sub == "auto":
        sub = DEFAULT_SUB.get(pm.name)
    ps = (sub if isinstance(sub, Profile) else PROFILES[sub]) if sub else None
    frac = power_main if ps else 1.0
    rng = np.random.default_rng(seed)
    off = pm.block // 2
    esm = cn0 + 10 * np.log10(frac) - 10 * np.log10(symbol_rate(pm))
    fa = Transmitter(pm, 0, 0, cipher=cipher).run(x)
    fa = through(fa, esm, fading_gains(len(fa), kind_main, np.random.default_rng(seed + 100)), rng)
    fb, ess = None, None
    if ps:
        ess = cn0 + 10 * np.log10(1 - frac) - 10 * np.log10(symbol_rate(ps))
        fb = Transmitter(ps, 1, off, cipher=cipher).run(x)
        fb = through(fb, ess, fading_gains(len(fb), kind_sub, np.random.default_rng(seed + 200)), rng)
    y, st = receive(pm, fa, fb, len(x), off, profile_b=ps, cipher=cipher, **rx_kw)
    return y, st, {"esn0_main": esm, "esn0_sub": ess}


def link_static_multipath(x, main, cn0, paths=(), sub="auto", power_main=0.5,
                          frequency_spacing_hz=0.0, equalize=True, training_frames=100,
                          equalizer_taps=11, max_lookahead=4, decision_passes=2, seed=1,
                          cipher=None, **rx_kw):
    """Static RRC multipath link with ideal synchronization and optional MMSE FIR.

    ``paths`` contains (delay_s, relative_path_dB, phase_at_main_rad). The
    secondary carrier sees the same physical paths with their phase shifted
    by -2*pi*frequency_spacing_hz*delay_s. Calibration uses only the first
    ``training_frames`` of each stream; benchmark callers should exclude
    those frames when scoring steady-state audio.
    """
    from .equalizer import through_matched_channel, equalize_static

    pm = main if isinstance(main, Profile) else PROFILES[main]
    if sub == "auto":
        sub = DEFAULT_SUB.get(pm.name)
    ps = (sub if isinstance(sub, Profile) else PROFILES[sub]) if sub else None
    if ps is not None and not (0.0 < power_main < 1.0):
        raise ValueError("power_main must be between zero and one")
    frac = power_main if ps else 1.0
    off = pm.block // 2
    esm = cn0 + 10 * np.log10(frac) - 10 * np.log10(symbol_rate(pm))
    fa = Transmitter(pm, 0, 0, cipher=cipher).run(x)
    fa, _ = through_matched_channel(fa, pm, esm, paths, seed=seed)
    diagnostics = {}
    if equalize:
        fa, diagnostics["main"] = equalize_static(
            fa, pm, 0, training_frames, equalizer_taps, max_lookahead,
            decision_passes, encrypted=cipher is not None)
    fb, ess = None, None
    if ps:
        ess = cn0 + 10 * np.log10(1 - frac) - 10 * np.log10(symbol_rate(ps))
        fb = Transmitter(ps, 1, off, cipher=cipher).run(x)
        fb, _ = through_matched_channel(fb, ps, ess, paths, frequency_spacing_hz, seed + 1)
        if equalize:
            fb, diagnostics["sub"] = equalize_static(
                fb, ps, 1, training_frames, equalizer_taps, max_lookahead,
                decision_passes, encrypted=cipher is not None)
    y, st = receive(pm, list(fa), None if fb is None else list(fb), len(x), off,
                    profile_b=ps, cipher=cipher, **rx_kw)
    return y, st, {"esn0_main": esm, "esn0_sub": ess, "equalizer": diagnostics}
