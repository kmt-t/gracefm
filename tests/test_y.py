"""位相・半径シンボル(Y)の主系。python tests/test_y.py でも実行可。"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import modem  # noqa: E402
from gracefm.codec import decode_block, decode_coeffs, encode_block, haar_forward  # noqa: E402
from gracefm.framing import pack, unpack  # noqa: E402
from gracefm.layout import Layout  # noqa: E402
from gracefm.profiles import PROFILES, make_y_profile  # noqa: E402
from gracefm.txrx import StreamDecoder, Transmitter, receive  # noqa: E402


def _audio(p, frames=8):
    t = np.arange(p.block * frames) / p.fs
    left = .25 * np.sin(2 * np.pi * 440 * t) + .08 * np.sin(2 * np.pi * 6100 * t)
    right = .22 * np.sin(2 * np.pi * 523 * t) + .07 * np.sin(2 * np.pi * 9200 * t)
    return np.stack([left, right], axis=1)


def _y_soft(lay, bd):
    """Y専用シンボルの位相から得る軟値の代わりに、真の最上位bitとパリティを高信頼の軟値にする。"""
    u, parity, _ = lay.y_parts(bd)
    msb = u >> (lay.p.y_bits - 1)
    return 8.0 * (1.0 - 2.0 * msb), 8.0 * (1.0 - 2.0 * parity)


def test_all_y_points_and_continuous_radius():
    rng = np.random.default_rng(11)
    for lower_bits in (4, 6, 8, 10):
        levels = 1 << lower_bits
        amplitude = .6 / ((levels - 1) / 2)
        u = np.arange(2 * levels)
        parity = rng.integers(0, 2, len(u))
        mask = modem.prbs(3 * len(u))
        symbols = modem.y_modulate(u, parity, amplitude, mask, lower_bits)
        recovered, variance, _ = modem.y_demodulate(
            symbols, u >> lower_bits, parity, amplitude, mask, modem.PREAMBLE, lower_bits)
        assert np.allclose(recovered, u, atol=1e-5)
        assert np.all(variance >= 0)
        noisy = symbols.copy()
        noisy[0] *= 1.15
        fractional, _, _ = modem.y_demodulate(
            noisy, u >> lower_bits, parity, amplitude, mask, modem.PREAMBLE, lower_bits)
        assert fractional[0] != np.rint(fractional[0])
        # 位相の軟値は最上位bitとパリティの値を示す (正 = 0)
        llr_msb, llr_par, _ = modem.y_phase_llr(symbols, amplitude, mask, modem.PREAMBLE, lower_bits)
        assert np.array_equal(llr_msb < 0, (u >> lower_bits) == 1)
        assert np.array_equal(llr_par < 0, parity == 1)
        assert np.allclose(modem.y_slice(symbols, amplitude, lower_bits), symbols)


def test_y_quantizer_uses_both_extreme_codes():
    p = PROFILES["B200MY"]
    bd = encode_block(_audio(p, 1), p)
    low = -(1 << (p.y_bits - 1))
    high = (1 << (p.y_bits - 1)) - 1
    bd.mant["M"][2][0] = low
    bd.mant["M"][2][1] = high
    lay = Layout(p)
    u = lay.y_u(bd)
    assert u[0] == 0 and u[1] == (1 << p.y_bits) - 1
    frame = pack(lay, bd, 0, 0)
    _, header = unpack(lay, 1.0 - 2.0 * frame, frame, y_soft=_y_soft(lay, bd))
    assert header["y_msb"][0] == 0 and header["y_msb"][1] == 1      # 最上位bitだけがフレームを通る (残りは専用シンボル)


def test_stereo_y_uses_registered_s_coefficients():
    y = PROFILES["B200Y"]
    assert y.bits_s == (11, 11, 7, 7, 7)               # Y帯域の分の余裕で、Sの最低域2帯域を11bitにする
    assert y.base_s[:2] == (5, 5)                      # 位相部に置く仮数bit (パリティを除く)。拡張層はその+1 bit
    assert y.y_channels == ("M", "S")             # Sの k=2〜4 もY方式の専用シンボルで送る
    assert y.modulation == "qam16h"
    x = _audio(y, 4)
    for i in range(4):
        block = x[i * y.block:(i + 1) * y.block]
        y_s = decode_coeffs(encode_block(block, y), y)["S"]
        assert all(len(band) == y.ncoef(k) for k, band in enumerate(y_s))


def test_y_bands_are_only_in_dedicated_symbols():
    """Y帯域の仮数はHaar係数部に無く専用シンボルで送る。位相は「最上位bit｜パリティ」で、終端bitだけがヘッダ側にある。"""
    for name in ("B200MY", "B200Y", "M700MY", "M700Y"):
        p = PROFILES[name]
        assert p.y_bits == 7 and p.protect_bits(p.y_start_k) == 1
        lay = Layout(p)
        assert lay.n_ytail == 12
        assert all(ch not in p.y_channels or k < p.y_start_k
                   for ch, k, _, _ in lay.coef_items)
        total = sum(b * p.ncoef(k) for bits in (p.bits_m, p.bits_s) for k, b in enumerate(bits))
        assert lay.n_coef_bits + p.y_bits * lay.n_y == total
        bd = encode_block(_audio(p, 1), p)
        sent = pack(lay, bd, 0, 1)
        u, parity, tail = lay.y_parts(bd)
        assert len(u) == len(parity) == lay.n_y and len(tail) == 12
        restored, header = unpack(lay, 1 - 2 * sent, sent, y_soft=_y_soft(lay, bd))
        assert header["pid"] == p.pid and header["high_ok"]
        assert np.array_equal(header["y_msb"], u >> (p.y_bits - 1))
        for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
            for k in range(p.nbands):
                if bits[k] and not p.y_band(ch, k):
                    assert np.array_equal(restored.mant[ch][k], bd.mant[ch][k])
        # 最上位bitを1つ誤っても、パリティで訂正して同じ結果になる
        msb_soft, parity_soft = _y_soft(lay, bd)
        msb_soft = msb_soft.copy()
        msb_soft[3] *= -0.4
        again, header = unpack(lay, 1 - 2 * sent, sent, y_soft=(msb_soft, parity_soft))
        assert again is not None and np.array_equal(header["y_msb"], u >> (p.y_bits - 1))
    # 無雑音なら、専用シンボルから元の仮数を復元する
    for name in ("B200MY", "M700Y"):
        p = PROFILES[name]
        x = _audio(p, 4)
        decoded, valid = StreamDecoder(p).run(Transmitter(p).run(x), len(x))
        reference = np.concatenate([decode_block(encode_block(x[i:i + p.block], p), p)
                                    for i in range(0, len(x), p.block)])
        assert valid.all() and np.allclose(decoded, reference, atol=1e-6)


def test_broadcast_y_bands_have_protected_attenuator_bytes():
    for name in ("B200MY", "B200Y"):
        p = PROFILES[name]
        assert p.attenuator_group("M", 2) == 2
        assert p.attenuator_group("M", 3) == 4
        assert p.attenuator_group("M", 4) == 8
        assert p.attenuator_bits("M", 2) == p.attenuator_bits("M", 3) == p.attenuator_bits("M", 4) == 4
        layout = Layout(p)
        assert len([item for item in layout.attn_items if item[:2] == ("M", 3)]) == 4
        bd = encode_block(_audio(p, 1), p)
        packed = pack(layout, bd, 0, 1)
        restored, _ = unpack(layout, 1.0 - 2.0 * packed, packed, y_soft=_y_soft(layout, bd))
        assert np.array_equal(restored.attn["M"][3], bd.attn["M"][3])
        assert np.array_equal(restored.attn["M"][4], bd.attn["M"][4])

        protected = layout.header_info(packed)
        first_attn = layout.header_bits + sum(p.exp_bits for ch, k in layout.exp_items)
        protected[layout.high_prot_indices[0]] ^= 1
        corrupted = layout.with_header(packed, protected)
        recovered, header = unpack(layout, 1.0 - 2.0 * corrupted, corrupted, y_soft=_y_soft(layout, bd))
        assert recovered is not None and header['high_ok'] is False


def test_y_digital_part_fills_strong_slots():
    """Y専用シンボルを除いたデジタル部は、強い位置で隙間なく埋まる (弱い位置の余りが詰め物になる)。"""
    for name in ("B200MY", "B200Y", "M700MY", "M700Y"):
        p = PROFILES[name]
        tx = Transmitter(p)
        lay = tx.layout
        assert tx.nsym == tx.digital_nsym + lay.n_y
        assert lay.n_strong <= 2 * tx.digital_nsym < lay.n_strong + 2
        assert lay.n_tx - lay.n_strong <= 2 * tx.digital_nsym


def test_y_noiseless_audio_and_phase_only_fallback():
    for name in ("B200MY", "B200Y"):
        p = PROFILES[name]
        x = _audio(p)
        frames = Transmitter(p).run(x)
        dec = StreamDecoder(p)
        full, valid = dec.run(frames, len(x))
        reference = np.concatenate([decode_block(encode_block(x[i:i + p.block], p), p)
                                    for i in range(0, len(x), p.block)])
        assert valid.all()
        assert np.allclose(full, reference, atol=1e-6)
        coarse, valid = StreamDecoder(p, y_phase_only=True).run(frames, len(x))
        assert valid.all()
        assert np.mean((coarse - reference) ** 2) > 0
        # 高域だけを粗くしても、低域のHaar係数は保たれる。
        for ch in range(2):
            low_full = haar_forward(full[:p.block, ch], p.levels)[:p.y_start_k]
            low_coarse = haar_forward(coarse[:p.block, ch], p.levels)[:p.y_start_k]
            assert all(np.allclose(a, b) for a, b in zip(low_full, low_coarse))


def test_amplitude_damage_does_not_damage_fec_or_low_bands():
    p = PROFILES["B200MY"]
    x = _audio(p, 1)
    frame = Transmitter(p).frame(x)
    lay = Layout(p)
    start = len(modem.PREAMBLE) + Transmitter(p).digital_nsym
    damaged = frame.copy()
    damaged[start:] *= np.linspace(.65, 1.35, lay.n_y)
    clean_decoder = StreamDecoder(p)
    damaged_decoder = StreamDecoder(p)
    clean, ok_clean = clean_decoder.decode(frame)
    degraded, ok_damaged = damaged_decoder.decode(damaged)
    assert ok_clean and ok_damaged
    assert damaged_decoder.stats["crc_fail"] == 0
    for ch in range(2):
        a = haar_forward(clean[:, ch], p.levels)[:p.y_start_k]
        b = haar_forward(degraded[:, ch], p.levels)[:p.y_start_k]
        assert all(np.allclose(u, v) for u, v in zip(a, b))


def test_y_eight_bit_option_and_two_stream_fusion():
    base = PROFILES["B200M"]
    p = make_y_profile(base, "y-8", 0, mantissa_bits=8)
    x = _audio(p, 12)
    fa = Transmitter(p).run(x)
    fs = Transmitter(PROFILES["SUB50M"], 1, 0).run(x)
    y, stats = receive(p, fa, fs, len(x), 0, profile_b=PROFILES["SUB50M"])
    assert stats["plc_samples"] == 0
    assert np.isfinite(y).all()


def test_m700y_radius_precision_does_not_use_extra_symbols_or_remove_fec():
    baseline = PROFILES["M700Y"]
    baseline_layout = Layout(baseline)
    for bits in (8, 10, 12):
        p = make_y_profile(PROFILES["M700"], f"M700Y-R{bits}", 13,
                        mantissa_bits=bits, format_id=3, bits_s=baseline.bits_s,
                        bits_m=baseline.bits_m[:2] + (bits,) * 3, channels=baseline.y_channels)
        lay = Layout(p)
        assert p.bits_m[2:] == (bits,) * 3
        assert p.bits_s[:2] == baseline.bits_s[:2] and p.bits_s[2:] == (bits,) * 3   # SのY帯域(k=2〜4)も同じ幅
        assert lay.n_y == baseline_layout.n_y == 112
        assert lay.n_coded == baseline_layout.n_coded
        assert Transmitter(p).nsym == Transmitter(baseline).nsym
        x = _audio(p, 4)
        frames = Transmitter(p).run(x)
        decoded, valid = StreamDecoder(p).run(frames, len(x))
        assert valid.all() and np.isfinite(decoded).all()


def test_m700_y_profiles_preserve_channel_mode_and_format_id():
    from gracefm.equalizer import header_training_symbols
    from gracefm.profiles import BY_ID, BY_HEADER

    for old_name, y_name in (("M700M", "M700MY"), ("M700", "M700Y")):
        old, y = PROFILES[old_name], PROFILES[y_name]
        assert y.y_bits == 7
        assert y.fs == 48000 and y.block == 64 and y.y_start_k == 2
        # M700 は S の H1 (k=4) を 3bit で送り、Y 版 (M700Y) は S の k=2〜4 も Y 帯域 (7bit) で送る
        assert y.bits_s[:2] == ((11, 11) if old_name == "M700" else (0, 0))      # M700YのSは最低域2帯域を11bitにする (B200Yと同じ)
        assert any(y.bits_s) == (old_name == "M700")
        assert y.pid != old.pid and y.format_id == old.format_id == 3
        assert BY_ID[y.pid] is y and BY_HEADER[(y.pid, 3)] is y
        lay, old_lay = Layout(y), Layout(old)
        assert lay.header_bits == old_lay.header_bits == 24
        attn_bits = lambda q: sum(q.attenuator_bits(ch, k) for ch in "MS" for k in range(q.nbands))
        assert lay.n_prot - old_lay.n_prot == attn_bits(y) - attn_bits(old)      # 差はアッテネータのbitだけ
        assert lay.n_header == 2 * (lay.n_prot_crc + 6)
        assert lay.n_y == sum(y.ncoef(k) for ch in y.y_channels for k in range(y.y_start_k, y.nbands)
                              if (y.bits_m if ch == "M" else y.bits_s)[k])
        bd = encode_block(_audio(y, 1), y)
        y_s = decode_coeffs(bd, y)["S"]
        assert all(len(band) == y.ncoef(k) for k, band in enumerate(y_s))
        packed = pack(lay, bd, 0, 0)
        soft = 1 - 2 * packed
        assert unpack(lay, soft, packed, y_soft=_y_soft(lay, bd))[0] is not None
        assert unpack(old_lay, np.resize(soft, old_lay.n_tx), np.resize(packed, old_lay.n_tx)) == (None, None)
        x = _audio(y)
        frames = Transmitter(y).run(x)
        pilot = header_training_symbols(y, 0, 0)
        assert np.array_equal(np.sign(frames[0][:len(pilot)].real), np.sign(pilot.real))
        assert np.array_equal(np.sign(frames[0][:len(pilot)].imag), np.sign(pilot.imag))
        _, accepted_by_old = StreamDecoder(old).decode(frames[0])
        assert not accepted_by_old
        decoded, valid = StreamDecoder(y).run(frames, 8 * y.block)
        reference = np.concatenate([
            decode_block(encode_block(x[i:i + y.block], y), y)
            for i in range(0, 8 * y.block, y.block)])
        assert valid.all() and np.allclose(decoded, reference, atol=1e-6)


def test_y_phase_pairs_top_bit_with_its_parity():
    """位相は「最上位bit｜パリティ」で、隣の象限へ誤ると片方のbitだけが変わる (Gray割当)。"""
    bits = modem._QUADRANT_BITS                       # 象限番号 → 2*最上位bit + パリティ
    assert sorted(bits) == [0, 1, 2, 3]
    assert all(bin(int(a) ^ int(b)).count("1") == 1 for a, b in zip(bits, np.roll(bits, -1)))
    u = np.array([0, 64, 0, 64])
    parity = np.array([0, 0, 1, 1])
    symbols = modem.y_modulate(u, parity, .02, lower_bits=6)
    assert len(set(np.round(np.angle(symbols), 6))) == 4


def test_m700_hierarchy_keeps_base_bits_on_strong_qam_positions():
    """M/S の基本層が 16QAM の弱い振幅位置へ漏れない。"""
    for name in ("M700", "M700Y"):
        p = PROFILES[name]
        tx = Transmitter(p)
        lay = tx.layout
        strong_slots = 2 * tx.digital_nsym
        assert lay.n_strong <= strong_slots
        assert strong_slots - lay.n_strong < 2
        for bit_index, (ch, k, coefficient, pos) in zip(lay.coef_stream_idx, lay.coef_items):
            width = (p.bits_m if ch == "M" else p.bits_s)[k]
            rank = width - 1 - pos
            if rank < p.base_bits(ch, k):
                assert bit_index < strong_slots
            if bit_index >= strong_slots:
                assert rank >= p.base_bits(ch, k)


def test_m700_y_bit_positions_preserve_s_codes():
    from gracefm.profiles import BY_HEADER

    old = PROFILES["M700"]
    y_profile = PROFILES["M700Y"]
    assert y_profile.bits_s == (11, 11, 7, 7, 7) and old.bits_s[4] == 3
    assert y_profile.base_s[:2] == (5, 5)
    assert y_profile.base_m == (5, 5, 1, 1, 1)
    assert BY_HEADER[(y_profile.pid, y_profile.format_id)] is y_profile
    old_lay, y_layout = Layout(old), Layout(y_profile)
    attn_bits = lambda q: sum(q.attenuator_bits(ch, k) for ch in "MS" for k in range(q.nbands))
    assert y_layout.n_prot - old_lay.n_prot == attn_bits(y_profile) - attn_bits(old)      # Y帯域は4区間ずつ (4bit)
    strong_slots = 2 * Transmitter(y_profile).digital_nsym
    strong_s = [(k, pos) for i, (ch, k, _, pos) in enumerate(y_layout.coef_items)
                if ch == "S" and y_layout.coef_stream_idx[i] < strong_slots]
    # S の基本層2bitはすべて強い位置に入り、拡張層は弱い位置に入る
    assert len(strong_s) == sum(y_profile.ncoef(k) * y_profile.base_bits("S", k) for k in range(2))   # k=2 以上のSはY
    assert all(pos >= y_profile.bits_s[k] - y_profile.base_bits("S", k) for k, pos in strong_s)
    assert Transmitter(y_profile).nsym + len(modem.PREAMBLE) == 240
    x = _audio(y_profile, 8)
    for start in range(0, len(x), y_profile.block):
        block = x[start:start + y_profile.block]
        s_y = decode_coeffs(encode_block(block, y_profile), y_profile)["S"]
        assert all(len(band) == y_profile.ncoef(k) for k, band in enumerate(s_y))
    y, valid = StreamDecoder(y_profile).run(Transmitter(y_profile).run(x), len(x))
    assert valid.all()
    expected = np.concatenate([decode_block(encode_block(x[i:i + y_profile.block], y_profile), y_profile)
                               for i in range(0, len(x), y_profile.block)])
    assert np.allclose(y, expected, atol=1e-6)


def test_m700_y_optional_secondary_fusion():
    from gracefm import channel

    for name in ("M700MY", "M700Y"):
        p = PROFILES[name]
        x = _audio(p, 12)
        y, stats, _ = channel.link(x, name, 90, sub="auto", seed=1)
        assert y.shape == x.shape and np.isfinite(y).all()
        assert "B" in stats and stats["plc_samples"] == 0


def test_m700_y_equalizer_uses_extended_header():
    from gracefm import channel

    for name in ("M700MY", "M700Y"):
        p = PROFILES[name]
        y, stats, diagnostics = channel.link_static_multipath(
            _audio(p, 100), p, 85, paths=((5e-6, -10, .5),), sub=None,
            training_frames=30, decision_passes=1)
        assert np.isfinite(y).all() and stats["A"]["crc_fail"] == 0
        assert diagnostics["equalizer"]["main"]["training_frames"] == 30


def test_y_cipher_is_explicitly_rejected():
    p = PROFILES["B200MY"]
    for factory in (Transmitter, StreamDecoder):
        try:
            factory(p, cipher=object())
        except ValueError as exc:
            assert "AES-CTR" in str(exc)
        else:
            raise AssertionError("暗号化を黙って有効化してはいけない")


def test_y_equalizer_accepts_mixed_constellation():
    from gracefm import channel

    p = PROFILES["B200Y"]
    x = _audio(p, 100)
    y, stats, diagnostics = channel.link_static_multipath(
        x, p, 80, paths=((5e-6, -10, .5),), sub=None,
        training_frames=30, decision_passes=1)
    assert np.isfinite(y).all()
    assert stats["A"]["crc_fail"] == 0
    assert diagnostics["equalizer"]["main"]["training_frames"] == 30


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
