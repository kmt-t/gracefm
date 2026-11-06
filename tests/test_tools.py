"""道具のスクリプトが、引数を見ずに本体を実行しないことを確かめる (--help で結果やダウンロードが走らないように)"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def scripts():
    return [p for p in sorted((ROOT / "tools").rglob("*.py")) if "__main__" in p.read_text()]


def test_every_script_parses_arguments():
    missing = [str(p.relative_to(ROOT)) for p in scripts() if "argparse" not in p.read_text()]
    assert not missing


def test_help_has_no_side_effects():
    for name in ("tools/samples/sample_catalog.py", "tools/samples/regenerate_samples.py", "tools/report/rtp_budget.py"):
        out = subprocess.run([sys.executable, str(ROOT / name), "--help"], capture_output=True, text=True, cwd=ROOT, timeout=60)
        assert out.returncode == 0 and "usage" in out.stdout


def test_sample_names_use_the_documented_form():
    sys.path.insert(0, str(ROOT))
    from tools.samples.sample_names import reference_name, sample_name

    assert sample_name("demo-mono", 32000, "B200M-L", "awgn66", sub="SUB50M-L") == "demo-mono__32k__B200M-L+SUB50M-L__awgn-cn0-66dBHz.flac"
    assert sample_name("piano-stereo", 48000, "M700") == "piano-stereo__48k__M700__codec.flac"
    assert reference_name("piano-mono") == "piano-mono__32k__reference.flac"
