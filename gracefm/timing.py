"""
因果的な時刻モデル。

時刻 0 を原音の先頭とし、系統 i のフレーム j が運ぶ原音の区間を
  A: [j·B, (j+1)·B)      B: [j·B - B/2, (j+1)·B - B/2)   (B はブロック長 [s]。B の先頭の負時刻は 0 埋め)
とする。送信は連続 (フレームを隙間なく並べる) で、1フレームの直列化時間は
  T_ser = (プリアンブル込みのシンボル数) / (シンボルレート) = B
(シンボルレートを「1フレームのシンボル数 × 毎秒のフレーム数」で決めているため。txrx.Transmitter.symbol_rate)。

各フレームの時刻:
  取得完了   = 区間の終わり
  送信開始   = 取得完了 + t_enc
  送信完了   = 送信開始 + T_ser
  受信完了   = 送信完了 + t_filt (送受信フィルタの群遅延など。伝搬時間は 5m で約 17ns なので無視)
  復号完了   = 受信完了 + t_dec
出力: 原音の時刻 t のサンプルを t + D に再生する (D は一定)。出力は単位 (半ブロックまたは 1ブロック)
ごとに確定し、単位の先頭サンプルの再生時刻までに、その単位が使うすべてのフレームの復号が終わっている
必要がある (+ 融合・出力の処理時間 t_out)。これを満たす最小の D を求める。

処理時間を 0 とすると:
  1系統                           : D = 2B (蓄積 B + 直列化 B)
  2系統・半ブロック単位で融合      : D = 2B (系統 B の待ちは生じない)
  2系統・A の 1ブロック単位で融合  : D = 2.5B (系統 B の後半のフレームを待つため +B/2)
"""
from dataclasses import dataclass

import numpy as np

from .profiles import Profile


@dataclass
class Timing:
    t_enc: float = 0.0       # 符号化・フレーム化 [s]
    t_filt: float = 0.0      # 送受信フィルタと等化器の先読みの遅延 [s]
    t_dec: float = 0.0       # 復調・復号 [s]
    t_out: float = 0.0       # 融合・PLC・出力バッファ [s]
    t_filt_b: float | None = None  # 副系が異なるシンボルレート・フィルタを使うとき [s]


def frame_times(profile: Profile, stream: str, nframes: int, tm: Timing = Timing()):
    """系統 'A' / 'B' のフレームごとの時刻 [s] (dict of arrays)"""
    B = profile.block / profile.fs
    off = 0.0 if stream == "A" else B / 2
    j = np.arange(nframes)
    start = j * B - off
    cap_end = start + B
    tx_start = cap_end + tm.t_enc
    tx_end = tx_start + B                          # T_ser = B
    filter_delay = tm.t_filt_b if stream == "B" and tm.t_filt_b is not None else tm.t_filt
    rx_end = tx_end + filter_delay
    done = rx_end + tm.t_dec
    return {"start": start, "capture_end": cap_end, "tx_start": tx_start, "tx_end": tx_end,
            "rx_end": rx_end, "decoded": done}


def units(profile: Profile, two_streams: bool, unit: str, nunits: int):
    """出力単位ごとに (原音での開始時刻, 使う A のフレーム, 使う B のフレーム一覧)"""
    B = profile.block / profile.fs
    out = []
    if unit == "half":
        for s in range(nunits):
            a = s // 2
            b = [(s + 1) // 2] if two_streams else []
            out.append((s * B / 2, [a], b))
    elif unit == "block":
        for j in range(nunits):
            out.append((j * B, [j], [j, j + 1] if two_streams else []))
    else:
        raise ValueError(unit)
    return out


def min_latency(profile: Profile, two_streams=True, unit="half", tm: Timing = Timing(), nunits=64):
    """すべての出力単位が締切に間に合う最小の一定遅延 D [s]"""
    n = nunits + 4
    tA = frame_times(profile, "A", n, tm)["decoded"]
    tB = frame_times(profile, "B", n, tm)["decoded"]
    need = 0.0
    for t0, fa, fb in units(profile, two_streams, unit, nunits):
        ready = max([tA[i] for i in fa] + [tB[i] for i in fb]) + tm.t_out
        need = max(need, ready - t0)
    return need


def breakdown(profile: Profile, two_streams=True, unit="half", tm: Timing = Timing()):
    """遅延の内訳 [ms] (表示用)"""
    B = profile.block / profile.fs * 1000
    total = min_latency(profile, two_streams, unit, tm) * 1000
    filt = max(tm.t_filt, tm.t_filt_b if two_streams and tm.t_filt_b is not None else tm.t_filt)
    wait = total - (2 * B + (tm.t_enc + filt + tm.t_dec + tm.t_out) * 1000)
    return {"蓄積 (ブロック長)": B, "送信の直列化": B, "符号化": tm.t_enc * 1000,
            "フィルタ": filt * 1000, "復号": tm.t_dec * 1000, "融合・出力": tm.t_out * 1000,
            "系統Bの待ち": max(wait, 0.0), "合計": total}


def rrc_equalizer_delay(profile: Profile, lookahead_symbols=0):
    """Transmit plus receive RRC group delay and FIR equalizer lookahead [s]."""
    from .channel import symbol_rate
    if lookahead_symbols < 0:
        raise ValueError("lookahead_symbols must be nonnegative")
    return (profile.pulse_span + lookahead_symbols) / symbol_rate(profile)


def waveform_timing(main: Profile, sub: Profile | None = None, lookahead_symbols=4):
    """Timing for the reference static equalizer, excluding compute time."""
    return Timing(t_filt=rrc_equalizer_delay(main, lookahead_symbols),
                  t_filt_b=None if sub is None else rrc_equalizer_delay(sub, lookahead_symbols))
