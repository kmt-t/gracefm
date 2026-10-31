"""
送信機 (音声 → シンボル)。すべて整数演算。シンボルは (n, 2) の整数 (I, Q)、PCM は符号つき24 bit整数。

analyze (gracefm.codec) → quantize → pack → scramble → modulate の順に、受信 (gracefm.decoder) の鏡になる。
同じ音声を 2系統で送る。2系統のブロックの格子は同じ (gracefm.receiver が時刻を合わせる)。
"""
import numpy as np

from . import framing, modem
from .codec import encode_block
from .layout import Layout
from .profiles import Profile
from .scrambler import scramble


class Encoder:
    def __init__(self, profile: Profile, stream_id=0, offset=0, clip_opt=True, cipher=None):
        """cipher: gracefm.crypto.StreamCipher (暗号化するとき)"""
        if profile.has_y and cipher is not None:
            raise ValueError("YプロファイルはAES-CTR暗号化に未対応です")
        self.p = profile
        self.sid = stream_id
        self.offset = offset
        self.clip_opt = clip_opt
        self.cipher = cipher
        self.layout = Layout(profile, encrypted=cipher is not None)
        self.frame_no = 0
        self.digital_nsym = modem.n_symbols(self.layout.n_tx, self.layout.n_strong, profile.modulation)
        self.nsym = self.digital_nsym + (self.layout.n_y if profile.has_y else 0)

    def frame(self, xblock):
        """xblock: (block, 2) の符号つき24 bit整数 → 1フレームぶんのシンボル (n, 2)"""
        bd = encode_block(xblock, self.p, self.clip_opt)
        ks = None
        if self.cipher is not None:
            ks = self.cipher.keystream(self.sid, self.frame_no, self.layout.n_keystream)
        bits = framing.pack(self.layout, bd, self.sid, self.frame_no, ks)
        self.frame_no += 1
        buf = np.zeros(self.digital_nsym * modem.bits_per_symbol(self.p.modulation), np.int64)
        buf[: len(bits)] = bits
        buf = scramble(buf)                              # 詰め物も含む
        digital = modem.modulate(buf, self.digital_nsym, self.p.modulation, self.p.alpha)
        if not self.p.has_y:
            return digital
        mask = modem.prbs(len(buf) + 3 * self.layout.n_y)[len(buf):]
        u, parity, _ = self.layout.y_parts(bd)
        high = modem.y_modulate(u, parity, self.p.y_step, mask, self.p.y_bits - 1)
        return np.concatenate([digital, high])

    def run(self, x):
        """x: (n, 2) の符号つき24 bit整数 → フレームのリスト"""
        b = self.p.block
        xp = np.pad(np.asarray(x, np.int64), ((self.offset, 0), (0, 0)))
        nfr = -(-len(xp) // b)
        xp = np.pad(xp, ((0, nfr * b - len(xp)), (0, 0)))
        return [self.frame(xp[i * b:(i + 1) * b]) for i in range(nfr)]

    def symbol_rate(self):
        return (self.nsym + modem.N_PREAMBLE) * self.p.frames_per_sec
