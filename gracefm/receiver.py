"""
受信の出力段。2系統の復号結果 (gracefm.decoder.StreamResult) を 1 本の音声にする。

  1. 2系統の合成: ブロック単位で、両方届いた区間は帯域ごとに融合 (gracefm/fusion.py) / 片方だけなら片方 / どちらも無ければ欠落
  2. 欠落の補間 (LPC): 系統の構成が変わる境目のクロスフェード、欠落区間の PLC (gracefm/plc.py)
  3. 出力 IIR 切替: 品質コードに応じて、高域を落とした出力へ切り替える (gracefm/iir.py)

フレームの復号 (decoder) と、出力の決め方 (ここ) は分けてある。出力段は状態を持たない。
"""
import numpy as np

from . import fusion, plc
from .decoder import QUALITY_MISSING, Decoder
from .fusion import INF_LOG
from .iir import apply_alt
from .profiles import Profile


def block_quality(profile: Profile, qA, qB, offset_b, n_blocks):
    """出力のブロックごとの品質コード (0 正常, 1 高域欠落, 2 欠落)。2系統のときは、良い方の系統の値を採る。
    qA, qB: 各系統のフレームごとの品質コード (qB は 1系統のとき None)。副系のフレームは、出力の時刻から offset_b を引いた位置で対応づける。"""
    b = profile.block
    out = np.full(n_blocks, QUALITY_MISSING, np.int64)
    for i in range(n_blocks):
        q = []
        if i < len(qA):
            q.append(int(qA[i]))
        if qB is not None:
            j = (i * b + offset_b) // b
            if 0 <= j < len(qB):
                q.append(int(qB[j]))
        out[i] = min(q) if q else QUALITY_MISSING
    return out


def output_stage(profile: Profile, y, v, quality, traces, plc_order=16):
    """合成後の音声 y と有効フラグ v を、欠落の補間と出力 IIR 切替にかける。
    quality: 出力ブロックごとの品質コード、traces: 系統ごとの誤差分散 (n, 2, 帯域数)"""
    patterns = [tuple(np.concatenate([(rb[i * profile.block] != INF_LOG).ravel() for rb in traces]))
                for i in range(len(y) // profile.block)]
    y = plc.crossfade_switch(y, patterns, profile.block, order=plc_order)
    y = plc.conceal(y, v, profile.fs, order=plc_order)
    return apply_alt(y, quality, profile.fs, profile.block)


def receive(profile: Profile, framesA, framesB, n, offset_b, plc_order=16,
            return_streams=False, profile_b=None, cipher=None, y_phase_only=False):
    """
    2系統 (framesB=None なら 1系統) を受信して (n, 2) の整数の音声を返す。
    return_streams=True なら stats に各系統の時刻合わせ済み出力と重みの推移も入れる (評価用)。
    profile_b: 副系のプロファイル (None なら主系と同じ)。サンプリング周波数とブロック長は主系と同じであること。
    cipher: 暗号化しているとき、送信側と同じ鍵・nonce の gracefm.crypto.StreamCipher。
    """
    pb = profile if profile_b is None else profile_b
    assert pb.fs == profile.fs and pb.block == profile.block
    A = Decoder(profile, cipher=cipher, y_phase_only=y_phase_only).run(framesA, n, 0)
    B = None
    stats = {"A": A.stats}
    if framesB is not None:
        B = Decoder(pb, cipher=cipher, y_phase_only=y_phase_only).run(framesB, n, offset_b)
        stats["B"] = B.stats
    if B is None:
        y, v, tr = A.pcm, A.valid, None
    else:
        y, v, tr = fusion.fuse_band(A.pcm, A.valid, B.pcm, B.valid, profile.block, profile.levels, A.rb, B.rb)
    if B is not None and return_streams:
        stats.update(yA=A.pcm, vA=A.valid, yB=B.pcm, vB=B.valid, weight_trace=tr)
    stats["plc_samples"] = int((~v).sum())
    n_blocks = -(-len(y) // profile.block)
    quality = block_quality(profile, A.quality, B.quality if B is not None else None, offset_b, n_blocks)
    stats["quality"] = quality
    traces = [A.rb] + ([B.rb] if B is not None else [])
    return output_stage(profile, y, v, quality, traces, plc_order), stats
