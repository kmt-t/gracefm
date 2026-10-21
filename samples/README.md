# サンプル音声（GraceFM）

- 16bit FLAC（TPDF ディザ）、各10秒。放送用は32kHz（このフォルダ）、モニター用は48kHz（`monitor/`）
- `tools/make_samples.py` で生成（このファイルも同じスクリプトが書く）

## 聴き比べ

| ファイル | 内容 |
|---|---|
| `*_final_*` | この方式の放送の最終構成（主系 B200MH / B200H ＋ 副系 S50M / S100、送信電力 50:50） |
| `*_fm_*` | 同じ受信電力のアナログFM（モノラル、ゴーストなし） |
| `*_B200MH`・`*_B200H` | コーデックだけ、全ビット（拡張層まで届いたときの上限） |
| `*_B200M`・`*_B200` | コーデックだけ、基本層だけ（拡張層が全部崩れたときの音） |

- おすすめ：`fishin_final_cn0-57` と `fishin_fm_cn0-57`（FM がスレッショルドを割る強さ）、`*_rayleigh_cn0-60`（途切れ方）
- demo（ステレオ）は FM ステレオのモデルがないため FM なし

## 電波の強さ

| C/N0 | C/N（180kHz） | 目安 |
|---|---|---|
| 80dB-Hz | 27.4dB | 良好 |
| 66dB-Hz | 13.4dB | 5m・室内の保守的な見積もり。FM はスレッショルドの少し上 |
| 60dB-Hz | 7.4dB | FM はスレッショルド割れ（クリック） |
| 57dB-Hz | 4.4dB | FM はかなり荒れる |
| 54dB-Hz | 1.4dB | FM はほぼ雑音 |

- 通信路：白色雑音のみ／系統ごとに独立なレイリーフェージング（時定数100ms、FM も同じ変動）／主系の周波数だけ10dB 低下（FM はその周波数で受信）
- 同期・等化は理想。FM のゴーストは含まない

## ファイル一覧

波形SNR：原音との差から求めた値（大きいほど良い。聴感の評価点ではない）。

| ファイル | 内容 | 波形SNR |
|---|---|---|
| `demo_orig.flac` | 原音（32kHzに変換したもの） | — |
| `demo_B200H.flac` | コーデックだけ（通信路なし）。B200H の全ビット（基本層＋拡張層、約530kbps） | 56.5dB |
| `demo_B200.flac` | コーデックだけ。基本層だけ（B200、約200kbps）＝拡張層が全部崩れたときの音 | 29.4dB |
| `demo_B200_nopf.flac` | 同上、ポストフィルタなし | 31.9dB |
| `demo_final_cn0-80.flac` | 白色雑音のみ。C/N0 80dB-Hz（C/N 27.4dB）。主系 B200H Es/N0 24.6dB、副系 S100 Es/N0 27.2dB（電力 50:50） | 47.3dB |
| `demo_final_cn0-66.flac` | 白色雑音のみ。C/N0 66dB-Hz（C/N 13.4dB）。主系 B200H Es/N0 10.6dB、副系 S100 Es/N0 13.2dB（電力 50:50） | 29.9dB |
| `demo_final_cn0-60.flac` | 白色雑音のみ。C/N0 60dB-Hz（C/N 7.4dB）。主系 B200H Es/N0 4.6dB、副系 S100 Es/N0 7.2dB（電力 50:50） | 23.8dB |
| `demo_final_cn0-57.flac` | 白色雑音のみ。C/N0 57dB-Hz（C/N 4.4dB）。主系 B200H Es/N0 1.6dB、副系 S100 Es/N0 4.2dB（電力 50:50） | 16.3dB |
| `demo_final_cn0-54.flac` | 白色雑音のみ。C/N0 54dB-Hz（C/N 1.4dB）。主系 B200H Es/N0 -1.4dB、副系 S100 Es/N0 1.2dB（電力 50:50） | 9.3dB |
| `demo_final_rayleigh_cn0-60.flac` | 系統ごとに独立なフェージング（時定数約100ms）。C/N0 60dB-Hz（C/N 7.4dB）。平均の 主系 B200H Es/N0 4.6dB、副系 S100 Es/N0 7.2dB（電力 50:50）。欠けて予測で埋めた時間 8.0% | 10.7dB |
| `demo_final_fade10_cn0-66.flac` | 主系の周波数だけ10dB落ちている。C/N0 66dB-Hz（C/N 13.4dB）。主系 B200H Es/N0 0.6dB、副系 S100 Es/N0 13.2dB（電力 50:50）。欠けて予測で埋めた時間 0.0% | 26.4dB |
| `fishin_orig.flac` | 原音（32kHzに変換したもの） | — |
| `fishin_B200MH.flac` | コーデックだけ（通信路なし）。B200MH の全ビット（基本層＋拡張層、約470kbps） | 82.7dB |
| `fishin_B200M.flac` | コーデックだけ。基本層だけ（B200M、約194kbps）＝拡張層が全部崩れたときの音 | 32.7dB |
| `fishin_B200M_nopf.flac` | 同上、ポストフィルタなし | 36.2dB |
| `fishin_final_cn0-80.flac` | 白色雑音のみ。C/N0 80dB-Hz（C/N 27.4dB）。主系 B200MH Es/N0 25.3dB、副系 S50M Es/N0 29.3dB（電力 50:50） | 55.1dB |
| `fishin_fm_cn0-80.flac` | アナログFMモノラル。白色雑音のみ。C/N0 80dB-Hz（C/N 27.4dB）。ゴーストなし | 51.2dB |
| `fishin_final_cn0-66.flac` | 白色雑音のみ。C/N0 66dB-Hz（C/N 13.4dB）。主系 B200MH Es/N0 11.3dB、副系 S50M Es/N0 15.3dB（電力 50:50） | 32.1dB |
| `fishin_fm_cn0-66.flac` | アナログFMモノラル。白色雑音のみ。C/N0 66dB-Hz（C/N 13.4dB）。ゴーストなし | 38.2dB |
| `fishin_final_cn0-60.flac` | 白色雑音のみ。C/N0 60dB-Hz（C/N 7.4dB）。主系 B200MH Es/N0 5.3dB、副系 S50M Es/N0 9.3dB（電力 50:50） | 22.6dB |
| `fishin_fm_cn0-60.flac` | アナログFMモノラル。白色雑音のみ。C/N0 60dB-Hz（C/N 7.4dB）。ゴーストなし | 24.1dB |
| `fishin_final_cn0-57.flac` | 白色雑音のみ。C/N0 57dB-Hz（C/N 4.4dB）。主系 B200MH Es/N0 2.3dB、副系 S50M Es/N0 6.3dB（電力 50:50） | 17.0dB |
| `fishin_fm_cn0-57.flac` | アナログFMモノラル。白色雑音のみ。C/N0 57dB-Hz（C/N 4.4dB）。ゴーストなし | 11.4dB |
| `fishin_final_cn0-54.flac` | 白色雑音のみ。C/N0 54dB-Hz（C/N 1.4dB）。主系 B200MH Es/N0 -0.7dB、副系 S50M Es/N0 3.3dB（電力 50:50） | 11.0dB |
| `fishin_fm_cn0-54.flac` | アナログFMモノラル。白色雑音のみ。C/N0 54dB-Hz（C/N 1.4dB）。ゴーストなし | 4.0dB |
| `fishin_final_rayleigh_cn0-60.flac` | 系統ごとに独立なフェージング（時定数約100ms）。C/N0 60dB-Hz（C/N 7.4dB）。平均の 主系 B200MH Es/N0 5.3dB、副系 S50M Es/N0 9.3dB（電力 50:50）。欠けて予測で埋めた時間 3.8% | 12.8dB |
| `fishin_fm_rayleigh_cn0-60.flac` | アナログFMモノラル。フェージング（同じモデル）。C/N0 60dB-Hz（C/N 7.4dB） | 4.7dB |
| `fishin_final_fade10_cn0-66.flac` | 主系の周波数だけ10dB落ちている。C/N0 66dB-Hz（C/N 13.4dB）。主系 B200MH Es/N0 1.3dB、副系 S50M Es/N0 15.3dB（電力 50:50）。欠けて予測で埋めた時間 0.0% | 17.3dB |
| `fishin_fm_fade10_cn0-66.flac` | アナログFMモノラル。その周波数が10dB落ちている。C/N0 66dB-Hz（C/N 13.4dB） | 8.4dB |
| `vibeace_orig.flac` | 原音（32kHzに変換したもの） | — |
| `vibeace_B200MH.flac` | コーデックだけ（通信路なし）。B200MH の全ビット（基本層＋拡張層、約470kbps） | 91.7dB |
| `vibeace_B200M.flac` | コーデックだけ。基本層だけ（B200M、約194kbps）＝拡張層が全部崩れたときの音 | 46.5dB |
| `vibeace_B200M_nopf.flac` | 同上、ポストフィルタなし | 48.5dB |
| `vibeace_final_cn0-80.flac` | 白色雑音のみ。C/N0 80dB-Hz（C/N 27.4dB）。主系 B200MH Es/N0 25.3dB、副系 S50M Es/N0 29.3dB（電力 50:50） | 68.2dB |
| `vibeace_fm_cn0-80.flac` | アナログFMモノラル。白色雑音のみ。C/N0 80dB-Hz（C/N 27.4dB）。ゴーストなし | 50.7dB |
| `vibeace_final_cn0-66.flac` | 白色雑音のみ。C/N0 66dB-Hz（C/N 13.4dB）。主系 B200MH Es/N0 11.3dB、副系 S50M Es/N0 15.3dB（電力 50:50） | 45.3dB |
| `vibeace_fm_cn0-66.flac` | アナログFMモノラル。白色雑音のみ。C/N0 66dB-Hz（C/N 13.4dB）。ゴーストなし | 36.6dB |
| `vibeace_final_cn0-60.flac` | 白色雑音のみ。C/N0 60dB-Hz（C/N 7.4dB）。主系 B200MH Es/N0 5.3dB、副系 S50M Es/N0 9.3dB（電力 50:50） | 30.9dB |
| `vibeace_fm_cn0-60.flac` | アナログFMモノラル。白色雑音のみ。C/N0 60dB-Hz（C/N 7.4dB）。ゴーストなし | 22.8dB |
| `vibeace_final_cn0-57.flac` | 白色雑音のみ。C/N0 57dB-Hz（C/N 4.4dB）。主系 B200MH Es/N0 2.3dB、副系 S50M Es/N0 6.3dB（電力 50:50） | 21.4dB |
| `vibeace_fm_cn0-57.flac` | アナログFMモノラル。白色雑音のみ。C/N0 57dB-Hz（C/N 4.4dB）。ゴーストなし | 10.2dB |
| `vibeace_final_cn0-54.flac` | 白色雑音のみ。C/N0 54dB-Hz（C/N 1.4dB）。主系 B200MH Es/N0 -0.7dB、副系 S50M Es/N0 3.3dB（電力 50:50） | 13.9dB |
| `vibeace_fm_cn0-54.flac` | アナログFMモノラル。白色雑音のみ。C/N0 54dB-Hz（C/N 1.4dB）。ゴーストなし | 2.8dB |
| `vibeace_final_rayleigh_cn0-60.flac` | 系統ごとに独立なフェージング（時定数約100ms）。C/N0 60dB-Hz（C/N 7.4dB）。平均の 主系 B200MH Es/N0 5.3dB、副系 S50M Es/N0 9.3dB（電力 50:50）。欠けて予測で埋めた時間 3.6% | 15.6dB |
| `vibeace_fm_rayleigh_cn0-60.flac` | アナログFMモノラル。フェージング（同じモデル）。C/N0 60dB-Hz（C/N 7.4dB） | 3.5dB |
| `vibeace_final_fade10_cn0-66.flac` | 主系の周波数だけ10dB落ちている。C/N0 66dB-Hz（C/N 13.4dB）。主系 B200MH Es/N0 1.3dB、副系 S50M Es/N0 15.3dB（電力 50:50）。欠けて予測で埋めた時間 0.0% | 29.3dB |
| `vibeace_fm_fade10_cn0-66.flac` | アナログFMモノラル。その周波数が10dB落ちている。C/N0 66dB-Hz（C/N 13.4dB） | 7.3dB |

## モニター用（48kHz、`monitor/`）

| ファイル | 内容 |
|---|---|
| `*_M700H*` | 階層16QAM、占有帯域 約356kHz（推奨） |
| `*_M700*` | QPSK、占有帯域 約642kHz（比較用） |
| `*_M700H-base` | M700H の基本層だけ（約329kbps） |

- 1系統・全電力、白色雑音のみ。近距離（1m 程度）は C/N0 約80dB-Hz の見込み
- fishin・vibeace は32kHz の原音を48kHz に変換したもの（元の帯域は約11kHz）

| ファイル | 内容 | 波形SNR |
|---|---|---|
| `monitor/demo_orig48.flac` | 原音（合成試験信号を48kHzで作ったもの、全帯域） | — |
| `monitor/demo_M700.flac` | コーデックだけ。M700（701kbps） | 33.9dB |
| `monitor/demo_M700H.flac` | コーデックだけ。M700H の全ビット（約854kbps） | 52.3dB |
| `monitor/demo_M700H-base.flac` | コーデックだけ。M700H の基本層だけ（約329kbps）＝拡張層が全部崩れたときの音 | 25.3dB |
| `monitor/demo_M700H_cn0-80.flac` | M700H（階層16QAM、占有帯域 約343kHz）1系統。白色雑音のみ。C/N0 80dB-Hz（C/N 27.4dB）、Es/N0 25.6dB | 46.7dB |
| `monitor/demo_M700H_cn0-75.flac` | M700H（階層16QAM、占有帯域 約343kHz）1系統。白色雑音のみ。C/N0 75dB-Hz（C/N 22.4dB）、Es/N0 20.6dB | 32.7dB |
| `monitor/demo_M700H_cn0-70.flac` | M700H（階層16QAM、占有帯域 約343kHz）1系統。白色雑音のみ。C/N0 70dB-Hz（C/N 17.4dB）、Es/N0 15.6dB | 27.6dB |
| `monitor/demo_M700H_cn0-65.flac` | M700H（階層16QAM、占有帯域 約343kHz）1系統。白色雑音のみ。C/N0 65dB-Hz（C/N 12.4dB）、Es/N0 10.6dB | 24.8dB |
| `monitor/demo_M700_cn0-70.flac` | M700（QPSK、占有帯域 約629kHz）1系統。白色雑音のみ。C/N0 70dB-Hz（C/N 17.4dB）、Es/N0 13.0dB | 33.9dB |
| `monitor/demo_M700_cn0-65.flac` | M700（QPSK、占有帯域 約629kHz）1系統。白色雑音のみ。C/N0 65dB-Hz（C/N 12.4dB）、Es/N0 8.0dB | 29.1dB |
| `monitor/fishin_orig48.flac` | 原音（32kHz の原音を48kHzに変換したもの。元の音源の帯域は約11kHz） | — |
| `monitor/fishin_M700.flac` | コーデックだけ。M700（701kbps） | 52.0dB |
| `monitor/fishin_M700H.flac` | コーデックだけ。M700H の全ビット（約854kbps） | 52.1dB |
| `monitor/fishin_M700H-base.flac` | コーデックだけ。M700H の基本層だけ（約329kbps）＝拡張層が全部崩れたときの音 | 28.6dB |
| `monitor/fishin_M700H_cn0-80.flac` | M700H（階層16QAM、占有帯域 約343kHz）1系統。白色雑音のみ。C/N0 80dB-Hz（C/N 27.4dB）、Es/N0 25.6dB | 49.3dB |
| `monitor/fishin_M700H_cn0-75.flac` | M700H（階層16QAM、占有帯域 約343kHz）1系統。白色雑音のみ。C/N0 75dB-Hz（C/N 22.4dB）、Es/N0 20.6dB | 37.0dB |
| `monitor/fishin_M700H_cn0-70.flac` | M700H（階層16QAM、占有帯域 約343kHz）1系統。白色雑音のみ。C/N0 70dB-Hz（C/N 17.4dB）、Es/N0 15.6dB | 31.8dB |
| `monitor/fishin_M700H_cn0-65.flac` | M700H（階層16QAM、占有帯域 約343kHz）1系統。白色雑音のみ。C/N0 65dB-Hz（C/N 12.4dB）、Es/N0 10.6dB | 27.2dB |
| `monitor/fishin_M700_cn0-70.flac` | M700（QPSK、占有帯域 約629kHz）1系統。白色雑音のみ。C/N0 70dB-Hz（C/N 17.4dB）、Es/N0 13.0dB | 51.9dB |
| `monitor/fishin_M700_cn0-65.flac` | M700（QPSK、占有帯域 約629kHz）1系統。白色雑音のみ。C/N0 65dB-Hz（C/N 12.4dB）、Es/N0 8.0dB | 29.8dB |
| `monitor/vibeace_orig48.flac` | 原音（32kHz の原音を48kHzに変換したもの。元の音源の帯域は約11kHz） | — |
| `monitor/vibeace_M700.flac` | コーデックだけ。M700（701kbps） | 65.9dB |
| `monitor/vibeace_M700H.flac` | コーデックだけ。M700H の全ビット（約854kbps） | 66.1dB |
| `monitor/vibeace_M700H-base.flac` | コーデックだけ。M700H の基本層だけ（約329kbps）＝拡張層が全部崩れたときの音 | 42.3dB |
| `monitor/vibeace_M700H_cn0-80.flac` | M700H（階層16QAM、占有帯域 約343kHz）1系統。白色雑音のみ。C/N0 80dB-Hz（C/N 27.4dB）、Es/N0 25.6dB | 63.3dB |
| `monitor/vibeace_M700H_cn0-75.flac` | M700H（階層16QAM、占有帯域 約343kHz）1系統。白色雑音のみ。C/N0 75dB-Hz（C/N 22.4dB）、Es/N0 20.6dB | 50.7dB |
| `monitor/vibeace_M700H_cn0-70.flac` | M700H（階層16QAM、占有帯域 約343kHz）1系統。白色雑音のみ。C/N0 70dB-Hz（C/N 17.4dB）、Es/N0 15.6dB | 45.4dB |
| `monitor/vibeace_M700H_cn0-65.flac` | M700H（階層16QAM、占有帯域 約343kHz）1系統。白色雑音のみ。C/N0 65dB-Hz（C/N 12.4dB）、Es/N0 10.6dB | 31.6dB |
| `monitor/vibeace_M700_cn0-70.flac` | M700（QPSK、占有帯域 約629kHz）1系統。白色雑音のみ。C/N0 70dB-Hz（C/N 17.4dB）、Es/N0 13.0dB | 64.9dB |
| `monitor/vibeace_M700_cn0-65.flac` | M700（QPSK、占有帯域 約629kHz）1系統。白色雑音のみ。C/N0 65dB-Hz（C/N 12.4dB）、Es/N0 8.0dB | 30.3dB |

## 楽曲の出典とライセンス

[librosa/data](https://github.com/librosa/data) 収録の音源を、抜粋・サンプリング周波数の変換・音量の正規化・本方式による符号化と復号で加工。元の楽曲は CC BY 3.0、加工したサンプルは [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)（元の楽曲の出典表示を含む）。

- **"Let's Go Fishin'" by Karissa Hobbs** — [Free Music Archive](https://freemusicarchive.org/music/Karissa_Hobbs/Age_of_Flowers/09_Lets_Go_Fishin)、[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)
- **"Vibe Ace" by Kevin MacLeod** — [Free Music Archive](https://freemusicarchive.org/music/Kevin_MacLeod/Jazz_Sampler/Vibe_Ace)、[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)
- `demo_*`：合成した試験信号（全帯域・ステレオ）
