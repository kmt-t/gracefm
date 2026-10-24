"""実験用の位相・振幅ハイブリッド主系。python tests/test_hybrid.py でも実行可。"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gracefm import fec, modem  # noqa: E402
from gracefm.codec import decode_block, decode_coeffs, encode_block, haar_forward, offset_of  # noqa: E402
from gracefm.framing import HybridLayout, Layout  # noqa: E402
from gracefm.profiles import PROFILES, make_hybrid  # noqa: E402
from gracefm.txrx import StreamDecoder, Transmitter, receive  # noqa: E402


def _audio(p, frames=8):
    t = np.arange(p.block * frames) / p.fs
    left = .25 * np.sin(2 * np.pi * 440 * t) + .08 * np.sin(2 * np.pi * 6100 * t)
    right = .22 * np.sin(2 * np.pi * 523 * t) + .07 * np.sin(2 * np.pi * 9200 * t)
    return np.stack([left, right], axis=1)


def test_all_hybrid_points_and_continuous_radius():
    for lower_bits in (4, 6, 8, 10):
        levels = 1 << lower_bits
        amplitude = .6 / ((levels - 1) / 2)
        u = np.arange(4 * levels)
        mask = modem.prbs(3 * len(u))
        symbols = modem.hybrid_modulate(u, amplitude, mask, lower_bits)
        recovered, variance, _ = modem.hybrid_demodulate(
            symbols, u >> (lower_bits + 1), amplitude, mask, modem.PREAMBLE,
            lower_bits)
        assert np.allclose(recovered, u, atol=1e-5)
        assert np.all(variance >= 0)
        noisy = symbols.copy()
        noisy[0] *= 1.15
        fractional, _, _ = modem.hybrid_demodulate(
            noisy, u >> (lower_bits + 1), amplitude, mask, modem.PREAMBLE,
            lower_bits)
        assert fractional[0] != np.rint(fractional[0])


def test_hybrid_quantizer_uses_both_extreme_codes():
    p = PROFILES["B200MHY"]
    bd = encode_block(_audio(p, 1), p)
    low = -(1 << (p.hybrid_bits - 1))
    high = (1 << (p.hybrid_bits - 1)) - 1
    bd.mant["M"][5][0] = low
    bd.mant["M"][5][1] = high
    lay = HybridLayout(p)
    u = lay.hybrid_u(bd)
    assert u[0] == 0 and u[1] == (1 << p.hybrid_bits) - 1
    conventional = Layout(p)
    frame = conventional.pack(bd, 0, 0)
    recovered, _ = conventional.unpack(1 - 2 * frame[:conventional.n_coded],
                                       frame[conventional.n_coded:])
    assert recovered.mant["M"][5][0] == low
    assert recovered.mant["M"][5][1] == high


def test_stereo_y_preserves_existing_s_coefficients():
    old = PROFILES["B200H"]
    y = PROFILES["B200HY"]
    assert y.bits_s == old.bits_s
    assert y.exp_offset_s == old.exp_offset_s
    assert y.attn_group_s == old.attn_group_s
    x = _audio(y, 4)
    for i in range(4):
        block = x[i * y.block:(i + 1) * y.block]
        old_s = decode_coeffs(encode_block(block, old), old)[0]["S"]
        y_s = decode_coeffs(encode_block(block, y), y)[0]["S"]
        for old_band, y_band in zip(old_s, y_s):
            assert np.array_equal(old_band, y_band)


def test_fec_top_bit_is_retained_and_has_separate_phase_copy():
    for name in ("B200MHY", "B200HY"):
        p = PROFILES[name]
        assert p.hybrid_bits == 8
        lay = HybridLayout(p)
        conventional = Layout(p)
        baseline = Layout(PROFILES["B200MH" if name.startswith("B200MH") else "B200H"])
        assert lay.n_coded == conventional.n_coded
        assert lay.n_prot == conventional.n_prot
        added_attenuator_bits = (p.attenuator_bits("M", 5) + p.attenuator_bits("M", 6)
                                 - baseline.p.attenuator_bits("M", 5)
                                 - baseline.p.attenuator_bits("M", 6))
        assert added_attenuator_bits == (8 if name.startswith("B200MH") else 12)
        assert lay.n_prot == baseline.n_prot + added_attenuator_bits
        assert len([item for item in lay.top_items
                    if item[0] in p.hybrid_channels and item[1] >= p.hybrid_start_k]) == lay.n_hybrid
        assert all(pos == p.hybrid_bits - 1 for ch, k, _, pos in lay.top_items
                   if ch in p.hybrid_channels and k >= p.hybrid_start_k)
        assert all(ch not in p.hybrid_channels or k < p.hybrid_start_k
                   for ch, k, _, _ in lay.unp_items)
        assert lay.n_tx + (p.hybrid_bits - 1) * lay.n_hybrid == conventional.n_tx
        bd = encode_block(_audio(p, 1), p)
        sent = lay.pack(bd, 0, 1)
        top_only, header = lay.unpack(1 - 2 * sent[:lay.n_coded], sent[lay.n_coded:])
        assert header["pid"] == p.pid
        for ch, k, j in lay.hybrid_items:
            offset = offset_of(p.hybrid_bits, p, ch, k)
            original = (int(bd.mant[ch][k][j]) + offset) >> (p.hybrid_bits - 1)
            protected = (int(top_only.mant[ch][k][j]) + offset) >> (p.hybrid_bits - 1)
            assert original == protected


def test_broadcast_y_two_high_m_bands_have_protected_attenuator_bytes():
    for name in ("B200MHY", "B200HY"):
        p = PROFILES[name]
        assert p.attenuator_group("M", 5) == 2
        assert p.attenuator_group("M", 6) == 4
        assert p.attenuator_bits("M", 5) == p.attenuator_bits("M", 6) == 8
        layout = HybridLayout(p)
        assert len([item for item in layout.attn_items if item[:2] == ("M", 5)]) == 8
        bd = encode_block(_audio(p, 1), p)
        packed = layout.pack(bd, 0, 1)
        restored, _ = layout.unpack(1 - 2 * packed[:layout.n_coded], packed[layout.n_coded:])
        assert np.array_equal(restored.attn["M"][5], bd.attn["M"][5])
        assert np.array_equal(restored.attn["M"][6], bd.attn["M"][6])

        protected = fec.viterbi_decode(1 - 2 * packed[:layout.n_coded], layout.n_prot_crc)
        first_attn = layout.header_bits + sum(p.exponent_bits(ch, k) for ch, k in layout.exp_items)
        protected[layout.high_prot_indices[0]] ^= 1
        corrupted = np.concatenate((fec.conv_encode(protected), packed[layout.n_coded:]))
        recovered, header = layout.unpack(1 - 2 * corrupted[:layout.n_coded], corrupted[layout.n_coded:])
        assert recovered is not None and header['high_ok'] is False


def test_stereo_y_uses_fewer_main_symbols_than_legacy_stereo():
    for old_name, y_name in (("B200H", "B200HY"), ("M700H", "M700HY")):
        old, y = PROFILES[old_name], PROFILES[y_name]
        assert Transmitter(y).nsym < Transmitter(old).nsym, (old_name, y_name)
        assert y.base_s == ((1, 1, 1, 1, 1, 1, 1) if y.fs == 32000
                            else (1, 1, 1, 1, 1, 2, 2))
        lay = HybridLayout(y)
        strong_slots = 2 * Transmitter(y).digital_nsym
        high_s = [(k, pos) for i, (ch, k, _, pos) in enumerate(lay.unp_items)
                  if ch == "S" and k in (5, 6) and lay.n_coded + i < strong_slots]
        assert len(high_s) == (0 if y.fs == 32000 else 48)
        assert all(pos == y.bits_s[k] - 2 for k, pos in high_s)


def test_hybrid_noiseless_audio_and_phase_only_fallback():
    for name in ("B200MHY", "B200HY"):
        p = PROFILES[name]
        x = _audio(p)
        frames = Transmitter(p).run(x)
        dec = StreamDecoder(p, postfilter=False)
        full, valid = dec.run(frames, len(x))
        reference = np.concatenate([decode_block(encode_block(x[i:i + p.block], p), p)
                                    for i in range(0, len(x), p.block)])
        assert valid.all()
        assert np.allclose(full, reference, atol=1e-6)
        coarse, valid = StreamDecoder(p, postfilter=False, hybrid_phase_only=True).run(frames, len(x))
        assert valid.all()
        assert np.mean((coarse - reference) ** 2) > 0
        # 高域だけを粗くしても、低域のHaar係数は保たれる。
        for ch in range(2):
            low_full = haar_forward(full[:p.block, ch], p.levels)[:p.hybrid_start_k]
            low_coarse = haar_forward(coarse[:p.block, ch], p.levels)[:p.hybrid_start_k]
            assert all(np.allclose(a, b) for a, b in zip(low_full, low_coarse))


def test_amplitude_damage_does_not_damage_fec_or_low_bands():
    p = PROFILES["B200MHY"]
    x = _audio(p, 1)
    frame = Transmitter(p).frame(x)
    lay = HybridLayout(p)
    start = len(modem.PREAMBLE) + Transmitter(p).digital_nsym
    damaged = frame.copy()
    damaged[start:] *= np.linspace(.65, 1.35, lay.n_hybrid)
    clean_decoder = StreamDecoder(p, postfilter=False)
    damaged_decoder = StreamDecoder(p, postfilter=False)
    clean, ok_clean = clean_decoder.decode(frame)
    degraded, ok_damaged = damaged_decoder.decode(damaged)
    assert ok_clean and ok_damaged
    assert damaged_decoder.stats["crc_fail"] == 0
    for ch in range(2):
        a = haar_forward(clean[:, ch], p.levels)[:p.hybrid_start_k]
        b = haar_forward(degraded[:, ch], p.levels)[:p.hybrid_start_k]
        assert all(np.allclose(u, v) for u, v in zip(a, b))


def test_hybrid_eight_bit_option_and_two_stream_fusion():
    base = PROFILES["B200MH"]
    p = make_hybrid(base, "experimental-8", 0, mantissa_bits=8)
    x = _audio(p, 12)
    fa = Transmitter(p).run(x)
    fs = Transmitter(PROFILES["SUB50M"], 1, p.block // 2).run(x)
    y, stats = receive(p, fa, fs, len(x), p.block // 2, profile_b=PROFILES["SUB50M"],
                       postfilter=False)
    assert stats["plc_samples"] == 0
    assert np.isfinite(y).all()


def test_m700hy_radius_precision_does_not_use_extra_symbols_or_remove_fec():
    baseline = PROFILES["M700HY"]
    baseline_layout = HybridLayout(baseline)
    for bits in (8, 10, 12):
        p = make_hybrid(PROFILES["M700H"], f"M700HY-R{bits}", 13,
                        mantissa_bits=bits, experimental_tag=3)
        lay = HybridLayout(p)
        assert p.bits_m[5:] == (bits, bits)
        assert p.bits_s == baseline.bits_s
        assert lay.n_hybrid == baseline_layout.n_hybrid == 48
        assert lay.n_coded == baseline_layout.n_coded
        assert Transmitter(p).nsym == Transmitter(baseline).nsym
        assert sum(ch == "M" and k >= 5 for ch, k, _, _ in lay.top_items) == 48
        x = _audio(p, 4)
        frames = Transmitter(p).run(x)
        decoded, valid = StreamDecoder(p, postfilter=False).run(frames, len(x))
        assert valid.all() and np.isfinite(decoded).all()


def test_m700_y_profiles_preserve_s_fec_and_experimental_identity():
    from gracefm.equalizer import header_training_symbols
    from gracefm.profiles import BY_ID, BY_HEADER

    for old_name, y_name in (("M700", "M700Y"), ("M700H", "M700HY")):
        old, y = PROFILES[old_name], PROFILES[y_name]
        assert y.hybrid_bits == 8
        assert y.fs == 48000 and y.block == 64 and y.hybrid_start_k == 5
        assert y.bits_s == old.bits_s and y.exp_offset_s == old.exp_offset_s
        assert y.attn_group_s == old.attn_group_s
        assert y.protect_k == old.protect_k
        assert y.pid != old.pid and y.experimental_tag == old.experimental_tag == 3
        assert BY_ID[y.pid] is y and BY_HEADER[(y.pid, 3)] is y
        lay, old_lay = HybridLayout(y), Layout(old)
        assert lay.header_bits == old_lay.header_bits == 24
        assert lay.n_prot == old_lay.n_prot + 8 and lay.n_coded == old_lay.n_coded + 16
        assert lay.n_hybrid == 48
        assert sum(ch == "M" and k >= 5 for ch, k, _, _ in lay.top_items) == 48 * y.protect_k
        bd = encode_block(_audio(y, 1), y)
        old_s = decode_coeffs(encode_block(_audio(y, 1), old), old)[0]["S"]
        y_s = decode_coeffs(bd, y)[0]["S"]
        assert all(np.array_equal(a, b) for a, b in zip(old_s, y_s))
        packed = lay.pack(bd, 0, 0)
        soft = 1 - 2 * packed[:lay.n_coded]
        assert lay.unpack(soft, packed[lay.n_coded:])[0] is not None
        assert old_lay.unpack(soft, packed[lay.n_coded:]) == (None, None)
        x = _audio(y)
        frames = Transmitter(y).run(x)
        pilot = header_training_symbols(y, 0, 0)
        assert np.array_equal(np.sign(frames[0][:len(pilot)].real), np.sign(pilot.real))
        assert np.array_equal(np.sign(frames[0][:len(pilot)].imag), np.sign(pilot.imag))
        _, accepted_by_old = StreamDecoder(old, postfilter=False).decode(frames[0])
        assert not accepted_by_old
        decoded, valid = StreamDecoder(y, postfilter=False).run(frames, 8 * y.block)
        reference = np.concatenate([
            decode_block(encode_block(x[i:i + y.block], y), y)
            for i in range(0, 8 * y.block, y.block)])
        assert valid.all() and np.allclose(decoded, reference, atol=1e-6)


def test_two_fec_phase_bits_constrain_hybrid_demodulation():
    u = np.arange(64)
    mask = modem.prbs(3 * len(u))
    symbols = modem.hybrid_modulate(u, .08, mask)
    recovered, variance, _ = modem.hybrid_demodulate(
        symbols, u >> 5, .08, mask, modem.PREAMBLE,
        protected_second=(u >> 4) & 1)
    assert np.allclose(recovered, u, atol=1e-5)
    assert np.all(variance >= 0)


def test_monitor_hierarchy_keeps_base_bits_on_strong_qam_positions():
    """M/S の基本層が 16QAM の弱い振幅位置へ漏れない。"""
    for name in ("M700H", "M700HY"):
        p = PROFILES[name]
        tx = Transmitter(p)
        lay = tx.layout
        strong_slots = 2 * tx.digital_nsym
        assert lay.n_strong <= strong_slots
        assert strong_slots - lay.n_strong < 2
        for bit_index, (ch, k, coefficient, pos) in enumerate(lay.unp_items, start=lay.n_coded):
            width = (p.bits_m if ch == "M" else p.bits_s)[k]
            rank = width - 1 - pos
            if rank < p.base_bits(ch, k, coefficient):
                assert bit_index < strong_slots
            if bit_index >= strong_slots:
                assert rank >= p.base_bits(ch, k, coefficient)
        for ch, k, _, pos in lay.top_items:
            if k >= 5:
                assert pos == (p.bits_m if ch == "M" else p.bits_s)[k] - 1


def test_monitor_y_bit_positions_preserve_s_codes():
    from gracefm.profiles import BY_HEADER

    old = PROFILES["M700H"]
    y_profile = PROFILES["M700HY"]
    assert y_profile.bits_s == old.bits_s and y_profile.exp_offset_s == old.exp_offset_s
    assert y_profile.attn_group_s == old.attn_group_s and y_profile.protect_k == old.protect_k == 1
    assert y_profile.base_s == (1, 1, 1, 1, 1, 2, 2)
    assert y_profile.base_m == (11, 10, 5, 4, 3, 3, 2)
    assert BY_HEADER[(y_profile.pid, y_profile.experimental_tag)] is y_profile
    old_lay, y_layout = Layout(old), HybridLayout(y_profile)
    assert y_layout.n_prot == old_lay.n_prot + 8  # 高域Mの追加アッテネータ8bit
    assert y_layout.n_coded == old_lay.n_coded + 16
    assert sum(ch == "S" for ch, _, _, _ in y_layout.top_items) == 64
    strong_slots = 2 * Transmitter(y_profile).digital_nsym
    strong_s = [(k, pos) for i, (ch, k, _, pos) in enumerate(y_layout.unp_items)
                if ch == "S" and y_layout.n_coded + i < strong_slots]
    assert sum(k in (5, 6) and pos == y_profile.bits_s[k] - 2
               for k, pos in strong_s) == 48
    assert len(strong_s) <= 49  # 端数の強い位置を1bit使える
    assert Transmitter(y_profile).nsym + len(modem.PREAMBLE) == 386
    x = _audio(y_profile, 8)
    for start in range(0, len(x), y_profile.block):
        block = x[start:start + y_profile.block]
        s_old = decode_coeffs(encode_block(block, old), old)[0]["S"]
        s_y = decode_coeffs(encode_block(block, y_profile), y_profile)[0]["S"]
        assert all(np.array_equal(a, b) for a, b in zip(s_old, s_y))
    y, valid = StreamDecoder(y_profile, postfilter=False).run(Transmitter(y_profile).run(x), len(x))
    assert valid.all()
    expected = np.concatenate([decode_block(encode_block(x[i:i + y_profile.block], y_profile), y_profile)
                               for i in range(0, len(x), y_profile.block)])
    assert np.allclose(y, expected, atol=1e-6)


def test_m700_y_optional_secondary_fusion():
    from gracefm import channel

    for name in ("M700Y", "M700HY"):
        p = PROFILES[name]
        x = _audio(p, 12)
        y, stats, _ = channel.link(x, name, 90, sub="auto", seed=1)
        assert y.shape == x.shape and np.isfinite(y).all()
        assert "B" in stats and stats["plc_samples"] == 0


def test_m700_y_equalizer_uses_extended_header():
    from gracefm import channel

    for name in ("M700Y", "M700HY"):
        p = PROFILES[name]
        y, stats, diagnostics = channel.link_static_multipath(
            _audio(p, 100), p, 85, paths=((5e-6, -10, .5),), sub=None,
            training_frames=30, decision_passes=1)
        assert np.isfinite(y).all() and stats["A"]["crc_fail"] == 0
        assert diagnostics["equalizer"]["main"]["training_frames"] == 30


def test_hybrid_cipher_is_explicitly_rejected():
    p = PROFILES["B200MHY"]
    for factory in (Transmitter, StreamDecoder):
        try:
            factory(p, cipher=object())
        except ValueError as exc:
            assert "AES-CTR" in str(exc)
        else:
            raise AssertionError("暗号化を黙って有効化してはいけない")


def test_hybrid_equalizer_accepts_mixed_constellation():
    from gracefm import channel

    p = PROFILES["B200HY"]
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
