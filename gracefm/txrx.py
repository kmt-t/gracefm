"""
送信機・受信機 (2系統)。すべて整数演算。シンボルは (n, 2) の整数 (I, Q)、PCM は符号つき24 bit整数。

送信: 同じ音声を 2系統で送る。2系統のブロックの格子は同じ。
      2系統は大きく離れた別の周波数で送り、欠落やフェージングを独立にする。
受信: 系統ごとに 復調 → 軟判定ビタビ → CRC 判定 → 復号。
      基本CRC不一致はフレーム欠落。H1/H2 CRCだけの不一致は高域を消去して低中域を採用する。
      2系統の合成: ブロック単位で、両方届いた区間は帯域ごとに融合 (gracefm/fusion.py。各系統の係数の
      誤差分散による逆分散重み) / 片方だけなら片方 / どちらも無ければ PLC。

誤差分散は (対数領域の整数) で扱う: log2(分散) × 2^8。届かない帯域は INF_LOG (情報なし)。
"""
import numpy as np

from . import fec, framing, fusion, modem, plc
from .codec import (attenuator_expanded, encode_block, exp_range, FRAC, haar_inverse, ms_to_lr, offset_of, qmax_of, qmin_of)
from .crypto import unwrap_counter
from .dsp import log2_q8, saturate, shift_signed, sigmoid_q15
from .fusion import INF_LOG
from .layout import Layout
from .profiles import Profile

ONE_TWELFTH_Q15 = 2731                                  # 1/12 (量子化誤差の分散。仮数の最下位bit単位) を Q15 で


class Transmitter:
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
        buf ^= modem.prbs(len(buf))                      # スクランブル (詰め物も含む)
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


class StreamDecoder:
    def __init__(self, profile: Profile, cipher=None, y_phase_only=False):
        if profile.has_y and cipher is not None:
            raise ValueError("YプロファイルはAES-CTR暗号化に未対応です")
        self.p = profile
        self.y_phase_only = y_phase_only
        self.cipher = cipher
        self.last_frame_no = -1
        self.layout = Layout(profile, encrypted=cipher is not None)
        self.digital_nsym = modem.n_symbols(self.layout.n_tx, self.layout.n_strong, profile.modulation)
        self.stats = {"frames": 0, "lost": 0, "crc_fail": 0, "high_crc_fail": 0}
        self.last_rb = None

    def _y_mask(self):
        lay = self.layout
        digital_bits = self.digital_nsym * modem.bits_per_symbol(self.p.modulation)
        return modem.prbs(digital_bits + 3 * lay.n_y)[digital_bits:]

    def _y_phase(self, sym, var):
        """専用シンボルの位相から、最上位bitとパリティの LLR を得る (ヘッダ部の復号に渡す)"""
        start = modem.N_PREAMBLE + self.digital_nsym
        return modem.y_phase_llr(sym[start:], self.p.y_step, self._y_mask(), var, self.p.y_bits - 1)

    def _recover_y(self, sym, hdr, var, high_ok=True):
        """Y帯域の半径の推定値 {(ch, k): 仮数の推定値 (小数 MANT_FRAC bit)} と、その誤差分散 {(ch, k): Q15 の分散}"""
        lay, p = self.layout, self.p
        start = modem.N_PREAMBLE + self.digital_nsym
        if len(sym) != start + lay.n_y:
            raise ValueError("Yフレームのシンボル数が一致しません")
        b = p.y_bits
        msb = hdr["y_msb"]                          # CRCを通った (パリティで訂正した) 最上位bit
        parity = fec_parity(msb)
        u, variance = modem.y_demodulate(sym[start:], msb, parity, p.y_step, self._y_mask(), var, b - 1, self.y_phase_only)
        mant, mvar = {}, {}
        shift = 15 - 2 * modem.MANT_FRAC
        for i, (ch, k, j) in enumerate(lay.y_items):
            if k >= p.high_k and not high_ok:
                continue
            if (ch, k) not in mant:
                mant[(ch, k)] = np.zeros(p.ncoef(k), np.int64)
                mvar[(ch, k)] = np.zeros(p.ncoef(k), np.int64)
            mant[(ch, k)][j] = u[i] - (offset_of(b, p, ch, k) << modem.MANT_FRAC)
            mvar[(ch, k)][j] = variance[i] << shift
        return mant, mvar

    def soft_coeffs(self, bd, p1_coef, y_mant, y_var, high_ok=True):
        """
        軟判定の復号: 非保護ビットを 0/1 に丸めず、1 である事後確率 p1 (Q15) をそのままビットの値として使う。
        ビットどうしは独立とみなし、仮数の期待値と事後分散を求める:
          期待値   E[u] = 硬判定の u + Σ (p1 - 硬判定ビット)·2^pos
          事後分散 Σ p1 (1 - p1)·4^pos
        返り値: 帯域係数 {ch: [整数の係数]}、誤差分散 rb (半ブロック・M/S・帯域) の対数領域 (INF_LOG = 情報なし)
        """
        p, lay = self.p, self.layout
        hard = (p1_coef > 16384).astype(np.int64)
        w = np.int64(1) << lay.coef_pos
        du = lay.segment_sum((p1_coef - hard * 32768) * w)
        var = lay.segment_sum(((p1_coef * (32768 - p1_coef)) >> 15) * w * w)
        coefs = {}
        rb = np.full((2, 2, p.nbands), INF_LOG, np.int64)
        for ci, (ch, bits) in enumerate((("M", p.bits_m), ("S", p.bits_s))):
            coefs[ch] = []
            for k, b in enumerate(bits):
                n = p.ncoef(k)
                if b == 0 or (k >= p.high_k and not high_ok):
                    coefs[ch].append(np.zeros(n, np.int64))
                    continue
                o = lay.coef_offset[(ch, k)]
                qmax, qmin = qmax_of(b), qmin_of(b, p, ch, k)
                if (ch, k) in y_mant:
                    m_q15 = y_mant[(ch, k)] << (15 - modem.MANT_FRAC)
                    extra = y_var[(ch, k)]
                else:
                    m_q15 = (bd.mant[ch][k].astype(np.int64) << 15) + du[o:o + n]
                    extra = 0
                m_q15 = np.clip(m_q15, qmin << 15, qmax << 15)
                a = attenuator_expanded(bd.attn[ch][k], p.attenuator_group(ch, k), n)
                s = int(bd.eidx[ch][k]) + exp_range(k, b, p)[0] + FRAC - a                   # 係数ごとの刻みの指数
                coefs[ch].append(saturate(shift_signed(m_q15, s - 15)))
                rv = (var[o:o + n] + extra + ONE_TWELFTH_Q15) >> (2 * a)                         # 刻み 2^s の二乗を除いた分散 (Q15)
                exp_two = 2 * (int(bd.eidx[ch][k]) + exp_range(k, b, p)[0] + FRAC) - 15
                if n >= 2:
                    halves = (int(rv[: n // 2].sum()) // (n // 2), int(rv[n // 2:].sum()) // (n // 2))
                else:
                    halves = (int(rv[0]), int(rv[0]))
                for hh in (0, 1):
                    rb[hh, ci, k] = log2_q8(max(halves[hh], 1)) + (exp_two << 8)
        self.last_rb = rb
        return coefs

    def decode(self, sym):
        """sym: 1フレームの受信シンボル (n, 2) (届かなければ None) → ((block, 2), 有効か)"""
        p, lay = self.p, self.layout
        self.stats["frames"] += 1
        n_pre = modem.N_PREAMBLE
        expected = n_pre + self.digital_nsym + (lay.n_y if p.has_y else 0)
        if sym is not None and len(sym) != expected:
            sym = None
        if sym is None:
            self.stats["lost"] += 1
            self.last_rb = None
            return np.zeros((p.block, 2), np.int64), False
        digital = sym[n_pre:n_pre + self.digital_nsym]
        llr, hard, var = modem.demodulate(digital, lay.n_tx, p.modulation, p.alpha)
        s = modem.prbs(lay.n_tx)                                  # スクランブルを戻す
        llr, hard = np.where(s == 1, -llr, llr), hard ^ s
        y_soft = self._y_phase(sym, var) if p.has_y else None
        bd, hdr = framing.unpack_recovering(lay, llr, hard, self._ks_for, y_soft=y_soft)
        if bd is None:
            self.stats["crc_fail"] += 1
            self.last_rb = None
            return np.zeros((p.block, 2), np.int64), False
        p1_coef = sigmoid_q15(llr[lay.coef_stream_idx])
        if self.cipher is not None:                              # 仮数bitの事後確率も暗号を戻す
            ku = hdr["ks"][lay.n_body:]
            p1_coef = np.where(ku == 1, 32768 - p1_coef, p1_coef)
        if lay.n_top:                                            # パリティで訂正した上位K bitを確定値にする
            p1_coef[lay.top_coef_idx] = hdr["top_bits"] * 32768
        high_ok = hdr["high_ok"]
        if not high_ok:
            self.stats["high_crc_fail"] += 1
        y_mant, y_var = ({}, {})
        if p.has_y:
            y_mant, y_var = self._recover_y(sym, hdr, var, high_ok)
        coefs = self.soft_coeffs(bd, p1_coef, y_mant, y_var, high_ok)
        out = {ch: haar_inverse(coefs[ch]) for ch in ("M", "S")}
        return ms_to_lr(out["M"], out["S"]), True

    def _ks_for(self, header):
        """ヘッダの24bit のフレーム番号から40bit の番号を復元し、キーストリームを作る"""
        if self.cipher is None:
            return None
        fn = unwrap_counter(header["counter"], self.last_frame_no)
        self.last_frame_no = fn
        return self.cipher.keystream(header["stream"], fn, self.layout.n_keystream)

    def run(self, frames, n, offset=0):
        """返り値: (時刻合わせ済みの音声 (n, 2)、有効フラグ)。self.rb_trace に帯域ごと・半ブロックごとの
        誤差分散 (対数領域) (n, 2, 帯域数) を残す。届かない帯域は INF_LOG"""
        b = self.p.block
        h = b // 2
        y = np.zeros((len(frames) * b, 2), np.int64)
        v = np.zeros(len(frames) * b, bool)
        rb = np.full((len(frames) * b, 2, self.p.nbands), INF_LOG, np.int64)
        for i, sym in enumerate(frames):
            y[i * b:(i + 1) * b], v[i * b:(i + 1) * b] = self.decode(sym)
            if self.last_rb is not None:
                rb[i * b:i * b + h] = self.last_rb[0]
                rb[i * b + h:(i + 1) * b] = self.last_rb[1]
        self.rb_trace = rb[offset:offset + n]
        return y[offset:offset + n], v[offset:offset + n]


def fec_parity(msb):
    return fec.rsc_parity(msb)[0][:len(msb)]


def receive(profile: Profile, framesA, framesB, n, offset_b, plc_order=16,
            return_streams=False, profile_b=None, cipher=None, y_phase_only=False):
    """
    2系統 (framesB=None なら 1系統) を受信して (n, 2) の整数の音声を返す。
    return_streams=True なら stats に各系統の時刻合わせ済み出力と重みの推移も入れる (評価用)。
    profile_b: 副系のプロファイル (None なら主系と同じ)。サンプリング周波数とブロック長は主系と同じであること。
    cipher: 暗号化しているとき、送信側と同じ鍵・nonce の gracefm.crypto.StreamCipher。
    """
    pb = profile if profile_b is None else profile_b
    assert pb.fs == profile.fs and pb.block == profile.block
    dA = StreamDecoder(profile, cipher=cipher, y_phase_only=y_phase_only)
    yA, vA = dA.run(framesA, n, 0)
    stats = {"A": dA.stats}
    if framesB is not None:
        dB = StreamDecoder(pb, cipher=cipher, y_phase_only=y_phase_only)
        yB, vB = dB.run(framesB, n, offset_b)
        stats["B"] = dB.stats
        y, v, tr = fusion.fuse_band(yA, vA, yB, vB, profile.block, profile.levels, dA.rb_trace, dB.rb_trace)
        if return_streams:
            stats.update(yA=yA, vA=vA, yB=yB, vB=vB, weight_trace=tr)
    else:
        y, v = yA, vA
    stats["plc_samples"] = int((~v).sum())
    traces = [dA.rb_trace] + ([dB.rb_trace] if framesB is not None else [])
    patterns = [tuple(np.concatenate([(rb[i * profile.block] != INF_LOG).ravel() for rb in traces]))
                for i in range(len(y) // profile.block)]
    y = plc.crossfade_switch(y, patterns, profile.block, order=plc_order)
    return plc.conceal(y, v, profile.fs, order=plc_order), stats
