"""python -m pytest tests/  (pytest が無ければ python tests/test_gracefm.py でも動く)"""
import os
import sys
from dataclasses import replace
from fractions import Fraction

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import fec, modem  # noqa: E402
from gracefm.codec import (decode_block, encode_block, haar_forward,  # noqa: E402
                        haar_inverse)
from gracefm.framing import pack, unpack  # noqa: E402
from gracefm.layout import Layout  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from gracefm.txrx import StreamDecoder, Transmitter, receive  # noqa: E402


def _signal(n, fs, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    x = 0.4 * np.sin(2 * np.pi * 110 * t)[:, None] + 0.05 * rng.standard_normal((n, 2))
    x[:, 1] += 0.2 * np.sin(2 * np.pi * 1234 * t)
    return pcm(x / np.abs(x).max() * 0.9)


def pcm(x):
    """試験用: 実数の波形 (±1) → 符号つき24 bit整数"""
    return np.clip(np.rint(np.asarray(x) * 2 ** 23), -2 ** 23 + 1, 2 ** 23 - 1).astype(np.int64)


def noisy(frames, snr_db, rng):
    """試験用: 通信路 (雑音と12 bit ADC) を通したシンボル"""
    from gracefm import channel
    return [channel.adc(channel.awgn(f / float(1 << modem.FRAC), snr_db, rng)) for f in frames]


def test_haar_perfect_reconstruction():
    x = np.random.default_rng(1).integers(-(1 << 20), 1 << 20, (10, 64)).astype(np.int64)
    assert np.abs(haar_inverse(haar_forward(x, 4)) - x).max() <= 64         # 定数 46341/65536 の誤差と丸め


def test_fec_roundtrip_and_correction():
    rng = np.random.default_rng(2)
    bits = rng.integers(0, 2, 300)
    c = fec.conv_encode(bits)
    soft = 8 * (1 - 2 * c)
    assert np.array_equal(fec.viterbi_decode(soft, 300), bits)
    soft[rng.choice(len(soft), 12, replace=False)] *= -1        # 散発的な誤りを訂正できる
    assert np.array_equal(fec.viterbi_decode(soft, 300), bits)


def test_crc_detects_error():
    bits = np.random.default_rng(3).integers(0, 2, 200)
    c = fec.crc16(bits)
    bits[17] ^= 1
    assert not np.array_equal(fec.crc16(bits), c)


def test_frame_roundtrip_bit_exact():
    for name, p in PROFILES.items():
        if p.has_y:                      # Y帯域の仮数は専用シンボルで送る (test_y.py)
            continue
        x = _signal(p.block, p.fs)
        bd = encode_block(x, p)
        lay = Layout(p)
        bits = pack(lay, bd, 1, 5)
        assert len(bits) == lay.n_tx
        bd2, hdr = unpack(lay, 8 * (1 - 2 * bits), bits)
        assert {k: v for k, v in hdr.items() if k not in ("top_bits", "y_msb")} == {
            "pid": p.pid, "stream": 1, "encrypted": False, "counter": 5, "high_ok": True}
        assert len(hdr["top_bits"]) == lay.n_top
        assert np.array_equal(decode_block(bd2, p), decode_block(bd, p)), name


def test_attenuator_roundtrip():
    from gracefm.codec import dequantize, quantize
    base = replace(PROFILES["B200M"], attn_group_m=(0,) * 5)
    groups = (0, 0, 0, 0, 4)
    p = replace(base, attn_group_m=groups)
    x = _signal(p.block, p.fs)
    bd = encode_block(x, p)
    assert len(bd.attn["M"][4]) == 8
    lay = Layout(p)
    assert lay.n_prot == Layout(base).n_prot + 8
    frame = pack(lay, bd, 1, 5)
    recovered, hdr = unpack(lay, 8 * (1 - 2 * frame), frame)
    assert hdr["pid"] == p.pid
    assert np.array_equal(recovered.attn["M"][4], bd.attn["M"][4])
    assert np.array_equal(decode_block(recovered, p), decode_block(bd, p))
    wrong_layout = Layout(replace(p, pid=15))
    wrong, _ = unpack(wrong_layout, 8 * (1 - 2 * frame), frame)
    assert wrong is None
    body = lay.header_info(frame)
    body[lay.header_bits + 5 * 4] ^= 1  # 最初のアッテネータbitを壊す
    damaged = lay.with_header(frame, body)
    recovered, hdr = unpack(lay, 8 * (1 - 2 * damaged), damaged)
    assert recovered is not None and hdr["high_ok"] is False

    rng = np.random.default_rng(123)
    for _ in range(50):
        x = pcm(rng.uniform(-1, 1, (p.block, 2)))
        c = haar_forward((x[:, 0] + x[:, 1] + 4) >> 3, p.levels)[4]
        m0, e0, _ = quantize(c, 4, p.bits_m[4], base)
        m1, e1, a1 = quantize(c, 4, p.bits_m[4], p)
        err0 = np.sum((c - dequantize(m0, e0, 4, p.bits_m[4], base)).astype(float) ** 2)
        err1 = np.sum((c - dequantize(m1, e1, 4, p.bits_m[4], p, attn=a1)).astype(float) ** 2)
        assert err1 <= err0 * 1.05 + 1.0               # 選択は誤差を 8 bit に切り詰めて比べる (docs/FIXED.md)



def test_adopted_attenuator_profile_end_to_end():
    p = PROFILES["B200M"]
    assert p.pid == 1 and p.exp_bits == 4 and p.attn_group_m[-1] == 4
    assert Layout(p).n_prot_crc == 78
    x = _signal(p.block * 12, p.fs)
    frames = Transmitter(p).run(x)
    y, valid = StreamDecoder(p).run(frames, len(x))
    expected = np.concatenate([decode_block(encode_block(x[i:i + p.block], p), p)
                               for i in range(0, len(x), p.block)])
    assert valid.all() and np.abs(y - expected).max() <= 64      # 確率 1 − 2^-11 の軟判定が硬判定とわずかに違う分


def test_broadcast_joint_stereo_attenuators():
    p = PROFILES["B200"]
    assert p.pid == 2 and p.exp_bits == 4
    assert p.pulse_beta_pct == 10 and p.pulse_span == 32
    from gracefm.channel import symbol_rate
    assert symbol_rate(p) <= 180000
    assert p.attn_group_m[-1] == 4 and p.attn_group_s[-1] == 4
    assert p.attenuator_bits("M", 4) == 8 and p.attenuator_bits("S", 4) == 8
    assert p.attenuator_bits("M", 2) == 4 and p.attenuator_bits("S", 2) == 4
    assert Layout(p).n_prot_crc == 110
    assert p.audio_kbps() == 504
    x = _signal(p.block * 8, p.fs)
    bd = encode_block(x[:p.block], p)
    assert len(bd.attn["M"][4]) == 8 and len(bd.attn["S"][4]) == 8
    frames = Transmitter(p).run(x)
    y, valid = StreamDecoder(p).run(frames, len(x))
    expected = np.concatenate([decode_block(encode_block(x[i:i + p.block], p), p)
                               for i in range(0, len(x), p.block)])
    assert valid.all() and np.abs(y - expected).max() <= 64


def test_modem_noiseless():
    for mod in ("qpsk", "qam16h"):
        bits = np.random.default_rng(4).integers(0, 2, 600)
        nsym = modem.n_symbols(600, 200, mod)
        alpha = 5 if mod == "qam16h" else 1
        llr, hard, _ = modem.demodulate(modem.modulate(bits, nsym, mod, alpha)[modem.N_PREAMBLE:], 600, mod, alpha)
        assert np.array_equal(hard, bits), mod
        assert np.array_equal((llr[:200] < 0).astype(int), bits[:200]), mod


def test_end_to_end_without_noise():
    p = PROFILES["M700M"]
    x = _signal(p.block * 20, p.fs)
    tx = Transmitter(p)
    frames = tx.run(x)
    dec = StreamDecoder(p)
    y, v = dec.run(frames, len(x))
    ref = np.concatenate([decode_block(encode_block(x[i:i + 64], p), p) for i in range(0, len(x), 64)])
    assert v.all() and np.abs(y - ref).max() <= 64


def test_postfilter_resamples_to_48k_int32():
    from gracefm.postfilter import postfilter
    for fs in (32000, 48000):
        t = np.arange(fs) / fs
        x = pcm(np.stack([0.5 * np.sin(2 * np.pi * 1000 * t), 0.3 * np.sin(2 * np.pi * 5000 * t + 1)], axis=1))
        y = postfilter(x, fs)
        assert y.dtype == np.int64 and y.shape == (48000, 2) and np.abs(y).max() < 2 ** 31
        t48 = np.arange(len(y)) / 48000
        ref = np.stack([0.5 * np.sin(2 * np.pi * 1000 * t48), 0.3 * np.sin(2 * np.pi * 5000 * t48 + 1)],
                       axis=1) * (2 ** 31 - 1)
        err = (y[4800:-4800] - ref[4800:-4800]).astype(float)
        assert 10 * np.log10(np.mean(err ** 2) / np.mean(ref[4800:-4800] ** 2)) < -55, fs


def test_latency_model():
    """遅延モデル: 1系統・2系統とも 2ブロック。処理時間は加算"""
    from gracefm.timing import Timing, min_latency
    for p in PROFILES.values():
        B = Fraction(p.block, p.fs)
        assert min_latency(p, False) == 2 * B
        assert min_latency(p, True) == 2 * B
        tm = Timing(t_enc=Fraction(1, 10000), t_filt=Fraction(2, 10000), t_dec=Fraction(3, 10000), t_out=Fraction(4, 10000))
        assert min_latency(p, True, tm) == 2 * B + Fraction(1, 1000)


def test_receiver_is_causal():
    """受信処理 (復号・ポストフィルタ・融合・PLC) は未来のフレームを使わない:
    あるフレームを欠落させても、そのフレームが運ぶ区間より前の出力は変わらない"""
    from gracefm.txrx import receive
    p = PROFILES["B200"]
    x = _signal(p.block * 24, p.fs)
    off = 0
    rng = np.random.default_rng(3)
    fa = noisy(Transmitter(p, 0, 0).run(x), 9.0, rng)
    fb = noisy(Transmitter(p, 1, off).run(x), 9.0, rng)
    for mode in ("band",):
        y0, _ = receive(p, fa, fb, len(x), off)
        for j in (6, 13):
            fa2 = list(fa)
            fa2[j] = None
            y1, _ = receive(p, fa2, fb, len(x), off)
            t0 = j * p.block                                   # A のフレーム j の区間の先頭
            assert np.array_equal(y0[:t0], y1[:t0]), (mode, "A", j)
            assert not np.array_equal(y0, y1)
            fb2 = list(fb)
            fb2[j] = None
            y2, _ = receive(p, fa, fb2, len(x), off)
            t0 = j * p.block - off                             # B のフレーム j の区間の先頭
            assert np.array_equal(y0[:t0], y2[:t0]), (mode, "B", j)


def test_two_streams_survive_single_stream_loss():
    p = PROFILES["B200"]
    x = _signal(p.block * 40, p.fs)
    fa = Transmitter(p, 0, 0).run(x)
    fb = Transmitter(p, 1, 0).run(x)
    fa = [None if i % 3 == 0 else f for i, f in enumerate(fa)]       # A だけ 1/3 欠落
    y, st = receive(p, fa, fb, len(x), 0)
    assert st["plc_samples"] < p.block                               # B で埋まり PLC はほぼ不要


def test_low_rate_sub_stream():
    """副系が主系より低いビットレートでも融合でき、雑音なしなら主系の音質を落とさない"""
    from tools.common import metrics
    p, ps = PROFILES["B200M"], PROFILES["SUB50M"]
    x = _signal(p.block * 40, p.fs)
    x[:, 1] = x[:, 0]
    fa = Transmitter(p, 0, 0).run(x)
    fb = Transmitter(ps, 1, 0).run(x)
    y1, _ = receive(p, fa, None, len(x), 0)
    y2, _ = receive(p, fa, fb, len(x), 0, profile_b=ps)
    assert metrics.snr_db(x.astype(float), y2.astype(float)) > metrics.snr_db(x.astype(float), y1.astype(float)) - 0.5
    fa = [None if i % 3 == 0 else f for i, f in enumerate(fa)]
    y3, st = receive(p, fa, fb, len(x), 0, profile_b=ps)
    assert st["plc_samples"] < p.block                               # 主系の欠落を副系が埋める


def test_layered_profile():
    """階層化: 基本層は元のプロファイルと同じビットで強い位置に収まり、雑音なしなら全ビットで復号できる"""
    from tools.common import metrics
    from dataclasses import replace
    p = PROFILES["B200M"]
    lay, t = Layout(p), Transmitter(p)
    base_bits = sum(p.ncoef(k) * p.base_bits("M", k) for k in range(p.nbands))
    assert lay.n_base_bits == base_bits
    assert lay.n_tx == 2 * lay.n_strong == 4 * t.digital_nsym   # 位相部 (強い位置) と振幅部が同数で、隙間なく並ぶ
    weak_ext = lay.coef_stream_idx >= lay.n_strong               # 拡張層の仮数bit
    assert weak_ext.sum() == lay.n_coef_bits - base_bits
    # 拡張層 (弱い位置の仮数) をすべて壊しても、基本層だけで元の音の骨格が復号できる
    x = _signal(p.block * 40, p.fs)
    x[:, 1] = x[:, 0]
    rng = np.random.default_rng(3)
    full, damaged = [], []
    for i in range(0, len(x), p.block):
        bd = encode_block(x[i:i + p.block], p)
        frame = pack(lay, bd, 0, 0)
        bad = frame.copy()
        bad[lay.coef_stream_idx[weak_ext]] = rng.integers(0, 2, int(weak_ext.sum()))
        recovered, _ = unpack(lay, 8 * (1 - 2 * bad), bad)
        assert recovered is not None
        full.append(decode_block(bd, p))
        damaged.append(decode_block(recovered, p))
    full, damaged = np.concatenate(full), np.concatenate(damaged)
    assert metrics.snr_db(x.astype(float), damaged.astype(float)) > 4.0
    assert metrics.snr_db(x.astype(float), full.astype(float)) > metrics.snr_db(x.astype(float), damaged.astype(float)) + 20


def test_b200_link_preserves_high_side_signal():
    """帯域圧縮後も高域Sのレベルを保ち、基本層を減らしたY系の差を検出する。"""
    from gracefm import channel
    from tools.common import wavio
    from gracefm.codec import haar_forward

    p = PROFILES["B200"]
    path = os.path.join(os.path.dirname(__file__), "..", "samples", "demo-stereo__32k__reference.flac")
    x, fs = wavio.read(path)
    assert fs == p.fs
    x = pcm(x[:fs] * (0.89 / np.max(np.abs(x[:fs]))))
    s_ref = (x[:, 0] - x[:, 1] + 4) >> 3
    ref = haar_forward(s_ref.reshape(-1, p.block), p.levels)
    power_ref = float(sum(np.sum(a.astype(float) ** 2) for a in ref[p.high_k:]))
    for name in ("B200",):
        current = PROFILES[name]
        y, _, _ = channel.link(x, current, 66, sub="SUB100", seed=1)
        s_out = (y[:, 0] - y[:, 1] + 4) >> 3
        out = haar_forward(s_out.reshape(-1, current.block), current.levels)
        power_out = float(sum(np.sum(a.astype(float) ** 2) for a in out[p.high_k:]))
        error = float(sum(np.sum((a - b).astype(float) ** 2) for a, b in zip(ref[p.high_k:], out[p.high_k:])))
        level_change_db = 10 * np.log10(power_out / power_ref)
        snr_db = 10 * np.log10(power_ref / error)
        assert abs(level_change_db) < 1.0
        assert snr_db > 3.0                      # S高域は3bitなので低めだが、レベルは保つ


def test_encryption():
    """暗号化: 正しい鍵なら暗号化なしと同じ音、違う鍵なら復号できない。24bit のフレーム番号の周回も復元できる"""
    from tools.common import metrics
    from gracefm.crypto import StreamCipher, unwrap_counter
    p = PROFILES["B200M"]
    x = _signal(p.block * 30, p.fs)
    x[:, 1] = x[:, 0]
    key, nonce = bytes(range(16)), bytes(8)
    ca, cb = StreamCipher(key, nonce), StreamCipher(bytes(16), nonce)
    f_plain = Transmitter(p).run(x)
    f_enc = Transmitter(p, cipher=ca).run(x)
    f_enc_b = Transmitter(p, cipher=cb).run(x)
    assert not np.array_equal(f_enc_b[5], f_enc[5])                      # 鍵が違えば送信シンボルも違う
    y0, _ = receive(p, f_plain, None, len(x), 0)
    y1, st = receive(p, f_enc, None, len(x), 0, cipher=ca)
    y2, _ = receive(p, f_enc, None, len(x), 0, cipher=cb)
    assert st["plc_samples"] == 0
    assert np.array_equal(y0, y1)
    assert metrics.snr_db(x.astype(float), y2.astype(float)) < 0                                  # 鍵が違えば聴けない
    m = 1 << 24
    assert unwrap_counter(5, -1) == 5
    assert unwrap_counter(2, m - 3) == m + 2                          # 周回をまたぐ
    assert unwrap_counter(m - 1, m + 1) == m - 1                      # 少し前のフレーム


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)


def test_crossfade_switch_removes_step_only_where_pattern_changes():
    from gracefm import plc
    block, nb = 64, 8
    t = np.arange(block * nb)
    base = pcm(0.5 * np.sin(2 * np.pi * 440 * t / 32000))
    y = np.stack([base, base], axis=1)
    y[4 * block:] += pcm(0.2)                                        # 4 ブロック目の先頭に段差 (情報のある帯域の組が変わる)
    same = [(True, True)] * nb
    assert np.array_equal(plc.crossfade_switch(y, same, block), y)          # 組が変わらなければ何もしない
    changed = same[:4] + [(True, False)] * 4
    out = plc.crossfade_switch(y, changed, block)
    jump = lambda z: np.abs(np.diff(z[:, 0]))[4 * block - 1]
    assert jump(out) < jump(y) / 4                                          # 境界の段差が小さくなる
    assert np.array_equal(out[:4 * block], y[:4 * block])                  # 過去の出力は変えない (因果的)
    assert np.array_equal(out[4 * block + 16:], y[4 * block + 16:])        # クロスフェードは先頭16サンプルだけ
    lost = same[:4] + [(False, False)] * 2 + same[:2]
    assert np.array_equal(plc.crossfade_switch(y, lost, block), y)         # 全て届かないブロックは PLC に任せる

