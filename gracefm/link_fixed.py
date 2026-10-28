"""
整数だけで動く送信と受信 (単系統、Yなし)。フレーム化 → スクランブル → 変調 → [通信路] → 復調 → デスクランブル →
整数ビタビ → 整数デコーダ。通信路はこのモジュールの外 (試験の道具) で、(I, Q) の整数を受け渡す。

受信は、保護部を整数ビタビで復号し、非保護の仮数bitは硬判定で使う。基本CRCが合わないフレームは欠損として無音を返す
(補間はしない)。高域CRCだけが合わないフレームは、高域 (k >= high_k) の仮数を 0 にする。
"""
import numpy as np

from . import framing, modem
from .codec import BlockData
from .fec_fixed import rsc_decode_int
from .fixed import decode_block_int, encode_block_int
from .layout import Layout
from .modem_fixed import N_PREAMBLE, bits_per_symbol, demodulate, modulate
from .profiles import Profile


class FixedLink:
    """1つのプロファイルの送信・受信 (フレーム番号を持つ)"""

    def __init__(self, profile: Profile, stream_id: int = 0):
        if profile.has_y:
            raise ValueError("Yプロファイルは未対応です")
        self.p = profile
        self.sid = stream_id
        self.layout = Layout(profile)
        self.alpha = int(profile.alpha)
        assert self.alpha == profile.alpha
        self.nsym = modem.n_symbols(self.layout.n_tx, self.layout.n_strong, profile.modulation)
        self.frame_no = 0

    # ---------------------------------------------------------------- 送信
    def transmit(self, block):
        """block: (64, 2) の符号つき24 bit整数 → (I, Q) の整数 (プリアンブルを含む)"""
        bd = encode_block_int(block, self.p)
        bits = framing.pack(self.layout, bd, self.sid, self.frame_no)
        self.frame_no += 1
        buf = np.zeros(self.nsym * bits_per_symbol(self.p.modulation), np.int64)
        buf[: len(bits)] = bits
        buf ^= modem.prbs(len(buf))
        return modulate(buf, self.nsym, self.p.modulation, self.alpha)

    # ---------------------------------------------------------------- 受信
    def receive(self, i_sym, q_sym):
        """(I, Q) の整数 (プリアンブルを含む) → (block, 2) の符号つき24 bit整数。欠損は None"""
        lay, p = self.layout, self.p
        nb = self.nsym * bits_per_symbol(p.modulation)
        llr, hard, _ = demodulate(i_sym[N_PREAMBLE:], q_sym[N_PREAMBLE:], nb, p.modulation, self.alpha)
        prbs = modem.prbs(nb)
        llr = np.where(prbs == 1, -llr, llr)                 # デスクランブル: 反転したビットの軟値の符号も反転
        hard = hard ^ prbs
        bd, header = framing.unpack(lay, llr[: lay.n_tx], hard[: lay.n_tx], decoder=rsc_decode_int)
        if bd is None:
            return None
        if not header["high_ok"]:
            bd = self._erase_high(bd)
        return decode_block_int(bd, p)

    def _erase_high(self, bd: BlockData):
        for ch in ("M", "S"):
            for k in range(self.p.high_k, self.p.nbands):
                if bd.mant[ch][k] is not None:
                    bd.mant[ch][k] = np.zeros_like(bd.mant[ch][k])
        return bd
