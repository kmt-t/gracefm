"""
受信機 (1系統のシンボル → PCM)。すべて整数演算。

decode_frame は 1フレームを復号して DecodedFrame を返す (状態を持たない)。
run は系統の全フレームを復号して StreamResult を返す。2系統の合成と出力段は gracefm.receiver。
誤差分散は (対数領域の整数) で扱う: log2(分散) × 2^8。届かない帯域は INF_LOG (情報なし)。
"""
import itertools
from dataclasses import dataclass

import numpy as np

from . import fec, framing, modem
from .codec import (
    FRAC,
    BlockData,
    attenuator_expanded,
    analyze_stream,
    encode_block,
    exp_range,
    offset_of,
    overlap_valid,
    qmax_of,
    qmin_of,
    quantize,
    synthesize,
    synthesize_stream,
)
from .crypto import unwrap_counter
from .dsp import log2_q8, saturate, shift_signed, sigmoid_q15, wide_mul
from .fusion import INF_LOG
from .layout import Layout
from .profiles import Profile
from .scrambler import descramble

ONE_TWELFTH_Q15 = 2731                                  # 1/12 (量子化誤差の分散。仮数の最下位bit単位) を Q15 で
# 救済の閾値は計算量で決める (効果は測定で後から確かめる)。見積もり: フレーム 2 ms、ヘッダ復号 1 回 = K=7 のビタビ
# 84段 × 64状態 = 5376 ACS、1 ACS/クロック・100 MHz で約 54 µs。フレーム時間の 8 割 (1.6 ms) までに収めると、
# 復号 約 30 回。通常の復号 1 回を含めて、救済の試行は 28 回以内にする: 候補 7 個から反転 1〜2 個 (7 + 21 = 28)。
# CRC の誤採用は、試行 1 回あたり約 1/4096 なので、救済 1 フレームあたり 28/4096 ≈ 0.7%。
RECOVER_CANDIDATES = 7      # 救済: ヘッダの信頼度の低い候補の数
RECOVER_MAX_FLIPS = 2       # 救済: 同時に反転する最大数 (Chase 型)

QUALITY_NORMAL, QUALITY_HIGH_MISSING, QUALITY_MISSING = 0, 1, 2   # 品質コード (高域欠落 = 1, 欠落 = 2)
OK, HIGH_FAIL, LOST, CRC_FAIL = "ok", "high_fail", "lost", "crc_fail"   # フレームの状態


@dataclass
class DecodedFrame:
    pcm: np.ndarray | None          # (block, 2) の符号つき24 bit整数。帯域分割がブロックをまたぐ復号済みフレームは None (coefs から run が合成する)
    status: str                     # OK, HIGH_FAIL (高域CRCだけ不一致), LOST (届かない), CRC_FAIL (基本CRCが不一致)
    quality: int                    # 品質コード
    rb: np.ndarray | None        # (2 半ブロック, 2 成分, 帯域数) の誤差分散 (対数領域)。届かない・CRC不一致は None
    frame_no: int | None = None  # 暗号化時の 40 bit のフレーム番号 (次のフレームの番号の復元に使う)
    coefs: dict | None = None    # 帯域分割がブロックをまたぐときの {ch: [帯域係数]}

    @property
    def valid(self):
        """基本CRCが通ったか (高域CRCの結果は問わない)"""
        return self.status in (OK, HIGH_FAIL)


@dataclass
class StreamResult:
    pcm: np.ndarray                 # 時刻合わせ済みの (n, 2)
    valid: np.ndarray               # 時刻合わせ済みの有効フラグ (n,)
    quality: np.ndarray             # フレームごとの品質コード (時刻合わせ前)
    rb: np.ndarray                  # 時刻合わせ済みの誤差分散 (n, 2, 帯域数)
    stats: dict                     # frames, lost, crc_fail, high_crc_fail
    coefs: list | None = None       # 帯域分割がブロックをまたぐときの、フレームごとの {ch: [帯域係数]} (届かないフレームは全 0)
    frame_valid: np.ndarray | None = None  # 同じくフレームごとの、基本CRCが通ったか



def soft_coeffs(lay: Layout, bd: BlockData, p1_coef, y_mant, y_var, high_ok=True):
    """
    軟判定の復号: 非保護ビットを 0/1 に丸めず、1 である事後確率 p1 (Q15) をそのままビットの値として使う。
    ビットどうしは独立とみなし、仮数の期待値と事後分散を求める:
      期待値   E[u] = 硬判定の u + Σ (p1 - 硬判定ビット)·2^pos
      事後分散 Σ p1 (1 - p1)·4^pos
    y_mant, y_var: Y 帯域の仮数の推定値と分散 ({(ch, k): ...})。Y 帯域の仮数は p1_coef を使わない。
    返り値: (帯域係数 {ch: [整数の係数]}、誤差分散 rb (半ブロック・M/S・帯域) の対数領域 (INF_LOG = 情報なし))
    """
    p = lay.p
    hard = (p1_coef > 16384).astype(np.int64)
    w = np.int64(1) << lay.coef_pos
    du = lay.segment_sum((p1_coef - hard * 32768) * w)
    var = lay.segment_sum(wide_mul((p1_coef * (32768 - p1_coef)) >> 15, w * w))     # w·w は最大 2^20 (B 入力の幅を超えるので分割して掛ける)
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
    return coefs, rb


class Decoder:
    def __init__(self, profile: Profile, cipher=None, y_phase_only=False):
        if profile.has_y and cipher is not None:
            raise ValueError("YプロファイルはAES-CTR暗号化に未対応です")
        self.p = profile
        self.y_phase_only = y_phase_only
        self.cipher = cipher
        self.layout = Layout(profile, encrypted=cipher is not None)
        self.digital_nsym = modem.n_symbols(self.layout.n_tx, self.layout.n_strong, profile.modulation)
        self.high_absent = not any(profile.bits_m[profile.high_k:]) and not any(profile.bits_s[profile.high_k:])   # 高域を送らない (SUB 系)

    def _y_mask(self):
        lay = self.layout
        digital_bits = self.digital_nsym * modem.bits_per_symbol(self.p.modulation)
        return modem.prbs(digital_bits + 3 * lay.n_y)[digital_bits:]

    def _y_phase(self, sym, var):
        """専用シンボルの位相から、最上位bitとパリティの LLR を得る (ヘッダ部の復号に渡す)"""
        start = modem.N_PREAMBLE + self.digital_nsym
        return modem.y_phase_llr(sym[start:], self.p.y_step, self._y_mask(), var, self.p.y_bits - 1)

    def _recover_y(self, sym, ymsb, var, high_ok=True):
        """Y帯域の半径の推定値 {(ch, k): 仮数の推定値 (小数 MANT_FRAC bit)} と、その誤差分散 {(ch, k): Q15 の分散}"""
        lay, p = self.layout, self.p
        start = modem.N_PREAMBLE + self.digital_nsym
        if len(sym) != start + lay.n_y:
            raise ValueError("Yフレームのシンボル数が一致しません")
        b = p.y_bits
        parity = fec.rsc_parity(ymsb)[0][:len(ymsb)]
        u, variance = modem.y_demodulate(sym[start:], ymsb, parity, p.y_step, self._y_mask(), var, b - 1, self.y_phase_only)
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
        """soft_coeffs をこの受信機の配置で呼ぶ。派生クラスは、ここを上書きして確率を変えられる"""
        return soft_coeffs(self.layout, bd, p1_coef, y_mant, y_var, high_ok)

    def decode_frame(self, sym, last_frame_no=-1):
        """sym: 1フレームの受信シンボル (n, 2) (届かなければ None) → DecodedFrame。
        last_frame_no: 直前に受けたフレームの 40 bit の番号 (暗号化時、24 bit のヘッダ番号を復元するため)"""
        p, lay = self.p, self.layout
        silent = np.zeros((p.block, 2), np.int64)
        expected = modem.N_PREAMBLE + self.digital_nsym + (lay.n_y if p.has_y else 0)
        if sym is None or len(sym) != expected:
            return DecodedFrame(silent, LOST, QUALITY_MISSING, None)
        digital = sym[modem.N_PREAMBLE:modem.N_PREAMBLE + self.digital_nsym]
        llr, hard, var = modem.demodulate(digital, lay.n_tx, p.modulation, p.alpha)
        llr, hard = descramble(llr, hard)
        y_soft = self._y_phase(sym, var) if p.has_y else None
        found = unpack_recovering(lay, llr, hard, self._keystream_for(last_frame_no), y_soft=y_soft)
        if found is None:
            return DecodedFrame(silent, CRC_FAIL, QUALITY_MISSING, None)
        u, _ = found
        high_ok = u.high_ok
        p1_coef = sigmoid_q15(llr[lay.coef_stream_idx])
        if self.cipher is not None:                              # 仮数bitの事後確率も暗号を戻す
            ku = u.ks[lay.n_body:]
            p1_coef = np.where(ku == 1, 32768 - p1_coef, p1_coef)
        if lay.n_top:                                            # パリティで訂正した上位K bitを確定値にする
            p1_coef[lay.top_coef_idx] = u.top_bits * 32768
        y_mant, y_var = ({}, {})
        if p.has_y:
            y_mant, y_var = self._recover_y(sym, u.y_msb, var, high_ok)
        coefs, rb = self.soft_coeffs(u.bd, p1_coef, y_mant, y_var, high_ok)
        # 高域を送らないプロファイルは、高域CRCが通っても常に品質 1 (高域欠落)
        quality = QUALITY_NORMAL if (high_ok and not self.high_absent) else QUALITY_HIGH_MISSING
        pcm = None if p.overlapped else synthesize(coefs)
        return DecodedFrame(pcm, OK if high_ok else HIGH_FAIL, quality, rb, u.frame_no, coefs)

    def _keystream_for(self, last_frame_no):
        """(系統, ヘッダの24bit のフレーム番号) → (キーストリーム, 40bit の番号)。暗号化していなければ None"""
        if self.cipher is None:
            return None

        def keystream_for(stream, counter):
            fn = unwrap_counter(counter, last_frame_no)
            return self.cipher.keystream(stream, fn, self.layout.n_keystream), fn
        return keystream_for

    def run(self, frames, n, offset=0):
        """系統の全フレームを復号し、offset だけ時刻を合わせて n サンプルの StreamResult を返す"""
        b = self.p.block
        h = b // 2
        y = np.zeros((len(frames) * b, 2), np.int64)
        coefs = []
        zero = {ch: [np.zeros(self.p.ncoef(k), np.int64) for k in range(self.p.nbands)] for ch in ("M", "S")}
        v = np.zeros(len(frames) * b, bool)
        rb = np.full((len(frames) * b, 2, self.p.nbands), INF_LOG, np.int64)
        quality = np.zeros(len(frames), np.int64)
        stats = {"frames": len(frames), "lost": 0, "crc_fail": 0, "high_crc_fail": 0}
        last_frame_no = -1
        for i, sym in enumerate(frames):
            f = self.decode_frame(sym, last_frame_no)
            if f.frame_no is not None:
                last_frame_no = f.frame_no
            coefs.append(f.coefs if f.coefs is not None else zero)
            v[i * b:(i + 1) * b] = f.valid
            if not self.p.overlapped:
                y[i * b:(i + 1) * b] = f.pcm
            quality[i] = f.quality
            if f.rb is not None:
                rb[i * b:i * b + h] = f.rb[0]
                rb[i * b + h:(i + 1) * b] = f.rb[1]
            stats["lost"] += f.status == LOST
            stats["crc_fail"] += f.status == CRC_FAIL
            stats["high_crc_fail"] += f.status == HIGH_FAIL
        if not self.p.overlapped:
            return StreamResult(y[offset:offset + n], v[offset:offset + n], quality, rb[offset:offset + n], stats)
        if offset:
            raise ValueError("帯域分割がブロックをまたぐプロファイルは、2系統の格子をそろえてください (offset = 0)")
        frame_valid = v[::b]
        y = synthesize_stream(coefs) * overlap_valid(frame_valid, self.p, len(frames) * b)[:, None]
        return StreamResult(y[:n], overlap_valid(frame_valid, self.p, n), quality, rb[:n], stats, coefs, frame_valid)


def unpack_recovering(lay: Layout, soft, bits, keystream_for=None, y_soft=None):
    """framing.unpack と同じ。基本CRCが合わないとき、ヘッダの信頼度の低い bit を 1〜RECOVER_MAX_FLIPS 個反転して
    CRC が合う候補を探す (Chase 型)。候補は信頼度 (|軟値|) の小さい順に試し、最初に通ったものを採る。
    返り値: (Unpacked, 反転した bit の数 (0 = 救済なし))。救えなかったときは None。"""
    u = framing.unpack(lay, soft, bits, keystream_for, y_soft)
    if u is not None:
        return u, 0
    soft = np.asarray(soft)
    bits = np.asarray(bits)
    hdr_idx = np.concatenate([lay.hdata_idx, lay.hpar_idx])
    order = hdr_idx[np.argsort(np.abs(soft[hdr_idx]), kind="stable")][:RECOVER_CANDIDATES]
    for flips in range(1, RECOVER_MAX_FLIPS + 1):
        for comb in itertools.combinations(order, flips):
            idx = list(comb)
            s2 = soft.copy()
            b2 = bits.copy()
            s2[idx] = -s2[idx]
            b2[idx] ^= 1
            u = framing.unpack(lay, s2, b2, keystream_for, y_soft)
            if u is not None:
                return u, flips
    return None


def reconstruct_coeffs(bd: BlockData, profile: Profile):
    """BlockData → {ch: [帯域係数 (整数、小数22 bit)]} を、通信路なしで復元する。
    硬判定の復号は軟判定の特殊ケースで、各仮数 bit の確率を確定値 (0 か 32768) にして soft_coeffs に通す。"""
    lay = Layout(profile)
    p1 = framing.coefficient_bits(lay, bd) * 32768
    y_mant, y_var = {}, {}
    for ch, bits in (("M", profile.bits_m), ("S", profile.bits_s)):
        for k, b in enumerate(bits):
            if b and profile.y_band(ch, k):
                y_mant[(ch, k)] = np.asarray(bd.mant[ch][k], np.int64) << modem.MANT_FRAC
                y_var[(ch, k)] = np.zeros(profile.ncoef(k), np.int64)
    coefs, _ = soft_coeffs(lay, bd, p1, y_mant, y_var, True)
    return coefs


def reconstruct(bd: BlockData, profile: Profile):
    """BlockData → (block, 2) の L/R、符号つき24 bit整数 (通信路なしの復号)。ブロック内で完結する帯域分割だけ"""
    if profile.overlapped:
        raise ValueError(f"{profile.name} の帯域分割はブロックをまたぐので、1ブロックだけでは合成できません")
    return synthesize(reconstruct_coeffs(bd, profile))


def roundtrip(x, profile: Profile):
    """通信路なしの符号化と復号 (ブロックごと)。x は (n, 2) の符号つき24 bit整数"""
    n = profile.block
    nfr = -(-len(x) // n)
    xp = np.pad(np.asarray(x, np.int64), ((0, nfr * n - len(x)), (0, 0)))
    if profile.overlapped:
        decoded = [reconstruct_coeffs(quantize(bands, profile), profile) for bands in analyze_stream(xp, profile)]
        return synthesize_stream(decoded)[:len(x)]
    out = np.zeros_like(xp)
    for i in range(nfr):
        out[i * n:(i + 1) * n] = reconstruct(encode_block(xp[i * n:(i + 1) * n], profile), profile)
    return out[:len(x)]
