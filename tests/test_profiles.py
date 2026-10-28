"""Catalog generation, standard attenuation and actual layer placement contracts."""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gracefm import modem
from gracefm.codec import encode_block, decode_block
from gracefm.framing import Layout, YLayout
from gracefm.profiles import PROFILES, BY_ID, BY_HEADER, make_y_profile
from gracefm.txrx import Transmitter, StreamDecoder


def test_catalog_ids_and_standard_attenuation():
    from gracefm.channel import DEFAULT_SUB
    assert set(DEFAULT_SUB) <= PROFILES.keys()
    for main, secondary in DEFAULT_SUB.items():
        assert PROFILES[main].fs == PROFILES[secondary].fs
    assert list(BY_ID) == list(range(1, 12))
    assert set(PROFILES) == {
        'B200M', 'B200', 'B200MY', 'B200Y',
        'M700M', 'M700', 'M700MY', 'M700Y',
        'SUB50M', 'SUB100', 'SUB100-48K',
    }
    assert not {'S50M', 'S100', 'S100-48K'} & PROFILES.keys()
    assert all(PROFILES[name].modulation == 'qpsk' for name in ('SUB50M', 'SUB100', 'SUB100-48K'))
    assert all(PROFILES[name].modulation == 'qam16h' for name in ('B200M', 'B200', 'B200MY', 'B200Y'))
    assert all(PROFILES[name].modulation == 'qam16h' for name in ('M700M', 'M700', 'M700MY', 'M700Y'))
    assert PROFILES['M700M'].bits_s == PROFILES['M700MY'].bits_s == (0,) * 5
    assert PROFILES['M700M'].base_s == PROFILES['M700MY'].base_s == (0,) * 5
    assert all(PROFILES[name].bits_s != (0,) * 5 for name in ('M700', 'M700Y'))
    assert not {'M700Q16', 'B150', 'B150M', 'S85M', 'B200M-A4', 'B200-A4'} & PROFILES.keys()
    for p in PROFILES.values():
        assert p.format_id == 3 and BY_ID[p.pid] is p
        assert BY_HEADER[p.pid, 3] is p
        for ch, widths in [('M', p.bits_m), ('S', p.bits_s)]:
            groups = [p.attenuator_group(ch, k) for k in range(p.nbands)]
            if any(widths):
                highest = max(k for k, width in enumerate(widths) if width)
                assert groups[highest] > 0, (p.name, ch)
            else:
                assert not any(groups)


def test_all_profiles_roundtrip_and_attenuator_crc():
    rng = np.random.default_rng(24)
    for p in PROFILES.values():
        x = rng.uniform(-0.6, 0.6, (p.block, 2))
        tx = Transmitter(p)
        decoded, valid = StreamDecoder(p).run([tx.frame(x)], p.block)
        expected = decode_block(encode_block(x, p), p)
        assert valid.all() and np.allclose(decoded, expected), p.name
        lay = tx.layout
        bd = encode_block(x, p)
        packed = lay.pack(bd, 0, 0)
        body = lay.header_info(packed)
        first = lay.header_bits + sum(p.exp_bits for ch, k in lay.exp_items)
        assert lay.attn_items
        kwargs = {}
        if p.has_y:                                  # Y帯域の最上位bitは専用シンボルの位相から得る
            u, parity, _ = lay.y_parts(bd)
            kwargs["y_soft"] = (8.0 * (1.0 - 2.0 * (u >> (p.y_bits - 1))), 8.0 * (1.0 - 2.0 * parity))
        for index in {first, first + len(lay.attn_items) - 1}:
            damaged = body.copy()
            damaged[index] ^= 1
            frame = lay.with_header(packed, damaged)
            recovered, header = lay.unpack(1.0 - 2.0 * frame, frame, **kwargs)
            if index in lay.high_prot_indices:
                assert recovered is not None and header['high_ok'] is False
            else:
                assert (recovered, header) == (None, None)


def test_layer_assignment_matches_physical_positions():
    for p in PROFILES.values():
        if not p.layered:
            continue
        for encrypted in ([False] if p.has_y else [False, True]):
            lay = YLayout(p) if p.has_y else Layout(p, encrypted=encrypted)
            n = modem.n_symbols(lay.n_tx, lay.n_strong, p.modulation)
            assert lay.n_strong == 2 * n, p.name
            for index, (ch, k, j, pos) in zip(lay.coef_stream_idx, lay.coef_items):
                width = (p.bits_m if ch == 'M' else p.bits_s)[k]
                assert (index < 2 * n) == (width - pos <= p.base_bits(ch, k)), (p.name, ch, k, j, pos)


def test_b200y_stereo_side_uses_qam_strong_positions():
    p = PROFILES['B200Y']
    assert p.y_channels == ('M', 'S') and p.bits_s == (11, 11, 7, 7, 7)
    assert p.base_s[:2] == (5, 5)
    lay = YLayout(p)
    assert any(ch == 'S' for ch, *_ in lay.coef_items)
    assert lay.n_strong == 2 * modem.n_symbols(lay.n_tx, lay.n_strong, p.modulation)


def test_layers_are_even_and_balanced():
    """位相部 (基本層の仮数＋パリティ) と振幅部 (拡張層) はどちらも2の倍数で、強い位置と弱い位置の数が釣り合う。
    QPSKは仮数幅とパリティの和が2の倍数。"""
    from gracefm.layers import balanced
    for p in PROFILES.values():
        for ch, widths, base in (('M', p.bits_m, p.base_m), ('S', p.bits_s, p.base_s)):
            for k, width in enumerate(widths):
                if not width or p.y_band(ch, k):
                    continue
                assert (width + p.protect_bits(k)) % 2 == 0, (p.name, ch, k)
                if p.layered:
                    ext = width - base[k]                              # 位相部 = 基本層の仮数 + パリティ
                    assert (base[k] + p.protect_bits(k)) % 2 == 0 and ext % 2 == 0, (p.name, ch, k)
                    assert base[k] >= max(1, p.protect_bits(k)) and ext >= 2
        if not p.layered:
            continue
        assert (balanced(p).base_m, balanced(p).base_s) == (p.base_m, p.base_s), p.name
        lay = YLayout(p) if p.has_y else Layout(p)
        for ch, widths, base in (('M', p.bits_m, p.base_m), ('S', p.bits_s, p.base_s)):
            for k, width in enumerate(widths):
                if width and not p.y_band(ch, k):
                    # 係数をシンボル単位で分ける: 位相部 (基本層 + パリティ) = 振幅部 (拡張層)、仮数幅 = 4N - K
                    assert base[k] + p.protect_bits(k) == width - base[k], (p.name, ch, k)
        assert lay.n_tx == 2 * lay.n_strong
        # ヘッダ・終端・パリティはいずれも位相部と振幅部に同数ずつ入るので、詰め物は偶数そろえの1個以内
        n_other = lay.n_tx - lay.n_coef_bits - lay.n_top
        assert n_other - lay.n_header - lay.n_tail - lay.n_ytail <= 2, p.name


def test_other_format_identifiers_are_rejected_even_with_matching_id():
    for p in PROFILES.values():
        cls = YLayout if p.has_y else Layout
        current = cls(p)
        x = np.zeros((p.block, 2))
        for tag in (0, 1, 2):
            old = replace(p, format_id=tag)
            lay = cls(old)
            packed = lay.pack(encode_block(x, old), 0, 1)
            # The format identifier is fixed for this implementation.
            assert current.unpack(1.0 - 2.0 * packed, packed) == (None, None)


def test_y_factory_matches_catalog():
    for base, name in [('B200M', 'B200MY'), ('M700M', 'M700MY'), ('M700', 'M700Y')]:
        p = PROFILES[name]
        assert make_y_profile(PROFILES[base], name, p.pid, channels=p.y_channels, bits_m=p.bits_m, bits_s=p.bits_s) == p


def test_parity_next_to_coefficients_corrects_top_mantissa_bits():
    """係数ごとに先頭のシンボルがパリティ付き。上位K bitの誤りをパリティで訂正する。"""
    for name in ('B200M', 'M700'):
        p = PROFILES[name]
        lay = Layout(p)
        bd = encode_block(np.random.default_rng(7).uniform(-0.5, 0.5, (p.block, 2)), p)
        frame = lay.pack(bd, 0, 3)
        assert lay.n_top == sum(p.protect_bits(k) * p.ncoef(k) for bits in (p.bits_m, p.bits_s)
                                for k, w in enumerate(bits) if w)
        assert lay.n_parity == lay.n_top + 12
        # 強い位置の列は係数ごとに「パリティ K bit | 基本層」。係数の先頭にだけパリティがあり、続くbitにはない。
        first = lay.coef_items[lay.top_coef_idx[0]]
        assert 0 < lay.top_stream_idx[0] - lay.parity_idx[0] <= p.protect_bits(first[1])   # パリティは、その係数の最上位bitの直前
        assert lay.top_stream_idx[1] > lay.top_stream_idx[0] + 1 or p.protect_bits(first[1]) > 1
        soft = 1.0 - 2.0 * frame
        flipped = lay.top_stream_idx[np.random.default_rng(8).choice(lay.n_top, 6, replace=False)]
        bits = frame.copy()
        bits[flipped] ^= 1
        soft = 1.0 - 2.0 * bits
        soft[flipped] *= 0.3                           # 誤ったbitは信頼度が低い
        recovered, header = lay.unpack(soft, bits)
        assert recovered is not None and header['high_ok']
        assert np.allclose(decode_block(recovered, p), decode_block(bd, p)), name
        assert np.array_equal(header['top_bits'], frame[lay.top_stream_idx])


def test_high_crc_erases_only_h1_h2_in_receiver():
    from gracefm.codec import haar_forward
    p = PROFILES['B200']
    x = np.random.default_rng(42).uniform(-0.5, 0.5, (p.block, 2))
    tx = Transmitter(p)
    lay = tx.layout
    packed = lay.pack(encode_block(x, p), 0, 0)
    protected = lay.header_info(packed)

    def symbols(changed):
        bits = lay.with_header(packed, changed)
        buf = np.zeros(tx.digital_nsym * modem.bits_per_symbol(p.modulation), np.int64)
        buf[:len(bits)] = bits
        return modem.modulate(buf ^ modem.prbs(len(buf)), tx.digital_nsym, p.modulation, p.alpha)

    for soft in (False, True):
        decoder = StreamDecoder(p, soft_decode=soft)
        good, ok = decoder.decode(symbols(protected))
        assert ok
        high_damaged = protected.copy()
        high_damaged[lay.high_prot_indices[0]] ^= 1
        damaged, ok = decoder.decode(symbols(high_damaged))
        assert ok and decoder.stats['high_crc_fail'] == 1 and decoder.stats['crc_fail'] == 0
        for channel in (0, 1):
            good_bands = haar_forward(good[:, channel], p.levels)
            damaged_bands = haar_forward(damaged[:, channel], p.levels)
            for k in range(p.high_k):
                assert np.allclose(damaged_bands[k], good_bands[k], atol=1e-10)
            for k in range(p.high_k, p.nbands):
                assert np.allclose(damaged_bands[k], 0, atol=1e-10)
        if soft:
            assert np.isinf(decoder.last_rb[:, :, p.high_k:]).all()
            assert np.isfinite(decoder.last_rb[:, :, :p.high_k]).all()
        core_damaged = protected.copy()
        core_damaged[lay.core_prot_indices[-1]] ^= 1
        _, ok = decoder.decode(symbols(core_damaged))
        assert not ok and decoder.stats['crc_fail'] == 1


def test_y_high_crc_keeps_lower_y_band():
    from gracefm.codec import haar_forward
    p = PROFILES['B200Y']
    x = np.random.default_rng(43).uniform(-0.4, 0.4, (p.block, 2))
    tx = Transmitter(p)
    original = tx.frame(x)
    lay = tx.layout
    packed = lay.pack(encode_block(x, p), 0, 0)
    protected = lay.header_info(packed)
    protected[lay.high_prot_indices[0]] ^= 1
    bits = lay.with_header(packed, protected)
    buf = np.zeros(tx.digital_nsym * modem.bits_per_symbol(p.modulation), np.int64)
    buf[:len(bits)] = bits
    digital = modem.modulate(buf ^ modem.prbs(len(buf)), tx.digital_nsym, p.modulation, p.alpha)
    damaged = np.concatenate([digital, original[len(modem.PREAMBLE) + tx.digital_nsym:]])
    decoder = StreamDecoder(p)
    good, ok = decoder.decode(original)
    assert ok
    recovered, ok = decoder.decode(damaged)
    assert ok and decoder.stats['high_crc_fail'] == 1
    for channel in (0, 1):
        g = haar_forward(good[:, channel], p.levels)
        r = haar_forward(recovered[:, channel], p.levels)
        assert np.allclose(r[2], g[2], atol=1e-10)
        assert np.allclose(r[3], 0, atol=1e-10)
        assert np.allclose(r[4], 0, atol=1e-10)


def test_broadcast_main_occupied_bandwidth():
    from scipy.signal import welch
    from gracefm.pulse import shape
    audio = np.random.default_rng(2026).uniform(-0.4, 0.4, (64 * 200, 2))
    expected = {'B200M': 109_000, 'B200': 176_500}     # 99%占有帯域 (ランダム音声での実測)
    for name, reference in expected.items():
        p = PROFILES[name]
        tx = Transmitter(p)
        samples = shape(np.concatenate(tx.run(audio)), beta=p.pulse_beta,
                        span=p.pulse_span, sps=8)
        freq, power = welch(samples, fs=8 * tx.symbol_rate(), nperseg=4096,
                            return_onesided=False, scaling='density')
        order = np.argsort(freq)
        freq, power = freq[order], power[order]
        cumulative = np.cumsum(power) / np.sum(power)
        occupied = freq[np.searchsorted(cumulative, 0.995)] - freq[np.searchsorted(cumulative, 0.005)]
        assert abs(occupied - reference) <= 4_000 and occupied <= 180_000, (name, occupied)


if __name__ == '__main__':
    for name, function in list(globals().items()):
        if name.startswith('test_'):
            function()
            print('ok', name, flush=True)


def test_base_layer_widths_match_layer_solver():
    """登録プロファイルの基本層の幅は、強い位置と弱い位置の数が釣り合う解 (gracefm.layers) と一致する。"""
    from gracefm.layers import solve
    for p in PROFILES.values():
        if not p.layered:
            continue
        base_m, base_s = solve(p)
        assert (tuple(base_m), tuple(base_s)) == (tuple(p.base_m), tuple(p.base_s)), p.name
