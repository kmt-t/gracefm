"""python -m pytest tests/  (pytest が無ければ python tests/test_gracefm.py でも動く)"""
import os
import sys
from dataclasses import replace
from fractions import Fraction

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from helpers import header_info, with_header

from gracefm import fec, modem
from gracefm.codec import (
    FRAC,
    attenuator_expanded,
    encode_block,
    exp_range,
    haar_forward,
    haar_inverse,
    quantize_band,
)
from gracefm.decoder import (
    Decoder,
    reconstruct,
)
from gracefm.dsp import saturate, shift_signed
from gracefm.encoder import Encoder
from gracefm.framing import pack, unpack
from gracefm.layout import Layout
from gracefm.profiles import PROFILES
from gracefm.receiver import receive


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
    return [channel.adc(channel.awgn(f / float(1 << modem.SYM_FRAC), snr_db, rng)) for f in frames]


def test_haar_perfect_reconstruction():
    x = np.random.default_rng(1).integers(-(1 << 20), 1 << 20, (10, 64)).astype(np.int64)
    assert np.array_equal(haar_inverse(haar_forward(x, 4)), x)              # 整数可逆


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
    c = fec.crc_core(bits)
    bits[17] ^= 1
    assert not np.array_equal(fec.crc_core(bits), c)


def test_frame_roundtrip_bit_exact():
    for name, p in PROFILES.items():
        if p.has_y or p.overlapped:      # Y帯域の仮数は専用シンボルで送る (test_y.py)。ブロックをまたぐ帯域分割は test_legall.py
            continue
        x = _signal(p.block, p.fs)
        bd = encode_block(x, p)
        lay = Layout(p)
        bits = pack(lay, bd, 1, 5)
        assert len(bits) == lay.n_tx
        res = unpack(lay, 8 * (1 - 2 * bits), bits)
        assert (res.pid, res.stream, res.counter, res.high_ok, res.frame_no) == (p.pid, 1, 5, True, None)
        assert len(res.top_bits) == lay.n_top
        assert np.array_equal(reconstruct(res.bd, p), reconstruct(bd, p)), name


def test_attenuator_roundtrip():
    base = replace(PROFILES["B200M"], attn_group_m=(0,) * 5)
    groups = (0, 0, 0, 0, 4)
    p = replace(base, attn_group_m=groups)
    x = _signal(p.block, p.fs)
    bd = encode_block(x, p)
    assert len(bd.attn["M"][4]) == 8
    lay = Layout(p)
    assert lay.n_prot == Layout(base).n_prot + 8
    frame = pack(lay, bd, 1, 5)
    res = unpack(lay, 8 * (1 - 2 * frame), frame)
    assert res.pid == p.pid
    assert np.array_equal(res.bd.attn["M"][4], bd.attn["M"][4])
    assert np.array_equal(reconstruct(res.bd, p), reconstruct(bd, p))
    wrong_layout = Layout(replace(p, pid=15))
    res = unpack(wrong_layout, 8 * (1 - 2 * frame), frame)
    assert res is None
    body = header_info(lay, frame)
    body[lay.header_bits + 5 * 4] ^= 1  # 最初のアッテネータbitを壊す
    damaged = with_header(lay, frame, body)
    res = unpack(lay, 8 * (1 - 2 * damaged), damaged)
    assert res is not None and res.high_ok is False

    def dequantize_band(m, e, a, profile):                 # 1 帯域の復元 (軟判定の式と同じ: 指数と減衰の分だけ右シフト)
        s = int(e) + exp_range(4, p.bits_m[4], profile)[0] + FRAC
        shift = s - (attenuator_expanded(a, profile.attenuator_group("M", 4), len(m)) if a is not None else 0)
        return saturate(shift_signed(m, shift))

    rng = np.random.default_rng(123)
    for _ in range(50):
        x = pcm(rng.uniform(-1, 1, (p.block, 2)))
        c = haar_forward((x[:, 0] + x[:, 1] + 4) >> 3, p.levels)[4]
        m0, e0, _ = quantize_band(c, "M", 4, base)
        m1, e1, a1 = quantize_band(c, "M", 4, p)
        err0 = np.sum((c - dequantize_band(m0, e0, None, base)).astype(float) ** 2)
        err1 = np.sum((c - dequantize_band(m1, e1, a1, p)).astype(float) ** 2)
        assert err1 <= err0 * 1.05 + 1.0               # 選択は誤差を 8 bit に切り詰めて比べる (docs/FIXED.md)



def test_adopted_attenuator_profile_end_to_end():
    p = PROFILES["B200M"]
    assert p.pid == 1 and p.exp_bits == 4 and p.attn_group_m[-1] == 4
    assert Layout(p).n_prot_crc == 78
    x = _signal(p.block * 12, p.fs)
    frames = Encoder(p).run(x)
    result = Decoder(p).run(frames, len(x))
    y, valid = result.pcm, result.valid
    expected = np.concatenate([reconstruct(encode_block(x[i:i + p.block], p), p)
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
    assert p.audio_kbps() == 500
    x = _signal(p.block * 8, p.fs)
    bd = encode_block(x[:p.block], p)
    assert len(bd.attn["M"][4]) == 8 and len(bd.attn["S"][4]) == 8
    frames = Encoder(p).run(x)
    result = Decoder(p).run(frames, len(x))
    y, valid = result.pcm, result.valid
    expected = np.concatenate([reconstruct(encode_block(x[i:i + p.block], p), p)
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
    tx = Encoder(p)
    frames = tx.run(x)
    dec = Decoder(p)
    result = dec.run(frames, len(x))
    y, v = result.pcm, result.valid
    ref = np.concatenate([reconstruct(encode_block(x[i:i + 64], p), p) for i in range(0, len(x), 64)])
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
    """遅延モデル: 1系統・2系統とも 2ブロック (ブロックをまたぐ帯域分割は先読みの分を足す)。処理時間は加算"""
    from gracefm.iir import ALT_DELAY
    from gracefm.timing import Timing, min_latency
    for p in PROFILES.values():
        B = Fraction(p.block, p.fs)
        alt = Fraction(ALT_DELAY[p.fs] + p.encoder_lookahead + p.synth_reach_before, p.fs)   # 切り替え先の IIR に揃える遅延と先読み
        assert min_latency(p, False) == 2 * B + alt
        assert min_latency(p, True) == 2 * B + alt
        tm = Timing(t_enc=Fraction(1, 10000), t_filt=Fraction(2, 10000), t_dec=Fraction(3, 10000), t_out=Fraction(4, 10000))
        assert min_latency(p, True, tm) == 2 * B + Fraction(1, 1000) + alt


def test_postfilter_48k_passes_through_and_32k_rejects_images():
    from gracefm.postfilter import postfilter
    rng = np.random.default_rng(4)
    x = rng.integers(-2 ** 23 + 1, 2 ** 23, (480, 2))
    assert np.array_equal(postfilter(x, 48000), x << 8)                 # 48 kHz 系はフィルタなし
    t = np.arange(32000) / 32000
    y = postfilter(pcm(0.5 * np.sin(2 * np.pi * 14000 * t)[:, None]), 32000)[2000:-2000, 0].astype(float)
    spectrum = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    f = np.fft.rfftfreq(len(y), 1 / 48000)
    tone, image = spectrum[np.abs(f - 14000) < 20].max(), spectrum[np.abs(f - 18000) < 20].max()
    assert 10 * np.log10(image / tone) < -45                            # 14 kHz の鏡像 (18 kHz)


def test_receiver_is_causal():
    """受信処理 (復号・ポストフィルタ・融合・PLC) は未来のフレームを使わない:
    あるフレームを欠落させても、そのフレームが運ぶ区間より前の出力は変わらない"""
    from gracefm.receiver import receive
    p = PROFILES["B200"]
    x = _signal(p.block * 24, p.fs)
    off = 0
    rng = np.random.default_rng(3)
    fa = noisy(Encoder(p, 0, 0).run(x), 9.0, rng)
    fb = noisy(Encoder(p, 1, off).run(x), 9.0, rng)
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
    fa = Encoder(p, 0, 0).run(x)
    fb = Encoder(p, 1, 0).run(x)
    fa = [None if i % 3 == 0 else f for i, f in enumerate(fa)]       # A だけ 1/3 欠落
    _y, st = receive(p, fa, fb, len(x), 0)
    assert st["plc_samples"] < p.block                               # B で埋まり PLC はほぼ不要


def test_low_rate_sub_stream():
    """副系が主系より低いビットレートでも融合でき、雑音なしなら主系の音質を落とさない"""
    from tools.common import metrics
    p, ps = PROFILES["B200M"], PROFILES["SUB50M"]
    x = _signal(p.block * 40, p.fs)
    x[:, 1] = x[:, 0]
    fa = Encoder(p, 0, 0).run(x)
    fb = Encoder(ps, 1, 0).run(x)
    y1, _ = receive(p, fa, None, len(x), 0)
    y2, _ = receive(p, fa, fb, len(x), 0, profile_b=ps)
    assert metrics.snr_db(x.astype(float), y2.astype(float)) > metrics.snr_db(x.astype(float), y1.astype(float)) - 0.5
    fa = [None if i % 3 == 0 else f for i, f in enumerate(fa)]
    _y3, st = receive(p, fa, fb, len(x), 0, profile_b=ps)
    assert st["plc_samples"] < p.block                               # 主系の欠落を副系が埋める


def test_layered_profile():
    """階層化: 基本層は元のプロファイルと同じビットで強い位置に収まり、雑音なしなら全ビットで復号できる"""
    from tools.common import metrics
    p = PROFILES["B200M"]
    lay, t = Layout(p), Encoder(p)
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
        res = unpack(lay, 8 * (1 - 2 * bad), bad)
        assert res is not None
        full.append(reconstruct(bd, p))
        damaged.append(reconstruct(res.bd, p))
    full, damaged = np.concatenate(full), np.concatenate(damaged)
    assert metrics.snr_db(x.astype(float), damaged.astype(float)) > 4.0
    assert metrics.snr_db(x.astype(float), full.astype(float)) > metrics.snr_db(x.astype(float), damaged.astype(float)) + 20


def test_b200_link_preserves_high_side_signal():
    """帯域圧縮後も高域Sのレベルを保ち、基本層を減らしたY系の差を検出する。"""
    from gracefm import channel
    from gracefm.codec import haar_forward
    from tools.samples.make_samples import load_material

    p = PROFILES["B200"]
    x = load_material("demo", None, 0.0, None, p.fs)                  # 試料の原音と同じ合成信号 (samples/ は使わない)
    x = pcm(x[:p.fs] * (0.89 / np.max(np.abs(x[:p.fs]))))
    from gracefm.iir import ALT_DELAY
    d = ALT_DELAY[p.fs]
    x_ref = np.concatenate([np.zeros((d, 2), np.int64), x[:-d]])      # 出力は切り替え先の遅延の分だけ遅れる
    s_ref = (x_ref[:, 0] - x_ref[:, 1] + 4) >> 3
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
    from gracefm.crypto import StreamCipher, unwrap_counter
    from tools.common import metrics
    p = PROFILES["B200M"]
    x = _signal(p.block * 30, p.fs)
    x[:, 1] = x[:, 0]
    key, nonce = bytes(range(16)), bytes(8)
    ca, cb = StreamCipher(key, nonce), StreamCipher(bytes(16), nonce)
    f_plain = Encoder(p).run(x)
    f_enc = Encoder(p, cipher=ca).run(x)
    f_enc_b = Encoder(p, cipher=cb).run(x)
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


def test_header_recovery_flips_least_reliable_bits():
    """基本CRCが合わないフレームは、ヘッダの信頼度の低い bit を反転して救える場合がある。救えた内容は正しく、試行回数は上限内。"""
    from gracefm import channel
    from gracefm.decoder import unpack_recovering
    from gracefm.encoder import Encoder
    p = PROFILES["B200M"]
    lay = Layout(p)
    rng = np.random.default_rng(4)
    esn0 = 55 - 10 * np.log10(channel.symbol_rate(p))              # 失敗が多く出る条件 (救済の検査用)
    recovered = 0
    for i in range(120):
        x = np.clip(rng.normal(size=(p.block, 2)) * 2**20, -2**22, 2**22).astype(np.int64)
        tx = Encoder(p, 0)
        tx.frame_no = i
        sym = tx.frame(x)
        noisy = channel.adc(channel.awgn(sym[modem.N_PREAMBLE:] / float(1 << modem.SYM_FRAC), esn0, rng))
        llr, hard, _ = modem.demodulate(noisy[:tx.digital_nsym], lay.n_tx, p.modulation, p.alpha)
        s = modem.prbs(lay.n_tx)
        soft, hard = np.where(s == 1, -llr, llr), hard ^ s
        if unpack(lay, soft, hard) is not None:
            continue
        found = unpack_recovering(lay, soft, hard)
        if found is None:
            continue
        u, flips = found
        recovered += 1
        assert u.counter == i and flips >= 1
    # 救済の試行回数は計算量の見積もりの上限 (通常の復号を含めて 29 回) に収まる
    from math import comb

    from gracefm import decoder
    assert 1 + sum(comb(decoder.RECOVER_CANDIDATES, t) for t in range(1, decoder.RECOVER_MAX_FLIPS + 1)) <= 29


def test_block_quality_marks_lost_frames_and_switch_is_identity_when_clean():
    """受信の品質コードは、欠落フレームを 2 として出す。切り替えは、コードが 0 のときは y をそのまま返す。"""
    from gracefm.encoder import Encoder
    from gracefm.postfilter import select_by_quality
    from gracefm.receiver import receive
    p = PROFILES["B200M"]
    rng = np.random.default_rng(8)
    x = np.clip(np.cumsum(rng.normal(size=(p.block * 20, 2)), axis=0) * 2**10, -2**22, 2**22).astype(np.int64)
    frames = Encoder(p, 0).run(x)
    lost = {5, 6}
    rx = [None if i in lost else f for i, f in enumerate(frames)]
    _y, stats = receive(p, rx, None, len(x), 0, return_streams=False)
    q = stats["quality"]
    assert len(q) == len(x) // p.block
    assert all(q[i] == 2 for i in lost) and all(q[i] == 0 for i in range(len(q)) if i not in lost)
    clean = np.arange(len(q)) * 0
    yy = np.arange(p.block * len(q) * 2).reshape(-1, 2)
    assert np.array_equal(select_by_quality(yy, yy * 0, clean, p.block), yy)
    sel = select_by_quality(yy, yy * 0 + 7, np.full(len(q), 2), p.block)
    assert np.all(sel[p.block:] == 7)                            # 1 ブロック目以降は alt に切り替わっている
    assert sel[0, 0] == yy[0, 0]                                  # 先頭のサンプルは切り替え前の y


def test_quality_marks_profiles_without_high_bands():
    """高域を送らないプロファイル (SUB) は、届いたフレームでも品質 1 (高域欠落) になる。"""
    from gracefm.encoder import Encoder
    from gracefm.receiver import receive
    p = PROFILES["SUB50M"]
    rng = np.random.default_rng(9)
    x = np.clip(np.cumsum(rng.normal(size=(p.block * 8, 1)), axis=0) * 2**10, -2**22, 2**22).astype(np.int64)
    x = np.repeat(x, 2, axis=1)
    frames = Encoder(p, 0).run(x)
    _, stats = receive(p, frames, None, len(x), 0)
    assert np.all(stats["quality"] == 1)


def test_alt_iir_coefficients_fit_18_bit_and_are_stable():
    """切り替え先の IIR の係数は 18 bit 符号つき (Q16)、極は単位円の内側、低域通過の区間は b1 = 2·b0、b2 = b0"""
    from gracefm.iir import alt_sections
    for fs in (32000, 48000):
        for b0, a1, a2 in alt_sections(fs):
            assert all(abs(c) < 1 << 17 for c in (b0, a1, a2))
            assert np.abs(np.roots([1, a1 / 65536, a2 / 65536])).max() < 1


def test_alt_iir_matches_float_design_and_switches_only_marked_blocks():
    """切り替え先の整数 IIR は、浮動小数点の設計 (Butterworth 4 次、4 kHz) とほぼ一致する。
    切り替えは、コードが 1 か 2 のブロックだけ。それ以外は遅延させた入力そのもの。"""
    from scipy.signal import butter, sosfilt

    from gracefm.iir import ALT_DELAY, alt_sections, apply_alt, iir_filter
    rng = np.random.default_rng(12)
    for fs in (32000, 48000):
        x = np.clip(np.cumsum(rng.normal(size=(4000, 2)), axis=0) * 2**12, -2**22, 2**22).astype(np.int64)
        ref = sosfilt(butter(4, 4000, fs=fs, output="sos"), x.astype(float), axis=0)
        # 係数は Q16 の固定 (仕様の 18 bit)。丸めのずれは、ランダムウォーク入力で 48 kHz 約 440 LSB、32 kHz 約 70 LSB (FIXED.md)
        assert np.abs(iir_filter(x, alt_sections(fs)) - ref).max() < 512
        block = 64
        q = np.array([0, 2, 0] + [0] * (len(x) // block - 3))
        out = apply_alt(x, q, fs, block)
        d = ALT_DELAY[fs]
        delayed = np.concatenate([np.zeros((d, 2), np.int64), x[:-d]])
        assert np.array_equal(out[:block], delayed[:block])                       # 切り替えなしのブロック
        back = 2 * block + fs // 1000                                             # 戻りのフェード (1 ms) のあと
        assert np.array_equal(out[back:], delayed[back:])
        assert not np.array_equal(out[block + fs // 1000:2 * block], delayed[block + fs // 1000:2 * block])
