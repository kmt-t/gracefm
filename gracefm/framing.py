"""
フレームの送信 (pack) と受信 (unpack)。ビット配置は gracefm.layout.Layout が決める。

pack  : BlockData → 送信ビット列 (ヘッダ、CRC、系統符号のパリティ、仮数を Layout の位置へ置く。暗号化はここで行う)
unpack: 軟値・硬判定 → (BlockData, ヘッダ)。ヘッダとYの最上位bit、係数の上位K bit は軟判定ビタビで訂正し、CRCを検査する。
"""
import numpy as np

from . import fec
from .codec import BlockData, offset_of, qmax_of, qmin_of
from .layout import Layout, int_bits


def pack(lay: Layout, bd: BlockData, stream_id: int, counter: int, keystream=None):
    """keystream: 暗号化するとき、このフレームのキーストリーム (n_keystream ビット)"""
    p = lay.p
    tag = int_bits(p.format_id, 2)
    if lay.encrypted:
        hdr = int_bits(p.pid, 4) + int_bits(stream_id, 1) + [1] + tag + int_bits(counter & 0xFFFFFF, 24)
    else:
        counter_bits = lay.header_bits - 8
        hdr = (int_bits(p.pid, 4) + int_bits(stream_id, 1) + [0] + tag
               + int_bits(counter & ((1 << counter_bits) - 1), counter_bits))
    prot = list(hdr)
    for ch, k in lay.exp_items:
        prot += int_bits(bd.eidx[ch][k], p.exp_bits)
    for ch, k, j in lay.attn_items:
        prot.append(int(bd.attn[ch][k][j]))
    prot = np.array(prot, np.int64)
    flat_mant = np.concatenate([np.asarray(bd.mant[ch][k], np.int64) for ch, k in lay.coef_groups])
    coef = ((flat_mant[lay.coef_flat] + lay.coef_offset_bits) >> lay.coef_pos) & 1
    if lay.encrypted:
        prot[lay.header_bits:] ^= keystream[: lay.n_body]
        coef = coef ^ keystream[lay.n_body:]
    top = coef[lay.top_coef_idx]
    if lay.y_items:
        y_u, _, y_tail = lay.y_parts(bd)
        ymsb = y_u >> (p.y_bits - 1)
    else:
        ymsb, y_tail = np.zeros(0, np.int64), np.zeros(0, np.int64)
    core, high = lay._crc_inputs(prot, top, ymsb)
    checks = [fec.crc_core(core)]
    if lay.has_high_crc:
        checks.append(fec.crc_high(high))
    stream = np.zeros(lay.n_tx, np.int64)
    header_x = np.concatenate([prot, *checks])
    header_parity, header_tail = fec.rsc_parity(header_x)
    stream[lay.hpar_idx] = header_parity
    stream[lay.hdata_idx] = header_x
    stream[lay.htail_idx] = header_tail
    if lay.n_top:
        parity, tail = fec.rsc_parity(top)
        stream[lay.parity_idx] = parity[: lay.n_top]
        stream[lay.tail_idx] = np.concatenate([parity[lay.n_top:], tail])
    stream[lay.ytail_idx] = y_tail
    stream[lay.coef_stream_idx] = coef
    return stream


# 救済の閾値は計算量で決める (効果は測定で後から確かめる)。見積もり: フレーム 2 ms、ヘッダ復号 1 回 = K=7 のビタビ
# 84段 × 64状態 = 5376 ACS、1 ACS/クロック・100 MHz で約 54 µs。フレーム時間の 8 割 (1.6 ms) までに収めると、
# 復号 約 30 回。通常の復号 1 回を含めて、救済の試行は 28 回以内にする: 候補 7 個から反転 1〜2 個 (7 + 21 = 28)。
# CRC の誤採用は、試行 1 回あたり約 1/4096 なので、救済 1 フレームあたり 28/4096 ≈ 0.7%。
RECOVER_CANDIDATES = 7      # 救済: ヘッダの信頼度の低い候補の数
RECOVER_MAX_FLIPS = 2       # 救済: 同時に反転する最大数 (Chase 型)


def unpack_recovering(lay: Layout, soft, bits, keystream_for=None, y_soft=None):
    """unpack と同じ。基本CRCが合わないとき、ヘッダの信頼度の低い bit を 1〜RECOVER_MAX_FLIPS 個反転して
    CRC が合う候補を探す (Chase 型)。候補は信頼度 (|軟値|) の小さい順に試し、最初に通ったものを採る。
    返り値は unpack と同じ。救えた場合、header["recovered"] に反転した bit の数を入れる。"""
    bd, hdr = unpack(lay, soft, bits, keystream_for, y_soft)
    if bd is not None:
        return bd, hdr
    import itertools
    soft = np.asarray(soft)
    bits = np.asarray(bits)
    hdr_idx = np.concatenate([lay.hdata_idx, lay.hpar_idx])
    order = hdr_idx[np.argsort(np.abs(soft[hdr_idx]), kind="stable")][:RECOVER_CANDIDATES]
    for t in range(1, RECOVER_MAX_FLIPS + 1):
        for comb in itertools.combinations(order, t):
            idx = list(comb)
            s2 = soft.copy()
            b2 = bits.copy()
            s2[idx] = -s2[idx]
            b2[idx] ^= 1
            bd, hdr = unpack(lay, s2, b2, keystream_for, y_soft)
            if bd is not None:
                hdr["recovered"] = t
                return bd, hdr
    return None, None


def unpack(lay: Layout, soft, bits, keystream_for=None, y_soft=None):
    """
    soft: 送信ビット列全体の軟値 (正 = 0 らしい。足りない分は0とみなす。ヘッダのデータは振幅部にあるので、振幅部の軟値も必要)、
    bits: 送信ビット列全体の硬判定 (n_tx 個)
    y_soft: Y帯域があるとき、専用シンボルの位相から得た (最上位bitの軟値, パリティの軟値) (Y係数の数ずつ。省略時は消失扱い)
    keystream_for: 暗号化するとき、ヘッダ (dict) からキーストリームを返す関数。使ったキーストリームは header["ks"]
    返り値: (BlockData, header dict) / 基本CRCが合わなければ (None, None)。
    高域CRCだけが不一致なら header["high_ok"] が False。header["top_bits"] は訂正後の上位K bit (平文)。
    """
    p = lay.p
    soft = np.pad(np.asarray(soft), (0, max(0, lay.n_tx - len(soft))))
    bits = np.pad(np.asarray(bits, np.int64), (0, max(0, lay.n_tx - len(bits))))
    prot = fec.rsc_decode(soft[lay.hdata_idx], soft[lay.hpar_idx], soft[lay.htail_idx])
    body = prot[: lay.n_prot]
    if lay.n_top:
        top = fec.rsc_decode(soft[lay.top_stream_idx],
                             np.concatenate([soft[lay.parity_idx], soft[lay.tail_idx[: fec.K - 1]]]),
                             soft[lay.tail_idx[fec.K - 1:]])
    else:
        top = np.zeros(0, np.int64)
    if lay.y_items:
        if y_soft is None:                         # 位相の情報が無ければ消失扱い
            y_soft = (np.zeros(len(lay.y_items), np.int64), np.zeros(len(lay.y_items), np.int64))
        msb_soft, parity_soft = (np.asarray(v, np.int64) for v in y_soft)
        ymsb = fec.rsc_decode(msb_soft, np.concatenate([parity_soft, soft[lay.ytail_idx[: fec.K - 1]]]),
                              soft[lay.ytail_idx[fec.K - 1:]])
    else:
        ymsb = np.zeros(0, np.int64)
    core, high = lay._crc_inputs(body, top, ymsb)
    n_core = fec.CRC_CORE[0]
    if not np.array_equal(fec.crc_core(core), prot[lay.n_prot:lay.n_prot + n_core]):
        return None, None
    high_ok = (not lay.has_high_crc or
               np.array_equal(fec.crc_high(high), prot[lay.n_prot + n_core:]))
    hdr = body[: lay.header_bits]
    val = lambda bb: int("".join(str(int(v)) for v in bb), 2)
    header = {"pid": val(hdr[0:4]), "stream": int(hdr[4]), "encrypted": bool(hdr[5]),
              "counter": val(hdr[8: lay.header_bits]), "high_ok": high_ok}
    if (header["pid"] != p.pid or header["encrypted"] != lay.encrypted
            or val(hdr[6:8]) != p.format_id):
        return None, None
    coef_bits = bits[lay.coef_stream_idx].copy()
    coef_bits[lay.top_coef_idx] = top                 # 訂正後の上位K bit (暗号化時は暗号文)
    if lay.encrypted:
        ks = keystream_for(header)
        body = body.copy()
        body[lay.header_bits:] ^= ks[: lay.n_body]
        coef_bits ^= ks[lay.n_body:]
        top = coef_bits[lay.top_coef_idx]
        header["ks"] = ks
    header["top_bits"] = top
    header["y_msb"] = ymsb
    i = lay.header_bits
    eidx = {"M": [None] * p.nbands, "S": [None] * p.nbands}
    attn = {"M": [None] * p.nbands, "S": [None] * p.nbands}
    bits_of = {"M": p.bits_m, "S": p.bits_s}
    for ch, k in lay.exp_items:
        width = p.exp_bits
        eidx[ch][k] = val(body[i:i + width])
        i += width
    for ch, k in lay.exp_items:
        count = p.attenuator_bits(ch, k)
        attn[ch][k] = body[i:i + count].copy()
        i += count
    u_flat = lay.segment_sum(np.asarray(coef_bits, np.int64) << lay.coef_pos)
    if lay.n_y:
        u_flat[lay.y_flat] += np.asarray(ymsb, np.int64) << (p.y_bits - 1)
    mant = {"M": [None] * p.nbands, "S": [None] * p.nbands}
    for ch, k in lay.coef_groups:
        o, n = lay.coef_offset[(ch, k)], p.ncoef(k)
        mant[ch][k] = np.clip(u_flat[o:o + n] - offset_of(bits_of[ch][k], p, ch, k),
                              qmin_of(bits_of[ch][k], p, ch, k), qmax_of(bits_of[ch][k]))
    bd = BlockData(mant, eidx, attn)
    return bd, header
