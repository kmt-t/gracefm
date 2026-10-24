"""
送信機・受信機 (2系統)。

送信: 同じ音声を 2系統で送る。系統 B はブロックの格子を半ブロックずらす (先頭に block/2 サンプルの 0)。
      2系統は大きく離れた別の周波数で送り、欠落やフェージングを独立にする。
受信: 系統ごとに 復調 → 軟判定ビタビ → CRC 判定 → 復号 → ポストフィルタ。
      基本CRC不一致はフレーム欠落。H1/H2 CRCだけの不一致は高域を消去して低中域を採用する。
      2系統の合成: 半ブロック単位で、両方届いた区間は帯域ごとに融合 (gracefm/fusion.py。各系統の係数の
      誤差分散による逆分散重み) / 片方だけなら片方 / どちらも無ければ PLC。
"""
import numpy as np

from . import fusion, modem, plc
from .codec import (attenuator_expanded, cells, decode_coeffs, encode_block, exp_range,
                    haar_inverse, ms_to_lr, offset_of, qmax_of, qmin_of)
from .framing import HybridLayout, Layout
from .crypto import unwrap_counter
from .kalman import StreamBandKalman
from .postfilter import PAD, PostFilter
from .profiles import Profile


class Transmitter:
    def __init__(self, profile: Profile, stream_id=0, offset=0, clip_opt=True, cipher=None):
        """cipher: gracefm.crypto.StreamCipher (暗号化するとき)"""
        if profile.hybrid and cipher is not None:
            raise ValueError("実験用ハイブリッドプロファイルはAES-CTR暗号化に未対応です")
        self.p = profile
        self.sid = stream_id
        self.offset = offset
        self.clip_opt = clip_opt
        self.cipher = cipher
        self.layout = HybridLayout(profile) if profile.hybrid else Layout(profile, encrypted=cipher is not None)
        self.frame_no = 0
        self.digital_nsym = modem.n_symbols(self.layout.n_tx, self.layout.n_strong, profile.modulation)
        self.nsym = self.digital_nsym + (self.layout.n_hybrid if profile.hybrid else 0)
        self.counter = 0

    def frame(self, xblock):
        """xblock: (block, 2) → 1フレームぶんの複素シンボル"""
        bd = encode_block(xblock, self.p, self.clip_opt)
        ks = None
        if self.cipher is not None:
            ks = self.cipher.keystream(self.sid, self.frame_no, self.layout.n_keystream)
        bits = self.layout.pack(bd, self.sid, self.frame_no, ks)
        self.frame_no += 1
        self.counter = self.frame_no & (0xFFFF if self.p.experimental_tag else 0xFF)
        buf = np.zeros(self.digital_nsym * modem.bits_per_symbol(self.p.modulation), np.int64)
        buf[: len(bits)] = bits
        buf ^= modem.prbs(len(buf))                      # スクランブル (詰め物も含む)
        digital = modem.modulate(buf, self.digital_nsym, self.p.modulation, self.p.alpha)
        if not self.p.hybrid:
            return digital
        mask = modem.prbs(len(buf) + 3 * self.layout.n_hybrid)[len(buf):]
        high = modem.hybrid_modulate(self.layout.hybrid_u(bd), self.p.hybrid_amplitude,
                                     mask, self.p.hybrid_bits - 2)
        return np.concatenate([digital, high])

    def run(self, x):
        """x: (n, 2) → フレームのリスト (系統のずらしを含む)"""
        b = self.p.block
        xp = np.pad(x, ((self.offset, 0), (0, 0)))
        nfr = int(np.ceil(len(xp) / b))
        xp = np.pad(xp, ((0, nfr * b - len(xp)), (0, 0)))
        return [self.frame(xp[i * b:(i + 1) * b]) for i in range(nfr)]

    def symbol_rate(self):
        return (self.nsym + len(modem.PREAMBLE)) * self.p.frames_per_sec


class StreamDecoder:
    def __init__(self, profile: Profile, postfilter=True, pf_iters=None, soft_decode=True, eps=0.02,
                 kalman_bands=None, kalman_order=2, cipher=None, hybrid_phase_only=False):
        """
        soft_decode=True: 非保護ビットを硬判定せず、事後確率で重み付けした仮数の期待値で復号する
                          (modem.bit_probs。保護部は CRC が通った確定値)。False なら硬判定 (比較用)。
        eps: ポストフィルタの量子化区間を広げるとき、事後確率が eps〜1-eps のビットを「どちらもあり得る」とみなす
        """
        if profile.hybrid and cipher is not None:
            raise ValueError("実験用ハイブリッドプロファイルはAES-CTR暗号化に未対応です")
        self.p = profile
        self.hybrid_phase_only = hybrid_phase_only
        self.soft_decode = soft_decode
        self.eps = eps
        # 系統ごとの帯域カルマン (軟判定のときだけ)。kalman_bands = 帯域番号のリスト / "all" / None
        kb = None if kalman_bands is None else (None if kalman_bands == "all" else list(kalman_bands))
        self.kf = (StreamBandKalman(profile.nbands, kb, kalman_order)
                   if (kalman_bands is not None and soft_decode) else None)
        self.cipher = cipher
        self.last_frame_no = -1
        self.layout = HybridLayout(profile) if profile.hybrid else Layout(profile, encrypted=cipher is not None)
        self.digital_nsym = modem.n_symbols(self.layout.n_tx, self.layout.n_strong, profile.modulation)
        iters = profile.pf_iters if pf_iters is None else pf_iters
        self.pf = PostFilter(profile.levels, iters, profile.block) if postfilter else None
        self.last_ok = False
        self.stats = {"frames": 0, "lost": 0, "crc_fail": 0, "high_crc_fail": 0}
        self.last_r = (np.nan, np.nan)          # 直前フレームの誤差分散の見積もり (M, S)
        self.hybrid_variance = {}

    def _recover_hybrid(self, sym, bd, high_ok=True):
        lay, p = self.layout, self.p
        start = len(modem.PREAMBLE) + self.digital_nsym
        if len(sym) != start + lay.n_hybrid:
            raise ValueError("ハイブリッドフレームのシンボル数が一致しません")
        b = p.hybrid_bits
        protected_u = np.array([int(bd.mant[ch][k][j]) + offset_of(b, p, ch, k)
                                for ch, k, j in lay.hybrid_items], np.int64)
        top = protected_u >> (b - 1)
        second = (protected_u >> (b - 2)) & 1 if p.protect_k >= 2 else None
        digital_bits = self.digital_nsym * modem.bits_per_symbol(p.modulation)
        mask = modem.prbs(digital_bits + 3 * lay.n_hybrid)[digital_bits:]
        u, var, sigma2 = modem.hybrid_demodulate(sym[start:], top, p.hybrid_amplitude,
                                                 mask, sym[:len(modem.PREAMBLE)], b - 2,
                                                 self.hybrid_phase_only,
                                                 protected_second=second)
        self.hybrid_variance = {}
        for i, (ch, k, j) in enumerate(lay.hybrid_items):
            if k >= 5 and not high_ok:
                continue
            if (ch, k) not in self.hybrid_variance:
                self.hybrid_variance[(ch, k)] = np.zeros(p.ncoef(k))
                bd.mant[ch][k] = bd.mant[ch][k].astype(float)
            bd.mant[ch][k][j] = u[i] - offset_of(b, p, ch, k)
            self.hybrid_variance[(ch, k)][j] = var[i]
        self.stats["hybrid_axis_noise_variance_sum"] = self.stats.get("hybrid_axis_noise_variance_sum", 0.0) + sigma2
        self.stats["hybrid_frames"] = self.stats.get("hybrid_frames", 0) + 1

    def error_variance(self, bd, soft_unp):
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
        if p.modulation == "qpsk" and lay.n_unp:
            a = 1 / np.sqrt(2)
            sig2 = max(float(np.mean((np.abs(self._axis) - a) ** 2)), 1e-6)
            q = 1.0 / (1.0 + np.exp(np.minimum(2 * a * np.abs(soft_unp) / sig2, 60.0)))
            e = q * (2.0 ** lay.unp_pos * steps[lay.unp_flat]) ** 2
            tot += np.bincount(lay.unp_ch, weights=e, minlength=2)
        return tot / p.block

    def soft_coeffs(self, bd, p1_unp, high_ok=True):
        """
        軟判定の復号: 非保護ビットを 0/1 に丸めず、1 である事後確率 p1 をそのままビットの値として使う。
        ビットどうしは独立とみなし、仮数の期待値・事後分散・取り得る区間を閉じた式で求める:
          期待値   E[u] = 硬判定の u + Σ (p1 - 硬判定ビット)·2^pos
          事後分散 Σ p1 (1 - p1)·4^pos
          区間     事後確率が eps〜1-eps のビットは 0 と 1 のどちらもあり得るとして、量子化区間をその範囲まで広げる
        返り値: (帯域係数, 量子化区間, 誤差分散 (M, S) / 1サンプル)
        """
        p, lay = self.p, self.layout
        hard = (p1_unp > 0.5).astype(float)
        w = 2.0 ** lay.unp_pos
        du = np.bincount(lay.unp_flat, weights=(p1_unp - hard) * w, minlength=lay.n_coef)
        var = np.bincount(lay.unp_flat, weights=p1_unp * (1 - p1_unp) * w * w, minlength=lay.n_coef)
        unc = (p1_unp > self.eps) & (p1_unp < 1 - self.eps)
        dn = np.bincount(lay.unp_flat, weights=unc * hard * w, minlength=lay.n_coef)
        up = np.bincount(lay.unp_flat, weights=unc * (1 - hard) * w, minlength=lay.n_coef)
        coefs, cell = {}, {}
        R = np.zeros(2)
        rb = np.full((2, 2, p.nbands), np.inf)          # (前半/後半, M/S, 帯域) の係数あたりの誤差分散
        for ci, (ch, bits) in enumerate((("M", p.bits_m), ("S", p.bits_s))):
            coefs[ch], cell[ch] = [], []
            for k, b in enumerate(bits):
                n = p.ncoef(k)
                if k >= 5 and not high_ok:
                    coefs[ch].append(np.zeros(n))
                    cell[ch].append((np.zeros(n), np.zeros(n)))
                    if self.kf is not None and b:
                        self.kf.predict_only(ch, k, n)
                    continue
                if b == 0:
                    coefs[ch].append(np.zeros(n))
                    cell[ch].append(None)
                    continue
                o = lay.coef_offset[(ch, k)]
                qmax = qmax_of(b)
                qmin = qmin_of(b, p, ch, k)
                m = bd.mant[ch][k].astype(float)
                e = np.int64(bd.eidx[ch][k])
                a = attenuator_expanded(bd.attn[ch][k], p.attenuator_group(ch, k), n)
                step = 2.0 ** (e + exp_range(k, b, p, ch)[0] - a)
                z = np.clip(m + du[o:o + n], qmin, qmax) * step
                extra = self.hybrid_variance.get((ch, k), 0)
                rv = (var[o:o + n] + extra + 1.0 / 12) * step ** 2
                spread = 2 * np.sqrt(extra)
                lo, _ = cells(np.clip(np.round(m - dn[o:o + n] - spread), qmin, qmax).astype(np.int64), e, k, b, p, ch, bd.attn[ch][k])
                _, hi = cells(np.clip(np.round(m + up[o:o + n] + spread), qmin, qmax).astype(np.int64), e, k, b, p, ch, bd.attn[ch][k])
                if self.kf is not None:
                    z, rv = self.kf.update(ch, k, z, rv, scale=qmax * step)
                    lo, hi = np.minimum(lo, z), np.maximum(hi, z)   # 区間は予測で動いた値も含める
                coefs[ch].append(z)
                cell[ch].append((lo, hi))
                R[ci] += np.sum(rv)
                if n >= 2:
                    rb[0, ci, k], rb[1, ci, k] = np.mean(rv[: n // 2]), np.mean(rv[n // 2:])
                else:
                    rb[:, ci, k] = rv[0]
        self.last_rb = rb
        return coefs, cell, R / p.block

    def decode(self, sym):
        """sym: 1フレームの受信シンボル (届かなければ None) → ((block, 2), 有効か)"""
        p = self.p
        lay = self.layout
        self.stats["frames"] += 1
        bd = None
        self.hybrid_variance = {}
        expected_symbols = len(modem.PREAMBLE) + self.digital_nsym + (lay.n_hybrid if p.hybrid else 0)
        if sym is not None and len(sym) != expected_symbols:
            sym = None
        digital_sym = sym[:len(modem.PREAMBLE) + self.digital_nsym] if sym is not None and p.hybrid else sym
        if sym is None:
            self.stats["lost"] += 1
        elif self.soft_decode:
            p1, llr = modem.bit_probs(digital_sym, lay.n_tx, p.modulation, p.alpha)
            s = modem.prbs(lay.n_tx).astype(bool)        # スクランブルを戻す
            p1, llr = np.where(s, 1 - p1, p1), np.where(s, -llr, llr)
            bd, hdr = lay.unpack(llr[: lay.n_coded], (p1[lay.n_coded:] > 0.5).astype(np.int64), self._ks_for)
            if bd is not None and self.cipher is not None:  # 非保護部の事後確率も暗号を戻す
                ku = hdr["ks"][lay.n_body:].astype(bool)
                p1 = p1.copy()
                p1[lay.n_coded:] = np.where(ku, 1 - p1[lay.n_coded:], p1[lay.n_coded:])
            if bd is None:
                self.stats["crc_fail"] += 1
        else:
            soft, hard = modem.demodulate(digital_sym, lay.n_tx, p.modulation, p.alpha)
            sc = modem.prbs(len(soft))                   # スクランブルを戻す (軟値は強い位置の分だけ)
            soft = soft * (1 - 2 * sc)
            hard = hard ^ modem.prbs(len(hard))
            self._axis = soft
            bd, hdr = lay.unpack(soft[: lay.n_coded], hard[lay.n_coded:], self._ks_for)
            p1 = hard.astype(float)
            if bd is None:
                self.stats["crc_fail"] += 1
        if bd is None:
            self.last_ok = False
            self.last_r = (np.nan, np.nan)
            self.last_rb = None
            if self.kf is not None:
                for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
                    for k, b in enumerate(bits):
                        if b > 0:
                            self.kf.predict_only(ch, k, p.ncoef(k))
            return np.zeros((p.block, 2)), False
        high_ok = hdr["high_ok"]
        if not high_ok:
            self.stats["high_crc_fail"] += 1
        if p.hybrid:
            self._recover_hybrid(sym, bd, high_ok)
        if self.soft_decode or p.hybrid:
            coefs, cell, R = self.soft_coeffs(bd, p1[lay.n_coded:lay.n_tx], high_ok)
            self.last_r = tuple(R)
        else:
            self.last_r = tuple(self.error_variance(bd, soft[lay.n_coded:lay.n_tx]))
            self.last_rb = None
            coefs, cell = decode_coeffs(bd, p)
            if not high_ok:
                self.last_rb = np.broadcast_to(np.asarray(self.last_r)[None, :, None],
                                               (2, 2, p.nbands)).copy()
                self.last_rb[:, :, 5:] = np.inf
                for ch in ("M", "S"):
                    for k in (5, 6):
                        coefs[ch][k] = np.zeros(p.ncoef(k))
                        cell[ch][k] = (np.zeros(p.ncoef(k)), np.zeros(p.ncoef(k)))
        out = {}
        for ch in ("M", "S"):
            if self.pf is None or ch == "S":
                out[ch] = haar_inverse(coefs[ch])
            else:
                if not self.last_ok:
                    y0 = haar_inverse(coefs[ch])
                    self.pf.reset_history(ch, np.full(PAD, y0[0]))
                out[ch] = self.pf.process(ch, coefs[ch], cell[ch])
        self.last_ok = True
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


def receive(profile: Profile, framesA, framesB, n, offset_b, postfilter=True, plc_order=32,
            return_streams=False, soft_decode=True, profile_b=None,
            kalman_bands=None, kalman_order=2, cipher=None, hybrid_phase_only=False):
    """
    2系統 (framesB=None なら 1系統) を受信して (n, 2) の音声を返す。
    return_streams=True なら stats に各系統の時刻合わせ済み出力と重みの推移も入れる (評価用)。
    profile_b: 副系のプロファイル (None なら主系と同じ)。サンプリング周波数とブロック長は主系と同じであること。
    kalman_bands, kalman_order: 系統ごとの帯域カルマン (StreamDecoder を参照)。
    cipher: 暗号化しているとき、送信側と同じ鍵・nonce の gracefm.crypto.StreamCipher。
    """
    pb = profile if profile_b is None else profile_b
    assert pb.fs == profile.fs and pb.block == profile.block
    dA = StreamDecoder(profile, postfilter, soft_decode=soft_decode, kalman_bands=kalman_bands,
                       kalman_order=kalman_order, cipher=cipher,
                       hybrid_phase_only=hybrid_phase_only)
    yA, vA = dA.run(framesA, n, 0)
    stats = {"A": dA.stats}
    if framesB is not None:
        dB = StreamDecoder(pb, postfilter, soft_decode=soft_decode, kalman_bands=kalman_bands,
                           kalman_order=kalman_order, cipher=cipher,
                           hybrid_phase_only=hybrid_phase_only)
        yB, vB = dB.run(framesB, n, offset_b)
        stats["B"] = dB.stats
        y, v, tr = fusion.fuse_band(yA, vA, yB, vB, profile.block // 2, dA.rb_trace, dB.rb_trace)
        if return_streams:
            stats.update(yA=yA, vA=vA, yB=yB, vB=vB, weight_trace=tr)
    else:
        y, v = yA, vA
    stats["plc_samples"] = int((~v).sum())
    return plc.conceal(y, v, profile.fs, order=plc_order), stats
