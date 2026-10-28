"""基本層だけを復号する (拡張層の事後確率を 0.5 に置き、係数ごとの昇格を保つ)。"""
import copy
import numpy as np
from gracefm.codec import offset_of
from gracefm.txrx import StreamDecoder, Transmitter


class BaseLayerDecoder(StreamDecoder):
    def soft_coeffs(self, bd, probabilities, y_mant, y_var, high_ok=True):
        bd = copy.deepcopy(bd)
        probabilities = np.array(probabilities, np.int64, copy=True)
        # soft_coeffs expects mantissas to contain the hard decisions for its probabilities.
        # An erased bit has p=0.5 (16384 in Q15) and hard decision 0, so clear that bit before taking its mean.
        for ch, k, j, pos in self.layout.coef_items[self.layout.n_base_bits:]:
            bits = self.p.bits_m if ch == "M" else self.p.bits_s
            offset = offset_of(bits[k], self.p, ch, k)
            value = int(bd.mant[ch][k][j]) + offset
            bd.mant[ch][k][j] = (value & ~(1 << pos)) - offset
        # Only the extension layer evidence is erased (the base layer stays in the strong positions).
        probabilities[self.layout.n_base_bits:] = 16384                    # 確率 0.5 (Q15)
        return super().soft_coeffs(bd, probabilities, y_mant, y_var, high_ok)


def base_layer_audio(audio, profile):
    if not profile.layered or profile.has_y:
        raise ValueError('a conventional layered profile is required')
    decoder = BaseLayerDecoder(profile)
    output, valid = decoder.run(Transmitter(profile).run(audio), len(audio))
    if not np.all(valid):
        raise AssertionError('noiseless basic-layer decode failed')
    return output
