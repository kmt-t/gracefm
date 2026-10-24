"""Catalog generation, standard attenuation and actual layer placement contracts."""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gracefm import fec, modem
from gracefm.codec import encode_block, decode_block
from gracefm.framing import Layout, HybridLayout
from gracefm.profiles import PROFILES, BY_ID, BY_HEADER, make_hybrid
from gracefm.txrx import Transmitter, StreamDecoder


def test_catalog_ids_and_standard_attenuation():
    from gracefm.channel import DEFAULT_SUB
    assert set(DEFAULT_SUB) <= PROFILES.keys()
    for main, secondary in DEFAULT_SUB.items():
        assert PROFILES[main].fs == PROFILES[secondary].fs
    assert list(BY_ID) == list(range(1, 13))
    assert not {'B200', 'B200M', 'S50M', 'S100', 'S100-48K'} & PROFILES.keys()
    assert all(PROFILES[name].modulation == 'qpsk' for name in ('SUB50M', 'SUB100', 'SUB100-48K'))
    assert all(PROFILES[name].modulation == 'qam16h' for name in ('B200H', 'B200Y', 'B200HY'))
    assert all(PROFILES[name].modulation == 'qam16h' for name in ('M700', 'M700H', 'M700Y', 'M700HY'))
    assert PROFILES['M700'].base_s == PROFILES['M700Y'].base_s == (2,) * 7
    assert not {'M700Q16', 'B150', 'B150M', 'S85M', 'B200MH-A4', 'B200H-A4'} & PROFILES.keys()
    for p in PROFILES.values():
        assert p.experimental_tag == 3 and BY_ID[p.pid] is p
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
        decoded, valid = StreamDecoder(p, postfilter=False).run([tx.frame(x)], p.block)
        expected = decode_block(encode_block(x, p), p)
        assert valid.all() and np.allclose(decoded, expected), p.name
        lay = tx.layout
        packed = lay.pack(encode_block(x, p), 0, 0)
        body = fec.viterbi_decode(1 - 2 * packed[:lay.n_coded], lay.n_prot_crc)
        first = lay.header_bits + sum(p.exponent_bits(ch, k) for ch, k in lay.exp_items)
        assert lay.attn_items
        for index in {first, first + len(lay.attn_items) - 1}:
            damaged = body.copy()
            damaged[index] ^= 1
            recovered, header = lay.unpack(1 - 2 * fec.conv_encode(damaged), packed[lay.n_coded:])
            if index in lay.high_prot_indices:
                assert recovered is not None and header['high_ok'] is False
            else:
                assert (recovered, header) == (None, None)


def test_layer_assignment_matches_physical_positions():
    for p in PROFILES.values():
        if not p.layered:
            continue
        for encrypted in ([False] if p.hybrid else [False, True]):
            lay = HybridLayout(p) if p.hybrid else Layout(p, encrypted=encrypted)
            n = modem.n_symbols(lay.n_tx, lay.n_strong, p.modulation)
            assert lay.n_strong == 2 * n, p.name
            for index, (ch, k, j, pos) in enumerate(lay.unp_items, lay.n_coded):
                width = (p.bits_m if ch == 'M' else p.bits_s)[k]
                assert (index < 2 * n) == (width - pos <= p.base_bits(ch, k, j)), (p.name, ch, k, j, pos)


def test_b200y_stereo_side_uses_qam_strong_positions():
    p = PROFILES['B200Y']
    assert p.hybrid_channels == ('M',) and p.bits_s == (7, 6, 5, 2, 2, 0, 2)
    assert p.base_s == (1, 1, 1, 1, 1, 0, 1)
    lay = HybridLayout(p)
    assert any(ch == 'S' for ch, *_ in lay.unp_items)
    assert lay.n_strong == 2 * modem.n_symbols(lay.n_tx, lay.n_strong, p.modulation)


def test_other_format_identifiers_are_rejected_even_with_matching_id():
    for p in PROFILES.values():
        cls = HybridLayout if p.hybrid else Layout
        current = cls(p)
        x = np.zeros((p.block, 2))
        for tag in (0, 1, 2):
            old = replace(p, experimental_tag=tag)
            lay = cls(old)
            packed = lay.pack(encode_block(x, old), 0, 1)
            # The format identifier is fixed for this implementation.
            assert current.unpack(1 - 2 * packed[:current.n_coded], packed[current.n_coded:]) == (None, None)


def test_hybrid_factory_matches_catalog():
    for base, name in [('B200MH', 'B200MHY'), ('B200H', 'B200HY'), ('M700', 'M700Y'), ('M700H', 'M700HY')]:
        p = PROFILES[name]
        assert make_hybrid(PROFILES[base], name, p.pid) == p


def test_high_crc_erases_only_h1_h2_in_receiver():
    from gracefm.codec import haar_forward
    p = PROFILES['B200H']
    x = np.random.default_rng(42).uniform(-0.5, 0.5, (p.block, 2))
    tx = Transmitter(p)
    lay = tx.layout
    packed = lay.pack(encode_block(x, p), 0, 0)
    protected = fec.viterbi_decode(1 - 2 * packed[:lay.n_coded], lay.n_prot_crc)

    def symbols(changed):
        bits = np.concatenate([fec.conv_encode(changed), packed[lay.n_coded:]])
        buf = np.zeros(tx.digital_nsym * modem.bits_per_symbol(p.modulation), np.int64)
        buf[:len(bits)] = bits
        return modem.modulate(buf ^ modem.prbs(len(buf)), tx.digital_nsym, p.modulation, p.alpha)

    for soft in (False, True):
        decoder = StreamDecoder(p, postfilter=False, soft_decode=soft)
        good, ok = decoder.decode(symbols(protected))
        assert ok
        high_damaged = protected.copy()
        high_damaged[lay.high_prot_indices[0]] ^= 1
        damaged, ok = decoder.decode(symbols(high_damaged))
        assert ok and decoder.stats['high_crc_fail'] == 1 and decoder.stats['crc_fail'] == 0
        for channel in (0, 1):
            good_bands = haar_forward(good[:, channel], p.levels)
            damaged_bands = haar_forward(damaged[:, channel], p.levels)
            for k in range(5):
                assert np.allclose(damaged_bands[k], good_bands[k], atol=1e-10)
            for k in (5, 6):
                assert np.allclose(damaged_bands[k], 0, atol=1e-10)
        if soft:
            assert np.isinf(decoder.last_rb[:, :, 5:]).all()
            assert np.isfinite(decoder.last_rb[:, :, :5]).all()
        core_damaged = protected.copy()
        core_damaged[lay.core_prot_indices[-1]] ^= 1
        _, ok = decoder.decode(symbols(core_damaged))
        assert not ok and decoder.stats['crc_fail'] == 1
    filtered, ok = StreamDecoder(p, postfilter=True).decode(symbols(high_damaged))
    assert ok
    for channel in (0, 1):
        bands = haar_forward(filtered[:, channel], p.levels)
        assert np.allclose(bands[5], 0, atol=1e-10)
        assert np.allclose(bands[6], 0, atol=1e-10)


def test_hybrid_high_crc_keeps_lower_hybrid_band():
    from gracefm.codec import haar_forward
    p = PROFILES['B200HY']
    x = np.random.default_rng(43).uniform(-0.4, 0.4, (p.block, 2))
    tx = Transmitter(p)
    original = tx.frame(x)
    lay = tx.layout
    packed = lay.pack(encode_block(x, p), 0, 0)
    protected = fec.viterbi_decode(1 - 2 * packed[:lay.n_coded], lay.n_prot_crc)
    protected[lay.high_prot_indices[0]] ^= 1
    bits = np.concatenate([fec.conv_encode(protected), packed[lay.n_coded:]])
    buf = np.zeros(tx.digital_nsym * modem.bits_per_symbol(p.modulation), np.int64)
    buf[:len(bits)] = bits
    digital = modem.modulate(buf ^ modem.prbs(len(buf)), tx.digital_nsym, p.modulation, p.alpha)
    damaged = np.concatenate([digital, original[len(modem.PREAMBLE) + tx.digital_nsym:]])
    decoder = StreamDecoder(p, postfilter=False)
    good, ok = decoder.decode(original)
    assert ok
    recovered, ok = decoder.decode(damaged)
    assert ok and decoder.stats['high_crc_fail'] == 1
    for channel in (0, 1):
        g = haar_forward(good[:, channel], p.levels)
        r = haar_forward(recovered[:, channel], p.levels)
        assert np.allclose(r[4], g[4], atol=1e-10)
        assert np.allclose(r[5], 0, atol=1e-10)
        assert np.allclose(r[6], 0, atol=1e-10)


def test_broadcast_main_occupied_bandwidth_is_near_180_khz():
    from scipy.signal import welch
    from gracefm.pulse import shape
    audio = np.random.default_rng(2026).uniform(-0.4, 0.4, (64 * 200, 2))
    for name in ('B200MH', 'B200H', 'B200HY'):
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
        assert 175_000 <= occupied <= 185_000, (name, occupied)


if __name__ == '__main__':
    for name, function in list(globals().items()):
        if name.startswith('test_'):
            function()
            print('ok', name, flush=True)
