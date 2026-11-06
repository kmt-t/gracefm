# 固定小数点実装（DSP 依存）

`gracefm/` は整数だけで動く。ハードウェアに載せるための参照実装で、**この文書の幅と演算は、想定する DSP（Zynq-7010 の DSP48E1）に依存する**。ハードウェアが変わるときは、DSP に依存する演算を集めた [`gracefm/dsp.py`](../gracefm/dsp.py) の幅と関数を差し替える。

**float は使わない。** `gracefm/` のモジュールには、float のリテラル、float 型、真の除算、浮動小数点の関数を書かない。`tests/test_fixed.py` が検査する。例外は、アナログの通信路を模擬する [`gracefm/channel.py`](../gracefm/channel.py) と、評価の道具 `tools/` で、ハードウェアではない。定数表（フィルタ係数、確率のテーブルなど）は、設計時に [`tools/gen/gen_tables.py`](../tools/gen/gen_tables.py) が浮動小数点で計算して整数にし、[`gracefm/tables.py`](../gracefm/tables.py) に書き出す（ハードウェアでは ROM になる）。

## 1. 想定ハードウェアと制約

| 項目 | 値 | 出典 |
|---|---|---|
| DSP スライス | DSP48E1。Zynq-7010 に 80 スライス | [UG953](https://docs.amd.com/r/2021.1-English/ug953-vivado-7series-libraries/DSP48E1)、[UG479 の写し](https://gitea.federationhq.de/csander/Dissertation/raw/branch/main/bibliography/documents/ug479_7Series_DSP48E1.pdf) |
| 乗算器 | 25 bit × 18 bit の符号つき（A ポート下位 25 bit、B ポート 18 bit） | 同上 |
| プリアダー | 25 bit | 同上 |
| アキュムレータ | 48 bit | 同上 |
| ADC/DAC | I・Q とも 12 bit（AD9363） | [AD9363 データシート](https://www.analog.com:443/media/en/technical-documentation/data-sheets/AD9363.pdf) |

`gracefm/dsp.py` はこの値を `MULT_BITS = 25`、`CONST_BITS = 18`、`ACC_BITS = 48` として持ち、演算（`mac_sq2_inv`、`round_shift`、`shift_signed`、`saturate`、`sq_err_sum` など）はこの幅を前提にする。

## 2. 数値形式

**方針。** 値は 0〜1 の範囲で、固定小数点のフルレンジは 20 bit 強（[SPEC](SPEC.md) 6.1）なので、PCM は符号つき 24 bit（±1 = 2^23）、IQ と Haar の係数は **小数 22 bit**（±1 = 2^22）の固定小数点で扱う。Haar 4 段の利得で最低域は ±2^24 になるが、これは乗算器の入力（25 bit）に余裕を持たせて載せているだけで、精度が 25 bit あるわけではない。IQ は受け取った段階（12 bit の ADC 出力）で小数 22 bit に変換する。**DSP の都合で精度が下がることは容認する**。参照実装は numpy の int64 で計算する。ハードでは、乗算の入力と積和の幅（25×18 bit、48 bit）に収まる必要がある。収まることを確かめた箇所は、テストで検査する（`tests/test_fixed.py`）。確かめていない箇所は、下の表に残りとして示す。

| 量 | 形式 |
|---|---|
| PCM | 符号つき 24 bit 整数（±1 = 2^23） |
| Haar の係数 | 小数 22 bit の整数（±1 = 2^22）。M = (L+R)/2、S = (L−R)/2 を、PCM から最後の 2 bit を四捨五入して作る |
| 1/√2 | 46341 / 65536（17 bit の正の整数。18 bit 符号つきの乗数に収まる） |
| 共有指数 | s = e + 22（係数の整数単位での 2 のべき乗の刻み）。指数範囲は整数の式 `(lev >> 1) + 3 - b` |
| シンボル（IQ） | 小数 22 bit の整数（±1 = 2^22）、配列の形は (n, 2)。ADC の 12 bit は左へ 12 bit シフトして変換 |
| LLR | 符号つき 8 bit の整数（小数 2 bit、±31.75）。正 = 0 らしい |
| ビタビの経路メトリック | 符号つき 14 bit。毎ステップで最大値を引いて正規化し、範囲に飽和させる |
| 確率 | Q15 の整数。LLR から 255 エントリのテーブルで引く |
| 誤差分散 | 対数領域の整数（log2 × 2^8）。融合の重みは 2^(−d/16) の 16 エントリのテーブルで作る |
| フィルタ係数 | 符号つき 18 bit（Q14〜Q17） |

- **精度を落として幅に収める**: Haar 4 段の最低域は、満点の直流で ±2^24 に達し、乗算器の入力（符号つき 25 bit）の上限 2^24 − 1 を 1 だけ超える。この 1 LSB（2^-22）は `saturate` で切る。
- **Haar の演算**: (e ± o)/√2 を、e·C ± o·C をアキュムレータで足し合わせ、四捨五入して 16 bit 右シフトする形で書く。
- **LeGall 5/3 の演算**（`-L` プロファイル）: リフティングは加算とシフトだけで乗算器を使わず、各段の結果を 25 bit に飽和させる。スケーリングは Haar と同じ `mac_sq2_inv` で、√2 倍は s·C + s·C、1/√2 倍は s·C。最低域の分析の利得は最悪で 6.79 倍（Haar は 4 倍）で、その符号に合わせた満点の入力では飽和する（[SPEC](SPEC.md) 6.2）。
- **刻みの下限**: アッテネータの半刻みを整数にするため、共有指数の刻みは s ≥ 1 に制限する。デコーダは s ≤ 0 の値が来ても、右シフトで復号する。
- **誤差の二乗和**: エンコーダは、指数とアッテネータの選択で量子化誤差の二乗和を比べる。誤差は 25 bit あるので、量子化刻みに対する相対精度を 8 bit に切り詰めて（`ERR_FRAC_BITS`）18 bit に収めてから二乗する。
- **距離の二乗**: 復調の距離は右シフトして 17 bit にしてから二乗する。

## 3. モジュール

| モジュール | 内容 |
|---|---|
| [`dsp.py`](../gracefm/dsp.py) | DSP に依存する演算（乗算、累積、シフト、飽和、誤差の二乗和） |
| [`codec.py`](../gracefm/codec.py) | M/S、Haar、LeGall 5/3、ブロック浮動小数点の量子化・逆量子化 |
| [`fec.py`](../gracefm/fec.py) | 畳み込み符号、系統符号、CRC、整数ビタビ（乗算なし） |
| [`modem.py`](../gracefm/modem.py) | 変調、軸ごとの max-log LLR、Y 方式の変調・復調、PRBS |
| [`layout.py`](../gracefm/layout.py)、[`framing.py`](../gracefm/framing.py) | ビット配置、送信（pack）と受信（unpack） |
| [`encoder.py`](../gracefm/encoder.py) | 送信機（符号化、フレーム化、スクランブル、変調） |
| [`decoder.py`](../gracefm/decoder.py) | 1系統の受信機（確率による仮数の期待値、誤差分散、Chase 救済、硬判定の再構成） |
| [`receiver.py`](../gracefm/receiver.py) | 2 系統の合成と出力段（PLC、クロスフェード、IIR 切替） |
| [`fusion.py`](../gracefm/fusion.py) | 2 系統の帯域ごとの融合（逆分散重み、Q15）。`-L` は係数のまま融合する |
| [`plc.py`](../gracefm/plc.py) | LPC による補間（整数のレビンソン・ダービン）とクロスフェード |
| [`postfilter.py`](../gracefm/postfilter.py) | 出力段（Lanczos 補間、LPF、再標本化）。係数は整数の表 |
| [`iir.py`](../gracefm/iir.py) | 出力の切り替え先の IIR（因果、4 次 Butterworth、4 kHz）。係数は符号つき 18 bit の Q16（固定）。積は 25×18 bit、累積は 48 bit。係数は Q16 の固定（仕様どおり）。浮動小数点の設計との誤差は、振幅 3×10^5 のランダムウォーク入力で 32 kHz 約 70 LSB、48 kHz 約 440 LSB。1 kHz・振幅 2^22 の正弦波では 32 kHz 約 600 LSB、48 kHz 約 4200 LSB（約 −60 dB）。48 kHz の精度は不足（未解決、下の「未実装」を参照） |
| [`dsp.py`](../gracefm/dsp.py) の `wide_mul` / `wide_matmul` | 広い積（等化器の行列積、係数との積）を 11 bit ずつの片に分けて足す。値は正確な積と同じ。片どうしの積は 22 bit 以内で、乗算器に収まる |
| CPU 側（分割の方針） | 等化器の連立方程式（`linalg.py`）、PLC の Levinson 再帰と外挿（`plc.py`）、割り算（変数どうし）。逐次の処理で、幅は Python の整数 |
| [`equalizer.py`](../gracefm/equalizer.py)、[`modem.py`](../gracefm/modem.py) の Y 帯域 | 行列積、係数との積、二乗和、分散の積は `wide_mul` / `wide_matmul` で分割して掛ける。値は正確な積と同じ（テストで確認） |
| [`equalizer.py`](../gracefm/equalizer.py)、[`linalg.py`](../gracefm/linalg.py) | 訓練つき MMSE 等化器。通信路の推定と重みの設計を、整数のコレスキー分解で解く |
| [`tables.py`](../gracefm/tables.py) | 定数表（`tools/gen/gen_tables.py` が作る） |
| [`profiles.py`](../gracefm/profiles.py)、[`timing.py`](../gracefm/timing.py) | 設定値（整数と分数）、遅延モデル（分数） |

### 3.1 整数ビタビ

- 軟値は符号つき 8 bit の整数 LLR。枝メトリックは、期待される符号（±1）と 2 つの軟値の和・差だけで作る。**乗算を使わず**、加算・比較・選択だけなので、DSP48E1 の乗算器は要らない。

### 3.2 変調・復調

- 信号点は小数 22 bit の整数。平均エネルギーの正規化は整数の平方根（`isqrt`）で行い、定数は起動時に整数だけで作る。α は整数（5 または 1）。
- LLR は軸ごとに独立な max-log で作る: LLR = (D1 − D0) / (2σ²)。D は、そのビットが 1 / 0 の信号点のうち最も近いものとの距離の二乗。σ²（軸あたりの雑音分散）は、受信点と最寄りの信号点の差の二乗平均から、フレームごとに求める。I と Q の相関は見ない。
- Y 方式の半径は、象限の軸への射影から段を 1/2 刻み（段 6 bit + 小数 1 bit = 7 bit）で推定する。最上位 bit の位相 1 bit と合わせて、Y の仮数は 8 bit である。

### 3.3 等化器

- 通信路は、フレーム先頭の既知のシンボルを使った最小二乗法で推定する。正規方程式（15 タップ）を整数のコレスキー分解で解く。MMSE の重みは、通信路のタップから 11 タップの連立方程式を同じソルバで解いて作り、先読み量（0〜4）は予測誤差が最小のものを選ぶ。FIR は重みを Q14 に縮めて畳み込む。
- 通信路のモデル（RRC の応答、エコー）は評価の道具 [`tools/sim/multipath.py`](../tools/sim/multipath.py) にある。RRC の整合フィルタはまだ実装がなく、シンボル時刻の理想同期を前提にする。

### 3.4 CPUとDSPの役割分担

受信の処理を、DSPスライス（積和、25×18 bit の乗算器と 48 bit の累積器）で行うものと、制御用のCPU（ARM）で行うものに分ける。幅の定義は上の 2 節、DSP 側の演算は `gracefm/dsp.py` に集めてある。

**精度の方針。** 精度を厳密に保つのは、PCM（24 bit）と Haar 係数（小数 22 bit）の経路だけ。それ以外（等化器、PLC、融合、LLR）は、仕様の幅に収まる範囲でベストエフォートとする。

**DSP側（積和と幅の決まった演算）。**
- Haar 逆変換（`mac_sq2_inv`、係数 1/√2 は 17 bit）。
- 軟判定の復号（`decoder.soft_coeffs`）。確率と係数の積。
- 出力のポストフィルタ（`postfilter.py`）。信号は 25 bit（PCM 24 bit に 1 bit のガード）、係数は 18 bit 以内、各段の出力は 25 bit に飽和、累積は 48 bit。
- 出力切り替えの IIR（`iir.py`）。係数は符号つき 18 bit の Q16（固定）。低域通過の区間は b1 = 2·b0、b2 = b0 なので b0 だけ持つ。
- 等化器の行列積とタップとの積（`equalizer.py`）、Y 帯域の半径の積と分散（`modem.py`）。幅が 25×18 を超える積は、`dsp.wide_mul` / `dsp.wide_matmul` で 11 bit の片に分けて掛け、正確な積と同じ値にする。
- LLR の計算（8 bit の整数、`dsp.log2_q8` などは乗算と比較だけ）、ビタビ（加算・比較・選択）、CRC（ビット演算）。

**CPU側（逐次処理、割り算、制御）。**
- 連立方程式の解（`linalg.py`、コレスキー分解）。Python の整数で書いてあり、ハードの幅は未定。
- PLC の Levinson 再帰と外挿（`plc.py`）。フレームごとの逐次処理。
- 変数どうしの割り算（LLR の正規化、量子化の分散、等化器の重みの正規化）。DSP のモデルに割り算はない。
- 設計時の定数（Y 帯域の段の尺度、タップ表の生成）。
- 同期（シンボルタイミング、搬送波、AGC）、AD9363 の制御、フレーム管理、暗号（AES-CTR）、ヘッダの解析。

**精度の注意。**
- IIR の出力は、浮動小数点の設計との差が、ランダムウォーク入力で 32 kHz 約 70 LSB、48 kHz 約 440 LSB。1 kHz・振幅 2^22 の正弦波では 32 kHz 約 600 LSB、48 kHz 約 4200 LSB。係数の Q16 の丸めによる（48 kHz の 1 段目の b0 は 0.0026 で、Q16 では 169 しか表せない）。品質コードが 1 か 2 のブロックにだけ効く。
- CPU 側の幅は Python の任意精度の整数で、ハードで実装するときは幅を決め直す必要がある。
- 割り算を含む処理は、DSP の幅の検査（テスト）の対象外。

## 4. 検査

| ファイル | 内容 |
|---|---|
| [`tests/test_fixed.py`](../tests/test_fixed.py) | 乗数の幅、Haar が 25 bit に収まること、全プロファイルの SNR、**`gracefm/` に float が無いこと** |
| [`tests/test_fec.py`](../tests/test_fec.py) | 整数ビタビ |
| [`tests/test_legall.py`](../tests/test_legall.py) | LeGall 5/3 の再構成、影響範囲と先読みの実測、欠落、融合、遅延 |
| [`tests/test_gracefm.py`](../tests/test_gracefm.py)、`test_profiles.py`、`test_y.py`、`test_equalizer.py`、`test_baselayer.py` | フレーム、リンク、融合、補間、Y、等化器 |

## 5. 未実装

- `-L` プロファイルのストリーム処理（遅延線と係数のバッファ）。参照実装は配列全体で変換する。`tools/report/circuit_estimate.py` と [方式間比較](COMPARISON.md) の回路見積もりは Haar のプロファイルだけが対象で、`-L` の演算量・メモリは見積もっていない。
- 同期（シンボルタイミング、搬送波、AGC）、RRC 整合フィルタ、AD9363 とのインターフェース。
- 暗号化（AES-128-CTR）は、ライブラリの AES が作るキーストリームとの排他的論理和で、`gracefm/crypto.py` にある。AES 自体の回路は設計していない。
