"""python -m pytest tests/  (pytest が無ければ python tests/test_gracefm.py でも動く)"""
import os
import sys
from dataclasses import replace

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import fec, modem  # noqa: E402
from gracefm.codec import (decode_block, decode_coeffs, encode_block, haar_forward,  # noqa: E402
                        haar_inverse)
from gracefm.framing import Layout  # noqa: E402
from gracefm.postfilter import PostFilter  # noqa: E402
from gracefm.profiles import PROFILES  # noqa: E402
from gracefm.txrx import StreamDecoder, Transmitter, receive  # noqa: E402


def _signal(n, fs, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    x = 0.4 * np.sin(2 * np.pi * 110 * t)[:, None] + 0.05 * rng.standard_normal((n, 2))
    x[:, 1] += 0.2 * np.sin(2 * np.pi * 1234 * t)
    return x / np.abs(x).max() * 0.9


def test_haar_perfect_reconstruction():
    x = np.random.default_rng(1).standard_normal((10, 64))
    assert np.allclose(haar_inverse(haar_forward(x, 6)), x)


def test_fec_roundtrip_and_correction():
    rng = np.random.default_rng(2)
    bits = rng.integers(0, 2, 300)
    c = fec.conv_encode(bits)
    soft = 1.0 - 2.0 * c
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
        x = _signal(p.block, p.fs)
        bd = encode_block(x, p)
        lay = Layout(p)
        bits = lay.pack(bd, 1, 5)
        assert len(bits) == lay.n_tx
        bd2, hdr = lay.unpack(1.0 - 2.0 * bits[: lay.n_coded], bits[lay.n_coded:])
        assert hdr == {"pid": p.pid, "stream": 1, "encrypted": False, "counter": 5}
        assert np.allclose(decode_block(bd2, p), decode_block(bd, p)), name


def test_band_exponents_use_fixed_offsets_and_variable_widths():
    from gracefm.codec import exp_range

    base = PROFILES["B200M"]
    widths = (4, 3, 4, 3, 4, 3, 4)
    offsets = tuple(exp_range(k, b, base)[1] - (2 ** widths[k] - 1)
                    for k, b in enumerate(base.bits_m))
    p = replace(base, exp_bits_m=widths, exp_offset_m=offsets)
    x = _signal(p.block, p.fs)
    bd = encode_block(x, p)
    lay = Layout(p)
    assert lay.n_prot == Layout(base).n_prot - 3
    for k, b in enumerate(p.bits_m):
        assert exp_range(k, b, p) == (offsets[k], offsets[k] + 2 ** widths[k] - 1)
    frame = lay.pack(bd, 1, 5)
    decoded, header = lay.unpack(1.0 - 2.0 * frame[:lay.n_coded], frame[lay.n_coded:])
    assert header["pid"] == p.pid
    assert np.allclose(decode_block(decoded, p), decode_block(bd, p))


def test_attenuator_roundtrip():
    from gracefm.codec import cells, dequantize, quantize, quantize_attenuated
    base = PROFILES["B200MH"]
    groups = (0, 0, 0, 0, 0, 0, 4)
    p = replace(base, attn_group_m=groups)
    x = _signal(p.block, p.fs)
    bd = encode_block(x, p)
    assert len(bd.attn["M"][6]) == 8
    lay = Layout(p)
    assert lay.n_prot == Layout(base).n_prot + 8
    frame = lay.pack(bd, 1, 5)
    recovered, hdr = lay.unpack(1.0 - 2.0 * frame[:lay.n_coded], frame[lay.n_coded:])
    assert hdr["pid"] == p.pid
    assert np.array_equal(recovered.attn["M"][6], bd.attn["M"][6])
    assert np.allclose(decode_block(recovered, p), decode_block(bd, p))
    wrong_layout = Layout(replace(p, pid=15))
    wrong, _ = wrong_layout.unpack(1.0 - 2.0 * frame[:lay.n_coded], frame[lay.n_coded:])
    assert wrong is None
    body = fec.viterbi_decode(1.0 - 2.0 * frame[:lay.n_coded], lay.n_prot_crc)
    body[16 + 7 * 4] ^= 1  # 最初のアッテネータbitを壊す
    damaged = np.concatenate([fec.conv_encode(body), frame[lay.n_coded:]])
    rejected, _ = lay.unpack(1.0 - 2.0 * damaged[:lay.n_coded], damaged[lay.n_coded:])
    assert rejected is None

    rng = np.random.default_rng(123)
    for _ in range(50):
        x = rng.uniform(-1, 1, (p.block, 2))
        bd = encode_block(x, p)
        c = haar_forward((x[:, 0] + x[:, 1]) / 2, p.levels)[6]
        m, e, a = bd.mant["M"][6], bd.eidx["M"][6], bd.attn["M"][6]
        lo, hi = cells(m, e, 6, p.bits_m[6], p, "M", a)
        assert np.all(c >= lo - 1e-12) and np.all(c <= hi + 1e-12)
        m0, e0 = quantize(c, 6, p.bits_m[6], base)
        m1, e1, a1 = quantize_attenuated(c, 6, p.bits_m[6], p)
        err0 = np.sum((c - dequantize(m0, e0, 6, p.bits_m[6], base)) ** 2)
        err1 = np.sum((c - dequantize(m1, e1, 6, p.bits_m[6], p, attn=a1)) ** 2)
        assert err1 <= err0 + 1e-20

    # 指数幅を帯域ごとに減らした同レート案でも、区間ビットの位置が一致する。
    narrow = replace(p, exp_bits_m=(3, 3, 3, 3, 2, 3, 3),
                     exp_offset_m=(-18, -18, -19, -20, -17, -20, -18))
    assert Layout(narrow).n_prot_crc == Layout(base).n_prot_crc
    bd = encode_block(_signal(narrow.block, narrow.fs) * 0.01, narrow)
    lay = Layout(narrow)
    frame = lay.pack(bd, 0, 1)
    recovered, _ = lay.unpack(1.0 - 2.0 * frame[:lay.n_coded], frame[lay.n_coded:])
    assert np.allclose(decode_block(recovered, narrow), decode_block(bd, narrow))


def test_adopted_attenuator_profile_end_to_end():
    p = PROFILES["B200MH-A4"]
    assert p.pid == 14 and p.exp_bits == 4 and p.attn_group_m[-1] == 4
    assert Layout(p).n_prot_crc == 132
    x = _signal(p.block * 12, p.fs)
    frames = Transmitter(p).run(x)
    y, valid = StreamDecoder(p, postfilter=False).run(frames, len(x))
    expected = np.concatenate([decode_block(encode_block(x[i:i + p.block], p), p)
                               for i in range(0, len(x), p.block)])
    assert valid.all() and np.allclose(y, expected)


def test_modem_noiseless():
    for mod in ("qpsk", "qam16h", "qam64h"):
        bits = np.random.default_rng(4).integers(0, 2, 600)
        nsym = modem.n_symbols(600, 200, mod)
        soft, hard = modem.demodulate(modem.modulate(bits, nsym, mod, 2.0), 600, mod, 2.0)
        assert np.array_equal(hard, bits), mod
        assert np.array_equal((soft[:200] < 0).astype(int), bits[:200]), mod


def test_end_to_end_without_noise():
    p = PROFILES["M700"]
    x = _signal(p.block * 20, p.fs)
    tx = Transmitter(p)
    frames = tx.run(x)
    dec = StreamDecoder(p, postfilter=False)
    y, v = dec.run(frames, len(x))
    ref = np.concatenate([decode_block(encode_block(x[i:i + 64], p), p) for i in range(0, len(x), 64)])
    assert v.all() and np.allclose(y, ref)


def test_postfilter_stays_in_cells():
    p = PROFILES["B200"]
    x = _signal(p.block, p.fs)
    coefs, cell = decode_coeffs(encode_block(x, p), p)
    pf = PostFilter(p.levels, p.pf_iters)
    y = pf.process("M", coefs["M"], cell["M"])
    for c, cl in zip(haar_forward(y, p.levels), cell["M"]):
        if cl is not None:
            assert np.all(c >= cl[0] - 1e-9) and np.all(c <= cl[1] + 1e-9)


def test_cells_contain_original():
    """量子化区間は元の係数を必ず含む (飽和・クリップを許す指数選択・指数の上下限を含めて)"""
    from gracefm.codec import cells, exp_range, quantize
    rng = np.random.default_rng(5)
    for p in PROFILES.values():
        for trial in range(200):
            kind = trial % 4
            if kind == 0:
                x = rng.uniform(-1, 1, (p.block, 2))                 # フルスケールの雑音
            elif kind == 1:
                x = rng.standard_normal((p.block, 2)) * 1e-6         # 指数の下限付近
            elif kind == 2:
                x = np.sign(rng.standard_normal((p.block, 2)))       # 振幅 ±1 (最大振幅)
            else:
                x = np.zeros((p.block, 2))                           # 1係数だけ突出 (飽和しやすい)
                x[rng.integers(p.block), :] = rng.uniform(-1, 1)
                x += rng.standard_normal((p.block, 2)) * 0.05
                x = np.clip(x, -1, 1)
            ms = {"M": (x[:, 0] + x[:, 1]) / 2, "S": (x[:, 0] - x[:, 1]) / 2}
            for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
                bands = haar_forward(ms[ch], p.levels)
                for k, (c, b) in enumerate(zip(bands, bits)):
                    if b == 0:
                        continue
                    for clip_opt in (True, False):
                        m, e = quantize(c, k, b, p, clip_opt)
                        lo, hi = cells(m, e, k, b, p)
                        assert np.all(c >= lo - 1e-12) and np.all(c <= hi + 1e-12), (p.name, ch, k, kind)


def test_saturated_cell_example():
    """飽和の例: B200 最高域の 0.8 が 0.5 に復号されても、区間は 0.8 を含む"""
    from gracefm.codec import cells
    p = PROFILES["B200"]
    bands = [np.zeros(p.ncoef(k)) for k in range(p.nbands)]
    bands[-1] = np.array([0.8] + [0.55] * (p.ncoef(p.nbands - 1) - 1))
    mono = haar_inverse(bands)
    bd = encode_block(np.stack([mono, mono], axis=1), p, clip_opt=True)
    coefs, cell = decode_coeffs(bd, p)
    lo, hi = cell["M"][-1]
    assert coefs["M"][-1][0] == 0.5 and lo[0] <= 0.8 <= hi[0]


def test_latency_model():
    """遅延モデル: 1系統・2系統(半ブロック単位) は 2ブロック、2系統(1ブロック単位) は 2.5ブロック。処理時間は加算"""
    from gracefm.timing import Timing, min_latency
    for p in PROFILES.values():
        B = p.block / p.fs
        assert np.isclose(min_latency(p, False, "half"), 2 * B)
        assert np.isclose(min_latency(p, True, "half"), 2 * B)
        assert np.isclose(min_latency(p, True, "block"), 2.5 * B)
        tm = Timing(t_enc=1e-4, t_filt=2e-4, t_dec=3e-4, t_out=4e-4)
        assert np.isclose(min_latency(p, True, "half", tm), 2 * B + 1e-3)


def test_receiver_is_causal():
    """受信処理 (復号・ポストフィルタ・融合・PLC) は未来のフレームを使わない:
    あるフレームを欠落させても、そのフレームが運ぶ区間より前の出力は変わらない"""
    from gracefm.txrx import receive
    p = PROFILES["B200"]
    x = _signal(p.block * 24, p.fs)
    off = p.block // 2
    rng = np.random.default_rng(3)
    fa = [modem.awgn(f, 9.0, rng) for f in Transmitter(p, 0, 0).run(x)]
    fb = [modem.awgn(f, 9.0, rng) for f in Transmitter(p, 1, off).run(x)]
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
    fb = Transmitter(p, 1, p.block // 2).run(x)
    fa = [None if i % 3 == 0 else f for i, f in enumerate(fa)]       # A だけ 1/3 欠落
    y, st = receive(p, fa, fb, len(x), p.block // 2)
    assert st["plc_samples"] < p.block                               # B で埋まり PLC はほぼ不要


def test_low_rate_sub_stream():
    """副系が主系より低いビットレートでも融合でき、雑音なしなら主系の音質を落とさない"""
    from gracefm import metrics
    p, ps = PROFILES["B200M"], PROFILES["S50M"]
    x = _signal(p.block * 40, p.fs)
    x[:, 1] = x[:, 0]
    fa = Transmitter(p, 0, 0).run(x)
    fb = Transmitter(ps, 1, p.block // 2).run(x)
    y1, _ = receive(p, fa, None, len(x), 0)
    y2, _ = receive(p, fa, fb, len(x), p.block // 2, profile_b=ps)
    assert metrics.snr_db(x, y2) > metrics.snr_db(x, y1) - 0.5
    fa = [None if i % 3 == 0 else f for i, f in enumerate(fa)]
    y3, st = receive(p, fa, fb, len(x), p.block // 2, profile_b=ps)
    assert st["plc_samples"] < p.block                               # 主系の欠落を副系が埋める


def test_layered_profile():
    """階層化: 基本層は元のプロファイルと同じビットで強い位置に収まり、雑音なしなら全ビットで復号できる"""
    from gracefm import metrics
    from dataclasses import replace
    p = PROFILES["B200MH"]
    base = replace(PROFILES["B200M"], protect_k=p.protect_k)   # 基本層 = B200M の割り当て (保護は上位 protect_k bit)
    lay, lb = Layout(p), Layout(base)
    t = Transmitter(p)
    assert lay.n_strong == lb.n_tx                          # 基本層 = B200M の割り当ての送信ビット数
    assert 2 * t.nsym >= lay.n_strong                       # 強い位置 (象限ビット) に全部入る
    assert t.nsym == Transmitter(base).nsym                 # 帯域幅 (シンボル数) は基本層を QPSK で送るのと同じ
    x = _signal(p.block * 40, p.fs)
    x[:, 1] = x[:, 0]
    y, st = receive(p, Transmitter(p).run(x), None, len(x), 0)
    yb, _ = receive(base, Transmitter(base).run(x), None, len(x), 0)
    assert st["plc_samples"] == 0
    assert metrics.snr_db(x, y) > metrics.snr_db(x, yb) + 20


def test_encryption():
    """暗号化: 正しい鍵なら暗号化なしと同じ音、違う鍵なら復号できない。24bit のフレーム番号の周回も復元できる"""
    from gracefm import metrics
    from gracefm.crypto import StreamCipher, unwrap_counter
    p = PROFILES["B200MH"]
    x = _signal(p.block * 30, p.fs)
    x[:, 1] = x[:, 0]
    key, nonce = bytes(range(16)), bytes(8)
    ca, cb = StreamCipher(key, nonce), StreamCipher(bytes(16), nonce)
    f_plain = Transmitter(p).run(x)
    f_enc = Transmitter(p, cipher=ca).run(x)
    f_enc_b = Transmitter(p, cipher=cb).run(x)
    assert not np.allclose(f_enc_b[5], f_enc[5])                      # 鍵が違えば送信シンボルも違う
    y0, _ = receive(p, f_plain, None, len(x), 0)
    y1, st = receive(p, f_enc, None, len(x), 0, cipher=ca)
    y2, _ = receive(p, f_enc, None, len(x), 0, cipher=cb)
    assert st["plc_samples"] == 0
    assert np.allclose(y0, y1)
    assert metrics.snr_db(x, y2) < 0                                  # 鍵が違えば聴けない
    m = 1 << 24
    assert unwrap_counter(5, -1) == 5
    assert unwrap_counter(2, m - 3) == m + 2                          # 周回をまたぐ
    assert unwrap_counter(m - 1, m + 1) == m - 1                      # 少し前のフレーム


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
