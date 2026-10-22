"""
プロファイル定義。

各プロファイルは、サンプリング周波数・ブロック長・分解段数・帯域ごとのビット割り当て・
FEC で保護する仮数の上位ビット数・変調方式を固定する。受信機はフレームヘッダの
プロファイル ID からこれらを決める。
"""
from dataclasses import dataclass, replace
from typing import Optional, Tuple


@dataclass(frozen=True)
class Profile:
    pid: int                    # ヘッダに載せる ID (4bit)
    name: str
    fs: int                     # サンプリング周波数 [Hz]
    block: int                  # 1ブロック = 1フレームのサンプル数
    levels: int                 # Haar の詳細帯域数。nbands は低域近似を加えた係数群数
    bits_m: Tuple[int, ...]     # M (= (L+R)/2) の帯域ごとの仮数ビット数 (低域→高域)。0 = 送らない
    bits_s: Tuple[int, ...]     # S (= (L-R)/2) の帯域ごとの仮数ビット数
    exp_bits: int = 4           # 帯域ごとの共有指数のビット数 (16段 × 約6dB)
    protect_k: int = 2          # FEC で保護する仮数の上位ビット数
    modulation: str = "qpsk"    # "qpsk" | "qam16h" | "qam64h"
    alpha: float = 1.0          # 階層 QAM の象限間距離パラメータ (1 = 通常の QAM)
    pf_iters: int = 4           # 受信側ポストフィルタの繰り返し回数 (全プロファイル共通。SPEC 3.6.3節)
    base_m: Optional[Tuple[int, ...]] = None   # 階層化したときの基本層の仮数ビット数 (None = 階層化なし)
    base_s: Optional[Tuple[int, ...]] = None   # 同 S。基本層を超えるビット (拡張層) は変調の弱い位置に入る
    exp_bits_m: Optional[Tuple[int, ...]] = None  # 評価用: M の帯域別指数幅。None は exp_bits を使う
    exp_bits_s: Optional[Tuple[int, ...]] = None  # 評価用: S の帯域別指数幅
    exp_offset_m: Optional[Tuple[int, ...]] = None  # 評価用: M の固定指数オフセット emin
    exp_offset_s: Optional[Tuple[int, ...]] = None  # 評価用: S の固定指数オフセット emin
    attn_group_m: Optional[Tuple[int, ...]] = None  # 0=無効、正数=その係数数ごとに1bit
    attn_group_s: Optional[Tuple[int, ...]] = None

    def __post_init__(self):
        if len(self.bits_m) != self.nbands or len(self.bits_s) != self.nbands:
            raise ValueError("仮数ビット割当の長さが帯域数と一致しません")
        for field in ("exp_bits_m", "exp_bits_s", "exp_offset_m", "exp_offset_s", "attn_group_m", "attn_group_s"):
            values = getattr(self, field)
            if values is not None and len(values) != self.nbands:
                raise ValueError(f"{field} は {self.nbands} 帯域ぶん必要です")
        for field in ("exp_bits_m", "exp_bits_s"):
            values = getattr(self, field)
            if values is not None and any(not 1 <= v <= 8 for v in values):
                raise ValueError(f"{field} は 1〜8 bit にしてください")
        for ch, bits in (("M", self.bits_m), ("S", self.bits_s)):
            for k, b in enumerate(bits):
                group = self.attenuator_group(ch, k)
                if group < 0 or (group and (b == 0 or self.ncoef(k) % group)):
                    raise ValueError("アッテネータの区間長は送信帯域の係数数を割り切る正数にしてください")

    def exponent_bits(self, ch: str, k: int) -> int:
        values = self.exp_bits_m if ch == "M" else self.exp_bits_s
        return self.exp_bits if values is None else values[k]

    def exponent_offset(self, ch: str, k: int) -> Optional[int]:
        values = self.exp_offset_m if ch == "M" else self.exp_offset_s
        return None if values is None else values[k]

    def attenuator_group(self, ch: str, k: int) -> int:
        values = self.attn_group_m if ch == "M" else self.attn_group_s
        return 0 if values is None else values[k]

    def attenuator_bits(self, ch: str, k: int) -> int:
        group = self.attenuator_group(ch, k)
        return self.ncoef(k) // group if group else 0

    @property
    def layered(self) -> bool:
        return self.base_m is not None

    def base_bits(self, ch: str, k: int) -> int:
        """帯域 k の基本層のビット数 (階層化なしなら全ビット)"""
        if not self.layered:
            return (self.bits_m if ch == "M" else self.bits_s)[k]
        return (self.base_m if ch == "M" else self.base_s)[k]

    @property
    def nbands(self) -> int:
        """独立に符号化する係数群の数（低域近似1群＋詳細帯域 levels 群）。"""
        return self.levels + 1

    @property
    def frame_ms(self) -> float:
        """ブロック長 (= 1フレームが運ぶ音声の長さ、エンコーダの蓄積時間) [ms]。伝送込みの遅延ではない
        (伝送込みは gracefm.timing.min_latency。処理時間 0 で、この値の 2倍)"""
        return self.block / self.fs * 1000.0

    @property
    def frames_per_sec(self) -> float:
        return self.fs / self.block

    def ncoef(self, k: int) -> int:
        """帯域 k の 1ブロックあたりの係数の数"""
        return self.block >> band_level(k, self.levels)

    def payload_bits(self) -> int:
        """音声データ (指数 + 仮数) の 1ブロックあたりのビット数"""
        tot = 0
        for ch, bits in (("M", self.bits_m), ("S", self.bits_s)):
            for k, b in enumerate(bits):
                if b > 0:
                    tot += self.exponent_bits(ch, k) + self.attenuator_bits(ch, k) + self.ncoef(k) * b
        return tot

    def audio_kbps(self) -> float:
        return self.payload_bits() * self.frames_per_sec / 1000.0


def band_level(k: int, levels: int) -> int:
    """係数群 k の分解段数（k=0 は低域近似、k=1..levels は詳細帯域）。"""
    return levels if k == 0 else levels + 1 - k


def band_edges(fs: int, levels: int):
    edges = [(0.0, fs / 2 ** (levels + 1))]
    for k in range(1, levels + 1):
        edges.append((fs / 2 ** (levels + 2 - k), fs / 2 ** (levels + 1 - k)))
    return edges


PROFILES = {
    # 放送 (FM 放送の代替)。32kHz, 帯域 〜16kHz, ブロック長 2.0ms (伝送込みの遅延は処理時間 0 で 4.0ms)。
    # ステレオの割り当ては全帯域・ステレオの試験信号で探索した暫定値。
    "B200": Profile(pid=1, name="B200", fs=32000, block=64, levels=6,
                    bits_m=(12, 11, 9, 7, 4, 2, 2), bits_s=(7, 6, 5, 3, 2, 2, 2),
                    protect_k=1),
    # 放送のモノラル版。
    "B200M": Profile(pid=2, name="B200M", fs=32000, block=64, levels=6,
                     bits_m=(9, 9, 9, 9, 8, 6, 4), bits_s=(0, 0, 0, 0, 0, 0, 0),
                     protect_k=1),
    # 放送の低ビットレート版 (約150kbps)。ステレオは 4kHz 以下だけ S を送る。
    "B150": Profile(pid=4, name="B150", fs=32000, block=64, levels=6,
                    bits_m=(12, 10, 8, 6, 4, 2, 2), bits_s=(7, 5, 4, 3, 2, 0, 0),
                    protect_k=1),
    "B150M": Profile(pid=5, name="B150M", fs=32000, block=64, levels=6,
                     bits_m=(9, 9, 8, 7, 6, 4, 3), bits_s=(0, 0, 0, 0, 0, 0, 0),
                     protect_k=1),
    # 副系 (主系より低いビットレートで、主系と半ブロックずらして別の周波数で送る。主系が壊れたときの受け皿)。
    # 試行中の暫定値。
    "S85M": Profile(pid=6, name="S85M", fs=32000, block=64, levels=6,
                    bits_m=(8, 8, 7, 6, 5, 3, 0), bits_s=(0, 0, 0, 0, 0, 0, 0),
                    protect_k=1),
    "S50M": Profile(pid=7, name="S50M", fs=32000, block=64, levels=6,
                    bits_m=(8, 7, 6, 5, 3, 0, 0), bits_s=(0, 0, 0, 0, 0, 0, 0),
                    protect_k=1),
    "S100": Profile(pid=8, name="S100", fs=32000, block=64, levels=6,
                    bits_m=(10, 9, 8, 6, 4, 2, 0), bits_s=(6, 5, 4, 2, 0, 0, 0),
                    protect_k=1),
    # 据え置き機のモニター用。48kHz, ブロック長 1.33ms (伝送込みの遅延は処理時間 0 で 2.67ms)。
    "M700": Profile(pid=3, name="M700", fs=48000, block=64, levels=6,
                    bits_m=(16, 14, 13, 12, 11, 9, 7), bits_s=(12, 9, 8, 9, 7, 5, 3),
                    protect_k=2),
}



def make_layered(base: Profile, name: str, pid: int, modulation: str = "qam16h", alpha: float = 5.0,
                 max_bits: int = 16, protect_k: int = 1) -> Profile:
    """
    階層変調のプロファイルを作る。基本層は base と同じビット数の仮数で (FEC で守る上位ビットは protect_k)、
    変調の強い位置 (象限ビット) に入る。シンボル数は基本層が強い位置に収まる数にし、
    弱い位置 (位置ビット) を、各帯域の仮数を 1bit ずつ下に延ばす拡張層で埋める
    (低域→高域、M→S の順に 1bit ずつ、上限 max_bits、入りきらなくなるまで)。
    拡張層は基本層の下位ビットなので、受信が弱くなると拡張層から崩れ、基本層 (base の音質) が残る。
    """
    from .framing import Layout          # 循環 import を避ける
    base = replace(base, protect_k=protect_k)
    from .modem import bits_per_symbol
    lay = Layout(base)
    nsym = -(-lay.n_tx // 2)
    cap = nsym * (bits_per_symbol(modulation) - 2)        # 弱い位置の数
    bm, bs = list(base.bits_m), list(base.bits_s)
    used = 0
    changed = True
    while changed:
        changed = False
        for bits in (bm, bs):
            for k in range(len(bits)):
                if bits[k] == 0 or bits[k] >= max_bits:
                    continue
                n = base.ncoef(k)
                if used + n <= cap:
                    bits[k] += 1
                    used += n
                    changed = True
    return replace(base, pid=pid, name=name, bits_m=tuple(bm), bits_s=tuple(bs), modulation=modulation,
                   alpha=alpha, base_m=base.bits_m, base_s=base.bits_s)


# 階層 16QAM の層付きプロファイル: B200M / B200 と同じ帯域幅・同じ基本層に、電波が強いときだけ効く拡張層を足す
PROFILES["B200MH"] = make_layered(PROFILES["B200M"], "B200MH", 9)
PROFILES["B200H"] = make_layered(PROFILES["B200"], "B200H", 10)

# モノラル主系: B200MH の6詳細帯域＋低域近似を維持し、最高域32係数を4係数ずつ8区間に分ける。
# 受信側がフレームごとにオフセットを受け取らずに復元できるよう、指数オフセットは固定値。
# 元の指数4bitを維持するので保護部は8bit増える。
PROFILES["B200MH-A4"] = replace(PROFILES["B200MH"], pid=14, name="B200MH-A4",
                                  exp_offset_m=(-26, -26, -27, -27, -28, -27, -26),
                                  attn_group_m=(0, 0, 0, 0, 0, 0, 4))

# モニター用 (48kHz) の 16QAM 主系 (SPEC 5.6節)。RF占有帯域は M700 (QPSK) の約半分。
# M700H: 階層16QAM。基本層 329.25kbps (48kHz、全帯域ステレオ) ＋ 拡張層。M700Q16: 通常の16QAM で M700 と同じビット
PROFILES["M700Q16"] = Profile(pid=11, name="M700Q16", fs=48000, block=64, levels=6,
                              bits_m=(16, 14, 13, 12, 11, 9, 7), bits_s=(12, 9, 8, 9, 7, 5, 3),
                              protect_k=2, modulation="qam16h", alpha=1.0)
PROFILES["M700H"] = make_layered(Profile(pid=0, name="M340", fs=48000, block=64, levels=6,
                                         bits_m=(11, 10, 9, 8, 6, 3, 2), bits_s=(7, 5, 4, 3, 3, 2, 2)),
                                 "M700H", 12, protect_k=1)
# モニター用の副系 (48kHz)
PROFILES["S100W"] = Profile(pid=13, name="S100W", fs=48000, block=64, levels=6,
                            bits_m=(9, 8, 7, 6, 4, 0, 0), bits_s=(5, 4, 3, 0, 0, 0, 0), protect_k=1)

BY_ID = {p.pid: p for p in PROFILES.values()}
