"""
送信機・受信機 (2系統)。

送信: 同じ音声を 2系統で送る。2系統のブロックの格子は同じ。
      2系統は大きく離れた別の周波数で送り、欠落やフェージングを独立にする。
受信: 系統ごとに 復調 → 軟判定ビタビ → CRC 判定 → 復号。
      基本CRC不一致はフレーム欠落。H1/H2 CRCだけの不一致は高域を消去して低中域を採用する。
      2系統の合成: ブロック単位で、両方届いた区間は帯域ごとに融合 (gracefm/fusion.py。各系統の係数の
      誤差分散による逆分散重み) / 片方だけなら片方 / どちらも無ければ PLC。
"""
import numpy as np

from . import fec, fusion, modem, plc
from .codec import (attenuator_expanded, decode_coeffs, encode_block, exp_range,
                    haar_inverse, ms_to_lr, offset_of, qmax_of, qmin_of)
from . import framing
from .layout import Layout
from .crypto import unwrap_counter
from .profiles import Profile


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
        """xblock: (block, 2) → 1フレームぶんの複素シンボル"""
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
        high = modem.y_modulate(u, parity, self.p.y_amplitude, mask, self.p.y_bits - 1)
        return np.concatenate([digital, high])

    def run(self, x):
        """x: (n, 2) → フレームのリスト"""
        b = self.p.block
        xp = np.pad(x, ((self.offset, 0), (0, 0)))
        nfr = int(np.ceil(len(xp) / b))
        xp = np.pad(xp, ((0, nfr * b - len(xp)), (0, 0)))
        return [self.frame(xp[i * b:(i + 1) * b]) for i in range(nfr)]

    def symbol_rate(self):
        return (self.nsym + len(modem.PREAMBLE)) * self.p.frames_per_sec


class StreamDecoder:
    def __init__(self, profile: Profile, soft_decode=True,
                 cipher=None, y_phase_only=False):
        """
        soft_decode=True: 非保護ビットを硬判定せず、事後確率で重み付けした仮数の期待値で復号する
                          (modem.bit_probs。保護部は CRC が通った確定値)。False なら硬判定 (比較用)。
        """
        if profile.has_y and cipher is not None:
            raise ValueError("YプロファイルはAES-CTR暗号化に未対応です")
        self.p = profile
        self.y_phase_only = y_phase_only
        self.soft_decode = soft_decode
        self.cipher = cipher
        self.last_frame_no = -1
        self.last_pre_err = None                        # 直前フレームの、既知プリアンブルとの差から求めた I/Q 軸あたりの誤差分散 (復調には使わない。記録用)
        self.layout = Layout(profile, encrypted=cipher is not None)
        self.digital_nsym = modem.n_symbols(self.layout.n_tx, self.layout.n_strong, profile.modulation)
        self.stats = {"frames": 0, "lost": 0, "crc_fail": 0, "high_crc_fail": 0}
        self.last_r = (np.nan, np.nan)          # 直前フレームの誤差分散の見積もり (M, S)
        self.y_variance = {}

    def _y_mask(self):
        lay = self.layout
        digital_bits = self.digital_nsym * modem.bits_per_symbol(self.p.modulation)
        return modem.prbs(digital_bits + 3 * lay.n_y)[digital_bits:]

    def _y_phase(self, sym):
        """専用シンボルの位相から、最上位bitとパリティの軟値を得る (ヘッダ部の復号に渡す)"""
        start = len(modem.PREAMBLE) + self.digital_nsym
        llr_msb, llr_par, _ = modem.y_phase_llr(sym[start:], self.p.y_amplitude, self._y_mask(),
                                                     sym[:len(modem.PREAMBLE)], self.p.y_bits - 1)
        return llr_msb, llr_par

    def _recover_y(self, sym, bd, hdr, high_ok=True):
        lay, p = self.layout, self.p
        start = len(modem.PREAMBLE) + self.digital_nsym
        if len(sym) != start + lay.n_y:
            raise ValueError("Yフレームのシンボル数が一致しません")
        b = p.y_bits
        msb = hdr["y_msb"]                          # CRCを通った (パリティで訂正した) 最上位bit
        parity = fec.rsc_parity(msb)[0][:len(msb)]
        u, var, sigma2 = modem.y_demodulate(sym[start:], msb, parity, p.y_amplitude,
                                                 self._y_mask(), sym[:len(modem.PREAMBLE)], b - 1,
                                                 self.y_phase_only)
        self.y_variance = {}
        for i, (ch, k, j) in enumerate(lay.y_items):
            if k >= p.high_k and not high_ok:
                continue
            if (ch, k) not in self.y_variance:
                self.y_variance[(ch, k)] = np.zeros(p.ncoef(k))
                bd.mant[ch][k] = bd.mant[ch][k].astype(float)
            bd.mant[ch][k][j] = u[i] - offset_of(b, p, ch, k)
            self.y_variance[(ch, k)][j] = var[i]
        self.stats["y_axis_noise_variance_sum"] = self.stats.get("y_axis_noise_variance_sum", 0.0) + sigma2
        self.stats["y_frames"] = self.stats.get("y_frames", 0) + 1

    def error_variance(self, bd, soft_coef):
        """
        受信座標からの補助情報: このフレームの復号音声に乗りうる誤差の分散 (1サンプルあたり, M と S)。
        非保護ビットごとに、軟判定値の大きさから誤っている確率 q を求め (QPSK の 1軸ぶんの雑音分散は
        受信座標のばらつきから推定)、そのビットが誤ったときの係数の変化 (2^pos × 量子化ステップ) の
        2乗をかけて合計する。量子化そのものの誤差 (ステップ^2/12) も足す。CRC が通った保護部は誤りなしとみなす。
        BER の推定値は使わず、ビットごとの信頼度だけを使う。QPSK 以外では量子化誤差の項だけを返す。
        """
        p = self.p
        lay = self.layout
        steps = np.zeros(lay.n_coef)                     # 係数ごとの量子化ステップ
        qn = np.zeros(2)
        for ci, ch in enumerate(("M", "S")):
            bits = p.bits_m if ch == "M" else p.bits_s
            for k, b in enumerate(bits):
                if b > 0:
                    emin = exp_range(k, b, p, ch)[0]
                    o, n = lay.coef_offset[(ch, k)], p.ncoef(k)
                    a = attenuator_expanded(bd.attn[ch][k], p.attenuator_group(ch, k), n)
                    steps[o:o + n] = 2.0 ** (bd.eidx[ch][k] + emin - a)
                    qn[ci] += np.sum(steps[o:o + n] ** 2) / 12
        tot = qn.copy()
        if p.modulation == "qpsk" and lay.n_coef_bits:
            a = 1 / np.sqrt(2)
            sig2 = max(float(np.mean((np.abs(self._axis) - a) ** 2)), 1e-6)
            q = 1.0 / (1.0 + np.exp(np.minimum(2 * a * np.abs(soft_coef) / sig2, 60.0)))
            e = q * (2.0 ** lay.coef_pos * steps[lay.coef_flat]) ** 2
            tot += np.bincount(lay.coef_ch, weights=e, minlength=2)
        return tot / p.block

    def soft_coeffs(self, bd, p1_coef, high_ok=True):
        """
        軟判定の復号: 非保護ビットを 0/1 に丸めず、1 である事後確率 p1 をそのままビットの値として使う。
        ビットどうしは独立とみなし、仮数の期待値と事後分散を閉じた式で求める:
          期待値   E[u] = 硬判定の u + Σ (p1 - 硬判定ビット)·2^pos
          事後分散 Σ p1 (1 - p1)·4^pos
        返り値: (帯域係数, 誤差分散 (M, S) / 1サンプル)
        """
        p, lay = self.p, self.layout
        hard = (p1_coef > 0.5).astype(float)
        w = 2.0 ** lay.coef_pos
        du = np.bincount(lay.coef_flat, weights=(p1_coef - hard) * w, minlength=lay.n_coef)
        var = np.bincount(lay.coef_flat, weights=p1_coef * (1 - p1_coef) * w * w, minlength=lay.n_coef)
        # 係数ごとに最も不確かなビット (誤差分散への寄与が最大) を選び、それを反転した候補との差 alt と反転確率 pa を求める
        contrib = p1_coef * (1 - p1_coef) * w * w
        best = np.zeros(lay.n_coef)
        np.maximum.at(best, lay.coef_flat, contrib)
        top = contrib >= best[lay.coef_flat] - 1e-300
        alt = np.zeros(lay.n_coef)
        pa = np.zeros(lay.n_coef)
        alt[lay.coef_flat[top]] = ((1 - 2 * hard) * w)[top]
        pa[lay.coef_flat[top]] = np.abs(p1_coef - hard)[top]
        coefs = {}
        R = np.zeros(2)
        rb = np.full((2, 2, p.nbands), np.inf)          # (前半/後半, M/S, 帯域) の係数あたりの誤差分散
        self.last_rv = {}                               # (ch, 帯域) → 係数ごとの誤差分散 (評価・学習データ用)
        self.last_su = {}                               # (ch, 帯域) → 係数ごとの誤差の標準偏差 (仮数の最下位bit単位)
        self.last_alt = {}                              # (ch, 帯域) → (最も不確かなビットを反転した候補との差, 反転確率)
        for ci, (ch, bits) in enumerate((("M", p.bits_m), ("S", p.bits_s))):
            coefs[ch] = []
            for k, b in enumerate(bits):
                n = p.ncoef(k)
                if k >= p.high_k and not high_ok:
                    coefs[ch].append(np.zeros(n))
                    continue
                if b == 0:
                    coefs[ch].append(np.zeros(n))
                    continue
                o = lay.coef_offset[(ch, k)]
                qmax = qmax_of(b)
                qmin = qmin_of(b, p, ch, k)
                m = bd.mant[ch][k].astype(float)
                e = np.int64(bd.eidx[ch][k])
                a = attenuator_expanded(bd.attn[ch][k], p.attenuator_group(ch, k), n)
                step = 2.0 ** (e + exp_range(k, b, p, ch)[0] - a)
                z = np.clip(m + du[o:o + n], qmin, qmax) * step
                extra = self.y_variance.get((ch, k), 0)
                rv = (var[o:o + n] + extra + 1.0 / 12) * step ** 2
                coefs[ch].append(z)
                self.last_rv[(ch, k)] = rv
                self.last_su[(ch, k)] = np.sqrt(var[o:o + n] + extra + 1.0 / 12)
                self.last_alt[(ch, k)] = (alt[o:o + n] * step, pa[o:o + n])
                R[ci] += np.sum(rv)
                if n >= 2:
                    rb[0, ci, k], rb[1, ci, k] = np.mean(rv[: n // 2]), np.mean(rv[n // 2:])
                else:
                    rb[:, ci, k] = rv[0]
        self.last_rb = rb
        return coefs, R / p.block

    def decode(self, sym):
        """sym: 1フレームの受信シンボル (届かなければ None) → ((block, 2), 有効か)"""
        p = self.p
        lay = self.layout
        self.stats["frames"] += 1
        bd = None
        self.y_variance = {}
        expected_symbols = len(modem.PREAMBLE) + self.digital_nsym + (lay.n_y if p.has_y else 0)
        if sym is not None and len(sym) != expected_symbols:
            sym = None
        digital_sym = sym[:len(modem.PREAMBLE) + self.digital_nsym] if sym is not None and p.has_y else sym
        y_soft = self._y_phase(sym) if sym is not None and p.has_y else None
        if sym is None:
            self.stats["lost"] += 1
        elif self.soft_decode:
            npre = len(modem.PREAMBLE)
            self.last_pre_err = float(np.mean(np.abs(digital_sym[:npre] - modem.PREAMBLE) ** 2) / 2)   # 記録用 (NN の入力に使う)
            p1, llr = modem.bit_probs(digital_sym, lay.n_tx, p.modulation, p.alpha)
            s = modem.prbs(lay.n_tx).astype(bool)        # スクランブルを戻す
            p1, llr = np.where(s, 1 - p1, p1), np.where(s, -llr, llr)
            bd, hdr = framing.unpack(lay, llr, (p1 > 0.5).astype(np.int64), self._ks_for, y_soft=y_soft)
            p1_coef = p1[lay.coef_stream_idx]
            if bd is not None and self.cipher is not None:  # 仮数bitの事後確率も暗号を戻す
                ku = hdr["ks"][lay.n_body:].astype(bool)
                p1_coef = np.where(ku, 1 - p1_coef, p1_coef)
            if bd is None:
                self.stats["crc_fail"] += 1
        else:
            soft, hard = modem.demodulate(digital_sym, lay.n_tx, p.modulation, p.alpha)
            sc = modem.prbs(len(soft))                   # スクランブルを戻す (軟値は強い位置の分だけ)
            soft = soft * (1 - 2 * sc)
            hard = hard ^ modem.prbs(len(hard))
            self._axis = soft
            # 弱い位置 (振幅部) には軟値が無いので、硬判定に小さな信頼度をつけて渡す
            weak_conf = 0.3 * max(float(np.median(np.abs(soft))), 1e-6)
            soft = np.concatenate([soft, weak_conf * (1.0 - 2.0 * hard[len(soft):])])
            bd, hdr = framing.unpack(lay, soft, hard, self._ks_for, y_soft=y_soft)
            p1_coef = hard.astype(float)[lay.coef_stream_idx]
            if bd is None:
                self.stats["crc_fail"] += 1
        if bd is not None and lay.n_top:                  # パリティで訂正した上位K bitを確定値にする
            p1_coef = np.array(p1_coef, float)
            p1_coef[lay.top_coef_idx] = hdr["top_bits"]
        if bd is None:
            self.last_r = (np.nan, np.nan)
            self.last_rb = None
            return np.zeros((p.block, 2)), False
        high_ok = hdr["high_ok"]
        if not high_ok:
            self.stats["high_crc_fail"] += 1
        if p.has_y:
            self._recover_y(sym, bd, hdr, high_ok)
        if self.soft_decode or p.has_y:
            coefs, R = self.soft_coeffs(bd, p1_coef, high_ok)
            self.last_r = tuple(R)
        else:
            self.last_r = tuple(self.error_variance(bd, soft[lay.coef_stream_idx] if p.modulation == "qpsk" else None))
            self.last_rb = None
            coefs = decode_coeffs(bd, p)
            if not high_ok:
                self.last_rb = np.broadcast_to(np.asarray(self.last_r)[None, :, None],
                                               (2, 2, p.nbands)).copy()
                self.last_rb[:, :, p.high_k:] = np.inf
                for ch in ("M", "S"):
                    for k in range(p.high_k, p.nbands):
                        coefs[ch][k] = np.zeros(p.ncoef(k))
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
        """返り値: (時刻合わせ済みの音声, 有効フラグ)。self.r_trace に誤差分散の見積もり (n, 2) を、
        self.rb_trace に帯域ごと・半ブロックごとの係数あたりの誤差分散 (n, 2, 帯域数) を残す"""
        b = self.p.block
        h = b // 2
        y = np.zeros((len(frames) * b, 2))
        v = np.zeros(len(frames) * b, bool)
        r = np.full((len(frames) * b, 2), np.nan)
        rb = np.full((len(frames) * b, 2, self.p.nbands), np.nan)
        for i, sym in enumerate(frames):
            y[i * b:(i + 1) * b], v[i * b:(i + 1) * b] = self.decode(sym)
            r[i * b:(i + 1) * b] = self.last_r
            if self.last_rb is not None:
                rb[i * b:i * b + h] = self.last_rb[0]
                rb[i * b + h:(i + 1) * b] = self.last_rb[1]
            elif v[i * b]:                                # 硬判定: 帯域の区別なし
                rb[i * b:(i + 1) * b] = np.asarray(self.last_r)[:, None]
        self.r_trace = r[offset:offset + n]
        self.rb_trace = rb[offset:offset + n]
        return y[offset:offset + n], v[offset:offset + n]


def receive(profile: Profile, framesA, framesB, n, offset_b, plc_order=16,
            return_streams=False, soft_decode=True, profile_b=None,
            cipher=None, y_phase_only=False):
    """
    2系統 (framesB=None なら 1系統) を受信して (n, 2) の音声を返す。
    return_streams=True なら stats に各系統の時刻合わせ済み出力と重みの推移も入れる (評価用)。
    profile_b: 副系のプロファイル (None なら主系と同じ)。サンプリング周波数とブロック長は主系と同じであること。
    cipher: 暗号化しているとき、送信側と同じ鍵・nonce の gracefm.crypto.StreamCipher。
    """
    pb = profile if profile_b is None else profile_b
    assert pb.fs == profile.fs and pb.block == profile.block
    dA = StreamDecoder(profile, soft_decode=soft_decode, cipher=cipher,
                       y_phase_only=y_phase_only)
    yA, vA = dA.run(framesA, n, 0)
    stats = {"A": dA.stats}
    if framesB is not None:
        dB = StreamDecoder(pb, soft_decode=soft_decode, cipher=cipher,
                           y_phase_only=y_phase_only)
        yB, vB = dB.run(framesB, n, offset_b)
        stats["B"] = dB.stats
        y, v, tr = fusion.fuse_band(yA, vA, yB, vB, profile.block, profile.levels, dA.rb_trace, dB.rb_trace)
        if return_streams:
            stats.update(yA=yA, vA=vA, yB=yB, vB=vB, weight_trace=tr)
    else:
        y, v = yA, vA
    stats["plc_samples"] = int((~v).sum())
    traces = [dA.rb_trace] + ([dB.rb_trace] if framesB is not None else [])
    patterns = [tuple(np.concatenate([np.isfinite(rb[i * profile.block]).ravel() for rb in traces]))
                for i in range(len(y) // profile.block)]
    y = plc.crossfade_switch(y, patterns, profile.block, order=plc_order)
    return plc.conceal(y, v, profile.fs, order=plc_order), stats
