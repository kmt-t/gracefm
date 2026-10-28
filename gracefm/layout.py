"""
フレームのビット配置。1フレーム = 1ブロック。ヘッダ (制御情報) とHaar係数部に分け、FECは
「位相部 (強い2位置) にパリティ、振幅部 (弱い2位置) にデータ」を置く系統符号で統一する。

系統符号: (133,171) の符号語集合を、情報bit x を第1系列とする再帰形で使う。パリティ (第2系列, n+6 bit) を位相部へ、
  情報bit x (と終端の情報bit 6 bit) を振幅部へ置くので、1シンボルが「パリティ2bit | データ2bit」になる。
  受信側は両方の軟値を合わせて軟判定ビタビで復号する (gracefm.fec.rsc_parity / rsc_decode)。

ヘッダ (先頭の (n+6)/2 シンボル):
  情報bit x = ヘッダ24bit | 指数 | 区間アッテネータ | 基本CRC 12 | 高域CRC 10※
  ヘッダ24bit: プロファイルID 4 | 系統ID 1 | 暗号化 1 (=0) | 形式識別子 2 | フレーム番号 16 (各 MSB から)
  (暗号化するとき 32bit: プロファイルID 4 | 系統ID 1 | 暗号化 1 (=1) | 形式識別子 2 | フレーム番号 24)
  形式識別子は3。
  指数           : M の係数群 0→最高域, 続いて S の係数群 0→最高域 (0bit の群は無し)。k=0 は低域近似、k=1.. は詳細帯域。各 exp_bits, MSB から
  区間アッテネータ: 全登録プロファイルに標準装備。M→S、帯域低→高、区間先頭→末尾の順に1bitずつ
  CRC            : 基本CRC (12bit) (ヘッダ・高域より低い帯域の指数/アッテネータ・仮数上位K bit) と、
                   高域CRC (10bit。最後の2帯域 (H2/H1) の指数/アッテネータ・仮数上位K bit・Y帯域の最上位bit)。高域を送らないプロファイルは基本CRCのみ。
Haar係数部 (ヘッダの直後。係数順 = 成分M→S、帯域 低→高、係数 先頭→末尾):
  終端: 仮数上位bit用の系統符号の終端 (パリティ6bit | 情報6bit)。Y帯域があればその分もう一組
  位相部の列: 係数ごとに [その係数の上位K bit のパリティ K bit | 基本層の仮数bit (rank の小さい順)]
  振幅部の列: 係数ごとに [拡張層の仮数bit (rank の小さい順)]
  上位K bit は基本層の先頭にあり、パリティと別の場所にある。係数の先頭のシンボルだけがパリティ付きで、続くシンボルにはない。
  K=1 で係数が N シンボルなら、位相部は 2N bit = パリティ1 + 基本層 2N-1、振幅部は拡張層 2N bit、仮数幅は 4N-1 bit。
  QPSKは全ビットが同じ位置種別なので、ヘッダ、終端、係数の順に並べるだけ (振幅部の列は空)。
  Y帯域の仮数は専用シンボルで送り、この列には入らない。専用シンボルは位相が「最上位bit｜そのパリティ」、半径が残りの仮数。
仮数は通常 オフセットバイナリ u = m + qmax (b bit) で表す。
Y高域だけ u = m + 2^(b-1) として全2^b値を使い、この帯域の仮数は専用シンボルで送る。
送信順: [位相部の列 全体] [振幅部の列 全体] (階層16QAMでは、両者を同じ長さにそろえるために末尾へ0の詰めを入れる)
暗号化するときは、ヘッダ以外のヘッダの内容と仮数bitをキーストリームとの XOR で暗号化してから
CRC とパリティをかける (CRC とパリティは暗号文に対してかかるので、鍵がなくても誤りは検出・訂正できる。gracefm.crypto)。
"""
import numpy as np

from . import fec
from .codec import BlockData, offset_of
from .profiles import Profile


def int_bits(v, n):
    return [(int(v) >> (n - 1 - i)) & 1 for i in range(n)]


class Layout:
    def __init__(self, profile: Profile, encrypted: bool = False):
        p = profile
        if encrypted and p.has_y:
            raise ValueError("Y帯域の暗号化は未対応です")
        self.p = p
        self.encrypted = encrypted
        self.header_bits = 32 if encrypted else 24
        self.exp_items = []         # (ch, k)
        self.attn_items = []        # (ch, k, group index)
        self.y_items = []      # (ch, k, j): Y帯域の係数 (専用シンボルで送る)
        for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
            for k, b in enumerate(bits):
                if b > 0:
                    self.exp_items.append((ch, k))
                    self.attn_items.extend((ch, k, j) for j in range(p.attenuator_bits(ch, k)))
        # 係数順に、強い位置の列 (パリティ + 基本層) と弱い位置の列 (拡張層) を作る
        strong, weak = [], []       # ("P", t) = t 番目のパリティ / ("C", ch, k, j, pos) = 仮数bit
        top_k = []                  # 上位K bit (情報列 x) の帯域
        top_item = []               # x の各bitの (ch, k, j, pos)
        for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
            for k, b in enumerate(bits):
                if b == 0:
                    continue
                in_y = p.y_band(ch, k)
                K, base = p.protect_bits(k), p.base_bits(ch, k)
                for j in range(p.ncoef(k)):
                    if in_y:
                        self.y_items.append((ch, k, j))
                        continue
                    for rank in range(K):
                        strong.append(("P", len(top_item)))
                        top_k.append(k)
                        top_item.append((ch, k, j, b - 1 - rank))
                    strong.extend(("C", ch, k, j, b - 1 - rank) for rank in range(base))
                    weak.extend(("C", ch, k, j, b - 1 - rank) for rank in range(base, b))
        self.n_top = len(top_item)
        self.n_prot = (self.header_bits + sum(p.exp_bits for ch, k in self.exp_items)
                       + len(self.attn_items))
        self.n_body = self.n_prot - self.header_bits      # 暗号化するヘッダの内容のビット数
        core, high = list(range(self.header_bits)), []
        bit = self.header_bits
        for items, widths in ((self.exp_items, (p.exp_bits for ch, k in self.exp_items)),
                              (self.attn_items, (1 for _ in self.attn_items))):
            for item, width in zip(items, widths):
                (high if item[1] >= p.high_k else core).extend(range(bit, bit + width))
                bit += width
        assert bit == self.n_prot
        self.core_prot_indices = np.asarray(core, np.int64)
        self.high_prot_indices = np.asarray(high, np.int64)
        self.core_top_indices = np.asarray([t for t, k in enumerate(top_k) if k < p.high_k], np.int64)
        self.high_top_indices = np.asarray([t for t, k in enumerate(top_k) if k >= p.high_k], np.int64)
        y_k = [k for _, k, _ in self.y_items]
        self.core_y_indices = np.asarray([t for t, k in enumerate(y_k) if k < p.high_k], np.int64)
        self.high_y_indices = np.asarray([t for t, k in enumerate(y_k) if k >= p.high_k], np.int64)
        self.has_high_crc = bool(len(high) or len(self.high_top_indices) or len(self.high_y_indices))
        self.n_prot_crc = self.n_prot + fec.CRC_CORE[0] + (fec.CRC_HIGH[0] if self.has_high_crc else 0)
        T = fec.K - 1                                                   # 終端 6 bit
        self.n_hdata = self.n_prot_crc                                  # ヘッダの情報bit (CRC込み)
        self.n_header = 2 * (self.n_hdata + T)                          # ヘッダが使う位置 (パリティ + データ)
        self.n_tail = 2 * T if self.n_top else 0                        # 上位K bit用の終端 (パリティ + 情報)
        self.n_ytail = 2 * T if self.y_items else 0                # Y帯域の最上位bit用の終端
        self.n_parity = self.n_top + self.n_tail + self.n_ytail         # 係数のパリティ (終端込み)
        self.n_coded = self.n_header + self.n_parity                    # 仮数以外が使う位置
        # 位相部の列 (強い位置) と振幅部の列 (弱い位置)
        strong_list = [("HP", i) for i in range(self.n_hdata + T)]
        weak_list = [("HD", i) for i in range(self.n_hdata)] + [("HT", i) for i in range(T)]
        if self.n_top:
            strong_list += [("CP", i) for i in range(T)]
            weak_list += [("CT", i) for i in range(T)]
        if self.y_items:
            strong_list += [("YP", i) for i in range(T)]
            weak_list += [("YT", i) for i in range(T)]
        strong_list += strong
        weak_list += weak
        self.n_strong_raw, self.n_weak_raw = len(strong_list), len(weak_list)     # 偶数そろえの前の長さ
        if p.layered:
            length = 2 * -(-max(len(strong_list), len(weak_list)) // 2)   # 同じ長さ・偶数にそろえる
            strong_list += [("Z",)] * (length - len(strong_list))
            weak_list += [("Z",)] * (length - len(weak_list))
            self.n_strong = length
        stream_list = strong_list + weak_list
        if not p.layered:
            self.n_strong = len(stream_list)
        self.n_tx = len(stream_list)
        T6 = np.arange(T)
        self.hpar_idx = np.zeros(self.n_hdata + T, np.int64)
        self.hdata_idx = np.zeros(self.n_hdata, np.int64)
        self.htail_idx = np.zeros(T, np.int64)
        self.tail_idx = np.zeros(2 * T if self.n_top else 0, np.int64)      # 先頭 T = パリティ、後ろ T = 情報
        self.ytail_idx = np.zeros(2 * T if self.y_items else 0, np.int64)
        self.parity_idx = np.zeros(self.n_top, np.int64)
        coef_items, coef_stream = [], []
        for pos, token in enumerate(stream_list):
            kind = token[0]
            if kind == "HP":
                self.hpar_idx[token[1]] = pos
            elif kind == "HD":
                self.hdata_idx[token[1]] = pos
            elif kind == "HT":
                self.htail_idx[token[1]] = pos
            elif kind == "CP":
                self.tail_idx[token[1]] = pos
            elif kind == "CT":
                self.tail_idx[T + token[1]] = pos
            elif kind == "YP":
                self.ytail_idx[token[1]] = pos
            elif kind == "YT":
                self.ytail_idx[T + token[1]] = pos
            elif kind == "P":
                self.parity_idx[token[1]] = pos
            elif kind == "C":
                coef_items.append(token[1:])
                coef_stream.append(pos)
        self.coef_items = coef_items
        self.coef_stream_idx = np.asarray(coef_stream, np.int64)
        self.n_coef_bits = len(coef_items)
        self.n_base_bits = sum(1 for t in strong if t[0] == "C")
        index_of = {item: i for i, item in enumerate(coef_items)}
        self.top_coef_idx = np.asarray([index_of[item] for item in top_item], np.int64)
        self.top_stream_idx = self.coef_stream_idx[self.top_coef_idx]
        self.n_keystream = self.n_body + self.n_coef_bits       # 1フレームに使うキーストリームのビット数
        # Haar係数ビットの属性 (受信側で誤差のエネルギーを見積もるため)
        self.coef_ch = np.array([0 if t[0] == "M" else 1 for t in self.coef_items], np.int64)
        self.coef_pos = np.array([t[3] for t in self.coef_items], np.int64)
        # 係数を (M→S, 帯域 低→高, 係数 先頭→末尾) で一列に並べたときの番号
        self.coef_offset = {}
        off = 0
        for ch, bits in (("M", p.bits_m), ("S", p.bits_s)):
            for k, b in enumerate(bits):
                if b > 0:
                    self.coef_offset[(ch, k)] = off
                    off += p.ncoef(k)
        self.n_coef = off
        self.n_y = len(self.y_items)
        self.coef_flat = np.array([self.coef_offset[(t[0], t[1])] + t[2] for t in self.coef_items], np.int64)
        # 係数ごとの集計 (同じ係数に属する仮数 bit の和) を、並べ替えた添字の区間和で行うための表
        self.coef_groups = list(self.coef_offset)                           # (成分, 帯域) の並び = 係数番号の並び
        self.coef_offset_bits = np.array([offset_of({"M": p.bits_m, "S": p.bits_s}[t[0]][t[1]], p, t[0], t[1])
                                          for t in self.coef_items], np.int64)
        self.y_flat = np.array([self.coef_offset[(ch, k)] + j for ch, k, j in self.y_items], np.int64)
        order = np.argsort(self.coef_flat, kind="stable")
        sorted_flat = self.coef_flat[order]
        starts = np.flatnonzero(np.concatenate([[True], sorted_flat[1:] != sorted_flat[:-1]])) if len(order) else order
        self._seg_order, self._seg_starts, self._seg_index = order, starts, sorted_flat[starts] if len(order) else order

    def segment_sum(self, values):
        """仮数 bit ごとの値 (coef_items の並び) を、係数ごとに足した長さ n_coef の配列にする"""
        out = np.zeros(self.n_coef, np.int64)
        if len(self._seg_order):
            out[self._seg_index] = np.add.reduceat(np.asarray(values, np.int64)[self._seg_order], self._seg_starts)
        return out

    def header_info(self, stream):
        """送信ビット列からヘッダの情報bit (CRC込み) を取り出す (振幅部にある)"""
        return np.asarray(stream)[self.hdata_idx].copy()

    def with_header(self, stream, header_x):
        """ヘッダの情報bitを差し替え、パリティと終端を作り直した送信ビット列を返す (試験・解析用)"""
        out = np.array(stream, np.int64)
        parity, tail = fec.rsc_parity(np.asarray(header_x, np.int64))
        out[self.hpar_idx] = parity
        out[self.hdata_idx] = header_x
        out[self.htail_idx] = tail
        return out

    def _crc_inputs(self, prot, top, ymsb):
        core = np.concatenate([prot[self.core_prot_indices], top[self.core_top_indices],
                               ymsb[self.core_y_indices]])
        high = np.concatenate([prot[self.high_prot_indices], top[self.high_top_indices],
                               ymsb[self.high_y_indices]])
        return core, high

    def y_u(self, bd: BlockData):
        """Y帯域の仮数 (オフセットバイナリ。最上位bitが位相、残りが半径の段)"""
        return np.asarray([int(bd.mant[ch][k][j]) + offset_of(self.p.y_bits, self.p, ch, k)
                           for ch, k, j in self.y_items], np.int64)

    def y_parts(self, bd: BlockData):
        """Y専用シンボルに載せる (u, 最上位bitのパリティ) と、ヘッダ部の終端bit (12個)"""
        u = self.y_u(bd)
        msb = u >> (self.p.y_bits - 1)
        parity, tail = fec.rsc_parity(msb)
        return u, parity[: len(u)], np.concatenate([parity[len(u):], tail])
