#!/usr/bin/env python3
"""指数配置の評価音源を取得し、公開 SHA-256 とライセンス情報を検証する。

  python tools/fetch_exp_audio.py

音声と取得したメタデータは Git 管理外の eval_audio/ に保存する。
出典: https://librosa.org/data/audio/ の公開サンプルと
https://github.com/librosa/librosa/blob/main/librosa/util/example_data/registry.txt
"""
import argparse
import hashlib
import json
from pathlib import Path
import tomllib
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://librosa.org/data/audio/"

# 音声 SHA-256 は librosa の公開 registry.txt (2026-10-22 確認)。
# train と holdout は評価ソフトが別々に集計し、探索音源への過適合を確認する。
SOURCES = {
    "choice": ("admiralbob77_-_Choice_-_Drum-bass", "57b4d95473b92a8441c1d3ab20f836a3e0cbf501bf3afe1ce7a5d0d98d7d4576", "CC-BY-NC-4.0", "train"),
    "brahms": ("Hungarian_Dance_number_5_-_Allegro_in_F_sharp_minor_(string_orchestra)", "8e93ff0182a93168b15346c497b164cb49d2a97bf1e987a1149ea579e914532e", "CC-PDM-1.0", "train"),
    "libri1": ("5703-47212-0000", "f09254a0daf4b14b292868d46dc2e3c8e158d19fafff739ad4c3931e2ce7b1b0", "CC-BY-4.0", "train"),
    "trumpet": ("sorohanro_-_solo-trumpet-06", "beb954ae2c9c16919b5ca6973d6d5196cdcb196b46a3c2a201dd8861e7e324de", "CC-BY-4.0", "holdout"),
    "libri3": ("198-209-0000", "6a8d2c16e56dcb27b7f5fe5aa99bfd26b4722a6dabca1968eff951b456936514", "CC-BY-4.0", "holdout"),
}


def fetch(url):
    with urlopen(url, timeout=60) as response:
        return response.read()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "eval_audio")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for key, (stem, digest, license_id, split) in SOURCES.items():
        metadata_url = BASE + quote(stem + ".toml")
        media_url = BASE + quote(stem + ".hq.ogg")
        metadata = tomllib.loads(fetch(metadata_url).decode("utf-8"))
        if metadata.get("license") != license_id:
            raise ValueError(f"{key}: ライセンス表示が変わりました: {metadata.get('license')}")
        path = args.out / f"{key}.ogg"
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            data = None
        else:
            data = fetch(media_url)
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"{key}: 音声の SHA-256 が公開値と異なります")
            path.write_bytes(data)
        manifest[key] = dict(file=path.name, sha256=digest, split=split,
                             title=metadata["title"], attribution=metadata["attribution"],
                             license=license_id, source=metadata.get("url", ""),
                             media_url=media_url, metadata_url=metadata_url)
        print(f"{key}: {path} ({'既存ファイルを検証' if data is None else '取得'})")
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
